"""channels/wechat.py — 微信通道（基于 iLink Bot API）
通过手机微信扫码登录，支持收发消息。
需要安装: pip install minibot[wechat]
"""

import asyncio
import base64
import json
import os
import secrets
import struct
import time
from datetime import datetime

from . import Channel

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

# ── iLink Bot API 常量 ──────────────────────────

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
QR_TIMEOUT_MS = 35_000

MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2
ITEM_TEXT = 1


class WeChatChannel(Channel):
    """微信 iLink Bot 通道"""

    name = "wechat"

    def __init__(self, env_prefix: str = "WECHAT"):
        self.env_prefix = env_prefix
        self.account_id = os.environ.get(f"{env_prefix}_ACCOUNT_ID", "")
        self.token = os.environ.get(f"{env_prefix}_TOKEN", "")
        self.base_url = os.environ.get(f"{env_prefix}_BASE_URL", ILINK_BASE_URL).rstrip("/")
        self.dm_policy = os.environ.get(f"{env_prefix}_DM_POLICY", "open")
        self.allowed_users = os.environ.get(f"{env_prefix}_ALLOWED_USERS", "")

        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._on_message = None
        self._sync_buf = ""  # 长轮询同步缓冲区

    def _has_creds(self) -> bool:
        return bool(self.account_id and self.token)

    @staticmethod
    def _random_uin() -> str:
        """随机 X-WECHAT-UIN 头"""
        value = struct.unpack(">I", secrets.token_bytes(4))[0]
        return base64.b64encode(str(value).encode()).decode()

    def _headers(self, body: str = "") -> dict:
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode("utf-8"))),
            "X-WECHAT-UIN": self._random_uin(),
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
        }

    def _base_info(self) -> dict:
        return {"channel_version": CHANNEL_VERSION}

    def _json_dumps(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    async def _api_post(self, endpoint: str, payload: dict, timeout_ms: int = API_TIMEOUT_MS) -> dict:
        """调用 iLink Bot API"""
        await self._ensure_session()
        body = self._json_dumps({**payload, "base_info": self._base_info()})
        url = f"{self.base_url}/{endpoint}"

        async def _do() -> dict:
            async with self._session.post(
                url, data=body, headers=self._headers(body), timeout=aiohttp.ClientTimeout(total=timeout_ms / 1000)
            ) as resp:
                raw = await resp.text()
                if not resp.ok:
                    raise RuntimeError(f"iLink POST {endpoint} HTTP {resp.status}: {raw[:200]}")
                return json.loads(raw)

        return await asyncio.wait_for(_do(), timeout=timeout_ms / 1000 + 5)

    # ── 登录流程 ───────────────────────────────────

    async def _login(self):
        """获取二维码 → 等待扫码 → 保存凭证"""
        print("\n📱 微信扫码登录")
        print("─" * 40)

        try:
            data = await self._api_post(EP_GET_BOT_QR, {}, timeout_ms=QR_TIMEOUT_MS)
        except Exception as e:
            print(f"❌ 获取二维码失败: {e}")
            return False

        qr_url = data.get("qrcode_url") or data.get("url", "")
        qr_session = data.get("session_id") or data.get("qrcode_session", "")

        if not qr_url:
            print(f"❌ 二维码数据异常: {json.dumps(data, ensure_ascii=False)[:200]}")
            return False

        # 显示二维码
        print(f"🔗 请用微信扫码:\n   {qr_url}")
        print(f"\n⏳ 等待扫码...")

        # 轮询扫码状态
        for _ in range(120):
            await asyncio.sleep(2)
            try:
                status_data = await self._api_post(
                    EP_GET_QR_STATUS,
                    {"qrcode_session": qr_session} if qr_session else {"qrcode_url": qr_url},
                    timeout_ms=QR_TIMEOUT_MS,
                )
            except Exception:
                continue

            state = status_data.get("status", "")
            if state == "scanned":
                print("✅ 已扫码，等待确认...")
            elif state in ("confirmed", "success"):
                self.account_id = status_data.get("account_id", "")
                self.token = status_data.get("token", "")
                if self.account_id and self.token:
                    print(f"✅ 微信登录成功！账号: {self.account_id}")
                    self._save_creds()
                    return True
                else:
                    print(f"⚠️ 登录响应异常: {json.dumps(status_data, ensure_ascii=False)[:200]}")
                    return False
            elif state in ("expired", "cancel"):
                print("❌ 二维码已过期")
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

    async def _poll_messages(self):
        """长轮询获取消息"""
        print(f"🔗 开始接收微信消息...")
        consecutive_failures = 0

        while self._running:
            try:
                data = await self._api_post(
                    EP_GET_UPDATES,
                    {"get_updates_buf": self._sync_buf},
                    timeout_ms=LONG_POLL_TIMEOUT_MS,
                )

                consecutive_failures = 0
                self._sync_buf = data.get("get_updates_buf", self._sync_buf)
                msgs = data.get("msgs", data.get("messages", []))

                for msg in msgs:
                    await self._handle_message(msg)

            except asyncio.TimeoutError:
                # 长轮询超时是正常的
                consecutive_failures = 0
                continue
            except Exception as e:
                consecutive_failures += 1
                print(f"  ⚠️ 消息轮询异常: {type(e).__name__}")
                if consecutive_failures >= 5:
                    print("❌ 连续失败过多，停止轮询")
                    break
                await asyncio.sleep(3)

    async def _handle_message(self, msg: dict):
        """处理单条消息"""
        msg_type = msg.get("msg_type", msg.get("type", 0))
        if msg_type != MSG_TYPE_USER:
            return  # 只处理用户发来的消息

        from_user = msg.get("from_user_id") or msg.get("from", "")
        content = ""
        items = msg.get("item_list", msg.get("items", []))
        for item in items:
            if item.get("type") == ITEM_TEXT:
                text_item = item.get("text_item", item.get("text", {}))
                content = text_item.get("text", "")

        if not content or not from_user:
            return

        # 检查 DM 策略
        if not self._check_dm_policy(from_user):
            return

        print(f"\n📩 [{datetime.now():%H:%M:%S}] {from_user}: {content[:80]}")

        if self._on_message:
            reply = await self._on_message("wechat", from_user, content)
            if reply:
                await self.send(from_user, reply)

    def _check_dm_policy(self, user_id: str) -> bool:
        if self.dm_policy == "open":
            return True
        if self.dm_policy in ("allowlist", "listed"):
            allowed = [u.strip() for u in self.allowed_users.split(",") if u.strip()]
            return user_id in allowed
        if self.dm_policy == "disabled":
            return False
        return True

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    # ── 公开接口 ───────────────────────────────────

    async def start(self, on_message):
        self._on_message = on_message
        await self._ensure_session()

        if not self._has_creds():
            ok = await self._login()
            if not ok:
                return

        self._running = True
        print(f"✅ 微信网关已就绪 (账号: {self.account_id})")

        try:
            await self._poll_messages()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            print("⚠️ 微信连接已断开")

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None

    async def send(self, user_id: str, text: str):
        """发送微信消息"""
        try:
            await self._api_post(
                EP_SEND_MESSAGE,
                {
                    "msg": {
                        "from_user_id": self.account_id,
                        "to_user_id": user_id,
                        "client_id": f"minibot_{int(time.time())}",
                        "message_type": MSG_TYPE_BOT,
                        "message_state": MSG_STATE_FINISH,
                        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
                    }
                },
            )
        except Exception as e:
            print(f"  ⚠️ 发送失败: {e}")
