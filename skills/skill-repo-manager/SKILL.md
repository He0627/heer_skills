---
name: skill-repo-manager
description: 维护个人 Skill 代码仓库：新增技能、登记 skills.json、校验结构、提交与发布。当用户要新建、修改、停用、删除某个 Skill，或准备把技能变更提交/合并到仓库时使用。
---

# Skill 仓库管理

本技能服务于一个「一个仓库、多个 Skill、清单驱动」的开发仓库。

## 仓库约定

- `skills.json` 是唯一清单：每个 Skill 一条，包含 `name`、`path`、`enabled`。
- 每个 Skill 独占 `skills/<name>/` 目录，目录内必须有 `SKILL.md`（含 `name` 与 `description` 的 YAML frontmatter）。
- `scripts/validate.py` 校验清单与目录一致性，`scripts/sync.py` 按清单把技能同步到本机 WorkBuddy 技能目录。
- CI（`.github/workflows/validate.yml`）在 push / PR 时自动跑校验。

## 新增一个 Skill

1. 复制 `skills/hello-world/` 为 `skills/<新名字>/`，改写 `SKILL.md`（frontmatter 的 `name` 必须与目录名、清单里的 `name` 一致）。
2. 在 `skills.json` 的 `skills` 数组追加一条：`{"name": "<新名字>", "path": "skills/<新名字>", "enabled": true, "description": "..."}`。
3. 本地运行 `python scripts/validate.py --strict` 确认通过。
4. 提交并合并到 main；同步器下一次运行会自动把它安装到 WorkBuddy。

## 停用 / 删除

- 停用：把 `enabled` 改为 `false`，同步器不再更新它（默认不卸载已安装副本）。
- 删除：从清单移除条目，并删除目录。需要同步器一并卸载本机副本时，用 `--prune` 显式运行（卸载前会备份）。

## 约束

- 不要绕过 `skills.json` 直接往本机技能目录里改文件：本机目录由同步器托管，改动会在下次同步被覆盖。
- 修改技能内容后必须提交到仓库，否则会被下次 pull 覆盖。
- 私有仓库不要把 token 写进 URL，凭据交给 Git Credential Manager 或 SSH key。
