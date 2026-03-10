"""Anti-captcha solver supporting Anti-Captcha.com and CapMonster backends."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

# Supported backends
BACKEND_ANTICAPTCHA = "anticaptcha"
BACKEND_CAPMONSTER = "capmonster"

# Endpoint templates
_ENDPOINTS = {
    BACKEND_ANTICAPTCHA: "https://api.anti-captcha.com",
    BACKEND_CAPMONSTER: "https://api.capmonster.cloud",
}


class CaptchaSolverError(Exception):
    """Raised when captcha solving fails."""


class CaptchaSolver:
    """Thin wrapper around Anti-Captcha.com / CapMonster REST APIs.

    Both services expose identical JSON endpoints (createTask / getTaskResult),
    so the same code works for either backend.
    """

    def __init__(
        self, backend: str, api_key: str, poll_interval: float = 3.0, max_wait: float = 120.0
    ) -> None:
        if backend not in _ENDPOINTS:
            raise ValueError(
                f"Unknown captcha backend: {backend!r}. Choose {BACKEND_ANTICAPTCHA!r} or {BACKEND_CAPMONSTER!r}."
            )
        if not api_key:
            raise ValueError("api_key must not be empty.")

        self.backend = backend
        self.api_key = api_key
        self.base_url = _ENDPOINTS[backend]
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        """Solve a reCAPTCHA v2 challenge and return the g-recaptcha-response token."""
        task = {
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        return self._run_task(task)

    def solve_image(self, image_base64: str) -> str:
        """Solve an image-based captcha and return the text solution."""
        task = {
            "type": "ImageToTextTask",
            "body": image_base64,
        }
        return self._run_task(task)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_task(self, task: dict) -> int:
        """Submit a task to the API and return the task ID."""
        payload = {"clientKey": self.api_key, "task": task}
        try:
            resp = requests.post(f"{self.base_url}/createTask", json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CaptchaSolverError(f"createTask request failed: {exc}") from exc

        data = resp.json()
        if data.get("errorId"):
            raise CaptchaSolverError(
                f"createTask error {data['errorId']}: {data.get('errorDescription', '')}"
            )
        return data["taskId"]

    def _get_task_result(self, task_id: int) -> dict:
        """Poll getTaskResult until the task is ready, then return the solution dict."""
        payload = {"clientKey": self.api_key, "taskId": task_id}
        deadline = time.monotonic() + self.max_wait

        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            try:
                resp = requests.post(f"{self.base_url}/getTaskResult", json=payload, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise CaptchaSolverError(f"getTaskResult request failed: {exc}") from exc

            data = resp.json()
            if data.get("errorId"):
                raise CaptchaSolverError(
                    f"getTaskResult error {data['errorId']}: {data.get('errorDescription', '')}"
                )
            if data.get("status") == "ready":
                return data.get("solution", {})
            # status == "processing" → keep polling

        raise CaptchaSolverError(f"Captcha not solved within {self.max_wait}s (task {task_id})")

    def _run_task(self, task: dict) -> str:
        """Create a task, wait for the solution, and return the solution text/token."""
        task_id = self._create_task(task)
        logger.debug("Captcha task %d created (backend=%s)", task_id, self.backend)
        solution = self._get_task_result(task_id)
        logger.debug("Captcha task %d solved", task_id)
        # reCAPTCHA → gRecaptchaResponse; image → text
        return solution.get("gRecaptchaResponse") or solution.get("text") or ""


def build_solver_from_settings() -> "CaptchaSolver | None":
    """Return a CaptchaSolver if configured in settings, otherwise None."""
    from config import get_settings

    settings = get_settings()
    backend = getattr(settings, "anti_captcha_provider", "")
    api_key = getattr(settings, "anti_captcha_api_key", "")
    if not backend or not api_key:
        return None
    try:
        return CaptchaSolver(backend=backend, api_key=api_key)
    except ValueError as exc:
        logger.warning("CaptchaSolver init failed: %s", exc)
        return None
