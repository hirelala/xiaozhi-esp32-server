"""
Voice2Voice Provider Base Class
Handles real-time voice-to-voice conversation, bypassing ASR→LLM→TTS pipeline
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class V2VProviderBase(ABC):
    """Voice2Voice提供者基类"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化Voice2Voice提供者

        Args:
            config: 配置字典，包含V2V相关配置
        """
        self.config = config
        self.logger = logger

    @abstractmethod
    async def initialize(self, conn) -> bool:
        """
        初始化V2V连接

        Args:
            conn: 连接对象

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    async def handle_audio_input(self, conn, audio_data: bytes) -> None:
        """
        处理输入音频数据

        Args:
            conn: 连接对象
            audio_data: 音频数据（Opus格式）
        """
        pass

    @abstractmethod
    async def start_conversation(self, conn) -> None:
        """
        开始对话会话

        Args:
            conn: 连接对象
        """
        pass

    @abstractmethod
    async def stop_conversation(self, conn) -> None:
        """
        停止对话会话

        Args:
            conn: 连接对象
        """
        pass

    @abstractmethod
    async def cleanup(self, conn) -> None:
        """
        清理资源

        Args:
            conn: 连接对象
        """
        pass

    def is_enabled(self, conn) -> bool:
        """
        检查V2V是否启用

        Args:
            conn: 连接对象

        Returns:
            bool: 是否启用V2V
        """
        return getattr(conn, 'enable_voice2voice', False)


