"""应用配置读取（BE-01）。

仅使用 Python 标准库：从 ``os.environ`` 与可选 ``.env`` 文件读取配置，
缺失必需项或仍为占位符时抛出 :class:`ConfigMissingError`（契约错误码
``CONFIG_MISSING``），**绝不静默降级为假数据 / Mock**。

设计约束（来自 PROJECT_REQUIREMENTS / ARCHITECTURE / DEPLOYMENT）：
- 所有配置环境变量化，不写死 Windows 路径；
- PostgreSQL 为唯一生产库，连接串必须是 ``postgresql`` 协议，禁止 SQLite 简化；
- 数据库凭据未确认（BLK-05）时 ``database_url`` 允许是占位符，但任何真正
  使用连接的路径必须调用 :func:`assert_database_configured` 明确报错；
- 外部凭据（Notion / AI / 通知）未授权时通过 :meth:`Settings.require` 明确报错。

本模块不依赖 pydantic / pydantic-settings，因而可在纯净环境中真实导入与测试。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

# 缺失即无法以真实配置启动的必需项。
REQUIRED_KEYS: tuple[str, ...] = ("DATABASE_URL", "SECRET_KEY")

# 占位符特征：命中即视为"未配置"，不得静默当作有效值使用。
PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "REPLACE_ME",
    "USER:PASSWORD",
    "CHANGEME",
    "YOUR_",
    "XXXX",
    "<",
    ">",
)

_DEFAULT_DOTENV = Path(__file__).resolve().parents[2] / ".env"


class ConfigMissingError(RuntimeError):
    """必需配置缺失或仍是占位符；对应 API 契约错误码 ``CONFIG_MISSING``。"""

    code = "CONFIG_MISSING"

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__("必需配置缺失或未替换占位符: " + ", ".join(self.missing))


def is_blank_or_placeholder(value: str | None) -> bool:
    """判断配置值是否为空或明显的占位符。"""
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    upper = stripped.upper()
    return any(marker.upper() in upper for marker in PLACEHOLDER_MARKERS)


@dataclass(frozen=True)
class Settings:
    """类型化的应用配置快照。``raw`` 保留原始环境变量，供外部凭据读取。"""

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    timezone: str = "UTC"
    database_url: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    access_token_expire_minutes: int = 1440
    scheduler_strategy: str = "fsrs"
    ebbinghaus_intervals_days: tuple[int, ...] = (1, 2, 4, 7, 15, 30)
    fsrs_target_retention: float = 0.9
    daily_review_limit: int = 30
    ai_billing_approved: bool = False
    background_tasks_enabled: bool = False
    login_failure_limit: int = 6
    login_ip_failure_limit: int = 60
    login_lock_minutes: int = 15
    online_window_seconds: int = 300
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:3030", "http://localhost:3030")
    raw: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    def get(self, name: str, default: str = "") -> str:
        return self.raw.get(name, default)

    def is_set(self, name: str) -> bool:
        return not is_blank_or_placeholder(self.raw.get(name, ""))

    def require(self, name: str) -> str:
        """读取外部凭据类配置；缺失 / 占位符时明确抛错（CONFIG_MISSING）。

        用于 AI Provider Key、Notion Token、通知渠道凭据等：未授权时只允许
        走"配置读取 + 明确报错"路径，绝不返回假数据。
        """
        value = self.raw.get(name, "")
        if is_blank_or_placeholder(value):
            raise ConfigMissingError([name])
        return value


def _read_dotenv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _parse_int(raw: Mapping[str, str], name: str, default: int) -> int:
    value = raw.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"配置项 {name} 必须为整数，实际为 {value!r}") from exc


def _parse_float(raw: Mapping[str, str], name: str, default: float) -> float:
    value = raw.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"配置项 {name} 必须为数值，实际为 {value!r}") from exc


def _parse_bool(raw: Mapping[str, str], name: str, default: bool) -> bool:
    value = raw.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_intervals(
    raw: Mapping[str, str], name: str, default: tuple[int, ...]
) -> tuple[int, ...]:
    value = raw.get(name)
    if value is None or value.strip() == "":
        return default
    parts = [part.strip() for part in value.split(",") if part.strip()]
    try:
        parsed = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"配置项 {name} 必须为逗号分隔的整数序列") from exc
    if not parsed or any(day <= 0 for day in parsed):
        raise ValueError(f"配置项 {name} 必须为正整数序列")
    return parsed


def load_settings(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """构造配置快照。

    - ``env`` 显式传入时完全以它为准（便于确定性测试，不触碰真实环境）；
    - 否则读取 ``.env``，再以真实 ``os.environ`` 覆盖（环境变量优先）；
    - 必需项缺失 / 占位符 -> :class:`ConfigMissingError`；类型错误 -> ``ValueError``。
    """
    if env is not None:
        raw: dict[str, str] = {str(k): str(v) for k, v in env.items()}
    else:
        selected_path = dotenv_path or (
            _DEFAULT_DOTENV
            if _DEFAULT_DOTENV.exists()
            else _DEFAULT_DOTENV.parent / "backend" / ".env"
        )
        raw = _read_dotenv(selected_path)
        raw.update({k: v for k, v in os.environ.items()})

    missing = [key for key in REQUIRED_KEYS if is_blank_or_placeholder(raw.get(key))]
    if missing:
        raise ConfigMissingError(missing)

    if len(raw["SECRET_KEY"].strip()) < 32:
        raise ConfigMissingError(["SECRET_KEY (minimum 32 characters)"])

    return Settings(
        app_env=raw.get("APP_ENV", "development"),
        app_host=raw.get("APP_HOST", "127.0.0.1"),
        app_port=_parse_int(raw, "APP_PORT", 8000),
        log_level=raw.get("LOG_LEVEL", "INFO"),
        timezone=raw.get("TZ", "UTC"),
        database_url=raw["DATABASE_URL"].strip(),
        secret_key=raw["SECRET_KEY"].strip(),
        access_token_expire_minutes=_parse_int(raw, "ACCESS_TOKEN_EXPIRE_MINUTES", 1440),
        scheduler_strategy=raw.get("SCHEDULER_STRATEGY", "fsrs"),
        ebbinghaus_intervals_days=_parse_intervals(
            raw, "EBBINGHAUS_INTERVALS_DAYS", (1, 2, 4, 7, 15, 30)
        ),
        fsrs_target_retention=_parse_float(raw, "FSRS_TARGET_RETENTION", 0.9),
        daily_review_limit=_parse_int(raw, "DAILY_REVIEW_LIMIT", 30),
        ai_billing_approved=_parse_bool(raw, "AI_BILLING_APPROVED", False),
        background_tasks_enabled=_parse_bool(raw, "BACKGROUND_TASKS_ENABLED", False),
        login_failure_limit=max(1, _parse_int(raw, "LOGIN_FAILURE_LIMIT", 6)),
        login_ip_failure_limit=max(1, _parse_int(raw, "LOGIN_IP_FAILURE_LIMIT", 60)),
        login_lock_minutes=max(1, _parse_int(raw, "LOGIN_LOCK_MINUTES", 15)),
        online_window_seconds=max(1, _parse_int(raw, "ONLINE_WINDOW_SECONDS", 300)),
        cors_origins=tuple(
            origin.strip()
            for origin in raw.get(
                "CORS_ORIGINS", "http://127.0.0.1:3030,http://localhost:3030"
            ).split(",")
            if origin.strip()
        ),
        raw=raw,
    )


def assert_database_configured(settings: Settings) -> str:
    """真正使用数据库连接前调用：未配置 / 占位符 / 非 PostgreSQL 均明确报错。"""
    url = settings.database_url
    if is_blank_or_placeholder(url):
        raise ConfigMissingError(["DATABASE_URL"])
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ConfigMissingError(["DATABASE_URL(必须为 PostgreSQL 连接串，禁止 SQLite)"])
    return url


def require_ai_billing(settings: Settings) -> None:
    """产生计费的模型调用前调用；未授权明确报错（不得静默跳过或伪造结果）。"""
    if not settings.ai_billing_approved:
        raise ConfigMissingError(["AI_BILLING_APPROVED"])
