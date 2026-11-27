"""渠道配置结构（NOTIF-01），对应 notification_channel_configs 表。

秘密不入库：credential_ref 是环境变量名 / 命名空间前缀；真正 token / secret / 密码
只从环境变量读取（绝不写入 settings、不落库、不进日志、不进 delivery 元数据）。
非秘密参数（touser / template_id / webhook 目标等）存 settings。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ChannelConfig:
    """notification_channel_configs 行的领域对象（字段名与契约表一致）。"""

    name: str
    channel_type: str
    credential_ref: str
    user_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    settings: dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True
    is_default: bool = False
    version: int = 1
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name 不能为空")
        if not self.credential_ref:
            raise ValueError("credential_ref 不能为空（秘密只经环境变量名引用）")
        # channel_type 不在此写死校验：注册表支持插件式扩展；
        # 与冻结契约的一致性由 contract_values.assert_contract_alignment() 与单测保证。

    # ---- 非秘密配置：仅从 settings 读取 ----
    def setting(self, key: str, default: Any = None) -> Any:
        value = self.settings.get(key)
        return default if value in (None, "") else value

    def setting_or_env(self, key: str, env_name: str, default: Any = None) -> Any:
        """非秘密项兼容读取：settings 优先，其次环境变量（便于 .env.example 直用）。"""
        value = self.settings.get(key)
        if value not in (None, ""):
            return value
        env_value = os.environ.get(env_name)
        if env_value not in (None, ""):
            return env_value
        return default

    # ---- 秘密凭据：只从环境变量读取，绝不读 settings（秘密不入库）----
    def credential(self, logical_name: str, default_env: str | None = None) -> str | None:
        """按 credential_ref 命名空间解析秘密。

        查找顺序：
          1) f"{credential_ref}_{LOGICAL_NAME.upper()}"  —— 多实例命名空间
          2) default_env                                  —— .env.example 默认变量名
        例如 credential_ref="WECOM"、logical="corp_id" -> WECOM_CORP_ID（与 .env.example 一致）。
        """
        candidates: list[str] = []
        if self.credential_ref:
            candidates.append(f"{self.credential_ref}_{logical_name.upper()}")
        if default_env:
            candidates.append(default_env)
        for name in candidates:
            value = os.environ.get(name)
            if value not in (None, ""):
                return value
        return None

    def credential_map(self, spec: tuple[tuple[str, str], ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for logical, env in spec:
            value = self.credential(logical, env)
            if value:
                result[logical] = value
        return result
