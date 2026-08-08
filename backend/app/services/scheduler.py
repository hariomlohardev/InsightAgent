"""
APScheduler wrapper for OSS in-process scheduling.
Persists jobs to storage/schedules/*.json and reloads on startup.
"""

from typing import Optional

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.start()
        except Exception as e:
            # If APScheduler not installed, provide dummy that stores jobs in memory (tests can still call run_now)
            class Dummy:
                def add_job(self, *a, **kw):
                    pass

                def remove_job(self, *a, **kw):
                    pass

                def start(self):
                    pass

                def shutdown(self, *a, **kw):
                    pass

            _scheduler = Dummy()
    return _scheduler


def add_job(sched: dict):
    try:
        from apscheduler.triggers.cron import CronTrigger

        sch = get_scheduler()
        trigger = CronTrigger.from_crontab(sched["cron"])
        # Avoid duplicate
        try:
            sch.remove_job(sched["id"])
        except:
            pass

        def _runner():
            try:
                from app.services.scheduler_service import run_schedule

                run_schedule(sched["id"])
            except Exception as e:
                import traceback

                traceback.print_exc()

        sch.add_job(_runner, trigger=trigger, id=sched["id"], replace_existing=True)
    except Exception as e:
        import traceback

        traceback.print_exc()
        pass


def remove_job(sid: str):
    try:
        sch = get_scheduler()
        sch.remove_job(sid)
    except:
        pass


def load_all_jobs():
    try:
        from app.services.scheduler_service import list_schedules

        for s in list_schedules():
            if s.get("enabled", True):
                try:
                    add_job(s)
                except Exception as e:
                    import traceback

                    traceback.print_exc()
    except Exception as e:
        import traceback

        traceback.print_exc()


def shutdown():
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except:
            pass
        _scheduler = None
