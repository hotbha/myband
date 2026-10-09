"""Exception handlers: every failure leaves as the same JSON shape.

``ApiProblem`` already carries its status, code and message, so handling it is
bookkeeping. Request validation is the interesting one: FastAPI's default 422 body
is a list of Pydantic issues, which would force a client to parse two shapes for
the same class of failure, so it is normalized into the one shape here.
"""

from http import HTTPStatus

from app.core.problems import ApiProblem, ErrorCode
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def handle_problem(_request: Request, error: ApiProblem) -> JSONResponse:
    """Render an :class:`ApiProblem` as it describes itself."""
    return JSONResponse(status_code=int(error.status), content=error.body())


async def handle_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    """Normalize a request-validation failure into ``invalid_request``."""
    return JSONResponse(
        status_code=int(HTTPStatus.UNPROCESSABLE_ENTITY),
        content={
            "detail": {
                "code": ErrorCode.INVALID_REQUEST.value,
                "message": _first_issue(error),
            }
        },
    )


def _first_issue(error: RequestValidationError) -> str:
    """Read the first validation issue as a sentence naming its field."""
    issues = error.errors()
    if not issues:
        return "The request is not valid."

    first = issues[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = str(first.get("msg", "is not valid"))

    return f"{location}: {message}" if location else message
