"""Read-only tools the agent can call. Each returns a ToolResult with citable evidence."""


from datetime import datetime


class ToolError(ValueError):
    """Bad tool arguments. The message tells the agent what to fix."""


def parse_time_arg(value: str | None, name: str) -> datetime | None:
    """Parse an optional ISO 8601 timestamp argument, or raise a ToolError the agent can act on."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ToolError(
            f"{name} must be a full ISO 8601 UTC timestamp such as 2026-03-01T14:00:00Z, "
            f"got {value!r}") from exc
    if parsed.tzinfo is None:
        raise ToolError(f"{name} needs a timezone, for example a trailing Z: got {value!r}")
    return parsed
