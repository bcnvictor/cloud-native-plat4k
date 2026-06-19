"""Unit tests for backend/core/exceptions.py — no DB, no HTTP."""
from fastapi import HTTPException, status

from backend.core.exceptions import (
    BadRequestException,
    CloudProviderException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)


def test_not_found_exception_default():
    exc = NotFoundException()
    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_404_NOT_FOUND
    assert exc.detail == "Resource not found"


def test_not_found_exception_custom_detail():
    exc = NotFoundException(detail="App not found")
    assert exc.status_code == status.HTTP_404_NOT_FOUND
    assert exc.detail == "App not found"


def test_bad_request_exception_default():
    exc = BadRequestException()
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == "Bad request"


def test_bad_request_exception_custom_detail():
    exc = BadRequestException(detail="Invalid payload")
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == "Invalid payload"


def test_unauthorized_exception_default():
    exc = UnauthorizedException()
    assert exc.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.detail == "Could not validate credentials"
    assert exc.headers == {"WWW-Authenticate": "Bearer"}


def test_unauthorized_exception_custom_detail():
    exc = UnauthorizedException(detail="Token expired")
    assert exc.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.detail == "Token expired"
    assert exc.headers == {"WWW-Authenticate": "Bearer"}


def test_forbidden_exception_default():
    exc = ForbiddenException()
    assert exc.status_code == status.HTTP_403_FORBIDDEN
    assert exc.detail == "Not enough permissions"


def test_forbidden_exception_custom_detail():
    exc = ForbiddenException(detail="Admins only")
    assert exc.status_code == status.HTTP_403_FORBIDDEN
    assert exc.detail == "Admins only"


def test_cloud_provider_exception_default():
    exc = CloudProviderException()
    assert exc.status_code == status.HTTP_502_BAD_GATEWAY
    assert exc.detail == "Error communicating with cloud provider"


def test_cloud_provider_exception_custom_detail():
    exc = CloudProviderException(detail="GitLab API unreachable")
    assert exc.status_code == status.HTTP_502_BAD_GATEWAY
    assert exc.detail == "GitLab API unreachable"
