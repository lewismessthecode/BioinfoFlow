from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_ui.contracts import (
    AgentUiBootstrap,
    StarterPromptView,
    default_ui_capabilities,
)
from app.services.agent_ui.execution_targets import execution_target_catalog


async def build_agent_ui_bootstrap(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    project_id: str | None,
    locale: str,
) -> AgentUiBootstrap:
    targets, default_scope = await execution_target_catalog(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        project_id=project_id,
    )
    chinese = locale.lower().startswith("zh")
    return AgentUiBootstrap(
        capabilities=default_ui_capabilities(),
        execution_targets=targets,
        execution_scope=default_scope,
        starter_prompts=_starter_prompts(project_id=project_id, chinese=chinese),
        composer_hint=(
            "输入 / 选择技能，或添加文件、工作流和运行记录作为上下文"
            if chinese
            else "Type / to choose a skill, or add files, workflows, and runs as context"
        ),
    )


def _starter_prompts(
    *, project_id: str | None, chinese: bool
) -> list[StarterPromptView]:
    if project_id and chinese:
        return [
            StarterPromptView(
                id="check-workflow",
                title="检查并运行工作流",
                prompt="检查当前项目的工作流和输入，确认无误后运行它。",
                icon="check",
            ),
            StarterPromptView(
                id="explain-inputs",
                title="解释项目输入",
                prompt="解释当前项目可用的工作流输入，以及应该如何准备数据。",
                icon="explain",
            ),
            StarterPromptView(
                id="review-run",
                title="复盘最近一次运行",
                prompt="查看当前项目最近一次运行，概括结果并指出需要处理的问题。",
                icon="review",
            ),
        ]
    if project_id:
        return [
            StarterPromptView(
                id="check-workflow",
                title="Check and run the workflow",
                prompt="Inspect this project's workflow and inputs, then run it when everything is ready.",
                icon="check",
            ),
            StarterPromptView(
                id="explain-inputs",
                title="Explain the project inputs",
                prompt="Explain the workflow inputs available in this project and how I should prepare the data.",
                icon="explain",
            ),
            StarterPromptView(
                id="review-run",
                title="Review the latest run",
                prompt="Review the latest run in this project, summarize the result, and identify anything that needs attention.",
                icon="review",
            ),
        ]
    if chinese:
        return [
            StarterPromptView(
                id="inspect-workspace",
                title="检查工作区",
                prompt="检查当前工作区，告诉我有哪些项目、工作流和最近的运行记录。",
                icon="check",
            ),
            StarterPromptView(
                id="plan-analysis",
                title="规划一次分析",
                prompt="帮我规划一次新的生物信息分析，并列出开始前需要准备的内容。",
                icon="explain",
            ),
            StarterPromptView(
                id="review-failures",
                title="检查失败运行",
                prompt="查找最近失败的运行，解释最可能的原因并给出下一步建议。",
                icon="review",
            ),
        ]
    return [
        StarterPromptView(
            id="inspect-workspace",
            title="Inspect the workspace",
            prompt="Inspect the current workspace and summarize its projects, workflows, and recent runs.",
            icon="check",
        ),
        StarterPromptView(
            id="plan-analysis",
            title="Plan an analysis",
            prompt="Help me plan a new bioinformatics analysis and list what I need before starting.",
            icon="explain",
        ),
        StarterPromptView(
            id="review-failures",
            title="Review failed runs",
            prompt="Find recent failed runs, explain the most likely causes, and recommend next steps.",
            icon="review",
        ),
    ]


__all__ = ["build_agent_ui_bootstrap"]
