"""Container healthcheck for an RQ worker, which has no HTTP listener."""

import os
import socket
from datetime import UTC, datetime


def worker_is_healthy(worker, *, hostname, now):
    if worker.hostname != hostname or not worker.pid or not worker.last_heartbeat:
        return False
    try:
        os.kill(worker.pid, 0)
    except PermissionError:
        # Docker healthchecks can run as root without CAP_KILL while gosu
        # runs the worker as PUID. EPERM still proves that the PID exists.
        pass
    except (OSError, TypeError):
        return False
    heartbeat = worker.last_heartbeat
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=UTC)
    # Idle RQ workers block for almost worker_ttl; busy workers heartbeat too.
    age = (now - heartbeat).total_seconds()
    return 0 <= age <= worker.worker_ttl + 60


def main():
    from redis import Redis
    from rq import Worker

    try:
        connection = Redis.from_url(
            os.environ["SUBLARR_REDIS_URL"], socket_connect_timeout=3, socket_timeout=3
        )
        workers = Worker.all(connection=connection)
        healthy = any(
            worker_is_healthy(w, hostname=socket.gethostname(), now=datetime.now(UTC))
            for w in workers
        )
    except Exception:
        # Do not log the connection URL: it can contain a Redis password.
        healthy = False
    print("RQ worker healthy" if healthy else "RQ worker unavailable or heartbeat stale")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
