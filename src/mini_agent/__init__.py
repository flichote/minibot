"""mini-agent — 极简 AI Agent 框架"""

from .dotenv import load_dotenv

# 自动加载项目根目录的 .env 文件（如有）
load_dotenv()

from .core import Agent
from .llm import LLM, LLMReply
from .tools import ToolRegistry
from .memory import Memory

__all__ = ["Agent", "LLM", "LLMReply", "ToolRegistry", "Memory"]
__version__ = "0.1.0"
