"""PII and secret redaction. Everything that can reach the LLM goes through here first.

    clean_text, findings = redact(text)

Detection is layered regexes plus checksums (Luhn for cards, Verhoeff for Aadhaar) and a
high-entropy token detector. Rules run in priority order; a later rule never touches text that an
earlier one already claimed. Values are replaced with typed placeholders such as [EMAIL_1]. A
`Redactor` keeps the value-to-placeholder map for one incident, so the agent can still see that two
log lines mention "the same user".

Known limits (also measured in eval/redaction_eval.py, see docs/redaction.md):
  * Names are only caught after a `user=` key. There is no NER, so free-text names are missed.
  * Phone numbers need a leading `+`.
  * 12-digit IDs that merely look like Aadhaar numbers can still pass the checksum (about 1 in 10).
"""

import math
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from incidentiq.checksums import luhn_valid, verhoeff_valid
from incidentiq.schemas import ToolResult

# --- Patterns -----------------------------------------------------------------------------

_URL_CREDENTIALS = re.compile(r"[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]+)(?=@)", re.IGNORECASE)
_AWS_KEY = re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9])")
_BEARER = re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{16,})", re.IGNORECASE)
_KEY_VALUE = re.compile(
    r"(?<![A-Za-z])(?:api[_-]?key|apikey|secret|token|passwd|password|pwd|"
    r"access[_-]?key(?:[_-]?id)?)\s*[=:]\s*[\"']?([^\s\"',;]{6,})",
    re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_PHONE = re.compile(r"(?<![\w+])\+\d{1,3}(?:[ -]?\d{2,6}){2,4}(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_IPV4 = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?!\d)")
_USER_NAME = re.compile(r"\buser=([A-Z][a-z]+(?: [A-Z][a-z]+)+)")
_TOKEN_CANDIDATE = re.compile(r"[A-Za-z0-9_+/-]{24,}={0,2}")  # '=' only as base64 padding

PLACEHOLDER_CLASS = {
    "email": "EMAIL", "phone": "PHONE", "name": "NAME", "card": "CARD", "aadhaar": "ID",
    "ip": "IP", "secret_password": "SECRET", "secret_token": "SECRET",
    "secret_apikey": "SECRET", "secret_aws": "SECRET",
}


@dataclass(frozen=True)
class Finding:
    """One redacted span. Positions refer to the original text. The value is not kept."""

    kind: str  # a key of PLACEHOLDER_CLASS
    detector: str  # the rule that fired
    placeholder: str
    start: int
    end: int


Span = tuple[int, int, str, str]  # start, end, kind, detector


def _entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def _group_span(match: re.Match, group: int = 1) -> tuple[int, int]:
    return match.start(group), match.end(group)


# --- Detectors (each yields spans; order below is priority order) -------------------------


def _url_credentials(text: str, **_) -> Iterator[Span]:
    for m in _URL_CREDENTIALS.finditer(text):
        yield (*_group_span(m), "secret_password", "url_credentials")


def _aws_key(text: str, **_) -> Iterator[Span]:
    for m in _AWS_KEY.finditer(text):
        yield (m.start(), m.end(), "secret_aws", "aws_key")


def _bearer(text: str, **_) -> Iterator[Span]:
    for m in _BEARER.finditer(text):
        yield (*_group_span(m), "secret_token", "bearer_token")


def _key_value(text: str, **_) -> Iterator[Span]:
    for m in _KEY_VALUE.finditer(text):
        name = m.group(0).lower()
        kind = ("secret_password" if any(w in name for w in ("pass", "pwd"))
                else "secret_token" if name.startswith("token")
                else "secret_apikey")
        yield (*_group_span(m), kind, "key_value_secret")


def _email(text: str, **_) -> Iterator[Span]:
    for m in _EMAIL.finditer(text):
        yield (m.start(), m.end(), "email", "email")


def _card(text: str, **_) -> Iterator[Span]:
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            yield (m.start(), m.end(), "card", "card_luhn")


def _phone(text: str, **_) -> Iterator[Span]:
    for m in _PHONE.finditer(text):
        if 8 <= len(re.sub(r"\D", "", m.group(0))) <= 15:
            yield (m.start(), m.end(), "phone", "phone")


def _aadhaar(text: str, verhoeff: bool = True, **_) -> Iterator[Span]:
    for m in _AADHAAR.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if not verhoeff or verhoeff_valid(digits):
            yield (m.start(), m.end(), "aadhaar", "aadhaar_verhoeff" if verhoeff else "aadhaar")


def _ip(text: str, **_) -> Iterator[Span]:
    for m in _IPV4.finditer(text):
        yield (m.start(), m.end(), "ip", "ipv4")


def _user_name(text: str, **_) -> Iterator[Span]:
    for m in _USER_NAME.finditer(text):
        yield (*_group_span(m), "name", "user_field_name")


def _looks_like_identifier(token: str) -> bool:
    """snake_case or kebab-case names built from word fragments, e.g. a migration name."""
    words = re.findall(r"[a-z]{4,}", token)
    return len(re.findall(r"[_-]", token)) >= 2 and len(words) >= 2


def _entropy_token(text: str, **_) -> Iterator[Span]:
    """Long random-looking strings that no other rule recognised."""
    for m in _TOKEN_CANDIDATE.finditer(text):
        token = m.group(0)
        letters_and_digits = re.sub(r"[^A-Za-z0-9]", "", token)
        if re.fullmatch(r"[0-9a-fA-F]+", token) and len(token) < 32:
            continue  # IDs and hashes of ordinary length are not secrets
        if _looks_like_identifier(token):
            continue
        if (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)
                and len(letters_and_digits) >= 20 and _entropy(token) >= 3.6):
            yield (m.start(), m.end(), "secret_token", "entropy")


