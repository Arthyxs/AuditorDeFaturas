"""M05 acceptance tests against disposable PostgreSQL."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, cast
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.api.dependencies import require_roles
from app.application.services.auth import AuthenticationError, AuthService
from app.config import Settings, get_settings
from app.infrastructure.persistence.models import AuthSession, User, UserRole
from app.infrastructure.persistence.session import create_session_factory
from app.infrastructure.security.passwords import hash_password
from app.main import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 with a disposable PostgreSQL server",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://invoice-auditor.test"
BOOTSTRAP_TOKEN = "test-only-bootstrap-token-00000000000000000000"
TEST_PASSWORD = "test-only-password-123"
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
OperatorUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))]
ViewerUser = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER))
]


@pytest.fixture
def postgres_database_url() -> Iterator[str]:
    """Create and remove an isolated M05 database."""
    configured_url = make_url(get_settings().database_url.get_secret_value())
    database_name = f"invoice_auditor_m05_{uuid4().hex}"
    admin_url = configured_url.set(database="postgres")
    test_url = configured_url.set(database=database_name)
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    database_url = test_url.render_as_string(hide_password=False)
    configuration = Config(str(PROJECT_ROOT / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(configuration, "head")
    try:
        yield database_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


def settings_for(database_url: str) -> Settings:
    """Build test-only settings without production credentials."""
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_base_url": ORIGIN,
            "app_secret_key": "test-app-secret-000000000000000000000000000",
            "first_admin_bootstrap_token": BOOTSTRAP_TOKEN,
            "postgres_password": "test-postgres-secret-00000000000000000000000",
            "database_url": database_url,
        }
    )


def app_for(database_url: str) -> FastAPI:
    """Create a test app bound to the disposable database."""
    return create_app(settings_for(database_url))


def bootstrap(client: TestClient, *, username: str = "admin") -> None:
    response = client.post(
        "/api/auth/bootstrap",
        headers={"Origin": ORIGIN},
        json={"username": username, "password": TEST_PASSWORD, "bootstrap_token": BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 201


def test_bootstrap_is_protected_one_time_and_cookie_is_secure(postgres_database_url: str) -> None:
    """Only the setup token creates one admin and issues the approved cookie."""
    application = app_for(postgres_database_url)
    with TestClient(application, base_url=ORIGIN) as client:
        assert client.get("/api/auth/bootstrap/status").json() == {"available": True}
        invalid = client.post(
            "/api/auth/bootstrap",
            headers={"Origin": ORIGIN},
            json={"username": "admin", "password": TEST_PASSWORD, "bootstrap_token": "x" * 32},
        )
        assert invalid.status_code == 409
        bootstrap(client)
        cookie = client.cookies.get("invoice_auditor_session")
        assert cookie is not None
        set_cookie = (
            client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN},
                json={"username": "admin", "password": TEST_PASSWORD},
            )
            .headers["set-cookie"]
            .lower()
        )
        assert "httponly" in set_cookie
        assert "secure" in set_cookie
        assert "samesite=strict" in set_cookie
        assert client.get("/api/auth/me").json() == {"username": "admin", "role": "ADMIN"}
        assert client.get("/api/auth/bootstrap/status").json() == {"available": False}
        second = client.post(
            "/api/auth/bootstrap",
            headers={"Origin": ORIGIN},
            json={
                "username": "admin2",
                "password": TEST_PASSWORD,
                "bootstrap_token": BOOTSTRAP_TOKEN,
            },
        )
        assert second.status_code == 409
    application.state.database_engine.dispose()


def test_concurrent_bootstrap_creates_exactly_one_admin(postgres_database_url: str) -> None:
    """The PostgreSQL transaction lock closes the first-admin race."""

    def attempt(username: str) -> int:
        application = app_for(postgres_database_url)
        try:
            with TestClient(application, base_url=ORIGIN) as client:
                return cast(
                    int,
                    client.post(
                        "/api/auth/bootstrap",
                        headers={"Origin": ORIGIN},
                        json={
                            "username": username,
                            "password": TEST_PASSWORD,
                            "bootstrap_token": BOOTSTRAP_TOKEN,
                        },
                    ).status_code,
                )
        finally:
            application.state.database_engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(attempt, ["admin-a", "admin-b"]))
    assert sorted(statuses) == [201, 409]

    engine = create_engine(postgres_database_url)
    with create_session_factory(engine)() as database:
        assert len(database.scalars(select(User).where(User.role == UserRole.ADMIN)).all()) == 1
    engine.dispose()


def test_session_expiration_revocation_logout_and_csrf(postgres_database_url: str) -> None:
    """Expired/revoked sessions fail and origin validation protects mutations."""
    application = app_for(postgres_database_url)
    with TestClient(application, base_url=ORIGIN) as client:
        missing_origin = client.post(
            "/api/auth/login", json={"username": "nobody", "password": TEST_PASSWORD}
        )
        assert missing_origin.status_code == 403
        wrong_origin = client.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.invalid"},
            json={"username": "nobody", "password": TEST_PASSWORD},
        )
        assert wrong_origin.status_code == 403
        bootstrap(client)
        token = client.cookies.get("invoice_auditor_session")
        assert token is not None

        engine = application.state.database_engine
        with create_session_factory(engine)() as database:
            service = AuthService(database, application.state.settings)
            user = service.resolve_session(token)
            expired = service.create_session(user, now=datetime.now(UTC) - timedelta(days=2))
            database.commit()
            with pytest.raises(AuthenticationError):
                service.resolve_session(expired.token)
            service.revoke_session(token)
            database.commit()
            with pytest.raises(AuthenticationError):
                service.resolve_session(token)

        client.cookies.clear()
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert login.status_code == 200
        assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
        assert client.get("/api/auth/me").status_code == 401
    application.state.database_engine.dispose()


def test_rbac_matrix(postgres_database_url: str) -> None:
    """ADMIN, OPERATOR and VIEWER receive only their approved capability levels."""
    application = app_for(postgres_database_url)

    @application.get("/test/admin")
    def admin_only(_: AdminUser) -> dict[str, bool]:
        return {"allowed": True}

    @application.get("/test/operate")
    def operate(_: OperatorUser) -> dict[str, bool]:
        return {"allowed": True}

    @application.get("/test/view")
    def view(_: ViewerUser) -> dict[str, bool]:
        return {"allowed": True}

    with create_session_factory(application.state.database_engine)() as database:
        for role in UserRole:
            database.add(
                User(
                    username=role.value.casefold(),
                    password_hash=hash_password(TEST_PASSWORD),
                    role=role,
                    is_active=True,
                )
            )
        database.commit()

    expected = {
        UserRole.ADMIN: [200, 200, 200],
        UserRole.OPERATOR: [403, 200, 200],
        UserRole.VIEWER: [403, 403, 200],
    }
    for role, statuses in expected.items():
        with TestClient(application, base_url=ORIGIN) as client:
            login = client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN},
                json={"username": role.value.casefold(), "password": TEST_PASSWORD},
            )
            assert login.status_code == 200
            assert [
                client.get(path).status_code
                for path in ("/test/admin", "/test/operate", "/test/view")
            ] == statuses
    application.state.database_engine.dispose()


def test_session_database_never_stores_raw_cookie(postgres_database_url: str) -> None:
    """A stolen database alone does not reveal active cookie values."""
    application = app_for(postgres_database_url)
    with TestClient(application, base_url=ORIGIN) as client:
        bootstrap(client)
        token = client.cookies.get("invoice_auditor_session")
        assert token is not None
        with create_session_factory(application.state.database_engine)() as database:
            record = database.scalar(select(AuthSession))
            assert record is not None
            assert record.token_hash != token
            assert len(record.token_hash) == 64
    application.state.database_engine.dispose()
