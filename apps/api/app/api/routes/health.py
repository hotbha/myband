"""Liveness.

Deliberately shallow: it answers whether this process is up and serving, not
whether the database or R2 are reachable. A readiness check that touches
dependencies belongs with the deployment that needs it, not in the request path
of every client.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ops"])


class HealthOut(BaseModel):
    """What ``GET /health`` reports."""

    status: str


@router.get("/health")
def health() -> HealthOut:
    return HealthOut(status="ok")
