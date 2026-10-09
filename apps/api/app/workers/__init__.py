"""The analysis worker: a standalone process that turns queued songs into results.

``python -m app.workers`` runs it (see ``runner.py`` for the loop, ``pipeline.py`` for
one job). It is separate from ``app/api/``: it shares this service's settings, models
and services, and nothing about its lifecycle - it is started, stopped and scaled on
its own, and it holds no state a restart would lose.

Its dependencies are not the API's. The audio stack (librosa, soundfile, pretty_midi)
lives in the ``worker`` dependency group, because the API process never decodes audio::

    uv sync --project apps/api --group worker
    uv run --project apps/api --group worker --directory apps/api python -m app.workers

Those two lines are the whole deployment story for now; docs/analysis-worker.md has the
reasoning, the measured cost of each stage, and what happens on a crash.
"""
