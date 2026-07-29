"""cli.py — 命令行入口 + 终端交互
提供 `mini-agent` 命令和 `python -m mini_agent` 两种启动方式。
"""

import asyncio
import os
import sys

from .dotenv import load_dotenv
from .core import Agent


def build_agent() -> Agent:
    """构建预置了常用工具的 Agent"""
    agent = Agent(
        system_prompt=(
            "你是一个轻量级 AI 助手。当你需要操作文件或查询网络时，"
            "请使用提供的工具。回答尽量简洁。"
        )
    )

    @agent.tools.register
    def read_file(path: str) -> str:
        """读取指定路径的文件内容"""
        try:
            with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"读取失败: {e}"

    @agent.tools.register
    def write_file(path: str, content: str) -> str:
        """写入内容到指定文件"""
        try:
            path = os.path.expanduser(path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"已写入 {len(content)} 字符到 {path}"
        except Exception as e:
            return f"写入失败: {e}"

    @agent.tools.register
    def list_files(dir_path: str = ".") -> str:
        """列出目录下的文件"""
        try:
            files = os.listdir(os.path.expanduser(dir_path))
            return "\n".join(files[:50]) or "(空目录)"
        except Exception as e:
            return f"列出失败: {e}"

    @agent.tools.register
    def get_time() -> str:
        """获取当前日期和时间"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return agent


BANNER = r"""
╔═══════════════════════════════════════╗
║    🐱 Mini Agent v0.1                ║
║    极简 AI 助手 · Ctrl+C 退出        ║
╚═══════════════════════════════════════╝
"""


def main():
    """CLI 入口函数"""
    load_dotenv()

    # 网关模式
    if len(sys.argv) > 1 and sys.argv[1] in ("gateway", "gw"):
        _run_gateway()
        return

    agent = build_agent()

    print(BANNER)
    print(f"  模型: {agent.llm.model}")
    print(f"  工具: {', '.join(agent.tools.list_tools()) or '(无)'}")
    print()

    while True:
        try:
            user_input = input("  ❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！👋")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "退出"):
            print("  再见！👋")
            break

        response = agent.run(user_input)
        print(f"  🤖 {response}")
        print()


def _run_gateway():
    """启动网关模式"""
    try:
        from .gateway import run_gateway
        asyncio.run(run_gateway())
    except ImportError as e:
        print(f"❌ 网关依赖缺失: {e}")
        print("   安装: pip install aiohttp")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  网关已停止。")
    except Exception as e:
        print(f"❌ 网关异常: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
