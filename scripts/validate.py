#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 skills.json 与仓库内 Skill 目录是否一致。供 CI 和本地提交前使用。

用法：
    python scripts/validate.py              # 未登记的目录只警告
    python scripts/validate.py --strict     # 未登记的目录也判失败（CI 用这个）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def read_frontmatter(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "SKILL.md 不是 UTF-8 编码"
    if not text.startswith("---"):
        return None, None, "SKILL.md 缺少 YAML frontmatter（需以 --- 开头）"
    end = text.find("\n---", 3)
    if end < 0:
        return None, None, "frontmatter 没有闭合的 ---"
    block = text[3:end]
    name = re.search(r"^name:\s*[\"']?([A-Za-z0-9_-]+)", block, re.M)
    desc = re.search(r"^description:\s*(\S.*)$", block, re.M)
    return (name.group(1) if name else None), (desc.group(1) if desc else None), None


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 Skill 仓库清单与目录结构")
    ap.add_argument("--root", default=str(ROOT), help="仓库根目录")
    ap.add_argument("--strict", action="store_true", help="未登记的 Skill 目录视为错误")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    manifest = root / "skills.json"

    if not manifest.is_file():
        print(f"[FAIL] 缺少 {manifest}")
        return 1
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] skills.json 不是合法 JSON：{exc}")
        return 1

    items = data.get("skills")
    if not isinstance(items, list) or not items:
        print("[FAIL] skills.json 必须包含非空数组 skills")
        return 1

    seen: set[str] = set()
    registered: set[Path] = set()
    enabled_count = 0

    for idx, item in enumerate(items):
        label = f"skills[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{label} 必须是对象")
            continue
        name, raw_path, enabled = item.get("name"), item.get("path"), item.get("enabled", True)

        if not isinstance(name, str) or not NAME_RE.match(name):
            errors.append(f"{label}.name 非法（需 kebab-case）：{name!r}")
            continue
        if name in seen:
            errors.append(f"{label}.name 重复：{name}")
        seen.add(name)
        if not isinstance(enabled, bool):
            errors.append(f"{label}.enabled 必须是 true/false")
        if enabled is True:
            enabled_count += 1
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{label}.path 不能为空")
            continue

        rel = Path(raw_path)
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"{label}.path 必须是不含 .. 的仓库内相对路径：{raw_path}")
            continue
        skill_dir = (root / rel).resolve()
        if not skill_dir.is_relative_to(root):
            errors.append(f"{label}.path 越出仓库范围：{raw_path}")
            continue
        registered.add(skill_dir)

        if not skill_dir.is_dir():
            errors.append(f"{label} 目录不存在：{raw_path}")
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"{label} 缺少 SKILL.md：{raw_path}")
            continue
        fm_name, desc, err = read_frontmatter(skill_md)
        if err:
            errors.append(f"{label} {err}：{raw_path}")
        if fm_name != name:
            errors.append(
                f"{label} 名称不一致：skills.json={name}，SKILL.md={fm_name}"
            )
        if not desc:
            errors.append(f"{label} SKILL.md 缺少 description：{raw_path}")

    skills_root = root / "skills"
    if skills_root.is_dir():
        for skill_md in sorted(skills_root.rglob("SKILL.md")):
            if skill_md.parent.resolve() not in registered:
                msg = f"目录 {skill_md.parent.relative_to(root)} 含 SKILL.md 但未登记进 skills.json"
                (errors if args.strict else warnings).append(msg)

    print(f"清单共 {len(items)} 个 Skill，启用 {enabled_count} 个，停用 {len(items) - enabled_count} 个")
    for msg in warnings:
        print("[WARN]", msg)
    for msg in errors:
        print("[FAIL]", msg)
    if errors:
        print(f"校验失败：{len(errors)} 个错误")
        return 1
    print("校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
