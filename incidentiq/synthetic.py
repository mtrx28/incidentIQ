"""Template-based log text shared by the data generator and the load-time log scaler.

The generator (scripts/generate_data.py) and incidentiq/data.py (INCIDENTIQ_LOG_SCALE=100) both
need the healthy-traffic templates and the function that fills them in, so they live here.
None of the templates contain PII or secrets. Some deliberately include hex IDs, build SHAs,
versions, long numbers and hostnames so the redaction false-positive rate is measured on
realistic look-alikes.
"""

import random
import re
from collections.abc import Callable

SEED = 20260301  # the one seed for the whole synthetic dataset
TOKEN = re.compile(r"\{(int|hex|pii|lk):([^}]+)\}")

NOISE: dict[str, list[tuple[str, str]]] = {
    "auth": [
        ("INFO", "token issued sub=u-{int:100000:999999} ttl=3600 request_id=req-{hex:8}"),
        ("INFO", "token validated sub=u-{int:100000:999999} latency_ms={int:1:9}"),
        ("INFO", "session refreshed session={hex:12} trace={hex:16}"),
        ("WARN", "slow ldap lookup took {int:350:900}ms"),
        ("INFO", "password policy check passed"),
    ],
    "checkout": [
        ("INFO", "cart loaded cart_id=c-{int:100000:999999} items={int:1:8} request_id=req-{hex:8}"),
        ("INFO", "POST /api/v1/checkout status=200 duration_ms={int:80:420} trace={hex:16}"),
        ("INFO", "order created order_ref={lk:order_ref} total_inr={int:199:24999}"),
        ("INFO", "inventory reserved sku=SKU-{int:1000:9999} qty={int:1:4}"),
        ("WARN", "retrying idempotent request attempt 1/3 request_id=req-{hex:8} (succeeded)"),
        ("INFO", "coupon applied code=FEST{int:10:50} discount_pct={int:5:30}"),
    ],
    "inventory": [
        ("INFO", "stock level query sku=SKU-{int:1000:9999} on_hand={int:0:900}"),
        ("INFO", "GET /api/v1/stock status=200 duration_ms={int:5:60} trace={hex:16}"),
        ("INFO", "reservation released sku=SKU-{int:1000:9999} qty={int:1:4}"),
        ("INFO", "warehouse sync batch={int:1000:9999} rows={int:100:5000} sha={hex:7}"),
        ("INFO", "shipment dispatched ref={lk:order_ref} carrier=express parcels={int:1:4}"),
        ("WARN", "slow request took {int:400:900}ms path=/api/v1/stock/bulk"),
    ],
    "notifications": [
        ("INFO", "email job dequeued job={hex:10} template=order_confirmation"),
        ("INFO", "push notification sent topic=order-updates delivered={int:1:300}"),
        ("INFO", "template rendered name=shipping_update version=v{lk:version}"),
        ("WARN", "provider rate hint: {int:80:99}% of hourly send quota used"),
        ("INFO", "queue depth={int:0:40} oldest_age_s={int:0:20}"),
    ],
    "payments": [
        ("INFO", "POST /api/v1/payments status=200 duration_ms={int:90:380} trace={hex:16}"),
        ("INFO", "gateway response code=00 gateway_ref={hex:12}"),
        ("INFO", "settlement batch closed batch={int:1000:9999} txns={int:50:900}"),
        ("INFO", "3ds challenge completed txn=TXN-{int:100000:999999}"),
        ("INFO", "reconciliation matched ref={lk:order_ref} ledger_entry={int:100000:999999}"),
        ("WARN", "gateway latency elevated {int:400:800}ms (within SLO)"),
    ],
    "search": [
        ("INFO", "GET /api/v1/search status=200 hits={int:0:500} duration_ms={int:20:140} trace={hex:16}"),
        ("INFO", "index refresh completed shard={int:0:3} docs={int:100000:900000}"),
        ("INFO", "autocomplete served prefix_len={int:2:6} duration_ms={int:3:25}"),
        ("INFO", "ranking model loaded version=v{lk:version} sha={hex:7}"),
        ("WARN", "slow request took {int:300:700}ms path=/api/v1/search"),
    ],
}

UNIVERSAL = [
    ("INFO", "healthcheck ok latency_ms={int:1:6}"),
    ("INFO", "metrics scrape served bytes={int:20000:90000}"),
    ("INFO", "config heartbeat ok revision={int:100:999}"),
    ("INFO", "gc pause {int:5:60}ms heap_used={int:40:68}%"),
]

# Symptom lines emitted by the affected service after the onset, whatever the cause.
SYMPTOM = [
    ("ERROR", "request failed status=500 path=/api/v1/{ep} request_id=req-{hex:8} "
     "duration_ms={int:20:30000}"),
    ("ERROR", "upstream returned 503 for /api/v1/{ep} request_id=req-{hex:8}"),
    ("WARN", "request error rate above SLO window=5m"),
    ("ERROR", "request failed status=502 path=/api/v1/{ep} request_id=req-{hex:8}"),
]


def _located(text: str, drawn: list[tuple[str, str]]) -> list[dict]:
    items = []
    for kind, value in drawn:
        start = text.find(value)
        assert start >= 0, (text, value)
        items.append({"type": kind, "value": value, "start": start, "end": start + len(value)})
    return items


def render(template: str, ctx: dict, rng: random.Random,
           draw_pii: Callable[[str, random.Random], str] | None = None,
           ) -> tuple[str, list[dict], list[dict]]:
    """Fill a template.

    Returns the message, the PII items injected into it, and the look-alike strings in it:
    harmless tokens (hex IDs, SHAs, versions, 12-digit order refs) that a redactor could mistake
    for PII. Release versions that come from the incident context are not tagged.
    `draw_pii` makes the value for a {pii:...} token; noise templates have none.
    """
    pii_drawn: list[tuple[str, str]] = []
    lookalikes: list[tuple[str, str]] = []

    def sub(match: re.Match) -> str:
        kind, arg = match.groups()
        if kind == "int":
            lo, hi = arg.split(":")
            return str(rng.randint(int(lo), int(hi)))
        if kind == "hex":
            value = "".join(rng.choice("0123456789abcdef") for _ in range(int(arg)))
            lookalikes.append(("sha" if arg == "7" else "hex_id", value))
            return value
        if kind == "lk":
            if arg == "version":
                value = f"{rng.randint(1, 9)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
            elif arg == "order_ref":
                value = str(rng.randint(202603000000, 202609999999))  # 12 digits, starts with 2
            else:
                raise ValueError(arg)
            lookalikes.append((arg, value))
            return value
        if draw_pii is None:
            raise ValueError(f"template needs a PII generator for {arg!r}")
        value = draw_pii(arg, rng)
        pii_drawn.append((arg, value))
        return value

    text = TOKEN.sub(sub, template).format_map(ctx)
    return text, _located(text, pii_drawn), _located(text, lookalikes)
