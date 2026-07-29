# minibot

🐱 极简 AI Agent 框架 — **零外部依赖**，核心约 **500 行** Python。

## 设计哲学

```
你 + Agent → LLM → 工具 → 你
                ↕
           记忆 / 上下文
```

极简 ≠ 简陋。这个框架砍掉了所有不必要的抽象层，只保留 Agent 最本质的循环：

> **系统提示 → 用户输入 → LLM 调用 → 工具执行 → 循环 → 输出 → 记忆**

## 为什么自己造轮子

| 对比 | nanobot (46k ⭐) | **minibot** |
|------|-----------------|-------------|
| 代码量 | 数万行 + WebUI | ~500 行纯 Python |
| 外部依赖 | httpx, fastapi 等 | **0**（只用标准库） |
| 数据库 | 有 | JSON 文件 |
| 学习成本 | 看半天源码 | 15 分钟读完 |
| 理解成本 | 需要理解框架抽象 | 每行代码都看得懂 |
| 定制自由 | 被框架结构约束 | 随意改，随便删 |

## 快速开始

```bash
# 1. 克隆 & 安装
git clone https://github.com/flichote/minibot.git
cd minibot
pip install -e .

# 2. 配置 API Key（二选一）
#
# 方式 A：使用 .env 文件（推荐）
cp .env.example .env
# 然后编辑 .env 填入你的 API Key:
#   LLM_API_KEY="sk-..."
#   LLM_BASE_URL="https://api.deepseek.com/v1"
#   LLM_MODEL="deepseek-chat"
#
# 方式 B：使用环境变量
# export LLM_API_KEY="sk-..."
# export LLM_BASE_URL="https://api.deepseek.com/v1"
# export LLM_MODEL="deepseek-v4-flash"

# 3. 运行
mini-agent
```

### 支持的 Provider

换环境变量就行，无需改代码。编辑 `.env` 文件即可切换：

```bash
# DeepSeek（默认配置）
LLM_API_KEY="sk-..."
LLM_BASE_URL="https://api.deepseek.com/v1"
LLM_MODEL="deepseek-v4-flash"

# DeepSeek Pro（更强推理）
# LLM_MODEL="deepseek-v4-pro"

# Ollama 本地
LLM_API_KEY="ollama"
LLM_BASE_URL="http://localhost:11434/v1"
LLM_MODEL="qwen2.5"

# Claude
LLM_API_KEY="sk-ant-..."
LLM_BASE_URL="https://api.anthropic.com/v1"
LLM_MODEL="claude-sonnet-4-20250514"
```

## 🌐 网关模式（连接微信）

minibot 支持通过网关连接即时通讯平台，目前支持 **微信（iLink Bot API）**。

### 安装依赖

```bash
pip install minibot[wechat]
```

### 配置

在 `.env` 中添加微信配置（首次运行会自动扫码登录并保存凭证）：

```bash
# 微信通道配置
WECHAT_ACCOUNT_ID=       # 首次扫码后自动填入
WECHAT_TOKEN=            # 首次扫码后自动填入
WECHAT_BASE_URL=https://ilinkai.weixin.qq.com
WECHAT_DM_POLICY=open    # open=允许所有人, allowlist=白名单, disabled=关闭
WECHAT_ALLOWED_USERS=    # 白名单用户ID（逗号分隔，仅 allowlist 模式需要）

# 网关通道列表
GATEWAY_CHANNELS=wechat
```

### 启动网关

```bash
mini-agent gateway
# 或
python -m mini_agent gateway
```

首次启动会显示二维码，用微信扫码即可登录。后续启动会自动复用保存的凭证。

### 架构

```
微信 ──→ WeChatChannel ──→ Agent ──→ LLM
  ↑                          │
  └──── 回复 ←───────────────┘
```

消息流：微信消息 → 网关 → Agent 处理 → LLM 回复 → 发回微信

## 项目结构

```
minibot/
├── .env.example             # 配置模板（复制为 .env 使用）
├── .gitignore
├── pyproject.toml           # 项目元数据
├── README.md                # 本文件
├── src/
│   └── mini_agent/
│       ├── __init__.py     # 统一导出
│       ├── __main__.py     # python -m mini_agent 入口
│       ├── cli.py          # CLI 交互 + gateway 子命令
│       ├── core.py         # 🔥 Agent 核心循环 (~90 行)
│       ├── dotenv.py       # .env 文件加载器 (~50 行)
│       ├── gateway.py      # 🌐 网关运行器 (~100 行)
│       ├── llm.py          # LLM API 调用 (~60 行)
│       ├── tools.py        # 工具注册系统 (~80 行)
│       ├── memory.py       # 记忆存储 (~50 行)
│       └── channels/
│           ├── __init__.py  # 通道基类
│           └── wechat.py    # 📱 微信通道 (~250 行)
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

[MIT](LICENSE)
