"""Shared error handling for local command-line helpers."""

import logging
import sys
from collections.abc import Callable

import httpx
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("mrd-demo")


def checked_json(response: httpx.Response) -> dict:
    """Raise actionable HTTP/JSON errors instead of consuming bad responses."""
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("API returned an invalid JSON response") from exc
    if not isinstance(payload, dict):
        raise ValueError("API returned an unexpected JSON response shape")
    return payload


def run_cli(action: Callable[[], None]) -> int:
    """Run a CLI action, report expected failures, and avoid raw tracebacks."""
    try:
        action()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        print(f"API returned HTTP {exc.response.status_code}: {detail}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"Could not reach the Orders API: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(
            f"Database operation failed ({type(exc).__name__}). Check DATABASE_URL and PostgreSQL.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(f"Demo command failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Unexpected command failure")
        print("Demo command failed unexpectedly; see the command log for details.", file=sys.stderr)
        return 1
    return 0
