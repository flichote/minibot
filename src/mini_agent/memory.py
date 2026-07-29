"""memory.py — JSON 文件记忆系统
轻量、无数据库。自动保存关键信息，重启不丢失。
"""

import json
import os
from datetime import datetime


class Memory:
    """极简记忆存储 — 追加到 JSON 文件"""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.expanduser("~/.mini_agent_memory.json")
        self.max_entries = 50
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load(self) -> list:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, entries: list):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(entries[-self.max_entries :], f, ensure_ascii=False, indent=2)

    def save(self, content: str):
        """存入一条记忆"""
        entries = self._load()
        entries.append(
            {
                "timestamp": datetime.now().isoformat(),
                "content": content[:500],
            }
        )
        self._save(entries)

    def load_recent(self, limit: int = 5) -> str:
        """读取最近 N 条记忆，拼接成上下文文本"""
        entries = self._load()
        recent = entries[-limit:]
        if not recent:
            return ""
        lines = [f"[{e['timestamp'][:16]}] {e['content'][:200]}" for e in recent]
        return "\n".join(lines)

    def clear(self):
        """清空记忆"""
        self._save([])
