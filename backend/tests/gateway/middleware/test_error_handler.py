"""Tests for centralized error handling middleware."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from src.gateway.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
    WenjinException,
    map_exception_to_status,
)
from src.gateway.middleware.error_handler import (
    generic_exception_handler,
    http_exception_handler,
    register_error_handlers,
    validation_exception_handler,
    wenjin_exception_handler,
)

# ============================================================================ #
# Exception Classes Tests
# ============================================================================ #

class TestWenjinException:
    """Tests for WenjinException base class."""

    def test_base_exception_with_defaults(self):
        """Test base exception with default code."""
        exc = WenjinException("Something went wrong")

        assert exc.message == "Something went wrong"
        assert exc.code == "UNKNOWN_ERROR"
        assert str(exc) == "Something went wrong"

    def test_base_exception_with_custom_code(self):
        """Test base exception with custom code."""
        exc = WenjinException("Custom error", code="CUSTOM_ERROR")

        assert exc.message == "Custom error"
        assert exc.code == "CUSTOM_ERROR"


class TestNotFoundError:
    """Tests for NotFoundError exception."""

    def test_not_found_error_message_format(self):
        """Test NotFoundError formats message correctly."""
        exc = NotFoundError("User", "user-123")

        assert exc.message == "User with id 'user-123' not found"
        assert exc.code == "NOT_FOUND"

    def test_not_found_error_with_different_resource(self):
        """Test NotFoundError with different resource types."""
        exc = NotFoundError("Workspace", "ws-456")

        assert exc.message == "Workspace with id 'ws-456' not found"
        assert exc.code == "NOT_FOUND"


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_validation_error_message(self):
        """Test ValidationError with custom message."""
        exc = ValidationError("Email format is invalid")

        assert exc.message == "Email format is invalid"
        assert exc.code == "VALIDATION_ERROR"

    def test_validation_error_with_complex_message(self):
        """Test ValidationError with complex validation message."""
        exc = ValidationError("Field 'title' must be between 5 and 100 characters")

        assert exc.code == "VALIDATION_ERROR"


class TestDuplicateError:
    """Tests for DuplicateError exception."""

    def test_duplicate_error_message_format(self):
        """Test DuplicateError formats message correctly."""
        exc = DuplicateError("User", "email", "test@example.com")

        assert exc.message == "User with email 'test@example.com' already exists"
        assert exc.code == "DUPLICATE"

    def test_duplicate_error_with_different_field(self):
        """Test DuplicateError with different field name."""
        exc = DuplicateError("Workspace", "name", "My Research")

        assert exc.message == "Workspace with name 'My Research' already exists"


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_authentication_error_default_message(self):
        """Test AuthenticationError with default message."""
        exc = AuthenticationError()

        assert exc.message == "Authentication failed"
        assert exc.code == "AUTH_ERROR"

    def test_authentication_error_custom_message(self):
        """Test AuthenticationError with custom message."""
        exc = AuthenticationError("Invalid API key")

        assert exc.message == "Invalid API key"
        assert exc.code == "AUTH_ERROR"


class TestAuthorizationError:
    """Tests for AuthorizationError exception."""

    def test_authorization_error_default_message(self):
        """Test AuthorizationError with default message."""
        exc = AuthorizationError()

        assert exc.message == "Not authorized"
        assert exc.code == "FORBIDDEN"

    def test_authorization_error_custom_message(self):
        """Test AuthorizationError with custom message."""
        exc = AuthorizationError("You don't have permission to access this resource")

        assert exc.message == "You don't have permission to access this resource"
        assert exc.code == "FORBIDDEN"


class TestRateLimitError:
    """Tests for RateLimitError exception."""

    def test_rate_limit_error_default_message(self):
        """Test RateLimitError with default message."""
        exc = RateLimitError()

        assert exc.message == "Rate limit exceeded"
        assert exc.code == "RATE_LIMIT_EXCEEDED"

    def test_rate_limit_error_custom_message(self):
        """Test RateLimitError with custom message."""
        exc = RateLimitError("Too many requests. Please wait 60 seconds.")

        assert exc.message == "Too many requests. Please wait 60 seconds."


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError exception."""

    def test_service_unavailable_error_with_service_name(self):
        """Test ServiceUnavailableError with service name."""
        exc = ServiceUnavailableError("OpenAI API")

        assert exc.message == "OpenAI API is currently unavailable"
        assert exc.code == "SERVICE_UNAVAILABLE"

    def test_service_unavailable_error_with_custom_message(self):
        """Test ServiceUnavailableError with custom message."""
        exc = ServiceUnavailableError("Redis", "Connection refused")

        assert exc.message == "Connection refused"
        assert exc.code == "SERVICE_UNAVAILABLE"


