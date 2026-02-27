"""Hook engine -- executes shell scripts on event signals.

HookEngine dispatches script execution asynchronously via ThreadPoolExecutor.
Scripts receive event data as SUBLARR_ prefixed environment variables.
All execution results are logged to the hook_log table.
"""

import json
import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Max length for env var values and captured output
_MAX_ENV_VALUE_LEN = 4096
_MAX_OUTPUT_LEN = 4096


class HookEngine:
    """Executes shell scripts on event signals via ThreadPoolExecutor.

    Each hook config specifies a script_path and timeout. Scripts receive
    a controlled environment with SUBLARR_ prefixed variables. Execution
    never blocks the event producer (async dispatch to thread pool).
    """

    def __init__(self, max_workers: int = 4):
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="hook",
        )
        logger.debug("HookEngine created with %d workers", max_workers)

    def execute_hook(self, hook_config: dict, event_name: str, event_data: dict) -> dict:
        """Execute a single hook synchronously (called inside thread pool).

        Args:
            hook_config: Dict with script_path, timeout_seconds, id, etc.
            event_name: Name of the event that triggered the hook.
            event_data: Event payload dict.

        Returns:
            Result dict with success, exit_code, stdout, stderr, duration_ms.
        """
        script_path = hook_config.get("script_path", "")
        timeout = hook_config.get("timeout_seconds", 30)

        # Validate script exists and is a file
        if not os.path.isfile(script_path):
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": f"Script not found: {script_path}",
                "duration_ms": 0,
            }

        # Build controlled environment
        hook_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            "SUBLARR_EVENT": event_name,
            "SUBLARR_EVENT_DATA": json.dumps(event_data, default=str)[:_MAX_ENV_VALUE_LEN],
        }

        # Add individual event_data keys as SUBLARR_ prefixed env vars
        for key, value in event_data.items():
            env_key = f"SUBLARR_{key.upper()}"
            env_val = str(value)[:_MAX_ENV_VALUE_LEN]
            hook_env[env_key] = env_val

        start = time.monotonic()

        try:
            proc = subprocess.run(
                [script_path],
                env=hook_env,
                timeout=timeout,
                capture_output=True,
                text=True,
                cwd="/tmp",
            )

            duration_ms = (time.monotonic() - start) * 1000

            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[:_MAX_OUTPUT_LEN],
                "stderr": (proc.stderr or "")[:_MAX_OUTPUT_LEN],
                "error": "" if proc.returncode == 0 else f"Exit code {proc.returncode}",
                "duration_ms": round(duration_ms, 1),
            }

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start) * 1000
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": f"Timeout after {timeout}s",
                "duration_ms": round(duration_ms, 1),
            }

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "duration_ms": round(duration_ms, 1),
            }

    def dispatch(self, event_name: str, event_data: dict) -> None:
        """Async dispatch: find matching hooks and submit to thread pool.

        Args:
            event_name: Event name from the catalog.
            event_data: Event payload dict.
        """
        try:
            from db.hooks import get_hook_configs

            configs = get_hook_configs(event_name=event_name)
        except Exception as e:
            logger.error("Failed to load hook configs for %s: %s", event_name, e)
            return

        enabled_configs = [c for c in configs if c.get("enabled", 1)]

        for config in enabled_configs:
            try:
                self._pool.submit(self._execute_and_log, config, event_name, event_data)
            except Exception as e:
                logger.error(
                    "Failed to submit hook %s for event %s: %s",
                    config.get("name", "?"),
                    event_name,
                    e,
                )

    def _execute_and_log(self, config: dict, event_name: str, event_data: dict) -> None:
        """Execute hook and log the result (runs in thread pool).

        Args:
            config: Hook config dict from DB.
            event_name: Event name.
            event_data: Event payload.
        """
        hook_id = config.get("id")

        try:
            result = self.execute_hook(config, event_name, event_data)

            # Log execution to DB
            from db.hooks import log_hook_execution, update_hook_trigger_stats

            log_hook_execution(
                hook_id=hook_id,
                event_name=event_name,
                hook_type="script",
                success=result["success"],
                exit_code=result.get("exit_code"),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                error=result.get("error", ""),
                duration_ms=result.get("duration_ms", 0),
            )
            update_hook_trigger_stats(hook_id, result["success"])

            # Emit meta-event
            from events.catalog import hook_executed

            try:
                hook_executed.send(
                    None,
                    data={
                        "hook_id": hook_id,
                        "hook_type": "script",
                        "event_name": event_name,
                        "success": result["success"],
                        "duration_ms": result.get("duration_ms", 0),
                    },
                )
            except Exception:
                pass  # Meta-event failure should not break hook execution

            if result["success"]:
                logger.debug(
                    "Hook '%s' executed for %s (%.0fms)",
                    config.get("name", "?"),
                    event_name,
                    result.get("duration_ms", 0),
                )
            else:
                logger.warning(
                    "Hook '%s' failed for %s: %s",
                    config.get("name", "?"),
                    event_name,
                    result.get("error", "unknown"),
                )

        except Exception as e:
            logger.error(
                "Unexpected error executing hook '%s' for %s: %s",
                config.get("name", "?"),
                event_name,
                e,
            )

    def shutdown(self) -> None:
        """Shutdown the thread pool gracefully."""
        self._pool.shutdown(wait=False)
        logger.info("HookEngine shut down")


def init_hook_subscribers(engine: HookEngine) -> None:
    """Subscribe the HookEngine to all catalog events.

    Creates a closure for each event that calls engine.dispatch with
    the correct event_name.

    Args:
        engine: HookEngine instance to register.
    """
    from events.catalog import EVENT_CATALOG

    def _make_hook_handler(event_name: str):
        """Create a handler that captures event_name via closure."""

        def _handler(sender, data=None, **kwargs):
            engine.dispatch(event_name, data or {})

        return _handler

    count = 0
    for name, entry in EVENT_CATALOG.items():
        # Skip hook_executed to avoid infinite recursion
        if name == "hook_executed":
            continue
        handler = _make_hook_handler(name)
        entry["signal"].connect(handler, weak=False)
        count += 1

    logger.info("HookEngine subscribed to %d events", count)
