import groq
import httpx

from app.llm.errors import ErrorClass, classify_error, parse_retry_after_seconds


def _status_error(cls, message: str) -> Exception:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=429, request=request)
    return cls(message, response=response, body=None)


def test_classifies_rate_limit():
    exc = _status_error(groq.RateLimitError, "Rate limit reached. Please try again in 19m41.088s.")
    assert classify_error(exc) is ErrorClass.RATE_LIMIT


def test_classifies_auth_error():
    exc = _status_error(groq.AuthenticationError, "Invalid API Key")
    assert classify_error(exc) is ErrorClass.AUTH


def test_classifies_context_length_as_context_length():
    exc = _status_error(groq.BadRequestError, "This model's maximum context length is 8192 tokens")
    assert classify_error(exc) is ErrorClass.CONTEXT_LENGTH


def test_classifies_other_bad_request_as_unknown():
    exc = _status_error(groq.BadRequestError, "Invalid 'temperature': must be between 0 and 2")
    assert classify_error(exc) is ErrorClass.UNKNOWN


def test_classifies_timeout_as_transient():
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    exc = groq.APITimeoutError(request=request)
    assert classify_error(exc) is ErrorClass.TRANSIENT


def test_classifies_plain_exception_as_unknown():
    assert classify_error(ValueError("something else entirely")) is ErrorClass.UNKNOWN


def test_parses_minutes_and_seconds():
    exc = ValueError("Rate limit reached. Please try again in 19m41.088s. Need more tokens?")
    assert parse_retry_after_seconds(exc) == 19 * 60 + 41.088


def test_parses_seconds_only():
    exc = ValueError("Please try again in 45.5s")
    assert parse_retry_after_seconds(exc) == 45.5


def test_returns_none_when_no_retry_info():
    assert parse_retry_after_seconds(ValueError("no retry info here")) is None
