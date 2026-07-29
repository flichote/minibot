# Mini Agent

🐱 极简 AI Agent 框架 — **零外部依赖**，核心约 **400 行** Python。

## 设计哲学

```
你 + Agent → LLM → 工具 → 你
                ↕
           记忆 / 上下文
```

极简 ≠ 简陋。这个框架砍掉了所有不必要的抽象层，只保留 Agent 最本质的循环：

> **系统提示 → 用户输入 → LLM 调用 → 工具执行 → 循环 → 输出 → 记忆**

## 为什么自己造轮子

| 对比 | nanobot (46k ⭐) | 这个 Mini Agent |
|------|-----------------|-----------------|
| 代码量 | 数万行 + WebUI | ~400 行纯 Python |
| 外部依赖 | httpx, fastapi 等 | **0**（只用标准库） |
| 数据库 | 有 | JSON 文件 |
| 学习成本 | 看半天源码 | 15 分钟读完 |
| 理解成本 | 需要理解框架抽象 | 每行代码都看得懂 |
| 定制自由 | 被框架结构约束 | 随意改，随便删 |

## 快速开始

```bash
# 1. 安装（pip 可安装模式）
cd ~/hermes-workspace/mini-agent
pip install -e .

# 2. 设置你的 API Key
export LLM_API_KEY="sk-..."
export LLM_MODEL="gpt-4o-mini"          # 或其他模型

# 3. 运行
mini-agent
```

### 支持的 Provider

换环境变量就行，无需改代码：

```bash
# DeepSeek
export LLM_BASE_URL="https://api.deepseek.com/v1" LLM_MODEL="deepseek-chat"

# Ollama 本地
export LLM_BASE_URL="http://localhost:11434/v1" LLM_MODEL="qwen2.5"

# Claude
export LLM_BASE_URL="https://api.anthropic.com/v1" LLM_MODEL="claude-sonnet-4-20250514"
```

## 项目结构

```
mini-agent/
├── pyproject.toml          # 项目元数据
├── README.md               # 本文件
├── .gitignore
├── src/
│   └── mini_agent/
│       ├── __init__.py     # 统一导出
│       ├── __main__.py     # python -m mini_agent 入口
│       ├── core.py         # 🔥 Agent 核心循环 (~90 行)
│       ├── llm.py          # LLM API 调用 (~60 行)
│       ├── tools.py        # 工具注册系统 (~80 行)
│       ├── memory.py       # 记忆存储 (~50 行)
│       └── cli.py          # 终端交互 (~80 行)
└── examples/
    └── custom_tools.py     # 扩展工具示例
```

## 核心架构

### 核心循环（`core.py`）

```
user_input
    │
    ▼
加载记忆 ── 从 JSON 文件读取最近 N 条
    │
    ▼
调用 LLM ──── 有 tool_calls? ──是──▶ 执行工具 ──▶ 结果入 messages ──▶ 回到 LLM
    │
    否
    ▼
返回文本 → 存记忆 → 输出
```

### 工具注册（`tools.py`）

```python
from mini_agent import Agent

agent = Agent()

@agent.tools.register
def read_file(path: str) -> str:
    """读取文件内容"""
    with open(path) as f:
        return f.read()
```

### 记忆系统（`memory.py`）

纯 JSON 文件，存在 `~/.mini_agent_memory.json`。每条记忆带时间戳，自动截断最新 50 条。

### LLM 调用（`llm.py`）

只用 Python 标准库 `urllib`。支持任意 OpenAI 兼容 API。

## Python API 使用

```python
from mini_agent import Agent

agent = Agent("你是一个写代码的助手。")

@agent.tools.register
def evaluate_code(code: str) -> str:
    """执行 Python 代码并返回结果"""
    ...

reply = agent.run("请帮我写一个斐波那契函数")
print(reply)
```

## 扩展指南

从 400 行到产品级，每步加什么：

| 步骤 | 加什么 | 约多少行 |
|------|--------|---------|
| 1 | WebSocket API（外部程序调用） | +80 |
| 2 | 流式输出（SSE / WebSocket） | +60 |
| 3 | MCP 协议支持 | +120 |
| 4 | 多渠道（Telegram、微信） | +100/渠道 |
| 5 | 定时任务（cron 调度） | +80 |
| 6 | 轻量 WebUI（纯 HTML + JS） | +200 |
| 7 | 多模型路由 + 自动 fallback | +100 |

每一步都是独立的，可以按需添加。

## License

MIT