DETECTORS: list[Callable[..., Iterator[Span]]] = [
    _url_credentials, _aws_key, _bearer, _key_value, _email, _card, _phone, _aadhaar, _ip,
    _user_name, _entropy_token,
]


def _normalise(kind: str, value: str) -> str:
    if kind == "email":
        return value.lower()
    if kind in ("card", "aadhaar", "phone"):
        return re.sub(r"[^\d+]", "", value)
    return value


@dataclass
class Redactor:
    """Holds the placeholder numbering for one incident. Use one per incident."""

    verhoeff: bool = True  # validate Aadhaar-like IDs with the Verhoeff checksum
    _seen: dict[tuple[str, str], str] = field(default_factory=dict)
    _counts: Counter = field(default_factory=Counter)

    def _placeholder(self, kind: str, value: str) -> str:
        cls = PLACEHOLDER_CLASS[kind]
        key = (cls, _normalise(kind, value))
        if key not in self._seen:
            self._counts[cls] += 1
            self._seen[key] = f"[{cls}_{self._counts[cls]}]"
        return self._seen[key]

    def redact(self, text: str) -> tuple[str, list[Finding]]:
        claimed: list[Span] = []
        for detector in DETECTORS:
            for span in detector(text, verhoeff=self.verhoeff):
                if not any(span[0] < c[1] and c[0] < span[1] for c in claimed):
                    claimed.append(span)
        claimed.sort()
        findings, pieces, pos = [], [], 0
        for start, end, kind, detector in claimed:
            placeholder = self._placeholder(kind, text[start:end])
            findings.append(Finding(kind, detector, placeholder, start, end))
            pieces += [text[pos:start], placeholder]
            pos = end
        pieces.append(text[pos:])
        return "".join(pieces), findings


def redact(text: str, redactor: Redactor | None = None) -> tuple[str, list[Finding]]:
    """Redact one string. Without a redactor the placeholder numbering starts fresh."""
    return (redactor or Redactor()).redact(text)


def redact_tool_result(result: ToolResult, redactor: Redactor) -> tuple[ToolResult, list[Finding]]:
    """Redact every free-text field of a tool result. Evidence IDs are left alone."""
    findings: list[Finding] = []

    def clean(text: str) -> str:
        out, found = redactor.redact(text)
        findings.extend(found)
        return out

    args = {k: clean(v) if isinstance(v, str) else v for k, v in result.args.items()}
    evidence = [e.model_copy(update={"excerpt": clean(e.excerpt)}) for e in result.evidence]
    cleaned = result.model_copy(
        update={"args": args, "summary": clean(result.summary), "evidence": evidence})
    return cleaned, findings
