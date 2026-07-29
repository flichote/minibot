"""channels/wechat.py — 微信通道（基于 iLink Bot API）
通过手机微信扫码登录，支持收发消息。
需要安装: pip install minibot[wechat]
"""

import asyncio
import json
import os
import time
from datetime import datetime

from . import Channel

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore


QRCODE_API = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"


class WeChatChannel(Channel):
    """微信 iLink Bot 通道"""

    name = "wechat"

    def __init__(self, env_prefix: str = "WECHAT"):
        self.env_prefix = env_prefix
        self.account_id = os.environ.get(f"{env_prefix}_ACCOUNT_ID", "")
        self.token = os.environ.get(f"{env_prefix}_TOKEN", "")
        self.base_url = os.environ.get(
            f"{env_prefix}_BASE_URL", "https://ilinkai.weixin.qq.com"
        ).rstrip("/")
        self.dm_policy = os.environ.get(f"{env_prefix}_DM_POLICY", "open")
        self.allowed_users = os.environ.get(f"{env_prefix}_ALLOWED_USERS", "")

        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._on_message = None
        self._bot_id = ""

    def _has_creds(self) -> bool:
        return bool(self.account_id and self.token)

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    # ── 登录流程 ───────────────────────────────────

    async def _login(self):
        """首次登录：获取二维码 → 等待扫码 → 保存凭证"""
        self._bot_id = self.account_id
        print("\n📱 微信扫码登录")
        print("─" * 40)

        # 请求二维码
        async with self._session.post(
            f"{self.base_url}/api/login/qrcode",
            json={},
        ) as resp:
            data = await resp.json()

        qr_url = data.get("qrcode_url", "")
        session_id = data.get("session_id", "")

        if not qr_url:
            print("❌ 获取二维码失败，检查网络连接")
            return False

        # 显示二维码 URL + QR 码
        qr_img_url = QRCODE_API.format(url=qr_url)
        print(f"🔗 二维码链接: {qr_url}")
        print(f"🖼️ 或浏览器打开: {qr_img_url}")
        print("\n⏳ 请用微信扫码登录...")
        print("   (如果已有凭证，设置环境变量可跳过此步)")

        # 轮询扫码状态
        for _ in range(120):  # 最多等 2 分钟
            await asyncio.sleep(2)
            async with self._session.post(
                f"{self.base_url}/api/login/check",
                json={"session_id": session_id},
            ) as resp:
                status = await resp.json()
                state = status.get("status", "pending")

                if state == "scanned":
                    print("✅ 已扫码，等待确认...")
                elif state == "confirmed":
                    self.account_id = status.get("account_id", "")
                    self.token = status.get("token", "")
                    print(f"✅ 微信登录成功！账号: {self.account_id}")
                    self._save_creds()
                    return True
                elif state == "expired":
                    print("❌ 二维码已过期，请重试")
                    return False

        print("❌ 登录超时")
        return False

    def _save_creds(self):
        """保存凭证到 .env 文件"""
        env_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_path):
            return

        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()

        updates = {
            f"{self.env_prefix}_ACCOUNT_ID": self.account_id,
            f"{self.env_prefix}_TOKEN": self.token,
        }

        new_lines = []
        written_keys = set()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            for key in updates:
                if stripped.startswith(key + "="):
                    new_lines.append(f'{key}="{updates[key]}"\n')
                    written_keys.add(key)
                    break
            else:
                new_lines.append(line)

        for key, val in updates.items():
            if key not in written_keys:
                new_lines.append(f'{key}="{val}"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"💾 凭证已保存到 .env")

    # ── 消息收发 ───────────────────────────────────

    async def _handle_ws_message(self, msg_data: dict):
        """处理收到的 WebSocket 消息"""
        msg_type = msg_data.get("type", "")

        if msg_type == "message":
            content = msg_data.get("content", "")
            from_user = msg_data.get("from", "")
            msg_id = msg_data.get("id", "")

            # DM 策略检查
            if not self._check_dm_policy(from_user):
                print(f"  ⛔ 拒绝: {from_user} (DM 策略)")
                return

            print(f"\n📩 [{datetime.now():%H:%M:%S}] {from_user}: {content[:80]}")

            if self._on_message:
                reply = await self._on_message("wechat", from_user, content)
                if reply:
                    await self.send(from_user, reply)

        elif msg_type == "ping":
            # 心跳回复
            await self._ws.send_json({"type": "pong"})

    def _check_dm_policy(self, user_id: str) -> bool:
        """检查用户是否有权限发消息"""
        if self.dm_policy == "open":
            return True
        if self.dm_policy in ("allowlist", "listed"):
            allowed = [u.strip() for u in self.allowed_users.split(",") if u.strip()]
            return user_id in allowed
        if self.dm_policy == "disabled":
            return False
        # pairing 模式：全部通过（简化版）
        return True

    # ── 公开接口 ───────────────────────────────────

    async def start(self, on_message):
        self._on_message = on_message
        await self._ensure_session()

        if not self._has_creds():
            ok = await self._login()
            if not ok:
                return

        # 连接 WebSocket
        ws_url = f"{self.base_url}/ws"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Account-Id": self.account_id,
        }

        print(f"🔗 连接微信消息服务...")
        try:
            self._ws = await self._session.ws_connect(
                ws_url, headers=headers, heartbeat=30
            )
        except Exception as e:
            print(f"❌ WebSocket 连接失败: {e}")
            return

        self._running = True
        print(f"✅ 微信网关已就绪 (账号: {self.account_id})")

        # 消息循环
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._handle_ws_message(data)
                except json.JSONDecodeError:
                    pass
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                break

        self._running = False
        print("⚠️ 微信连接已断开")

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    async def send(self, user_id: str, text: str):
        """发送微信消息"""
        await self._ensure_session()
        async with self._session.post(
            f"{self.base_url}/api/message/send",
            json={
                "to": user_id,
                "content": text,
                "account_id": self.account_id,
            },
            headers={"Authorization": f"Bearer {self.token}"},
        ) as resp:
            result = await resp.json()
            if result.get("code") != 0:
                print(f"  ⚠️ 发送失败: {result.get('message', '')}")
