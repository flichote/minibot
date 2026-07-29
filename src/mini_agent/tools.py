"""tools.py — 装饰器驱动的工具注册系统
用 @agent.tools.register 一行注册工具，自动生成 OpenAI function calling schema。
"""

import inspect
import json


class ToolRegistry:
    """工具注册中心 — 管理所有 Agent 可用的工具"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, func=None, *, name=None, description=None):
        """装饰器/直接调用两用注册

        用法:
            @agent.tools.register
            def my_tool(arg: str) -> str: ...

            @agent.tools.register(name="别名", description="描述")
            def another(): ...
        """
        if func is None:
            return lambda f: self.register(f, name=name, description=description)

        tool_name = name or func.__name__
        sig = inspect.signature(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object",
                }
                param_type = type_map.get(param.annotation, "string")
            properties[param_name] = {
                "type": param_type,
                "description": f"参数 {param_name}",
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        self._tools[tool_name] = {
            "fn": func,
            "schema": {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description
                    or (func.__doc__ or "").strip()
                    or f"执行 {tool_name}",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                    },
                },
            },
        }

        if required:
            self._tools[tool_name]["schema"]["function"]["parameters"]["required"] = (
                required
            )

        return func

    def schema(self) -> list[dict]:
        """返回 OpenAI tools 格式的 schema 列表"""
        return [t["schema"] for t in self._tools.values()]

    def execute(self, name: str, args_json: str) -> str:
        """执行工具并返回字符串化的结果"""
        tool = self._tools.get(name)
        if not tool:
            return f"错误：未知工具 '{name}'"

        try:
            args = json.loads(args_json) if args_json else {}
            result = tool["fn"](**args)
            return json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as e:
            return f"工具执行错误 [{name}]: {type(e).__name__}: {e}"

    def list_tools(self) -> list[str]:
        """列出所有已注册的工具名"""
        return list(self._tools.keys())
