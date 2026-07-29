"""core.py — Agent 核心循环
这是整个框架的灵魂：~90 行完成 LLM 调用 → 工具执行 → 循环 → 输出。
"""

import json

from .llm import LLM
from .tools import ToolRegistry
from .memory import Memory


class Agent:
    """极简 Agent — 可注册工具、自动循环、持久记忆"""

    def __init__(
        self,
        system_prompt: str = "",
        llm: LLM | None = None,
        tools: ToolRegistry | None = None,
        memory: Memory | None = None,
    ):
        self.llm = llm or LLM()
        self.tools = tools or ToolRegistry()
        self.memory = memory or Memory()
        self.system_prompt = system_prompt or (
            "你是一个有用的 AI 助手。你可以使用工具来帮助用户。"
            "如果需要使用工具，请准确提供参数。"
        )
        self.messages: list[dict] = []
        self.max_turns = 10

    def run(self, user_input: str) -> str:
        """处理一条用户输入，返回最终回复"""
        # 1. 初始化会话消息
        self.messages = [{"role": "system", "content": self.system_prompt}]

        # 2. 注入记忆上下文
        context = self.memory.load_recent(limit=5)
        if context:
            self.messages[0]["content"] += f"\n\n近期记忆：\n{context}"

        # 3. 用户输入入队
        self.messages.append({"role": "user", "content": user_input})

        # 4. 核心循环
        turn = 0
        while turn < self.max_turns:
            turn += 1

            reply = self.llm.chat(self.messages, tools=self.tools.schema())

            # 处理 LLM 调用失败
            if reply.text and reply.text.startswith("[LLM 调用失败]"):
                return reply.text

            # 情况 A：LLM 调用了工具
            if reply.tool_calls:
                for tc in reply.tool_calls:
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["function"]["name"],
                                        "arguments": tc["function"]["arguments"],
                                    },
                                }
                            ],
                        }
                    )

                    result = self.tools.execute(
                        tc["function"]["name"], tc["function"]["arguments"]
                    )

                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )
                continue

            # 情况 B：LLM 返回了文本回复
            else:
                self.messages.append(
                    {"role": "assistant", "content": reply.text}
                )
                self.memory.save(reply.text[:200])
                return reply.text

        return "[Agent] 已达到最大对话轮次限制"
