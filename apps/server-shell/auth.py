"""Small in-memory session authority for the local server shell."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import Lock
import time


@dataclass(frozen=True)
class LoginResult:
    token: str | None
    retry_after: int = 0


class AuthManager:
    def __init__(
        self,
        username: str,
        password: str,
        session_seconds: int = 8 * 60 * 60,
        max_attempts: int = 5,
        attempt_window_seconds: int = 5 * 60,
    ) -> None:
        self._username = username
        self._password_digest = hashlib.sha256(password.encode("utf-8")).digest()
        self._session_seconds = session_seconds
        self._max_attempts = max_attempts
        self._attempt_window_seconds = attempt_window_seconds
        self._sessions: dict[str, float] = {}
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def login(self, username: str, password: str, client_id: str) -> LoginResult:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[client_id]
            while attempts and now - attempts[0] > self._attempt_window_seconds:
                attempts.popleft()
            if len(attempts) >= self._max_attempts:
                retry = max(1, int(self._attempt_window_seconds - (now - attempts[0])))
                return LoginResult(None, retry)

            supplied_digest = hashlib.sha256(password.encode("utf-8")).digest()
            valid = hmac.compare_digest(username, self._username) and hmac.compare_digest(
                supplied_digest, self._password_digest
            )
            if not valid:
                attempts.append(now)
                return LoginResult(None)

            attempts.clear()
            token = secrets.token_urlsafe(32)
            self._sessions[token] = now + self._session_seconds
            self._prune_sessions(now)
            return LoginResult(token)

    def verify(self, token: str | None) -> bool:
        if not token:
            return False
        now = time.monotonic()
        with self._lock:
            expires = self._sessions.get(token)
            if expires is None or expires <= now:
                self._sessions.pop(token, None)
                return False
            return True

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _prune_sessions(self, now: float) -> None:
        expired = [token for token, expires in self._sessions.items() if expires <= now]
        for token in expired:
            self._sessions.pop(token, None)
