"""llm.py — LLM API 调用封装
零外部依赖，仅用 Python 标准库 urllib。
支持任意 OpenAI 兼容 API（OpenAI / Claude / Ollama / DeepSeek / 本地模型）。
"""

import json
import os
from dataclasses import dataclass, field
from urllib.request import Request, urlopen
from urllib.error import URLError


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list | None = None


class LLM:
    """极简 LLM 客户端 — 仅用标准库"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or self._load_key()
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")

    def _load_key(self) -> str:
        """尝试从 ~/.llm_key 读取 API Key"""
        key_file = os.path.expanduser("~/.llm_key")
        if os.path.exists(key_file):
            with open(key_file) as f:
                return f.read().strip()
        raise ValueError(
            "请设置 LLM_API_KEY 环境变量，或在项目根目录创建 .env 文件"
        )

    def chat(self, messages: list, tools: list | None = None) -> LLMReply:
        """一次 LLM 对话调用"""
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        req = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            resp = json.loads(urlopen(req, timeout=60).read())
        except URLError as e:
            return LLMReply(text=f"[LLM 调用失败] {e.reason}")

        choice = resp["choices"][0]
        msg = choice["message"]

        return LLMReply(
            text=msg.get("content") or "",
            tool_calls=msg.get("tool_calls"),
        )
