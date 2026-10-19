"""Garmin Connect access: token-based client for tools, interactive login for /setup.

garminconnect is synchronous, so callers run these methods in a worker thread.
Only the session tokens (garmin_tokens.json) are ever written to disk; the
password lives in memory for the duration of one login attempt.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Callable

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

log = logging.getLogger(__name__)

TOKEN_FILE = "garmin_tokens.json"


class NotConnected(Exception):
    """No usable Garmin session; the user needs to (re)connect on /setup."""


class GarminManager:
    def __init__(self, token_dir: str) -> None:
        self.token_dir = token_dir
        os.makedirs(token_dir, mode=0o700, exist_ok=True)
        self._client: Garmin | None = None
        self._lock = threading.Lock()

    # ---- token state -------------------------------------------------------
    @property
    def token_path(self) -> str:
        return os.path.join(self.token_dir, TOKEN_FILE)

    def has_tokens(self) -> bool:
        return os.path.exists(self.token_path)

    def reset(self) -> None:
        with self._lock:
            self._client = None

    def disconnect(self) -> None:
        """Forget the Garmin session entirely (used by the setup page)."""
        with self._lock:
            self._client = None
            if os.path.exists(self.token_path):
                os.remove(self.token_path)

    # ---- client used by MCP tools -----------------------------------------
    def _get_client(self) -> Garmin:
        with self._lock:
            if self._client is None:
                if not self.has_tokens():
                    raise NotConnected("Garmin has not been connected yet.")
                client = Garmin()
                try:
                    # Loads tokens and refreshes them when near expiry.
                    client.login(self.token_dir)
                except GarminConnectAuthenticationError as exc:
                    raise NotConnected("The saved Garmin session has expired.") from exc
                self._client = client
            return self._client

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(self._get_client(), method)(*args, **kwargs)
        except GarminConnectAuthenticationError:
            # Token may have been rotated on disk; rebuild the client once.
            self.reset()
            try:
                return getattr(self._get_client(), method)(*args, **kwargs)
            except GarminConnectAuthenticationError as exc:
                raise NotConnected("The saved Garmin session was rejected.") from exc


class LoginSession:
    """One interactive Garmin login, driven by the /setup web page.

    garminconnect asks for the MFA code through a blocking `prompt_mfa`
    callback. We run the login in a worker thread and make that callback wait
    on a queue that the web page fills when the user submits the code.
    States: running -> (needs_mfa -> running)* -> done | error
    """

    MFA_TIMEOUT_S = 300

    def __init__(self, manager: GarminManager, email: str, password: str) -> None:
        self.manager = manager
        self.state = "running"
        self.error: str | None = None
        self.started_at = time.monotonic()
        self._mfa_codes: queue.Queue[str] = queue.Queue(maxsize=1)
        self._cond = threading.Condition()
        threading.Thread(
            target=self._run, args=(email, password), daemon=True, name="garmin-login"
        ).start()

    def _set(self, state: str, error: str | None = None) -> None:
        with self._cond:
            self.state, self.error = state, error
            self._cond.notify_all()

    def _prompt_mfa(self) -> str:
        self._set("needs_mfa")
        try:
            return self._mfa_codes.get(timeout=self.MFA_TIMEOUT_S)
        except queue.Empty as exc:
            raise TimeoutError("No verification code was entered within 5 minutes.") from exc

    def _run(self, email: str, password: str) -> None:
        try:
            client = Garmin(email=email, password=password, prompt_mfa=self._prompt_mfa)
            del password
            client.login(self.manager.token_dir)  # writes garmin_tokens.json (mode 0600)
            self.manager.reset()                  # tools pick up the new session
            self._set("done")
        except GarminConnectAuthenticationError:
            self._set("error", "Garmin didn't accept that email, password or code. Try again.")
        except GarminConnectTooManyRequestsError:
            self._set("error", "Garmin is limiting login attempts. Wait 30 minutes, then try again.")
        except TimeoutError as exc:
            self._set("error", str(exc))
        except Exception:  # noqa: BLE001 - surface a safe message, log the detail
            log.exception("Garmin login failed")
            self._set("error", "The login didn't complete. Ask the person who runs this server to check its logs.")

    def submit_mfa(self, code: str) -> None:
        with self._cond:
            if self.state != "needs_mfa":
                return
            self.state = "running"
        self._mfa_codes.put_nowait(code.strip())

    def wait_until_settled(self, timeout: float) -> str:
        """Block until the session needs input or has finished."""
        settled: Callable[[], bool] = lambda: self.state in ("needs_mfa", "done", "error")
        with self._cond:
            self._cond.wait_for(settled, timeout=timeout)
            return self.state
