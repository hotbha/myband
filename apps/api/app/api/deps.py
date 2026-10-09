"""Shared FastAPI dependencies.

Two of them, plus a note on what is deliberately *not* one.

``CurrentUserId`` proves who is calling. ``StorageDep`` hands a route the object
store, so a test can swap in a fake.

There is no connection dependency: ``core.db.connect`` is a context manager that
commits on a clean exit and rolls back when the block raises, and FastAPI runs a
dependency's exit code *after* the response has been sent. A route that opened its
transaction that way would answer "created" before the commit had happened, and a
commit failure would be invisible to the caller. Each route therefore opens its
own transaction and returns afterwards::

    with connect() as conn:
        ...
    return ...
"""

from typing import Annotated
from uuid import UUID

from app.core.auth import bearer_token, verify_access_token
from app.services.storage import ObjectStore, get_object_store
from fastapi import Depends, Header


def current_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    """The signed-in user, from the request's bearer token."""
    return verify_access_token(bearer_token(authorization))


# The `sub` of a verified Supabase access token.
CurrentUserId = Annotated[UUID, Depends(current_user_id)]

# Where uploaded audio lives.
StorageDep = Annotated[ObjectStore, Depends(get_object_store)]
