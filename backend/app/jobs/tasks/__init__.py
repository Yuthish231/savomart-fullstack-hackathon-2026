# Importing a task module registers its handlers with the worker.
from app.jobs.tasks import area_report, demo  # noqa: F401
