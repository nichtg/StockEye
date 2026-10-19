from types import SimpleNamespace

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


def test_refresh_discover_runs_one_build_and_prints_the_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    refreshed: list[str] = []
    closed: list[str] = []

    class FakeDiscover:
        async def refresh(self) -> None:
            refreshed.append("x")

        async def lists(self) -> SimpleNamespace:
            def one(list_id: str, n: int) -> SimpleNamespace:
                return SimpleNamespace(id=list_id, rows=[object()] * n)

            return SimpleNamespace(lists=[one("us_small_movers", 10), one("sg_under_radar", 0)])

    class FakeServices:
        discover = FakeDiscover()

        async def aclose(self) -> None:
            closed.append("x")

    async def fake_build(_settings: Settings, _db: Database) -> FakeServices:
        return FakeServices()

    monkeypatch.setattr(cli, "build_services", fake_build)

    code = cli.main(["refresh-discover"])

    out = capsys.readouterr().out
    assert code == 0
    assert (len(refreshed), len(closed)) == (1, 1)
    assert "us_small_movers: 10 rows" in out
    assert "sg_under_radar: 0 rows" in out
