"""channels/__init__.py — 通道基类
所有平台通道（微信、Telegram 等）继承此接口。
"""

from abc import ABC, abstractmethod


class Channel(ABC):
    """消息通道基类"""

    name: str = ""

    @abstractmethod
    async def start(self, on_message):
        """启动通道连接，on_message 是消息回调

        on_message(channel_name, user_id, text) -> str | None
        返回回复文本，或 None 表示不回复
        """
        ...

    @abstractmethod
    async def stop(self):
        """停止通道"""
        ...

    @abstractmethod
    async def send(self, user_id: str, text: str):
        """向指定用户发送消息"""
        ...
