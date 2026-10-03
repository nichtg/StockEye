import pytest

from app import cli
from app.config import Settings
from app.db import Database
from tests.integration.conftest import PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _cli_env(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setenv("STOCKEYE_ADMIN_PASSWORD", PASSWORD)


def test_create_admin_creates_a_new_admin(db: Database, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["create-admin", "--email", "Root@Example.com"])

    assert code == 0
    assert "created" in capsys.readouterr().out


async def test_create_admin_promotes_existing_user(db: Database) -> None:
    await db.users.insert_one(
        {
            "email": "alice@example.com",
            "password_hash": "x",
            "role": "user",
            "status": "disabled",
            "failed_logins": 0,
            "locked_until": None,
            "created_at": None,
            "last_login_at": None,
        }
    )

    message = await cli.create_admin("alice@example.com", PASSWORD)

    doc = await db.users.find_one({"email": "alice@example.com"})
    assert doc is not None
    assert (doc["role"], doc["status"]) == ("admin", "active")
    assert "promoted" in message


def test_create_admin_rejects_weak_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STOCKEYE_ADMIN_PASSWORD", "short")

    code = cli.main(["create-admin", "--email", "root@example.com"])

    assert code == 2
    assert "at least 12" in capsys.readouterr().err
