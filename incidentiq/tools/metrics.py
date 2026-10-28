"""metrics_query: summarise one time series instead of returning thousands of raw points."""

from dataclasses import dataclass
from statistics import mean, pstdev

from incidentiq import data
from incidentiq.schemas import Evidence, ToolResult
from incidentiq.tools import ToolError, parse_time_arg

AGGREGATIONS = ("mean", "max", "min", "last")
MIN_CHANGE_SCORE = 3.0  # shift must be at least this many baseline standard deviations
MIN_POINTS_FOR_CHANGE = 8  # the detector needs a few points on each side of a change


@dataclass
class ChangePoint:
    ts: str
    before_mean: float
    after_mean: float
    score: float


@dataclass
class MetricSummary:
    series_id: str
    service: str
    metric: str
    start: str
    end: str
    points: int
    minimum: float
    maximum: float
    average: float
    last: float
    aggregate: float
    change_point: ChangePoint | None
    notable: list[tuple[str, float, str]]  # (timestamp, value, why)


def find_change_point(points: list[tuple[str, float]]) -> ChangePoint | None:
    """Best single split of the series: biggest shift in mean, scaled by the noise before it."""
    values = [v for _, v in points]
    best: ChangePoint | None = None
    for k in range(3, len(values) - 2):
        before, after = values[:k], values[k:]
        noise = max(pstdev(before), 0.01 * abs(mean(before)), 1e-6)
        score = abs(mean(after) - mean(before)) / noise
        if best is None or score > best.score:
            best = ChangePoint(points[k][0], mean(before), mean(after), score)
    if best is None or best.score < MIN_CHANGE_SCORE:
        return None
    return best


def query_metric(
    incident_id: str, service: str, metric: str,
    start: str | None = None, end: str | None = None, aggregation: str = "mean",
) -> MetricSummary:
    series = data.load_metrics(incident_id)
    if service not in data.known_services(incident_id):
        raise ToolError(f"unknown service {service!r}; choose from {data.known_services(incident_id)}")
    if metric not in data.known_metrics(incident_id):
        raise ToolError(f"unknown metric {metric!r}; choose from {data.known_metrics(incident_id)}")
    if aggregation not in AGGREGATIONS:
        raise ToolError(f"aggregation must be one of {AGGREGATIONS}")

    series_id, all_points = series[(service, metric)]
    lo, hi = parse_time_arg(start, "start"), parse_time_arg(end, "end")
    points = [
        (ts, v) for ts, v in all_points
        if (lo is None or data.parse_ts(ts) >= lo) and (hi is None or data.parse_ts(ts) <= hi)
    ]
    if len(points) < 2:
        raise ToolError(
            f"no data for {service}.{metric} in that range; "
            f"data covers {all_points[0][0]} to {all_points[-1][0]}")

    values = [v for _, v in points]
    aggregate = {"mean": mean(values), "max": max(values), "min": min(values),
                 "last": values[-1]}[aggregation]
    peak = max(points, key=lambda p: p[1])
    trough = min(points, key=lambda p: p[1])
    change = find_change_point(points)
    notable = [(peak[0], peak[1], "peak"), (trough[0], trough[1], "lowest")]
    if change:
        notable.append((change.ts, dict(points)[change.ts], "first point after the change"))
    notable.append((points[-1][0], points[-1][1], "last"))

    return MetricSummary(
        series_id=series_id, service=service, metric=metric, start=points[0][0],
        end=points[-1][0], points=len(points), minimum=min(values), maximum=max(values),
        average=mean(values), last=values[-1], aggregate=aggregate, change_point=change,
        notable=sorted(set(notable)))


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def metrics_query(
    incident_id: str, service: str, metric: str,
    start: str | None = None, end: str | None = None, aggregation: str = "mean",
) -> ToolResult:
    s = query_metric(incident_id, service, metric, start, end, aggregation)
    lines = [
        f"{s.service}.{s.metric} from {s.start} to {s.end} ({s.points} points, 5-minute steps): "
        f"min={_fmt(s.minimum)} max={_fmt(s.maximum)} mean={_fmt(s.average)} last={_fmt(s.last)}; "
        f"{aggregation}={_fmt(s.aggregate)}."
    ]
    if s.change_point:
        c = s.change_point
        lines.append(
            f"Change detected at {c.ts}: mean {_fmt(c.before_mean)} before, "
            f"{_fmt(c.after_mean)} after ({c.score:.1f} baseline standard deviations).")
    elif s.points < MIN_POINTS_FOR_CHANGE:
        lines.append(f"Only {s.points} points in this range, too few to test for a change; "
                     f"use a wider range.")
    else:
        lines.append("No significant change detected in this range.")
    lines.append("Notable points: " + "; ".join(
        f"{ts} = {_fmt(v)} ({why})" for ts, v, why in s.notable) + ".")
    excerpt = " ".join(lines)
    return ToolResult(
        tool="metrics_query",
        args={"service": service, "metric": metric, "start": start, "end": end,
              "aggregation": aggregation},
        summary=f"{s.series_id}: {lines[1]}",
        evidence=[Evidence(evidence_id=s.series_id, kind="metric", excerpt=excerpt)])
