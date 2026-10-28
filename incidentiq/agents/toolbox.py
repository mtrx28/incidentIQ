"""Runs one planned tool call after checking its name and arguments."""

from collections.abc import Callable

from incidentiq.schemas import PlanStep, ToolResult
from incidentiq.tools import ToolError
from incidentiq.tools.logs import log_search
from incidentiq.tools.metrics import metrics_query

ALLOWED_ARGS = {
    "metrics_query": {"service", "metric", "start", "end", "aggregation"},
    "log_search": {"service", "start", "end", "query", "level", "limit"},
    "runbook_retrieve": {"query", "k"},
}
REQUIRED_ARGS = {
    "metrics_query": {"service", "metric"},
    "log_search": set(),
    "runbook_retrieve": {"query"},
}
INTEGER_ARGS = {"limit", "k"}


def _clean_args(step: PlanStep) -> dict:
    allowed, required = ALLOWED_ARGS[step.tool], REQUIRED_ARGS[step.tool]
    unknown = set(step.args) - allowed
    if unknown:
        raise ToolError(f"{step.tool} has no argument(s) {sorted(unknown)}; allowed: {sorted(allowed)}")
    args = {k: v for k, v in step.args.items() if v is not None and v != ""}
    missing = required - set(args)
    if missing:
        raise ToolError(f"{step.tool} needs argument(s) {sorted(missing)}")
    for name in INTEGER_ARGS & set(args):
        try:
            args[name] = int(args[name])
        except (TypeError, ValueError) as exc:
            raise ToolError(f"{name} must be a whole number") from exc
    return args


class ToolBox:
    """The three tools for one incident.

    `runbook_search` is injected so tests (and the keyword baseline) can replace pgvector; by
    default it opens a database connection on first use.
    """

    def __init__(self, incident_id: str,
                 runbook_search: Callable[..., ToolResult] | None = None):
        self.incident_id = incident_id
        self._runbook_search = runbook_search
        self._conn = None

    def _default_runbook_search(self, query: str, k: int = 3) -> ToolResult:
        from incidentiq.store import db
        from incidentiq.tools.runbooks import runbook_retrieve

        if self._conn is None:
            self._conn = db.connect()
        return runbook_retrieve(query, k, conn=self._conn)

    def run(self, step: PlanStep) -> ToolResult:
        args = _clean_args(step)
        try:
            if step.tool == "metrics_query":
                return metrics_query(self.incident_id, **args)
            if step.tool == "log_search":
                return log_search(self.incident_id, **args)
            return (self._runbook_search or self._default_runbook_search)(**args)
        except TypeError as exc:  # a wrongly typed argument that slipped through
            raise ToolError(f"invalid arguments for {step.tool}: {exc}") from exc

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
