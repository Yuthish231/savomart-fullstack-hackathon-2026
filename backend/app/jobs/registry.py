from collections.abc import Callable

from app.jobs.queue import JobContext

Handler = Callable[[JobContext], None]
_HANDLERS: dict[str, Handler] = {}


def task(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn

    return deco


def get_handler(job_type: str) -> Handler | None:
    return _HANDLERS.get(job_type)
