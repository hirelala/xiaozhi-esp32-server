"""
V2V (Voice2Voice) Utility Module
Handles voice2voice provider initialization
"""

import importlib
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


def create_instance(v2v_type: str, config: dict):
    """
    动态创建V2V实例

    Args:
        v2v_type: V2V类型 (如 'livekit')
        config: V2V配置

    Returns:
        V2V实例
    """
    try:
        # 根据type动态导入对应的provider模块
        module_path = f"core.providers.v2v.{v2v_type}"
        module = importlib.import_module(module_path)
        
        # 获取Provider类并实例化
        provider_class = getattr(module, "V2VProvider")
        instance = provider_class(config)
        
        logger.bind(tag=TAG).info(f"V2V provider '{v2v_type}' initialized")
        return instance
        
    except ImportError as e:
        logger.bind(tag=TAG).error(
            f"Failed to import V2V provider '{v2v_type}': {e}"
        )
        raise
    except Exception as e:
        logger.bind(tag=TAG).error(
            f"Failed to create V2V instance for '{v2v_type}': {e}"
        )
        raise


