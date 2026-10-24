"""Hand-written PII/secret lines in formats the injected dataset does not use.

The injected set (data/pii_manifest.json) comes from the same generator that the detectors were
written against, so a high score there says little about real logs. These cases were written
separately, as varied and awkward as logs tend to be, and the redactor was not tuned to them.
Values are marked with {{...}}; the markers are stripped to build the log line.

Fake values only. Vendor-specific key formats are altered so GitHub secret scanning does not
mistake them for real credentials.
"""

import re

from incidentiq.checksums import verhoeff_check_digit

_AADHAAR_BODY = "23456789012"
_AADHAAR = _AADHAAR_BODY + verhoeff_check_digit(_AADHAAR_BODY)

# (type, line with the sensitive value wrapped in {{ }})
_RAW: list[tuple[str, str]] = [
    # phone numbers
    ("phone", "callback requested on {{98765 43210}} for order ORD-48213"),
    ("phone", "customer phone {{09876543210}} verified by agent"),
    ("phone", "delivery contact {{(415) 555-0132}} added to shipment"),
    ("phone", "otp sent to {{+91 98 7654 3210}} via sms gateway"),
    ("phone", "whatsapp opt-in recorded for {{+919876543210}}"),
    ("phone", "support call from {{+44 (0)20 7946 0958}} transferred"),
    # names in free text
    ("name", "Customer {{Priya Sharma}} called about a delayed refund"),
    ("name", "ticket opened by {{Rahul Iyer}} regarding duplicate charge"),
    ("name", "shipping to {{Ananya Gupta}}, 14 MG Road, Pune"),
    ("name", 'account holder="{{Meera Nair}}" flagged for review'),
    ("name", "user={{Priya Sharma}} updated address"),
    # emails
    ("email", "reply-to: {{Priya.Sharma@Example.COM}}"),
    ("email", "callback url contact%3D{{priya.sharma%40gmail.com}}"),
    ("email", "from <{{a.b+tag@sub.mail.co.in}}> accepted by relay"),
    ("email", "notified {{ops-team@corp.shop}} about queue depth"),
    # cards
    ("card", "pan={{4111111111111111}} declined by issuer"),
    ("card", "card number {{4111.1111.1111.1111}} rejected by validator"),
    ("card", "amex {{3782 822463 10005}} authorised"),
    # government IDs
    ("aadhaar", "kyc id {{" + _AADHAAR[:4] + " " + _AADHAAR[4:8] + " " + _AADHAAR[8:] + "}} accepted"),
    ("aadhaar", "kyc id {{" + _AADHAAR[:4] + "." + _AADHAAR[4:8] + "." + _AADHAAR[8:] + "}} accepted"),
    ("aadhaar", "uid={{" + _AADHAAR + "}} matched"),
    ("gov_id", "pan card {{ABCDE1234F}} submitted for payout"),
    # IP addresses
    ("ip", "x-forwarded-for: {{198.51.100.23}}, {{10.0.0.1}}"),
    ("ip", "connection from {{203.0.113.77}} closed"),
    ("ip", "src={{192.168.1.20}}:5432 refused"),
    ("ip", "client {{2001:db8:85a3::8a2e:370:7334}} connected"),
    # passwords
    ("secret_password", "mysql -u root --password={{Hunter2!x9z}} -h db-1"),
    ("secret_password", 'config dump {"password": "{{Zebra#7781q}}", "port": 5432}'),
    ("secret_password", "env DB_PASSWORD={{s3cr3tValue9}} loaded"),
    ("secret_password", "login with pwd {{Maple#4821x}} failed"),
    ("secret_password", "mysql -u root -p{{Winter2024!x}} -h db-1"),
    ("secret_password", "connecting to redis://:{{p4ssW0rdX9}}@redis-1:6379/0"),
    # tokens and keys
    ("secret_token", "Authorization: Basic {{dXNlcjpTdXBlclNlY3JldDEyMw==}}"),
    ("secret_token", "jwt={{eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1LTEyMzQ1NiIsInJvbGUiOiJhZG1pbiJ9."
                     "c2lnbmF0dXJlLWJ5dGVzLWhlcmUtMTIzNDU2}}"),
    ("secret_token", "session cookie {{9f8e7d6c5b4a39281706f5e4d3c2b1a0}} rotated"),
    ("secret_token", "token {{ghx_abcdEFGH1234ijklMNOP5678qrstUVWX9012}} revoked"),
    ("secret_apikey", "x-api-key: {{kq9Zx2LmN8vB4tYw7RcD1sFh}}"),
    ("secret_apikey", "client_secret={{Qm4xT9pLw2Zv8NcR7sDa1}} loaded"),
    ("secret_apikey", "GET https://api.corp.shop/v1/orders?api_key={{abcd1234EFGH5678ijkl9012}}&limit=10"),
    ("secret_aws", "temporary credentials {{ASIAQWERTYUI01234567}} issued"),
    ("secret_aws", "aws_secret_access_key={{wJalrXUtnFEMI/K7MDENG/bPxRfiCYzzzzzzzzzzz}}"),
]

_MARKER = re.compile(r"\{\{(.+?)\}\}")


def hard_cases() -> list[dict]:
    """Each case: {type, line, value, start, end} with positions in the unmarked line."""
    cases = []
    for kind, template in _RAW:
        line = _MARKER.sub(r"\1", template)
        for value in _MARKER.findall(template):
            start = line.index(value)
            cases.append({"type": kind, "line": line, "value": value,
                          "start": start, "end": start + len(value)})
    return cases
