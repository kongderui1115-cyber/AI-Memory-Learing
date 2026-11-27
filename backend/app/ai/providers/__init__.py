"""AI Provider 具体实现包：三种 OpenAI 协议族实现 + 注册表。"""

from .registry import PROVIDER_CLASSES, resolve_provider

__all__ = ["PROVIDER_CLASSES", "resolve_provider"]
