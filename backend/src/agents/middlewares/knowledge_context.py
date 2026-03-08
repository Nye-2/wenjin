"""Knowledge context middleware for injecting academic artifacts."""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class KnowledgeContextMiddleware(Middleware):
    """Middleware that injects existing academic artifacts.

    This middleware:
    1. Loads all artifacts from current workspace
    2. Builds a knowledge graph structure
    3. Injects into state for context
    """

    def __init__(self, artifact_service):
        """Initialize with artifact service.

        Args:
            artifact_service: Service for artifact CRUD operations
        """
        self.artifact_service = artifact_service

    def _build_knowledge_graph(self, artifacts: list) -> str:
        """Build knowledge graph context from artifacts."""
        if not artifacts:
            return ""

        # Group artifacts by type
        by_type: dict[str, list] = {}
        for artifact in artifacts:
            artifact_type = artifact.type
            if artifact_type not in by_type:
                by_type[artifact_type] = []
            by_type[artifact_type].append(artifact)

        # Build context
        context_parts = ["<knowledge_context>"]
        context_parts.append("Existing knowledge in your workspace:")

        type_labels = {
            "research_idea": "Research Ideas",
            "methodology": "Methodologies",
            "framework_outline": "Frameworks",
            "abstract": "Abstracts",
            "paper_draft": "Paper Drafts",
        }

        for artifact_type, items in by_type.items():
            label = type_labels.get(artifact_type, artifact_type.replace("_", " ").title())
            context_parts.append(f"\n### {label}")
            for item in items[:5]:  # Limit per type
                content = item.content
                if isinstance(content, dict):
                    title = content.get("title", "Untitled")
                    context_parts.append(f"- {title}")
                else:
                    context_parts.append(f"- {str(content)[:100]}...")

        context_parts.append("</knowledge_context>")
        return "\n".join(context_parts)

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Load and inject knowledge context."""
        workspace_id = state.workspace_id
        if not workspace_id:
            return state.model_dump()

        # Load artifacts
        artifacts = await self.artifact_service.list_by_workspace(workspace_id)

        # Build context
        knowledge_context = self._build_knowledge_graph(artifacts)
        return {
            **state.model_dump(),
            "_knowledge_context": knowledge_context,
        }
