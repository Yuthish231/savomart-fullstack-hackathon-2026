# Importing a task module registers its handlers with the worker.
from app.jobs.tasks import area_report, demo, property_eval  # noqa: F401
