"""Generation record service for tracking skill executions."""

from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import GenerationRecord


class GenerationService:
    """Service for tracking skill executions."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        workspace_id: str,
        skill_name: str,
        thread_id: str | None = None,
        model_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        duration_ms: int | None = None,
        token_usage: dict | None = None,
        status: str = "success",
        error_message: str | None = None,
        metadata: dict | None = None,
    ) -> GenerationRecord:
        """Create a generation record.

        Args:
            workspace_id: Workspace ID
            skill_name: Name of the skill executed
            thread_id: LangGraph thread ID
            model_name: Model used for generation
            input_summary: Summary of input
            output_summary: Summary of output
            duration_ms: Execution time in milliseconds
            token_usage: Token usage breakdown
            status: Execution status
            error_message: Error message if failed
            metadata: Additional metadata

        Returns:
            Created generation record
        """
        record = GenerationRecord(
            workspace_id=workspace_id,
            thread_id=thread_id,
            skill_name=skill_name,
            model_name=model_name,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            token_usage=token_usage,
            status=status,
            error_message=error_message,
            extra_data=metadata or {},
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get(self, record_id: str) -> GenerationRecord | None:
        """Get generation record by ID.

        Args:
            record_id: Record ID

        Returns:
            Record if found, None otherwise
        """
        result = await self.db.execute(
            select(GenerationRecord).where(GenerationRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecord]:
        """List generation records for a workspace.

        Args:
            workspace_id: Workspace ID
            skill_name: Filter by skill name
            status: Filter by status
            since: Only records after this datetime
            limit: Maximum records to return

        Returns:
            List of generation records
        """
        conditions = [GenerationRecord.workspace_id == workspace_id]

        if skill_name:
            conditions.append(GenerationRecord.skill_name == skill_name)
        if status:
            conditions.append(GenerationRecord.status == status)
        if since:
            conditions.append(GenerationRecord.created_at >= since)

        result = await self.db.execute(
            select(GenerationRecord)
            .where(and_(*conditions))
            .order_by(GenerationRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecord]:
        """List generation records for a thread.

        Args:
            thread_id: Thread ID

        Returns:
            List of generation records
        """
        result = await self.db.execute(
            select(GenerationRecord)
            .where(GenerationRecord.thread_id == thread_id)
            .order_by(GenerationRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_usage_stats(
        self,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict:
        """Get usage statistics for a workspace.

        Args:
            workspace_id: Workspace ID
            since: Only count records after this datetime

        Returns:
            Usage statistics dictionary
        """
        conditions = [GenerationRecord.workspace_id == workspace_id]
        if since:
            conditions.append(GenerationRecord.created_at >= since)

        records = await self.db.execute(
            select(GenerationRecord).where(and_(*conditions))
        )
        records_list = list(records.scalars().all())

        total_tokens = sum(r.total_tokens for r in records_list)
        total_input_tokens = sum(r.input_tokens for r in records_list)
        total_output_tokens = sum(r.output_tokens for r in records_list)
        total_duration_ms = sum(r.duration_ms or 0 for r in records_list)

        skill_counts = {}
        for r in records_list:
            skill_counts[r.skill_name] = skill_counts.get(r.skill_name, 0) + 1

        status_counts = {}
        for r in records_list:
            status_counts[r.status] = status_counts.get(r.status, 0) + 1

        return {
            "total_executions": len(records_list),
            "successful_executions": status_counts.get("success", 0),
            "failed_executions": status_counts.get("failed", 0),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_duration_ms": total_duration_ms,
            "skill_breakdown": skill_counts,
            "status_breakdown": status_counts,
        }

    async def cleanup_old_records(
        self,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        """Clean up old generation records.

        Args:
            days_old: Delete records older than this many days
            workspace_id: Only delete for this workspace (optional)

        Returns:
            Number of records deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        conditions = [GenerationRecord.created_at < cutoff]
        if workspace_id:
            conditions.append(GenerationRecord.workspace_id == workspace_id)

        result = await self.db.execute(
            select(GenerationRecord).where(and_(*conditions))
        )
        records_to_delete = result.scalars().all()

        count = 0
        for record in records_to_delete:
            await self.db.delete(record)
            count += 1

        await self.db.commit()
        return count
