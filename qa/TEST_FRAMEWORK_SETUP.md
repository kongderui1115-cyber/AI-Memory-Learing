# QA-01 测试框架配置与依赖需求（准备阶段）

> 维护者：QA Agent `qa-dev` ｜ 建立：2026-11-13 ｜ 分支 `agent/qa/qa-core`
>
> **状态：配置已落盘；未安装依赖、未执行任何产品测试。**
> 本批次只做**不依赖具体业务实现的准备工作**：框架配置、用例规格、契约静态检查脚本。
> 其他 Agent 仍在各自 Worktree 开发，本 Worktree 看不到它们的实现代码；
> **不虚构任何针对尚未存在代码的测试结果**。

---

## 0. 本批次边界（如实声明）

| 项 | 真实状态 |
| --- | --- |
| 依赖安装 | **未安装**（本机 pytest / pytest-asyncio / httpx / pydantic / vitest 均未安装；本批次不安装、不联网） |
| 产品测试执行 | **未执行**；`TEST_REPORT.md` §1「尚未执行任何测试」结论**不变** |
| 业务实现可见性 | 不可见（各 Agent 并行开发中） |
| 真实可运行且有真实输出 | `qa/check_api_contract.py`（仅标准库，输出见 `TEST_REPORT.md` §6） |
| 外部调用 | 无（不联网、不连数据库、不调用外部 API、不启动服务、不读凭据） |

本批次交付物：

| 文件 | 性质 | 状态 |
| --- | --- | --- |
| `backend/tests/conftest.py` | pytest fixture + marker 配置 | 已落盘，**未执行**（pytest 未安装） |
| `qa/TEST_FRAMEWORK_SETUP.md` | 本文件：配置建议 + 依赖需求清单 | 规格/建议 |
| `qa/test_matrix.md` | 19 个用例的可执行规格 | 规格设计，**未执行** |
| `qa/check_api_contract.py` | 契约一致性检查（标准库） | **已真实运行**，17 PASS / 0 FAIL |
| `TEST_REPORT.md` §6 | 真实执行记录 | 已如实补记 |

---

## 1. 后端 pytest

### 1.1 已生效的配置（只读，非本 Agent 所有权）

`backend/pyproject.toml` 已由 Chief Architect 提供：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- pytest `rootdir` 为 `backend/`；运行命令：`cd backend && python -m pytest tests -q`（**本批次未执行**）。
- QA Agent 的可写范围是 `backend/tests/**`、`tests/**`、`TEST_REPORT.md`、`qa/**`，
  **不包含** `backend/pyproject.toml`（所有权归 Chief Architect / Backend Agent）。
  因此本批次**不新建** `backend/pytest.ini`、也不修改 `pyproject.toml`，
  避免与既有 ini 配置冲突或产生双 rootdir。

### 1.2 本批次落盘：`backend/tests/conftest.py`

pytest 会自动加载 `backend/tests/conftest.py`，其中提供：

| fixture | 作用域 | 用途 |
| --- | --- | --- |
| `repo_root` | session | Worktree / 仓库根目录 `Path` |
| `contracts_dir` | session | `backend/app/contracts`（冻结契约代码目录，对本 Agent 只读） |
| `api_contracts_text` | session | `API_CONTRACTS.md` 全文 |
| `enums_source` | session | `enums.py` 源码文本 |
| `contract_check` | session | 以子进程**真实运行** `qa/check_api_contract.py`，返回 `(returncode, stdout)` |
| `api_base_url` | session | 真实联调基地址；由 `QA_API_BASE_URL` 提供，**未配置则 `skip`，绝不回退假地址** |
| `auth_headers` | session | 真实 Bearer JWT；由 `QA_AUTH_TOKEN` 提供，**未配置则 `skip`，绝不伪造令牌** |
| `idempotency_key` | session | 供创建/触发/完成类 POST 使用的幂等键构造器 |

并注册 3 个 marker（与 `qa/test_matrix.md` 分类一一对应）：

| marker | 含义 |
| --- | --- |
| `isolated` | 隔离测试（纯函数 / fixture / 契约静态检查 / 显式标注的测试替身） |
| `integration` | 真实联调（需外部授权或真实 HTTP；未授权必须 `skip`） |
| `regression` | 合并后完整回归 `QA-REG-01`（`INT-01/INT-02` 之后方可执行） |

所有 fixture **只读取已冻结的契约文档与 `app/contracts`**，不导入业务实现、不联网、不连库、不启动服务，
因此可在各模块合并前独立存在。

### 1.3 建议追加的 pytest 配置（**建议，需由 Backend / Architect 落盘**）

