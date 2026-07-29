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
        """调用 iLink Bot API (POST)"""
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

    async def _api_get(self, endpoint: str, timeout_ms: int = QR_TIMEOUT_MS) -> dict:
        """调用 iLink Bot API (GET) — 用于二维码流"""
        await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }

        async def _do() -> dict:
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_ms / 1000)) as resp:
                raw = await resp.text()
                if not resp.ok:
                    raise RuntimeError(f"iLink GET {endpoint} HTTP {resp.status}: {raw[:200]}")
                return json.loads(raw)

        return await asyncio.wait_for(_do(), timeout=timeout_ms / 1000 + 5)

    # ── 登录流程 ───────────────────────────────────

    async def _login(self):
        """获取二维码 → 等待扫码 → 保存凭证"""
        print("\n📱 微信扫码登录")
        print("─" * 40)

        try:
            data = await self._api_get(f"{EP_GET_BOT_QR}?bot_type=3", timeout_ms=QR_TIMEOUT_MS)
        except Exception as e:
            print(f"❌ 获取二维码失败: {e}")
            return False

        qrcode_value = str(data.get("qrcode") or "")
        qrcode_url = str(data.get("qrcode_img_content") or "")

        if not qrcode_value:
            print(f"❌ 二维码数据异常: {json.dumps(data, ensure_ascii=False)[:200]}")
            return False

        # 优先使用完整的扫码 URL
        qr_scan_data = qrcode_url if qrcode_url else qrcode_value
        print(f"🔗 请用微信扫码:\n   {qr_scan_data}")
        print(f"\n⏳ 等待扫码...")

        # 轮询扫码状态
        refresh_count = 0
        for _ in range(120):
            await asyncio.sleep(2)
            try:
                status_data = await self._api_get(
                    f"{EP_GET_QR_STATUS}?qrcode={qrcode_value}",
                    timeout_ms=QR_TIMEOUT_MS,
                )
            except Exception:
                continue

            status = str(status_data.get("status", "wait"))

            if status == "wait":
                print(".", end="", flush=True)
            elif status == "scaned":
                print("\n✅ 已扫码，请在手机上确认...")
            elif status == "scaned_but_redirect":
                redirect_host = str(status_data.get("redirect_host", ""))
                if redirect_host:
                    self.base_url = f"https://{redirect_host}"
                print(f"\n↪️ 重定向到 {redirect_host}")
            elif status == "expired":
                refresh_count += 1
                if refresh_count > 3:
                    print("\n❌ 二维码多次过期")
                    return False
                print(f"\n🔄 二维码过期，刷新中 ({refresh_count}/3)...")
                try:
                    data = await self._api_get(f"{EP_GET_BOT_QR}?bot_type=3", timeout_ms=QR_TIMEOUT_MS)
                    qrcode_value = str(data.get("qrcode", ""))
                    qrcode_url = str(data.get("qrcode_img_content", ""))
                    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
                    print(f"   {qr_scan_data}")
                except Exception:
                    pass
            elif status == "confirmed":
                self.account_id = str(status_data.get("ilink_bot_id", ""))
                self.token = str(status_data.get("bot_token", ""))
                base_url = str(status_data.get("baseurl", ILINK_BASE_URL))
                if base_url:
                    self.base_url = base_url
                if self.account_id and self.token:
                    print(f"\n✅ 微信登录成功！账号: {self.account_id}")
                    self._save_creds()
                    return True
                else:
                    print(f"\n⚠️ 登录响应异常: {json.dumps(status_data, ensure_ascii=False)[:200]}")
                    return False

        print("\n❌ 登录超时")
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
        print(f"   (长轮询每 35 秒检查一次，有新消息会自动显示)")
        consecutive_failures = 0
        poll_count = 0

        while self._running:
            poll_count += 1
            try:
                if poll_count <= 3 or poll_count % 10 == 0:
                    print(f"  📡 [{datetime.now():%H:%M:%S}] 轮询 #{poll_count}...", flush=True)

                data = await self._api_post(
                    EP_GET_UPDATES,
                    {"get_updates_buf": self._sync_buf},
                    timeout_ms=LONG_POLL_TIMEOUT_MS,
                )

                consecutive_failures = 0

                # 更新同步缓存
                new_buf = str(data.get("get_updates_buf") or "")
                if new_buf:
                    self._sync_buf = new_buf

                ret = data.get("ret", 0)
                errcode = data.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    if poll_count <= 3:
                        print(f"  ⚠️ [{datetime.now():%H:%M:%S}] API 返回: ret={ret} errcode={errcode} msg={data.get('errmsg','')}")
                    continue

                msgs = data.get("msgs") or []
                if msgs:
                    print(f"\n📨 [{datetime.now():%H:%M:%S}] 收到 {len(msgs)} 条消息!")
                    for msg in msgs:
                        await self._handle_message(msg)

            except asyncio.TimeoutError:
                # 长轮询超时是正常的 — 没有新消息
                consecutive_failures = 0
                continue
            except Exception as e:
                consecutive_failures += 1
                if poll_count <= 5 or consecutive_failures >= 3:
                    print(f"  ⚠️ [{datetime.now():%H:%M:%S}] 轮询异常 ({consecutive_failures}/5): {type(e).__name__}")
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
