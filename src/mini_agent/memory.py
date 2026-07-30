"""memory.py — 增强型记忆系统
适用于 ESP32 等资源受限设备。特点：

- JSONL 格式（每行一条 JSON，追加写入，对 Flash 友好）
- 分类记忆：fact / preference / conversation / task
- 重要性评分：重要的记忆永不丢失，低分自动清理
- 存储预算控制：自动压缩，适配小容量设备
- 快速检索：按类型 / 标签 / 关键词搜索
- 内存事实缓存：高频调用时无需回读文件
- 零外部依赖
"""

import json
import os
import re
from datetime import datetime
from typing import Any

# 记忆类型
MEMORY_TYPES = {
    "fact": 3,        # 事实性知识（用户信息、配置等），高重要性
    "preference": 3,  # 用户偏好
    "task": 2,        # 任务相关
    "conversation": 1, # 对话历史，低重要性
}

# 默认配置（ESP32 友好）
DEFAULT_MAX_SIZE = 256 * 1024  # 最大 256KB
DEFAULT_MAX_ENTRIES = 200


class Memory:
    """增强型记忆存储 — JSONL 格式，支持分类 / 搜索 / 自动压缩"""

    def __init__(
        self,
        path: str | None = None,
        max_size: int = DEFAULT_MAX_SIZE,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self.path = path or self._default_path()
        self.max_size = max_size
        self.max_entries = max_entries
        self._fact_cache: dict[str, str] = {}  # 内存中的关键事实缓存
        self._ensure_file()

    @staticmethod
    def _default_path() -> str:
        """跨平台默认路径 — ESP32 上用 /flash/minibot_memory.jsonl"""
        # 检测是否在 MicroPython / ESP32 环境
        try:
            import sys
            if sys.platform == "esp32" or sys.implementation.name == "micropython":
                return "/flash/minibot_memory.jsonl"
        except Exception:
            pass
        # 桌面环境
        home = os.path.expanduser("~")
        return os.path.join(home, ".minibot_memory.jsonl")

    def _ensure_file(self):
        """确保文件存在"""
        try:
            if not os.path.exists(self.path):
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write("")
        except OSError:
            # ESP32 上可能路径不同
            pass

    # ── 读写接口 ───────────────────────────────────

    def save(
        self,
        content: str,
        mem_type: str = "conversation",
        tags: list[str] | None = None,
        importance: int | None = None,
    ):
        """存入一条分类记忆

        Args:
            content: 记忆内容
            mem_type: 类型 (fact/preference/conversation/task)
            tags: 标签列表，用于检索
            importance: 重要性 (1-5, 自动推断如果为 None)
        """
        if mem_type not in MEMORY_TYPES:
            mem_type = "conversation"
        if importance is None:
            importance = MEMORY_TYPES.get(mem_type, 1)

        entry = {
            "t": datetime.now().isoformat(),
            "c": content[:500],
            "type": mem_type,
            "imp": importance,
        }
        if tags:
            entry["tags"] = tags[:10]  # 最多 10 个标签

        # 重要事实同时缓存在内存中
        if mem_type in ("fact", "preference") and importance >= 3:
            key = content[:50]
            self._fact_cache[key] = content

        # 追加写入（JSONL 格式）
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

        # 触发压缩检查（仅在写入后采样一次）
        self._maybe_compact()

    def load_recent(
        self,
        limit: int = 5,
        mem_type: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """读取最近的记忆，支持按类型/标签筛选"""
        entries = self._load_all()
        if not entries:
            return ""

        # 筛选
        if mem_type:
            entries = [e for e in entries if e.get("type") == mem_type]
        if tags:
            entries = [
                e for e in entries
                if any(t in e.get("tags", []) for t in tags)
            ]

        recent = entries[-limit:]
        lines = []
        for e in recent:
            ts = e.get("t", "")[:16]
            content = e.get("c", "")[:200]
            etype = e.get("type", "?")
            lines.append(f"[{ts}][{etype}] {content}")
        return "\n".join(lines)

    def search(self, keyword: str, limit: int = 5) -> str:
        """搜索包含关键词的记忆"""
        entries = self._load_all()
        if not entries:
            return ""

        keyword_lower = keyword.lower()
        matched = []
        for e in entries:
            content = e.get("c", "")
            if keyword_lower in content.lower():
                matched.append(e)

        lines = []
        for e in matched[-limit:]:
            ts = e.get("t", "")[:16]
            content = e.get("c", "")[:200]
            etype = e.get("type", "?")
            lines.append(f"[{ts}][{etype}] {content}")
        return "\n".join(lines)

    def get_facts(self) -> str:
        """读取所有高重要性事实（来自内存缓存 + 文件）"""
        if self._fact_cache:
            return "\n".join(self._fact_cache.values())

        # 从文件恢复
        entries = self._load_all()
        facts = [
            e.get("c", "")
            for e in entries
            if e.get("type") in ("fact", "preference") and e.get("imp", 0) >= 3
        ]
        return "\n".join(facts[-20:])  # 最多 20 条

    def count(self, mem_type: str | None = None) -> int:
        """统计记忆条数"""
        entries = self._load_all()
        if mem_type:
            return sum(1 for e in entries if e.get("type") == mem_type)
        return len(entries)

    def clear(self):
        """清空所有记忆"""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("")
        except OSError:
            pass
        self._fact_cache.clear()

    # ── 内部：JSONL 解析与压缩 ─────────────────────

    def _load_all(self) -> list[dict]:
        """读取全部记忆条目（惰性解析）"""
        entries = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except (OSError, FileNotFoundError):
            pass
        return entries

    def _file_size(self) -> int:
        """获取文件大小"""
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def _maybe_compact(self):
        """检查是否需要压缩（文件太大或条目太多）"""
        size = self._file_size()
        entries = self._load_all()
        count = len(entries)

        if size < self.max_size and count < self.max_entries:
            return

        # 需要压缩：保留高重要性 + 最新的
        # 按重要性降序，再按时间降序
        entries.sort(key=lambda e: (e.get("imp", 1), e.get("t", "")), reverse=True)

        # 保留所有高重要性条目，再补最新的
        keep = [e for e in entries if e.get("imp", 0) >= 3]
        high_count = len(keep)

        remaining_budget = self.max_entries - high_count
        if remaining_budget > 0:
            # 补充中等重要性 + 最新的
            medium = [
                e for e in entries
                if e.get("imp", 0) < 3 and e not in keep
            ]
            keep.extend(medium[:remaining_budget])

        # 写回
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                for e in keep:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        except OSError:
            pass

        # 重建事实缓存
        self._fact_cache = {}
        for e in keep:
            if e.get("type") in ("fact", "preference") and e.get("imp", 0) >= 3:
                key = e.get("c", "")[:50]
                self._fact_cache[key] = e.get("c", "")

    # ── 工具方法 ───────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """返回记忆系统统计信息"""
        entries = self._load_all()
        type_counts: dict[str, int] = {}
        for e in entries:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total": len(entries),
            "by_type": type_counts,
            "file_size": self._file_size(),
            "max_size": self.max_size,
            "max_entries": self.max_entries,
            "facts_cached": len(self._fact_cache),
        }
