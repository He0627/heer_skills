#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 skills.json 把仓库内的 Skill 同步到本机 WorkBuddy 技能目录。

此脚本随仓库一起版本化，因此同步逻辑本身也能通过 merge 升级。
通常由工作区的 skill-sync/sync_skills.py（负责 clone / pull）调用，也可单独运行：

    python scripts/sync.py --skills-dir ~/.workbuddy/skills --mode copy --changed
    python scripts/sync.py --mode link --dry-run --json

安全策略：
- 只同步 enabled=true 的技能；停用或从清单移除的条目默认只报告，不卸载。
- 需要同步器一并卸载时，显式加 --prune（卸载前把旧副本移到备份目录）。
- copy 模式覆盖前自动备份；link 模式只管理自己创建过的目录联接，遇到陌生目录会跳过。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store", "*.pyc")


def exists(path: Path) -> bool:
    return os.path.lexists(str(path))


def remove_link(dst: Path) -> None:
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/d", "/c", "rmdir", str(dst)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            raise RuntimeError(f"无法移除目录联接 {dst}：{(r.stdout or r.stderr).strip()}")
    else:
        dst.unlink()


def create_link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"创建目录联接失败（可改用 --mode copy）：{(r.stdout or r.stderr).strip()}"
            )
    else:
        dst.symlink_to(src, target_is_directory=True)


def backup(dst: Path, backup_dir: Path):
    """移除旧版本并留档；返回备份路径，联接则返回 None。"""
    if dst.is_symlink():
        remove_link(dst)
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{dst.name}-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.move(str(dst), str(target))
    return target


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def finish(actions: dict, messages: list[str], as_json: bool, error: str | None = None) -> int:
    payload = {"ok": error is None, "actions": actions, "messages": messages}
    if error:
        payload["error"] = error
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for msg in messages:
            print(msg)
        if error:
            print("[FAIL]", error)
        print("结果：" + (", ".join(f"{k}={v}" for k, v in actions.items()) or "无技能需要处理"))
    return 0 if error is None else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="按 skills.json 同步 Skill 到 WorkBuddy 技能目录")
    ap.add_argument("--repo-root", default=str(ROOT), help="仓库根目录（含 skills.json）")
    ap.add_argument("--manifest", default="skills.json", help="清单文件名，相对仓库根目录")
    ap.add_argument("--skills-dir", default=str(Path.home() / ".workbuddy" / "skills"))
    ap.add_argument("--mode", choices=["copy", "link"], default="copy")
    ap.add_argument("--changed", action="store_true", help="仓库有更新，需重新同步")
    ap.add_argument("--force", action="store_true", help="无更新也强制重新复制")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不改动文件")
    ap.add_argument("--prune", action="store_true", help="卸载清单中已停用/移除的技能")
    ap.add_argument("--state-file", default="")
    ap.add_argument("--backup-dir", default="")
    ap.add_argument("--json", action="store_true", help="只输出一行 JSON，供调用方解析")
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    skills_dir = Path(args.skills_dir).expanduser()
    state_file = Path(args.state_file).expanduser() if args.state_file else Path.home() / ".workbuddy" / "skill-sync-state.json"
    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else Path.home() / ".workbuddy" / "skill-sync-backups"

    actions: dict[str, str] = {}
    messages: list[str] = []

    try:
        data = json.loads((root / args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        return finish(actions, messages, args.json, f"读取 {args.manifest} 失败：{exc}")

    items = data.get("skills")
    if not isinstance(items, list):
        return finish(actions, messages, args.json, f"{args.manifest} 缺少数组字段 skills")

    state = load_state(state_file)
    links: dict = state.setdefault("links", {})
    installed: dict = state.setdefault("installed", {})
    listed: set[str] = set()

    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = item["name"]
        if item.get("enabled", True) is not True:
            actions[name] = "disabled"
            continue
        listed.add(name)
        raw_path = item.get("path", "")
        src = (root / raw_path).resolve()
        dst = skills_dir / name

        if not (src / "SKILL.md").is_file():
            actions[name] = "invalid"
            messages.append(f"跳过 {name}：{src} 里没有 SKILL.md，请先运行 validate.py")
            continue

        if args.mode == "link":
            if exists(dst):
                if links.get(name) == str(src):
                    actions[name] = "linked"
                    continue
                if links.get(name):
                    if args.dry_run:
                        actions[name] = "would-relink"
                        continue
                    remove_link(dst)
                    messages.append(f"已摘除旧联接 {name}")
                else:
                    actions[name] = "conflict"
                    messages.append(f"跳过 {name}：{dst} 已存在且不是本工具创建的联接，请手动处理")
                    continue
            if args.dry_run:
                actions[name] = "would-link"
                continue
            try:
                create_link(src, dst)
            except RuntimeError as exc:
                actions[name] = "failed"
                messages.append(str(exc))
                continue
            links[name] = str(src)
            installed[name] = {"mode": "link", "source": str(src)}
            messages.append(f"已创建目录联接 {name} -> {src}")
            actions[name] = "linked"
            continue

        need = args.changed or args.force or not exists(dst)
        if not need:
            actions[name] = "unchanged"
            continue
        if args.dry_run:
            actions[name] = "would-install" if not exists(dst) else "would-update"
            continue
        if exists(dst):
            saved = backup(dst, backup_dir)
            messages.append(
                f"已备份旧版 {name} -> {saved}" if saved else f"已移除旧联接 {name}"
            )
        skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=IGNORE)
        links.pop(name, None)
        installed[name] = {"mode": "copy", "source": str(src)}
        messages.append(f"已同步技能 {name} -> {dst}")
        actions[name] = "updated"

    for name in list(installed):
        if name in listed:
            continue
        if not args.prune:
            actions.setdefault(name, "retired-or-disabled")
            continue
        dst = skills_dir / name
        if args.dry_run:
            actions[name] = "would-prune"
            continue
        if exists(dst):
            saved = backup(dst, backup_dir)
            messages.append(
                f"已卸载并备份 {name} -> {saved}" if saved else f"已卸载联接 {name}"
            )
        installed.pop(name, None)
        links.pop(name, None)
        actions[name] = "pruned"

    if not args.dry_run:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return finish(actions, messages, args.json)


if __name__ == "__main__":
    sys.exit(main())
