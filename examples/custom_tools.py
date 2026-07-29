"""custom_tools.py — 扩展工具示例

用法: python examples/custom_tools.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mini_agent import Agent


def build_custom_agent() -> Agent:
    agent = Agent("你是一个系统管理助手。")

    @agent.tools.register
    def disk_usage(path: str = ".") -> str:
        """查看磁盘使用情况"""
        import shutil

        total, used, free = shutil.disk_usage(os.path.expanduser(path))
        return (
            f"总计: {total // (2**30)} GB\n"
            f"已用: {used // (2**30)} GB\n"
            f"剩余: {free // (2**30)} GB"
        )

    @agent.tools.register
    def count_lines(path: str, ext: str = ".py") -> str:
        """统计目录下指定扩展名的文件总行数"""
        total = 0
        files_found = 0
        for root, _, files in os.walk(os.path.expanduser(path)):
            for f in files:
                if f.endswith(ext):
                    files_found += 1
                    fp = os.path.join(root, f)
                    with open(fp, errors="ignore") as fh:
                        total += len(fh.readlines())
        return f"找到 {files_found} 个 {ext} 文件，共 {total} 行"

    @agent.tools.register
    def run_shell(command: str) -> str:
        """执行一段 shell 命令并返回输出"""
        import subprocess

        try:
            r = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            output = r.stdout or r.stderr or "(无输出)"
            return output[:1000]
        except Exception as e:
            return f"执行失败: {e}"

    return agent


if __name__ == "__main__":
    agent = build_custom_agent()
    print(f"🛠️  自定义 Agent (工具: {', '.join(agent.tools.list_tools())})")
    while True:
        try:
            user = input("\n❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in ("exit", "quit"):
            break
        print(f"🤖 {agent.run(user)}")
