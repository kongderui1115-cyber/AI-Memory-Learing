"""pytest 共享配置与 fixture —— QA-01 测试框架准备（未执行）。

如实声明（2026-11-13，qa-dev）：
  * 本机 **未安装 pytest / pytest-asyncio / httpx 等测试依赖**，本批次也**不安装依赖**，
    因此本文件在本批次 **未被执行**，仅作为框架配置与 fixture 契约落盘。
  * 这些 fixture 只读取**已冻结的契约文档**与 ``app/contracts`` 目录，
    **不导入任何业务实现代码、不联网、不连数据库、不启动服务、不读取密钥**；
    因此可在各 Agent 业务实现合并之前独立存在，后续测试直接复用。
  * ``backend/pyproject.toml`` 已由 Chief Architect 提供
    ``[tool.pytest.ini_options]``（asyncio_mode="auto", testpaths=["tests"]），
    pytest rootdir 为 ``backend/``；本文件位于 ``backend/tests/``，pytest 会自动加载，
    故**不新建** ``backend/pytest.ini``，避免与既有 ini 配置冲突或产生双 rootdir。
  * 真实联调所需环境变量一律 ``pytest.skip`` 并注明原因，**绝不伪造**地址、令牌或凭据，
    也绝不以 mock 结果冒充真实联调通过。

安装依赖后的运行方式（本批次未执行）：
    cd backend && python -m pytest tests -q
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
CONTRACTS_DIR = BACKEND / "app" / "contracts"
API_MD = ROOT / "API_CONTRACTS.md"
ENUMS_PY = CONTRACTS_DIR / "enums.py"
CONTRACT_CHECK = ROOT / "qa" / "check_api_contract.py"


def pytest_configure(config: pytest.Config) -> None:
    """注册用例分类 marker，与 ``qa/test_matrix.md`` 的测试模式一一对应。"""
    config.addinivalue_line(
        "markers", "isolated: 隔离测试（纯函数/fixture/契约静态检查/显式标注的测试替身）"
    )
    config.addinivalue_line(
        "markers", "integration: 真实联调（需外部授权或真实 HTTP；未授权必须 skip）"
    )
    config.addinivalue_line(
        "markers", "regression: 合并后完整回归 QA-REG-01（INT-01/INT-02 之后方可执行）"
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Worktree / 仓库根目录。"""
    return ROOT


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    """冻结契约代码目录 ``backend/app/contracts``（对本 Agent 只读）。"""
    return CONTRACTS_DIR


@pytest.fixture(scope="session")
def api_contracts_text() -> str:
    """``API_CONTRACTS.md`` 全文（UTF-8）。"""
    return API_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def enums_source() -> str:
    """``backend/app/contracts/enums.py`` 源码文本。"""
    return ENUMS_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def contract_check(repo_root: Path) -> tuple[int, str]:
    """以子进程**真实运行** ``qa/check_api_contract.py``，返回 ``(returncode, stdout)``。

    该脚本仅用标准库、不依赖 pytest 与业务实现，是本批次可真实执行的契约门禁；
    后续契约用例可直接断言 ``returncode == 0`` 且 stdout 含 ``RESULT: PASS``。
    """
    proc = subprocess.run(
        [sys.executable, str(repo_root / "qa" / "check_api_contract.py")],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """真实联调基地址。未配置时**跳过**，绝不回退到本地假地址。

    由 ``INT-02`` 集成启动后通过 ``QA_API_BASE_URL`` 提供，例如 ``http://127.0.0.1:8000/api/v1``。
    """
    value = os.environ.get("QA_API_BASE_URL")
    if not value:
        pytest.skip("QA_API_BASE_URL 未配置：真实联调需 INT-02 后由部署提供，禁止用 mock 冒充")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    """真实 Bearer JWT。未配置时**跳过**，绝不伪造令牌。"""
    token = os.environ.get("QA_AUTH_TOKEN")
    if not token:
        pytest.skip("QA_AUTH_TOKEN 未配置：真实联调需有效 Bearer Token，禁止伪造")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def idempotency_key() -> str:
    """供创建/触发/完成类 POST 使用的幂等键（构造器，非真实请求）。"""
    import uuid

    return f"qa-{uuid.uuid4()}"