# ============================================================================ #
# Status Code Mapping Tests
# ============================================================================ #

class TestMapExceptionToStatus:
    """Tests for exception to status code mapping."""

    def test_not_found_maps_to_404(self):
        """Test NOT_FOUND maps to 404."""
        exc = NotFoundError("Resource", "123")
        assert map_exception_to_status(exc) == status.HTTP_404_NOT_FOUND

    def test_validation_error_maps_to_400(self):
        """Test VALIDATION_ERROR maps to 400."""
        exc = ValidationError("Invalid input")
        assert map_exception_to_status(exc) == status.HTTP_400_BAD_REQUEST

    def test_duplicate_maps_to_409(self):
        """Test DUPLICATE maps to 409."""
        exc = DuplicateError("User", "email", "test@test.com")
        assert map_exception_to_status(exc) == status.HTTP_409_CONFLICT

    def test_auth_error_maps_to_401(self):
        """Test AUTH_ERROR maps to 401."""
        exc = AuthenticationError()
        assert map_exception_to_status(exc) == status.HTTP_401_UNAUTHORIZED

    def test_forbidden_maps_to_403(self):
        """Test FORBIDDEN maps to 403."""
        exc = AuthorizationError()
        assert map_exception_to_status(exc) == status.HTTP_403_FORBIDDEN

    def test_rate_limit_maps_to_429(self):
        """Test RATE_LIMIT_EXCEEDED maps to 429."""
        exc = RateLimitError()
        assert map_exception_to_status(exc) == status.HTTP_429_TOO_MANY_REQUESTS

    def test_service_unavailable_maps_to_503(self):
        """Test SERVICE_UNAVAILABLE maps to 503."""
        exc = ServiceUnavailableError("Test Service")
        assert map_exception_to_status(exc) == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_unknown_code_maps_to_500(self):
        """Test unknown error code maps to 500."""
        exc = WenjinException("Unknown error", code="UNKNOWN_ERROR")
        assert map_exception_to_status(exc) == status.HTTP_500_INTERNAL_SERVER_ERROR


# ============================================================================ #
# Exception Handler Tests
# ============================================================================ #

@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock()
    request.url = MagicMock()
    request.url.path = "/api/test"
    return request


class TestWenjinExceptionHandler:
    """Tests for wenjin_exception_handler."""

    @pytest.mark.asyncio
    async def test_returns_json_response_with_error(self, mock_request):
        """Test handler returns proper JSON response."""
        exc = NotFoundError("User", "123")

        response = await wenjin_exception_handler(mock_request, exc)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Parse the body content
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "User with id '123' not found"

    @pytest.mark.asyncio
    async def test_handles_validation_error(self, mock_request):
        """Test handler handles ValidationError."""
        exc = ValidationError("Invalid email format")

        response = await wenjin_exception_handler(mock_request, exc)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_handles_authentication_error(self, mock_request):
        """Test handler handles AuthenticationError."""
        exc = AuthenticationError("Token expired")

        response = await wenjin_exception_handler(mock_request, exc)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "AUTH_ERROR"


class TestValidationExceptionHandler:
    """Tests for validation_exception_handler."""

    @pytest.mark.asyncio
    async def test_returns_422_status(self, mock_request):
        """Test handler returns 422 status code."""
        # Create a mock validation error
        exc = MagicMock(spec=RequestValidationError)
        exc.errors = MagicMock(return_value=[
            {"loc": ["body", "email"], "msg": "invalid email", "type": "value_error.email"}
        ])

        response = await validation_exception_handler(mock_request, exc)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_includes_error_details(self, mock_request):
        """Test handler includes validation error details."""
        error_details = [
            {"loc": ["body", "title"], "msg": "field required", "type": "value_error.missing"}
        ]
        exc = MagicMock(spec=RequestValidationError)
        exc.errors = MagicMock(return_value=error_details)

        response = await validation_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "Invalid request data"
        assert body["error"]["details"] == error_details


