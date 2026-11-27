"""Notion 数据源与增量同步适配器（AI-02 / FR-01）。

父包 ``app.integrations`` 故意不提供 ``__init__.py``（PEP 420 命名空间包），
因为该路径不在 AI Integration Agent 的可写范围内。本包只依赖标准库与
``app.ai.errors``，不依赖 pydantic / httpx / 数据库。

未授权 Token 时只实现真实 HTTP 路径 + ``CONFIG_MISSING`` 明确报错，
绝不伪造同步结果。
"""

__all__ = ["client", "markdown", "models", "sync"]
