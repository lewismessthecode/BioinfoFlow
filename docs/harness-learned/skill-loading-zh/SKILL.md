---
name: skill-loading-zh
description: |
  按需知识加载的两层注入机制。适用于:
  (1) 设计 SKILL.md 格式、技能文件系统
  (2) 实现 SkillLoader、技能发现与加载
  (3) 优化系统提示的 token 预算
  (4) 理解 Layer 1(系统提示) + Layer 2(tool_result) 两层架构
  关键词: skill, 技能, SKILL.md, load_skill, 知识注入, frontmatter, SkillLoader, 按需加载
---

# 按需知识加载

用到什么知识，临时加载什么知识。通过 tool_result 注入，不塞 system prompt。

## 问题

全部领域知识塞进系统提示太浪费 — 10 个技能 x 2000 token = 20,000 token，大部分跟当前任务无关。

## 两层注入架构

```
System prompt (Layer 1 -- 始终存在):
+--------------------------------------+
| You are a coding agent.              |
| Skills available:                    |
|   - git: Git workflow helpers        |  ~100 tokens/skill
|   - test: Testing best practices     |
+--------------------------------------+

当模型调用 load_skill("git"):
+--------------------------------------+
| tool_result (Layer 2 -- 按需加载):   |
| <skill name="git">                   |
|   Full git workflow instructions...  |  ~2000 tokens
|   Step 1: ...                        |
| </skill>                             |
+--------------------------------------+
```

第一层: 名称 + 描述 (低成本)。第二层: 完整内容 (按需)。

## SKILL.md 格式

每个技能是一个目录，包含 `SKILL.md` 文件:

```
skills/
  pdf/
    SKILL.md       # YAML frontmatter + markdown body
  code-review/
    SKILL.md
```

YAML frontmatter 包含 `name` 和 `description`:

```yaml
---
name: code-review
description: |
  Code review checklist and best practices.
  Keywords: review, PR, quality, lint
---
```

`description` 中的关键词帮助模型判断何时加载该技能。

## SkillLoader 实现

```python
class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}
        for f in sorted(skills_dir.rglob("SKILL.md")):
            text = f.read_text()
            meta, body = self._parse_frontmatter(text)
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body}

    def get_descriptions(self) -> str:
        """Layer 1: 写入系统提示，每个技能 ~100 tokens"""
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "")
            lines.append(f"  - {name}: {desc}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        """Layer 2: 通过 tool_result 按需注入"""
        skill = self.skills.get(name)
        if not skill:
            return f"Error: Unknown skill '{name}'."
        return f'<skill name="{name}">\n{skill["body"]}\n</skill>'
```

## 集成到系统

```python
# Layer 1: 系统提示中列出技能名称
SYSTEM = f"""You are a coding agent at {WORKDIR}.
Skills available:
{SKILL_LOADER.get_descriptions()}"""

# Layer 2: dispatch map 中的普通工具
TOOL_HANDLERS = {
    # ...base tools...
    "load_skill": lambda **kw: SKILL_LOADER.get_content(kw["name"]),
}
```

## 最佳实践

1. **description 包含触发关键词**: 模型靠描述判断何时加载
2. **每个技能 1500-3000 tokens**: 自包含，不依赖其他技能
3. **用目录组织**: `skills/git/SKILL.md` 而非扁平文件
4. **Layer 1 成本极低**: 所有技能的描述加起来不超过几百 token
5. **Layer 2 只在需要时加载**: 避免预加载，信任模型判断

## 反模式

| 模式 | 问题 | 正确做法 |
|------|------|----------|
| 全部塞系统提示 | 上下文膨胀 | 两层注入 |
| 描述太短 | 模型不知道何时加载 | 包含关键词和使用场景 |
| 技能互相依赖 | 加载一个需要加载多个 | 每个技能自包含 |
| 技能太大 | 单个技能吃掉大量上下文 | 控制在 3000 tokens 内 |
