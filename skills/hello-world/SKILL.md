---
name: hello-world
description: 最小 Skill 模板，用于演示仓库目录结构与 SKILL.md 写法。默认在 skills.json 中停用，不会被安装。
---

# Hello World（模板）

复制本目录即可创建新 Skill：

1. 改目录名为 `skills/<新名字>/`。
2. 把 frontmatter 的 `name` 改为新名字，`description` 写清楚「什么时候该用这个技能」。
3. 正文写工作流程、约束、脚本用法。
4. 在仓库根目录 `skills.json` 追加一条并把 `enabled` 设为 `true`。
5. 运行 `python scripts/validate.py --strict` 校验后提交。

可选子目录：`scripts/`（可执行脚本）、`references/`（参考资料）、`assets/`（模板与资源）。
