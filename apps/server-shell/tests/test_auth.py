from pathlib import Path
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from auth import AuthManager


def test_valid_login_creates_and_revokes_session():
    auth = AuthManager("admin", "correct-password")
    result = auth.login("admin", "correct-password", "client-a")

    assert result.token
    assert auth.verify(result.token)

    auth.logout(result.token)
    assert not auth.verify(result.token)


def test_invalid_password_does_not_create_session():
    auth = AuthManager("admin", "correct-password")
    result = auth.login("admin", "wrong-password", "client-a")

    assert result.token is None
    assert result.retry_after == 0


def test_repeated_failures_are_rate_limited():
    auth = AuthManager("admin", "correct-password", max_attempts=2)
    auth.login("admin", "wrong-1", "client-a")
    auth.login("admin", "wrong-2", "client-a")
    blocked = auth.login("admin", "correct-password", "client-a")

    assert blocked.token is None
    assert blocked.retry_after > 0


def test_rate_limit_is_scoped_by_client():
    auth = AuthManager("admin", "correct-password", max_attempts=1)
    auth.login("admin", "wrong", "client-a")
    allowed = auth.login("admin", "correct-password", "client-b")

    assert allowed.token