class TestHTTPExceptionHandler:
    """Tests for http_exception_handler."""

    @pytest.mark.asyncio
    async def test_handles_404_exception(self, mock_request):
        """Test handler handles 404 HTTP exception."""
        exc = HTTPException(status_code=404, detail="Item not found")

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 404
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Item not found"

    @pytest.mark.asyncio
    async def test_handles_401_exception(self, mock_request):
        """Test handler handles 401 HTTP exception."""
        exc = HTTPException(status_code=401, detail="Not authenticated")

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 401
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_forwards_http_exception_headers(self, mock_request):
        """HTTP exception headers must be preserved in the JSON response."""
        exc = HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_handles_500_exception(self, mock_request):
        """Test handler handles 500 HTTP exception."""
        exc = HTTPException(status_code=500, detail="Internal server error")

        response = await http_exception_handler(mock_request, exc)

        assert response.status_code == 500
        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INTERNAL_ERROR"


class TestGenericExceptionHandler:
    """Tests for generic_exception_handler."""

    @pytest.mark.asyncio
    async def test_returns_500_status(self, mock_request):
        """Test handler returns 500 status code for unhandled exceptions."""
        exc = ValueError("Unexpected value")

        response = await generic_exception_handler(mock_request, exc)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_returns_generic_error_message(self, mock_request):
        """Test handler returns generic error message."""
        exc = RuntimeError("Something went terribly wrong")

        response = await generic_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["message"] == "An unexpected error occurred"


# ============================================================================ #
# Integration Tests with FastAPI
# ============================================================================ #

class TestRegisterErrorHandlers:
    """Tests for register_error_handlers function."""

    def test_registers_all_handlers(self):
        """Test that all handlers are registered."""
        app = FastAPI()
        register_error_handlers(app)

        # Check that exception handlers are registered
        assert WenjinException in app.exception_handlers
        assert RequestValidationError in app.exception_handlers
        assert HTTPException in app.exception_handlers
        assert Exception in app.exception_handlers


class TestErrorHandlingIntegration:
    """Integration tests for error handling with FastAPI."""

    @pytest.fixture
    def test_app(self):
        """Create a test FastAPI app with error handlers."""
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/not-found")
        async def raise_not_found():
            raise NotFoundError("User", "123")

        @app.get("/validation-error")
        async def raise_validation_error():
            raise ValidationError("Invalid data provided")

        @app.get("/duplicate")
        async def raise_duplicate():
            raise DuplicateError("Workspace", "name", "test-workspace")

        @app.get("/auth-error")
        async def raise_auth_error():
            raise AuthenticationError("Token expired")

        @app.get("/forbidden")
        async def raise_forbidden():
            raise AuthorizationError("Admin access required")

        @app.get("/rate-limit")
        async def raise_rate_limit():
            raise RateLimitError()

        @app.get("/service-unavailable")
        async def raise_service_unavailable():
            raise ServiceUnavailableError("OpenAI")

        @app.get("/http-error")
        async def raise_http_error():
            raise HTTPException(status_code=404, detail="Custom not found")

        return app

    @pytest.fixture
    def client(self, test_app):
        """Create a test client."""
        return TestClient(test_app, raise_server_exceptions=True)

    def test_not_found_endpoint(self, client):
        """Test NotFoundError returns 404."""
        response = client.get("/not-found")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_validation_error_endpoint(self, client):
        """Test ValidationError returns 400."""
        response = client.get("/validation-error")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_duplicate_error_endpoint(self, client):
        """Test DuplicateError returns 409."""
        response = client.get("/duplicate")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DUPLICATE"

    def test_auth_error_endpoint(self, client):
        """Test AuthenticationError returns 401."""
        response = client.get("/auth-error")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_ERROR"

    def test_forbidden_error_endpoint(self, client):
        """Test AuthorizationError returns 403."""
        response = client.get("/forbidden")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_rate_limit_error_endpoint(self, client):
        """Test RateLimitError returns 429."""
        response = client.get("/rate-limit")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    def test_service_unavailable_error_endpoint(self, client):
        """Test ServiceUnavailableError returns 503."""
        response = client.get("/service-unavailable")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"

    def test_http_error_endpoint(self, client):
        """Test HTTPException is handled properly."""
        response = client.get("/http-error")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_generic_exception_handler_integration(self):
        """Test generic exception handler through direct call."""
        # Test generic handler directly since TestClient re-raises in some cases
        request = MagicMock()
        request.url = MagicMock()
        request.url.path = "/test"

        exc = ValueError("Unexpected error")
        response = await generic_exception_handler(request, exc)

        import json
        body = json.loads(response.body.decode())
        assert response.status_code == 500
        assert body["error"]["code"] == "INTERNAL_ERROR"
