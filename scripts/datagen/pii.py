"""Synthetic PII and secret generators, and the log-line templates that carry them.

Every value is fake. Cards are Luhn-valid test numbers, AWS keys use the AKIA prefix with random
characters, and so on. The generator records each injected value with its type and position so the
redaction layer can be scored against ground truth.
"""

import random
import string

from incidentiq.checksums import luhn_check_digit, luhn_valid, verhoeff_check_digit

__all__ = ["PII_LINES", "PII_TYPES", "generate", "luhn_valid"]

PII_TYPES = [
    "email", "phone", "name", "card", "aadhaar", "ip",
    "secret_password", "secret_token", "secret_apikey", "secret_aws",
]

_FIRST = ["Priya", "Rahul", "Ananya", "Vikram", "Meera", "Arjun", "Sneha", "Karthik", "Aisha",
          "John", "Emily", "Carlos", "Fatima", "Wei", "Olga", "Liam"]
_LAST = ["Sharma", "Iyer", "Patel", "Reddy", "Nair", "Gupta", "Khan", "Menon", "Singh",
         "Smith", "Johnson", "Garcia", "Chen", "Petrov", "Murphy", "Okafor"]
_DOMAINS = ["gmail.com", "outlook.com", "yahoo.in", "proton.me", "example.org", "mail.co.uk"]
_WORDS = ["Maple", "Tiger", "Orbit", "Cobalt", "Monsoon", "Falcon", "Pepper", "Harbor"]


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))



def generate(kind: str, rng: random.Random) -> str:
    if kind == "email":
        first, last = rng.choice(_FIRST), rng.choice(_LAST)
        sep = rng.choice([".", "_", ""])
        return f"{first}{sep}{last}{rng.randint(1, 99)}@{rng.choice(_DOMAINS)}".lower()
    if kind == "phone":
        style = rng.randint(0, 4)
        mobile = rng.choice("6789") + _digits(rng, 9)
        if style == 0:
            return f"+91{mobile}"
        if style == 1:
            return f"+91 {mobile[:5]} {mobile[5:]}"
        if style == 2:
            return f"+91-{mobile[:5]}-{mobile[5:]}"
        if style == 3:
            return f"+1 {rng.randint(201, 989)}-555-{_digits(rng, 4)}"
        return f"+44 7{_digits(rng, 3)} {_digits(rng, 6)}"
    if kind == "name":
        return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
    if kind == "card":
        partial = rng.choice(["4111", "4539", "5500", "5425"]) + _digits(rng, 11)
        number = partial + luhn_check_digit(partial)
        style = rng.randint(0, 2)
        if style == 0:
            return number
        sep = " " if style == 1 else "-"
        return sep.join(number[i:i + 4] for i in range(0, 16, 4))
    if kind == "aadhaar":
        # Real Aadhaar numbers end in a Verhoeff check digit, so these do too. The random draws
        # are the same as before (11 digits, the last discarded) to keep the rest of the
        # generated data unchanged.
        body = str(rng.randint(2, 9)) + _digits(rng, 11)[:10]
        number = body + verhoeff_check_digit(body)
        return number if rng.random() < 0.4 else " ".join(number[i:i + 4] for i in (0, 4, 8))
    if kind == "ip":
        if rng.random() < 0.3:
            return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        return (f"{rng.randint(11, 223)}.{rng.randint(0, 255)}."
                f"{rng.randint(0, 255)}.{rng.randint(1, 254)}")
    if kind == "secret_password":
        return f"{rng.choice(_WORDS)}{rng.choice('#!_-')}{rng.randint(1000, 9999)}{rng.choice('xqz')}"
    if kind == "secret_token":
        alphabet = string.ascii_letters + string.digits + "-_"
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(32, 40)))
    if kind == "secret_apikey":
        alphabet = string.ascii_letters + string.digits
        # Custom prefixes on purpose: real vendor formats (e.g. Stripe's sk_live_) make GitHub's
        # secret scanning block pushes of this fake data.
        prefix = rng.choice(["iq_sk_", "iq_pk_", "key_"])
        return prefix + "".join(rng.choice(alphabet) for _ in range(24))
    if kind == "secret_aws":
        # Real AWS key IDs only use A-Z and 2-7. Every fake key includes one of 0/1/8/9 so GitHub's
        # secret scanning does not mistake this data for a leaked key. The redactor must not rely
        # on that: its pattern accepts any [A-Z0-9].
        body = [rng.choice(string.ascii_uppercase + string.digits) for _ in range(16)]
        body[rng.randrange(16)] = rng.choice("0189")
        return "AKIA" + "".join(body)
    raise ValueError(f"unknown PII type {kind}")


# (service, level, template). These lines are the only ones that carry injected values.
PII_LINES: dict[str, list[tuple[str, str, str]]] = {
    "email": [
        ("auth", "WARN", "login failed for {pii:email} reason=invalid_password attempt={int:1:5}"),
        ("notifications", "INFO", "receipt email queued to {pii:email} order=ORD-{int:10000:99999}"),
        ("checkout", "INFO", "guest checkout started contact={pii:email}"),
    ],
    "phone": [
        ("notifications", "INFO", "sms otp dispatched to {pii:phone} provider=sms-gw msg_id={hex:10}"),
        ("auth", "INFO", "phone verification requested number={pii:phone}"),
    ],
    "name": [
        ("checkout", "INFO", "order placed user={pii:name} items={int:1:6} total_inr={int:299:19999}"),
        ("payments", "INFO", "refund issued user={pii:name} order=ORD-{int:10000:99999}"),
        ("auth", "INFO", "profile updated user={pii:name}"),
    ],
    "card": [
        ("payments", "INFO", "payment authorised card={pii:card} amount_inr={int:199:24999} "
         "auth_code={hex:6}"),
        ("payments", "WARN", "card tokenisation request pan={pii:card} retry=1"),
    ],
    "aadhaar": [
        ("auth", "INFO", "kyc verification passed id={pii:aadhaar} status=ok"),
        ("payments", "INFO", "payout kyc check aadhaar={pii:aadhaar} result=match"),
    ],
    "ip": [
        ("auth", "INFO", "login ok client_ip={pii:ip} session={hex:12}"),
        ("search", "INFO", "query served for {pii:ip} q='wireless headphones' hits={int:5:400}"),
        ("checkout", "INFO", "fraud check passed ip={pii:ip} score=0.{int:10:40}"),
    ],
    "secret_password": [
        ("inventory", "INFO", "connecting to postgres://inventory_app:{pii:secret_password}"
         "@inventory-db-1:5432/inventory pool=20"),
        ("notifications", "INFO", "opening mongodb://notify:{pii:secret_password}@notify-db-1:27017/queue"),
    ],
    "secret_token": [
        ("checkout", "DEBUG", "outbound request headers Authorization: Bearer {pii:secret_token}"),
        ("payments", "DEBUG", "gateway call headers Authorization: Bearer {pii:secret_token}"),
    ],
    "secret_apikey": [
        ("notifications", "INFO", "email provider call api_key={pii:secret_apikey} status=200"),
        ("search", "INFO", "indexer config loaded api_key={pii:secret_apikey} shards=4"),
    ],
    "secret_aws": [
        ("inventory", "INFO", "s3 upload using aws_access_key_id={pii:secret_aws} bucket=inventory-exports"),
        ("notifications", "INFO", "ses client init aws_access_key_id={pii:secret_aws} region=ap-south-1"),
    ],
}
