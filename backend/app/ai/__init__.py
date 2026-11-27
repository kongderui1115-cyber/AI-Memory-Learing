"""AI 集成层：Provider 端口、结构化抽取/出题、数据驱动学科策略。

本包刻意只使用 Python 标准库，使领域纯逻辑在未安装任何第三方依赖的
环境中也能被导入和单元测试。字段名与枚举值严格对齐冻结契约
``app/contracts``（见 API_CONTRACTS.md / DATABASE_SCHEMA.md），但不 import
pydantic —— 该依赖在当前开发环境中尚未安装，且契约由 Chief Architect 独占。

外部 HTTP 只在凭据与计费授权齐备时才真实发起；缺失即抛 CONFIG_MISSING。
"""

__all__ = [
    "call_log",
    "config",
    "errors",
    "extraction",
    "generation",
    "ports",
    "prompts",
    "providers",
    "retry",
    "service",
    "strategies",
    "validation",
]