以下为建议片段，**本批次不写入 `backend/pyproject.toml`**：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
  "isolated: 隔离测试（纯函数/fixture/契约静态检查/显式标注的测试替身）",
  "integration: 真实联调（需外部授权或真实 HTTP；未授权必须 skip）",
  "regression: 合并后完整回归 QA-REG-01（INT-01/INT-02 之后方可执行）",
]
[tool.coverage.run]
source = ["app"]
[tool.coverage.report]
show_missing = true
```

> `--strict-markers` 可防止拼错 marker 被静默忽略；`markers` 与 `conftest.py::pytest_configure` 二选一即可，
> 若同时存在需保持一致。此决定权归 Chief Architect / Backend Agent。

---

## 2. 前端 Vitest（**配置建议，需由 Frontend Agent 落盘**）

`frontend/package.json` 当前 `devDependencies` 仅含 TypeScript 与 `@types/*`，**不含 vitest**。
QA Agent 可写范围为 `frontend/tests/**`，**不改动** `frontend/package.json` 与 frontend 根配置文件，
故以建议形式交付；`vitest.config.ts` 应放在 **frontend 根目录**（放 `frontend/tests/` 下不会自动生效）。

建议新增 `devDependencies`：

| 包 | 版本建议 | 用途 |
| --- | --- | --- |
| `vitest` | `^2.1.x`（与 Node 22 兼容；最终版本由 Frontend 定） | 测试运行器 |
| `@vitest/coverage-v8` | 与 vitest 同版本 | 覆盖率 |
| `jsdom` | `^25.x` | DOM 环境（组件测试） |
| `@testing-library/react` | `^16.x` | 组件渲染与交互 |
| `@testing-library/jest-dom` | `^6.x` | DOM 断言 |

建议新增 `scripts`：

```json
"test": "vitest run",
"test:watch": "vitest",
"test:coverage": "vitest run --coverage"
```

建议 `frontend/vitest.config.ts` 片段：

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    setupFiles: ["tests/setup.ts"],
    coverage: { provider: "v8", reporter: ["text", "html"] },
  },
});
```

建议 `frontend/tests/setup.ts` 片段：

```ts
import "@testing-library/jest-dom/vitest";
// 真实联调地址一律来自环境变量，未配置则跳过，禁止硬编码假地址：
// export const API_BASE = process.env.QA_API_BASE_URL; // 未提供时用例须 skip
```

**边界**：前端真实联调（`TC-E2E-01`）必须用真实浏览器或真实 HTTP，
不得用组件级 mock 冒充；未授权/未启动时一律 `skip` 并标注。

---

## 3. 依赖需求清单（明确列出；本批次不安装）

| 端 | 依赖 | 版本 / 范围 | 用途 | 本机是否已安装 | 落盘 Owner |
| --- | --- | --- | --- | --- | --- |
| 后端 | `pytest` | `>=8.3,<9` | 测试运行器 | ❌ 否 | Backend / Architect（`pyproject.toml [test]` 已有声明） |
| 后端 | `pytest-asyncio` | `>=0.25,<1` | 异步用例 | ❌ 否 | 同上 |
| 后端 | `pytest-cov` | `>=6,<7` | 覆盖率 | ❌ 否 | 同上 |
| 后端 | `httpx` | `>=0.28,<1` | 真实 HTTP / API 测试客户端 | ❌ 否 | 已在主依赖声明 |
| 后端 | `pydantic[email]` | `>=2.10,<3` | 契约模型可导入 | ❌ 否 | 已在主依赖声明 |
| 后端 | `coverage` | 随 pytest-cov | 覆盖率数据 | ❌ 否 | 传递依赖 |
| 后端 | `ruff` / `mypy` | `[dev]` 已声明 | 静态检查（非测试执行前提） | ❌ 否 | Backend / Architect |
| 前端 | `vitest` | `^2.1.x` | 测试运行器 | ❌ 否 | Frontend Agent |
| 前端 | `@vitest/coverage-v8` | 与 vitest 同版 | 覆盖率 | ❌ 否 | Frontend Agent |
| 前端 | `jsdom` | `^25.x` | DOM 环境 | ❌ 否 | Frontend Agent |
| 前端 | `@testing-library/react` | `^16.x` | 组件测试 | ❌ 否 | Frontend Agent |
| 前端 | `@testing-library/jest-dom` | `^6.x` | DOM 断言 | ❌ 否 | Frontend Agent |
| 运行时 | `pnpm` | `12.18.0`（已在 `package.json` 声明） | 前端依赖管理 | — | DevOps / Frontend |
| 运行时 | Python | `3.13.14` | 后端与检查脚本 | ✅ 是 | — |
| 运行时 | Node | `v22.22.2` | 前端 | ✅ 是 | — |

> 真实探测命令与输出见 `TEST_REPORT.md` §6.1。
> **本批次不安装上述任何依赖，也不联网。**

---

## 4. 关于 QA-01「真实可运行，有 1 个以上可验证用例」

- 本批次**真实可运行且有真实输出**的是 `qa/check_api_contract.py`：
  `python qa/check_api_contract.py` → `RESULT: PASS`（17 项检查全部 PASS，退出码 0）。
- 它是**契约静态一致性门禁**（仅标准库，针对当前已冻结的契约文件），
  **不是产品测试**，不冒充任何 `TC-*` 用例通过，也不替代 `TC-API-01` 的运行时测试。
- pytest / Vitest 框架配置与 fixture 已备好，但因依赖未安装、业务实现未合并，**本批次未执行**；
  安装与执行属于后续批次（`INT-01/INT-02` 之后）。

---

## 5. 回归门禁

`QA-REG-01` 必须在 Codex 完成 `INT-01`（合并/契约对齐）与 `INT-02`（整体集成与真实启动验证）之后，
在 **MAIN 树**对合并后的完整系统执行；本批次**未执行、未放行**。
详见 `TEST_REPORT.md` §5 与 `qa/test_matrix.md` 的 `TC-REG-01` 规格。
