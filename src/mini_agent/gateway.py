"""gateway.py — 网关运行器 + 诊断工具
管理多个消息通道，将消息路由到 Agent 处理。
"""

import asyncio
import json
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
    """启动网关主循环"""
    load_dotenv()

    if channels is None:
        channels_raw = os.environ.get("GATEWAY_CHANNELS", "wechat")
        channels = [c.strip() for c in channels_raw.split(",") if c.strip()]

    if not channels:
        print("❌ 未配置任何通道。设置 GATEWAY_CHANNELS=wechat 或传入 channels 参数。")
        return

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

    tasks = []
    for name in channels:
        task = asyncio.create_task(
            _start_channel(name, agent), name=f"channel-{name}"
        )
        tasks.append(task)

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("\n🛑 网关正在关闭...")
        for task in tasks:
            task.cancel()


async def _start_channel(name: str, agent: Agent):
    """启动单个通道"""
    try:
        if name == "wechat":
            from .channels.wechat import WeChatChannel

            channel = WeChatChannel()
        else:
            print(f"❌ 未知通道: {name}")
            return

        print(f"🚀 启动 {channel.name} 通道...")

        async def on_msg(chn, uid, text):
            reply = await _route_message(agent, chn, uid, text)
            return reply

        await channel.start(on_msg)

    except ImportError as e:
        print(f"❌ 通道 {name} 依赖缺失: {e}")
        print(f"   安装: pip install minibot[{name}]")
    except Exception as e:
        print(f"❌ 通道 {name} 异常: {type(e).__name__}: {e}")


async def run_diagnostic():
    """运行连接诊断 — 测试 iLink Bot API 连通性"""
    load_dotenv()

    account_id = os.environ.get("WECHAT_ACCOUNT_ID", "")
    token = os.environ.get("WECHAT_TOKEN", "")
    base_url = os.environ.get("WECHAT_BASE_URL", "https://ilinkai.weixin.qq.com").rstrip("/")

    print(f"\n🔍 minibot 微信诊断")
    print(f"{'=' * 50}")
    print(f"  WECHAT_ACCOUNT_ID: {account_id[:20] if account_id else '(未设置)'}")
    print(f"  WECHAT_TOKEN:      {'已设置(' + token[:10] + '...)' if token else '(未设置)'}")
    print(f"  WECHAT_BASE_URL:   {base_url}")
    print()

    if not account_id or not token:
        print("❌ 缺少凭证。请先运行 mini-agent gateway 完成微信扫码登录。")
        return

    try:
        import aiohttp
    except ImportError:
        print("❌ 缺少 aiohttp。请安装: pip install aiohttp")
        return

    async with aiohttp.ClientSession() as session:
        # 测试 1: 基本连接
        print("📡 测试 1: 基本网络连接 (get_bot_qrcode)...")
        try:
            async with session.get(
                f"{base_url}/ilink/bot/get_bot_qrcode?bot_type=3", timeout=10
            ) as resp:
                raw = await resp.text()
                print(f"   HTTP {resp.status}: {raw[:150]}")
                if resp.ok:
                    import json as _json
                    data = _json.loads(raw)
                    if data.get("qrcode"):
                        print("   ✅ iLink API 可达")
        except Exception as e:
            print(f"   ❌ 连接失败: {e}")
            print("   💡 提示: 请确保可以访问 ilinkai.weixin.qq.com")
            return

        # 测试 2: 用 token 调用 getupdates
        print("\n📡 测试 2: 消息轮询 API (getupdates)...")
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {token}",
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        }
        body = json.dumps(
            {"get_updates_buf": "", "base_info": {"channel_version": "2.2.0"}},
            ensure_ascii=False, separators=(",", ":")
        )
        try:
            async with session.post(
                f"{base_url}/ilink/bot/getupdates",
                data=body, headers=headers, timeout=15
            ) as resp:
                raw = await resp.text()
                print(f"   HTTP {resp.status}")
                print(f"   响应: {raw[:200]}")
                if resp.ok:
                    try:
                        data = json.loads(raw)
                        ret = data.get("ret", 0)
                        errcode = data.get("errcode", 0)
                        msgs = len(data.get("msgs", []))
                        print(f"   ret={ret} errcode={errcode} 待处理消息={msgs}")
                        if ret == 0:
                            print("   ✅ API 连接正常!")
                        else:
                            print(f"   ⚠️ API 返回错误: {data.get('errmsg', '')}")
                    except json.JSONDecodeError:
                        print("   ⚠️ 响应不是 JSON")
        except asyncio.TimeoutError:
            print("   ⚠️ 超时（长轮询正常，但没有待处理消息）")
        except Exception as e:
            print(f"   ❌ 请求失败: {e}")

    print(f"\n{'=' * 50}")
    print("诊断完成。如果测试 1 和 2 都正常，问题可能在微信端。")
    print("💡 请确认：")
    print("   1. 你已经添加了机器人联系人到微信通讯录")
    print(f"   2. 你给机器人账号 ({account_id}) 发的消息是私聊")
    print("   3. 机器人联系人的头像/名称出现在你的微信中")
