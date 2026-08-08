from backend.celery_app import celery_app
from backend.config import settings


def test_redis_visibility_timeout_is_configured_consistently():
    timeout = settings.celery_visibility_timeout_seconds

    assert timeout == 900
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == timeout
    assert (
        celery_app.conf.result_backend_transport_options["visibility_timeout"]
        == timeout
    )
    assert celery_app.conf.visibility_timeout == timeout
