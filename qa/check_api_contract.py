#!/usr/bin/env python3
"""QA-01 契约一致性检查（仅使用 Python 标准库）。

针对当前**已冻结**的契约文件做静态一致性校验：
  * 解析 ``API_CONTRACTS.md`` 的 §2 枚举表与 §4 端点登记表；
  * 以 ``ast`` 解析 ``backend/app/contracts/enums.py`` 中的 StrEnum 字符串值；
  * 逐项输出 PASS/FAIL 明细，给出汇总与退出码（全部通过返回 0）。

边界（如实声明）：
  * 本脚本 **不是产品测试**，不替代 ``TC-API-01`` 的运行时 schema/错误码测试；
  * 不依赖 pytest / pydantic / 任何业务实现代码；
  * 不联网、不连数据库、不调用外部 API、不启动服务、不读取未授权凭据。

运行（在 worktree 根目录）：
    python qa/check_api_contract.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_MD = ROOT / "API_CONTRACTS.md"
ENUMS_PY = ROOT / "backend" / "app" / "contracts" / "enums.py"

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# (检查项名称, 是否通过, 明细)
Check = tuple[str, bool, str]


def _section(text: str, heading: str) -> str:
    """截取 ``## <heading>`` 起到下一个二级标题之前的正文。"""
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("## ") and heading in line:
            start = idx + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].strip().startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end])


def parse_doc_enums(api_text: str) -> dict[str, list[str]]:
    """解析 §2 枚举表：``| `Name` | `v1`, `v2` |`` -> ``{Name: [v1, v2]}``。"""
    result: dict[str, list[str]] = {}
    for line in _section(api_text, "2. 枚举").splitlines():
        match = re.match(
            r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`\s*\|\s*(.*?)\s*\|\s*$", line
        )
        if not match:
            continue
        values = re.findall(r"`([^`]+)`", match.group(2))
        if values:
            result[match.group(1)] = values
    return result


def parse_code_enums(enums_text: str) -> dict[str, list[str]]:
    """以 AST 解析 enums.py 中每个类里的字符串常量赋值（枚举成员值）。"""
    result: dict[str, list[str]] = {}
    tree = ast.parse(enums_text, filename=str(ENUMS_PY))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        values = [
            item.value.value
            for item in node.body
            if isinstance(item, ast.Assign)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ]
        if values:
            result[node.name] = values
    return result


def parse_endpoints(api_text: str) -> list[tuple[list[str], str, str]]:
    """解析 §4 端点表第一列，返回 ``(方法列表, 路径, 原始单元格)``。

    支持 ``GET /path`` 与合并写法 ``GET/POST /path``、``GET/PATCH/DELETE /path``。
    """
    rows: list[tuple[list[str], str, str]] = []
    for line in _section(api_text, "4. 端点").splitlines():
        match = re.match(r"^\|\s*`([^`]+)`\s*\|", line)
        if not match:
            continue
        cell = match.group(1).strip()
        if not re.match(r"^[A-Z]+(?:/[A-Z]+)*\s+/", cell):
            continue
        methods_part, path = cell.split(None, 1)
        rows.append((methods_part.split("/"), path.strip(), cell))
    return rows


def _report(checks: list[Check]) -> int:
    print("=== AI Learning Memory OS 契约一致性检查 (qa/check_api_contract.py) ===")
    print(f"ROOT={ROOT}")
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")
    passed = sum(1 for _, ok, _ in checks if ok)
    failed = len(checks) - passed
    print(f"SUMMARY: PASS={passed} FAIL={failed} TOTAL={len(checks)}")
    print(f"RESULT: {'PASS' if failed == 0 else 'FAIL'}")
    return 0 if failed == 0 else 1


def main() -> int:
    checks: list[Check] = []

    # 1. 契约文件存在且非空
    api_ok = API_MD.is_file() and API_MD.stat().st_size > 0
    enums_ok = ENUMS_PY.is_file() and ENUMS_PY.stat().st_size > 0
    present = api_ok and enums_ok
    checks.append((
        "契约文件存在且非空",
        present,
        f"API_CONTRACTS.md={'ok' if api_ok else 'missing/empty'}, "
        f"enums.py={'ok' if enums_ok else 'missing/empty'}",
    ))
    if not present:
        return _report(checks)

    api_text = API_MD.read_text(encoding="utf-8")
    enums_text = ENUMS_PY.read_text(encoding="utf-8")

    # 2~3. 两侧枚举解析
    doc_enums = parse_doc_enums(api_text)
    code_enums = parse_code_enums(enums_text)
    checks.append(("枚举表解析(API §2)", bool(doc_enums), f"解析到 {len(doc_enums)} 个枚举"))
    checks.append(("枚举类解析(enums.py)", bool(code_enums), f"解析到 {len(code_enums)} 个类"))

    # 4. 名称集合一致
    doc_names, code_names = set(doc_enums), set(code_enums)
    only_doc = sorted(doc_names - code_names)
    only_code = sorted(code_names - doc_names)
    name_ok = bool(doc_names) and doc_names == code_names
    checks.append((
        "枚举名称集合一致",
        name_ok,
        f"doc={len(doc_names)} code={len(code_names)} "
        f"only_in_doc={only_doc or '[]'} only_in_code={only_code or '[]'}",
    ))

    # 5. 逐枚举值集合一致（每项单独一行明细）
    for name in sorted(doc_names | code_names):
        d = set(doc_enums.get(name, []))
        c = set(code_enums.get(name, []))
        missing = sorted(d - c)   # 文档登记、但 enums.py 缺失
        extra = sorted(c - d)     # enums.py 存在、但文档未登记
        ok = bool(d) and d == c
        checks.append((
            f"枚举值一致 {name}",
            ok,
            f"doc={sorted(d)} code={sorted(c)} "
            f"missing_in_code={missing or '[]'} extra_in_code={extra or '[]'}",
        ))

    # 6. 端点表解析
    endpoints = parse_endpoints(api_text)
    expanded = sum(len(methods) for methods, _, _ in endpoints)
    checks.append((
        "端点登记解析(API §4)",
        bool(endpoints),
        f"登记行={len(endpoints)} 展开(方法+路径)={expanded}",
    ))

    # 7. 端点登记格式校验（方法合法、路径以 / 开头）
    bad = []
    for methods, path, cell in endpoints:
        illegal = [m for m in methods if m not in ALLOWED_METHODS]
        if illegal or not path.startswith("/"):
            bad.append(
                f"{cell} (非法方法={illegal or '[]'}, path以/开头={path.startswith('/')})"
            )
    checks.append((
        "端点格式校验",
        bool(endpoints) and not bad,
        f"合法方法集={sorted(ALLOWED_METHODS)}; 不合规={bad or '[]'}",
    ))

    return _report(checks)


if __name__ == "__main__":
    sys.exit(main())
