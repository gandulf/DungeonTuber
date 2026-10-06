"""The user of the request that is being handled (set by the auth dependency, read where data differs per user)."""
from contextvars import ContextVar

current_user_var: ContextVar[str | None] = ContextVar("current_user", default=None)
