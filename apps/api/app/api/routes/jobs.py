"""Job routes: the state of one analysis.

This phase only reads. The dispatcher and the RunPod webhook will add transitions
to ``app/services/queue.py``; today the UI polls this to see a job move from
``queued`` once a worker exists.
"""

from http import HTTPStatus
from uuid import UUID

from app.api.deps import CurrentUserId
from app.core.db import connect
from app.core.problems import ApiProblem, ErrorCode
from app.models import analysis_job
from app.schemas.analysis_job import AnalysisJobOut
from fastapi import APIRouter

router = APIRouter(tags=["analysis"])


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, user_id: CurrentUserId) -> AnalysisJobOut:
    """One analysis job, if it is the caller's."""
    with connect() as conn:
        found = analysis_job.get(conn, job_id)
        if found is None or found.user_id != user_id:
            raise ApiProblem(HTTPStatus.NOT_FOUND, ErrorCode.JOB_NOT_FOUND, "No such analysis job.")

    return AnalysisJobOut.model_validate(found)
