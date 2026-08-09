import os

REDIS_URL = os.getenv("REDIS_URL")

# Optional celery setup — gracefully degrades if not installed
try:
    from celery import Celery

    celery_app = (
        Celery("insight", broker=REDIS_URL, backend=REDIS_URL)
        if REDIS_URL
        else Celery("insight", broker="memory://", backend="cache+memory://")
    )
    celery_app.conf.update(
        task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC"
    )
except ImportError:
    # Dummy for tests without celery
    class DummyCelery:
        def task(self, fn):
            # decorator returns fn itself
            return fn

        def delay(self, *a, **kw):
            pass

    celery_app = DummyCelery()


# Define task
def _save_job(job_id: str, payload: dict):
    try:
        from app.config import get_storage_path
        import json, pathlib

        d = get_storage_path() / "jobs"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{job_id}.json"
        with open(p, "w") as f:
            json.dump(payload, f, indent=2)
        # Also cache in redis if available
        try:
            from app.core.cache import set as cache_set

            cache_set(f"job:{job_id}", payload, ttl=600)
        except Exception:
            pass
    except Exception as e:
        import traceback

        traceback.print_exc()


if hasattr(celery_app, "task"):
    # Real celery task
    try:

        @celery_app.task(name="app.worker.run_chat_task")
        def run_chat_task(job_id: str, dataset_id: str, query: str, user_id: str = None):
            import asyncio
            from app.services.chat_service import process_query_v2

            # Update status running
            _save_job(
                job_id,
                {"job_id": job_id, "status": "running", "dataset_id": dataset_id, "query": query},
            )
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(process_query_v2(dataset_id, query))
                result["job_id"] = job_id
                result["status"] = "completed"
                _save_job(job_id, result)
                return result
            except Exception as e:
                import traceback

                traceback.print_exc()
                _save_job(job_id, {"job_id": job_id, "status": "failed", "error": str(e)[:500]})
                raise

    except Exception:
        # Fallback if decorator fails due to dummy
        def run_chat_task(job_id, dataset_id, query, user_id=None):
            import asyncio
            from app.services.chat_service import process_query_v2

            _save_job(job_id, {"job_id": job_id, "status": "running"})
            try:
                result = asyncio.run(process_query_v2(dataset_id, query))
                result["job_id"] = job_id
                result["status"] = "completed"
                _save_job(job_id, result)
                return result
            except Exception as e:
                _save_job(job_id, {"job_id": job_id, "status": "failed", "error": str(e)[:500]})
                raise

else:

    def run_chat_task(job_id, dataset_id, query, user_id=None):
        import asyncio
        from app.services.chat_service import process_query_v2

        _save_job(job_id, {"job_id": job_id, "status": "running"})
        try:
            result = asyncio.run(process_query_v2(dataset_id, query))
            result["job_id"] = job_id
            result["status"] = "completed"
            _save_job(job_id, result)
            return result
        except Exception as e:
            _save_job(job_id, {"job_id": job_id, "status": "failed", "error": str(e)[:500]})
            raise
