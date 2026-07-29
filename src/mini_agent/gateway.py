"""gateway.py — 网关运行器
管理多个消息通道，将消息路由到 Agent 处理。
"""

import asyncio
import importlib
import os
import sys
from datetime import datetime

from .dotenv import load_dotenv
from .core import Agent


async def _route_message(
    agent: Agent,
    channel_name: str,
    user_id: str,
    text: str,
) -> str | None:
    """消息路由：通道消息 → Agent → 回复"""
    text = text.strip()
    if not text:
        return None

    context = f"[来自 {channel_name} 用户 {user_id}]\n{text}"
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, agent.run, context)
    return reply


async def run_gateway(channels: list[str] | None = None):
    """启动网关主循环

    Args:
        channels: 要启动的通道列表，默认从环境变量读取
    """
    load_dotenv()

    # 确定要启动的通道
    if channels is None:
        channels_raw = os.environ.get("GATEWAY_CHANNELS", "wechat")
        channels = [c.strip() for c in channels_raw.split(",") if c.strip()]

    if not channels:
        print("❌ 未配置任何通道。设置 GATEWAY_CHANNELS=wechat 或传入 channels 参数。")
        return

    # 创建 Agent
    agent = Agent(
        system_prompt=(
            "你是一个 AI 助手，正在通过即时通讯平台与用户对话。"
            "请简洁、友好地回复。可以使用提供的工具帮助用户。"
        )
    )

    print(f"\n{'='*50}")
    print(f"🐱 minibot 网关 v0.1")
    print(f"   启动时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"   通道: {', '.join(channels)}")
    print(f"{'='*50}\n")

    # 启动各通道
    tasks = []
    for name in channels:
        task = asyncio.create_task(
            _start_channel(name, agent), name=f"channel-{name}"
        )
        tasks.append(task)

    # 等待所有通道结束（正常情况下不会结束）
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("\n🛑 网关正在关闭...")
        for task in tasks:
            task.cancel()


async def _start_channel(name: str, agent: Agent):
    """启动单个通道"""
    try:
        # 动态导入通道模块
        module_path = f"mini_agent.channels.{name}"
        if name == "wechat":
            from .channels.wechat import WeChatChannel

            channel = WeChatChannel()
        else:
            print(f"❌ 未知通道: {name}")
            return

        print(f"🚀 启动 {channel.name} 通道...")

        # 消息回调
        async def on_msg(chn, uid, text):
            reply = await _route_message(agent, chn, uid, text)
            return reply

        await channel.start(on_msg)

    except ImportError as e:
        print(f"❌ 通道 {name} 依赖缺失: {e}")
        print(f"   安装: pip install minibot[{name}]")
    except Exception as e:
        print(f"❌ 通道 {name} 异常: {type(e).__name__}: {e}")
