"""
Centralized error handling for the Inventory & Asset Management API.

Provides:
- APIError exception class for raising structured errors from routes/services
- register_error_handlers() to install global Flask error handlers
- Uniform JSON error envelope for all HTTP error responses
"""

from flask import jsonify


# ---------------------------------------------------------------------------
# Error code constants
# ---------------------------------------------------------------------------
class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"
    AUTH_ACCOUNT_INACTIVE = "AUTH_ACCOUNT_INACTIVE"
    AUTH_ROLE_FORBIDDEN = "AUTH_ROLE_FORBIDDEN"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# APIError exception
# ---------------------------------------------------------------------------
class APIError(Exception):
    """Raise from any route or service to produce a structured JSON error."""

    def __init__(self, message: str, code: str, status_code: int = 400, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details

    def to_dict(self):
        return {
            "success": False,
            "message": self.message,
            "errorCode": self.code,
            "details": self.details,
        }


def error_response(message: str, code: str, status_code: int, details=None):
    """Helper to build a JSON error response tuple without raising."""
    body = {
        "success": False,
        "message": message,
        "errorCode": code,
        "details": details,
    }
    return jsonify(body), status_code
def handle_api_error(exc):
    return jsonify(exc.to_dict()), exc.status_code

def handle_400(exc):
    return error_response(
        str(exc.description) if hasattr(exc, "description") else "Bad request",
        ErrorCode.VALIDATION_ERROR,
        400,
    )

def handle_404(exc):
    return error_response(
        "The requested resource was not found",
        ErrorCode.RESOURCE_NOT_FOUND,
        404,
    )

def handle_405(exc):
    return error_response(
        "Method not allowed",
        ErrorCode.VALIDATION_ERROR,
        405,
    )

def handle_500(exc):
    from flask import current_app
    current_app.logger.exception("Internal Server Error caught by error handler:")
    return error_response(
        "An internal server error occurred",
        ErrorCode.INTERNAL_ERROR,
        500,
    )

def handle_unhandled_exception(exc):
    from flask import current_app
    status_code = 500
    if hasattr(exc, "code"):
        status_code = exc.code
        
    current_app.logger.exception(f"Unhandled exception caught globally: {exc}")
    
    msg = str(exc) if current_app.config.get("DEBUG", False) else "An unexpected error occurred. Please try again later."
    return error_response(
        message=msg,
        code=ErrorCode.INTERNAL_ERROR,
        status_code=status_code,
    )

def register_error_handlers(app):
    """Install JSON error handlers on the Flask app."""
    app.register_error_handler(APIError, handle_api_error)
    app.register_error_handler(400, handle_400)
    app.register_error_handler(404, handle_404)
    app.register_error_handler(405, handle_405)
    app.register_error_handler(500, handle_500)
    app.register_error_handler(Exception, handle_unhandled_exception)
