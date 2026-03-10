import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Health endpoint returns 200 with status healthy."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cybersec-pipeline"


@pytest.mark.asyncio
async def test_register_first_user_is_admin(client: AsyncClient) -> None:
    """First registered user should automatically be an admin."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "firstuser",
            "email": "first@example.com",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "firstuser"
    assert data["email"] == "first@example.com"
    assert data["is_admin"] is True
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, test_user: User) -> None:
    """Registering with an existing username returns 409."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "other@example.com",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 409
    assert "Username already taken" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User) -> None:
    """Registering with an existing email returns 409."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "differentuser",
            "email": "test@example.com",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 409
    assert "Email already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User) -> None:
    """Valid credentials return an access token."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User) -> None:
    """Invalid password returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Nonexistent username returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "whatever"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, test_user: User, auth_headers: dict) -> None:
    """Authenticated user can access /auth/me."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Unauthenticated request to /auth/me returns 401 or 403 (no bearer token)."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient) -> None:
    """Invalid token returns 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert response.status_code == 401
