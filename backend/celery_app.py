from celery import Celery
from backend.config import settings

celery_app = Celery(
    "assessment_generator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "backend.workers.assessment_worker",
        "backend.workers.evaluation_worker",
    ],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.task_ignore_result = True
celery_app.conf.broker_transport_options = {
    "visibility_timeout": settings.celery_visibility_timeout_seconds,
}
celery_app.conf.result_backend_transport_options = {
    "visibility_timeout": settings.celery_visibility_timeout_seconds,
}
celery_app.conf.visibility_timeout = settings.celery_visibility_timeout_seconds
