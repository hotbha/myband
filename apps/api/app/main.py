"""The FastAPI application.

``uvicorn app.main:app`` imports ``app`` from here, which builds the application
once through ``create_app()``. Tests import the same factory, so the app under test
is the app that runs.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import handle_problem, handle_validation_error
from app.api.routes import health, jobs, songs, uploads
from app.core.config import get_settings
from app.core.problems import ApiProblem


def create_app() -> FastAPI:
    """Build the application: CORS, error shape, routes."""
    settings = get_settings()

    app = FastAPI(
        title="MyBand.video API",
        version=settings.pipeline_version,
        description="Music intelligence for uploaded audio: BPM, key, chords, MIDI, song sections.",
    )

    # The browser calls this API directly with the user's Supabase token, so CORS
    # is the only thing standing between a random page and an authenticated
    # request. Origins come from configuration; credentials are not allowed
    # because the token travels in the Authorization header, not a cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.add_exception_handler(ApiProblem, handle_problem)
    app.add_exception_handler(RequestValidationError, handle_validation_error)

    app.include_router(health.router)
    app.include_router(uploads.router)
    app.include_router(songs.router)
    app.include_router(jobs.router)

    return app


app = create_app()
