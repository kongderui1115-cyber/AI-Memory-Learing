"""冻结契约常量镜像 + 从 enums.py 文件真实加载的一致性校验。

为什么镜像而不直接 `import app.contracts`：
  `backend/app/contracts/__init__.py` 会 `from .models import *`，而 models.py 依赖
  pydantic。按 PROJECT_STATUS.md BLK-06，本项目尚未安装任何第三方依赖；通知模块必须
  做到「零外部依赖、仅标准库」即可导入与单测（Chief Architect 的 check_contracts.py
  同样以 AST 方式读取 enums.py 并 SKIP runtime_model_import）。
  因此这里把冻结枚举值以字符串常量镜像，并提供 `load_frozen_enums()` 用 importlib
  从 enums.py 文件（仅依赖标准库 enum.StrEnum）真实加载，供 `assert_contract_alignment()`
  与单元测试强制校验「零漂移」。

契约来源：
  - backend/app/contracts/enums.py   NotificationChannelType / NotificationJobStatus
  - API_CONTRACTS.md 第 2 节        NotificationChannelType / NotificationJobStatus
  - API_CONTRACTS.md 第 3 节        NotificationDeliveryRead.status (sending/sent/failed)
  - DATABASE_SCHEMA.md 第 2 节      notification_* 表字段与 CHECK 约束
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


class ChannelType:
    """NotificationChannelType（7 种，冻结）。"""

    WECOM_APP = "wecom_app"
    WECHAT_OFFICIAL_ACCOUNT = "wechat_official_account"
    THIRD_PARTY_PUSH = "third_party_push"
    WECOM_WEBHOOK = "wecom_webhook"
    DINGTALK_WEBHOOK = "dingtalk_webhook"
    DINGTALK_APP = "dingtalk_app"
    SMTP = "smtp"

    ALL: tuple[str, ...] = (
        WECOM_APP,
        WECHAT_OFFICIAL_ACCOUNT,
        THIRD_PARTY_PUSH,
        WECOM_WEBHOOK,
        DINGTALK_WEBHOOK,
        DINGTALK_APP,
        SMTP,
    )


class JobStatus:
    """NotificationJobStatus（冻结）。生命周期见 DATABASE_SCHEMA.md 第 3 节。"""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL: tuple[str, ...] = (PENDING, PROCESSING, SENT, FAILED, CANCELLED)


class DeliveryStatus:
    """notification_deliveries.status（API_CONTRACTS.md 第 3 节 / DATABASE_SCHEMA.md 第 2 节）。"""

    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"

    ALL: tuple[str, ...] = (SENDING, SENT, FAILED)


#: FR-07 微信优先的 4 种合规实现（个人微信无官方主动推送 API，禁止逆向协议）。
WECHAT_CHANNEL_TYPES: tuple[str, ...] = (
    ChannelType.WECOM_APP,
    ChannelType.WECHAT_OFFICIAL_ACCOUNT,
    ChannelType.THIRD_PARTY_PUSH,
    ChannelType.WECOM_WEBHOOK,
)

#: FR-08 企业微信渠道：复用 FR-07 路径 A（应用消息）与 D（群机器人 Webhook）。
#: 同一套实现同时承载 FR-07 与 FR-08，不重复造轮子。
WECOM_CHANNEL_TYPES: tuple[str, ...] = (
    ChannelType.WECOM_APP,
    ChannelType.WECOM_WEBHOOK,
)


def default_enums_path() -> Path:
    # __file__ = backend/app/notifications/contract_values.py -> parents[1] = backend/app
    return Path(__file__).resolve().parents[1] / "contracts" / "enums.py"


def load_frozen_enums(path: str | Path | None = None) -> ModuleType:
    """从 enums.py 文件真实加载冻结枚举（绕过会 import pydantic 的包 __init__）。

    仅依赖标准库；enums.py 本身只 `from enum import StrEnum`。
    """
    target = Path(path) if path is not None else default_enums_path()
    if not target.is_file():
        raise FileNotFoundError(f"冻结契约枚举文件不存在: {target}")
    spec = importlib.util.spec_from_file_location("_frozen_contract_enums_for_notif", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载冻结契约枚举: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_channel_types(module: ModuleType) -> tuple[str, ...]:
    return tuple(member.value for member in module.NotificationChannelType)


def frozen_job_statuses(module: ModuleType) -> tuple[str, ...]:
    return tuple(member.value for member in module.NotificationJobStatus)


def assert_contract_alignment(path: str | Path | None = None) -> None:
    """校验本文件常量与冻结 enums.py 完全一致，不一致即 AssertionError。

    由 tests_notif/test_contract_alignment.py 真实调用；新增渠道/状态必须先改契约文档
    与 enums.py，否则该校验与单元测试会失败，防止静默漂移。
    """
    module = load_frozen_enums(path)
    expected_channels = set(frozen_channel_types(module))
    expected_jobs = set(frozen_job_statuses(module))
    actual_channels = set(ChannelType.ALL)
    actual_jobs = set(JobStatus.ALL)
    assert actual_channels == expected_channels, (
        f"channel_type 与契约漂移: 仅本地={sorted(actual_channels - expected_channels)}, "
        f"仅契约={sorted(expected_channels - actual_channels)}"
    )
    assert actual_jobs == expected_jobs, (
        f"job status 与契约漂移: 仅本地={sorted(actual_jobs - expected_jobs)}, "
        f"仅契约={sorted(expected_jobs - actual_jobs)}"
    )
    assert set(WECHAT_CHANNEL_TYPES) <= expected_channels, "微信渠道类型不在契约枚举内"
