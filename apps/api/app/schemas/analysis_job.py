"""Response contract for an analysis job.

The API's JSON shape for ``public.analysis_jobs``. It mirrors the table rather
than the dataclass so that a column added for internal bookkeeping does not leak
into the payload by accident, and it leaves ``user_id`` out because the caller
already knows who they are.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.models.analysis_job import TERMINAL_STATUSES
from pydantic import BaseModel, ConfigDict


class AnalysisJobOut(BaseModel):
    """One analysis job as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    song_id: UUID
    status: str
    pipeline_version: str
    attempts: int
    compute_seconds: Decimal | None = None
    error_code: str | None = None
    error_message: str | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    @property
    def is_terminal(self) -> bool:
        """True once the job can no longer change state.

        Failed and canceled jobs are terminal and never billable; succeeded is
        terminal and billable once.
        """
        return self.status in TERMINAL_STATUSES

    @property
    def is_billable(self) -> bool:
        """True for the one transition that counts as a billable unit."""
        return self.status == "succeeded"
