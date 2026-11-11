"""Strict input validation helpers shared by API routes."""
import math


class ValidationError(ValueError):
    """Raised when a client-supplied value is missing or malformed (maps to HTTP 400)."""


def parse_finite_number(value, field, *, min_value=None, max_value=None):
    """
    Convert `value` to a finite float or raise ValidationError.
    Rejects None, booleans, NaN, +/-Infinity and out-of-range numbers.
    """
    if value is None or isinstance(value, bool):
        raise ValidationError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a valid number")
    if not math.isfinite(number):
        raise ValidationError(f"{field} must be a finite number")
    if min_value is not None and number < min_value:
        raise ValidationError(f"{field} must be greater than or equal to {min_value}")
    if max_value is not None and number > max_value:
        raise ValidationError(f"{field} must be less than or equal to {max_value}")
    return number


def parse_nonempty_string(value, field, *, max_length=255):
    """Return a stripped non-empty string or raise ValidationError."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return value

