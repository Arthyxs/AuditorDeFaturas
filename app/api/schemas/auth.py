"""Authentication API schemas."""

from pydantic import BaseModel, Field

from app.infrastructure.persistence.models import UserRole


class BootstrapStatusResponse(BaseModel):
    """Public first-access status without exposing the setup token."""

    available: bool


class BootstrapRequest(BaseModel):
    """Credentials and setup-generated token for the first administrator."""

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    bootstrap_token: str = Field(min_length=32, max_length=512)


class LoginRequest(BaseModel):
    """Local username/password login input."""

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    """Safe authenticated-user representation."""

    username: str
    role: UserRole


class LogoutResponse(BaseModel):
    """Logout confirmation."""

    logged_out: bool
