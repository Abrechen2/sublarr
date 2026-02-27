"""Hook and webhook database operations -- delegating to SQLAlchemy repository."""


from db.repositories.hooks import HookRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = HookRepository()
    return _repo


# ---- Hook configs CRUD ----

def create_hook_config(name: str, event_name: str, script_path: str,
                       timeout_seconds: int = 30) -> dict:
    """Create a new hook configuration."""
    return _get_repo().create_hook(name, event_name, script_path, timeout_seconds)


def get_hook_configs(event_name: str = None) -> list:
    """Get all hook configs, optionally filtered by event name."""
    return _get_repo().get_hooks(event_name)


def get_hook_config(hook_id: int) -> dict | None:
    """Get a single hook config by ID."""
    return _get_repo().get_hook(hook_id)


def update_hook_config(hook_id: int, **kwargs) -> None:
    """Update a hook config with arbitrary column values."""
    _get_repo().update_hook(hook_id, **kwargs)


def delete_hook_config(hook_id: int) -> None:
    """Delete a hook config by ID."""
    _get_repo().delete_hook(hook_id)


# ---- Webhook configs CRUD ----

def create_webhook_config(name: str, event_name: str, url: str,
                          secret: str = "", retry_count: int = 3,
                          timeout_seconds: int = 10) -> dict:
    """Create a new webhook configuration."""
    return _get_repo().create_webhook(name, event_name, url, secret,
                                       retry_count, timeout_seconds)


def get_webhook_configs(event_name: str = None) -> list:
    """Get all webhook configs, optionally filtered by event name."""
    return _get_repo().get_webhooks(event_name)


def get_webhook_config(webhook_id: int) -> dict | None:
    """Get a single webhook config by ID."""
    return _get_repo().get_webhook(webhook_id)


def update_webhook_config(webhook_id: int, **kwargs) -> None:
    """Update a webhook config with arbitrary column values."""
    _get_repo().update_webhook(webhook_id, **kwargs)


def delete_webhook_config(webhook_id: int) -> None:
    """Delete a webhook config by ID."""
    _get_repo().delete_webhook(webhook_id)


# ---- Hook log ----

def log_hook_execution(hook_id: int = None, webhook_id: int = None,
                       event_name: str = "", hook_type: str = "",
                       success: bool = False, exit_code: int = None,
                       status_code: int = None, stdout: str = "",
                       stderr: str = "", error: str = "",
                       duration_ms: float = 0) -> dict:
    """Record a hook or webhook execution in the log."""
    return _get_repo().create_hook_log(
        hook_id, webhook_id, event_name, hook_type, success,
        exit_code, status_code, stdout, stderr, error, duration_ms
    )


def get_hook_logs(hook_id: int = None, webhook_id: int = None,
                  limit: int = 50) -> list:
    """Get hook execution logs, optionally filtered."""
    return _get_repo().get_hook_logs(limit=limit, hook_id=hook_id,
                                      webhook_id=webhook_id)


def clear_hook_logs() -> int:
    """Delete all hook execution logs."""
    return _get_repo().clear_hook_logs()


# ---- Trigger stats helpers ----

def update_hook_trigger_stats(hook_id: int, success: bool) -> None:
    """Update hook trigger statistics after execution."""
    _get_repo().record_hook_triggered(hook_id, success)


def update_webhook_trigger_stats(webhook_id: int, success: bool,
                                 status_code: int = 0,
                                 error: str = "") -> None:
    """Update webhook trigger statistics after execution."""
    _get_repo().record_webhook_triggered(webhook_id, success, status_code, error)
