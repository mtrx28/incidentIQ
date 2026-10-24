"""Read-only tools the agent can call. Each returns a ToolResult with citable evidence."""


class ToolError(ValueError):
    """Bad tool arguments. The message tells the agent what to fix."""
