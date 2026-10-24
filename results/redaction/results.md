# Redaction evaluation

Recall: **601 of 601 injected items caught (100.0%)**. A value counts as caught only if the full original string is gone from the redacted line.

| Type | Caught | Total | Recall |
|---|---|---|---|
| aadhaar | 59 | 59 | 100.0% |
| card | 60 | 60 | 100.0% |
| email | 60 | 60 | 100.0% |
| ip | 54 | 54 | 100.0% |
| name | 58 | 58 | 100.0% |
| phone | 61 | 61 | 100.0% |
| secret_apikey | 60 | 60 | 100.0% |
| secret_aws | 61 | 61 | 100.0% |
| secret_password | 66 | 66 | 100.0% |
| secret_token | 62 | 62 | 100.0% |

## False positives

Clean lines altered: **119 of 20656 (0.6%)**.

| Look-alike | Tokens | Touched | Rate | Detector that fired |
|---|---|---|---|---|
| hex_id | 4780 | 1 | 0.0% | aadhaar_verhoeff (1) |
| order_ref | 968 | 118 | 12.2% | aadhaar_verhoeff (118) |
| sha | 689 | 0 | 0.0% | - |
| version | 746 | 0 | 0.0% | - |

Spurious findings by detector (findings that overlap no injected item): aadhaar_verhoeff: 119

Gold evidence log lines altered by redaction: 6 of 116.

## Ablation: Aadhaar without the Verhoeff checksum

Without the checksum, Aadhaar recall is 100.0% and 100.0% of 12-digit order refs are touched (with the checksum: 100.0% and 12.2%).

## Misses (0)


## Hard cases (hand-written, formats the injected data does not use)

**25 of 42 caught (59.5%)**. The injected-set score above is optimistic because the detectors were written against the same generator; this is the more realistic number.

| Type | Caught | Total | Recall |
|---|---|---|---|
| aadhaar | 2 | 3 | 66.7% |
| card | 2 | 3 | 66.7% |
| email | 3 | 4 | 75.0% |
| gov_id | 0 | 1 | 0.0% |
| ip | 4 | 5 | 80.0% |
| name | 1 | 5 | 20.0% |
| phone | 2 | 6 | 33.3% |
| secret_apikey | 3 | 3 | 100.0% |
| secret_aws | 2 | 2 | 100.0% |
| secret_password | 2 | 6 | 33.3% |
| secret_token | 4 | 4 | 100.0% |

### Hard-case misses (17)

- [phone] `98765 43210` -> `callback requested on 98765 43210 for order ORD-48213`
- [phone] `09876543210` -> `customer phone 09876543210 verified by agent`
- [phone] `(415) 555-0132` -> `delivery contact (415) 555-0132 added to shipment`
- [phone] `+44 (0)20 7946 0958` -> `support call from +44 (0)20 7946 0958 transferred`
- [name] `Priya Sharma` -> `Customer Priya Sharma called about a delayed refund`
- [name] `Rahul Iyer` -> `ticket opened by Rahul Iyer regarding duplicate charge`
- [name] `Ananya Gupta` -> `shipping to Ananya Gupta, 14 MG Road, Pune`
- [name] `Meera Nair` -> `account holder="Meera Nair" flagged for review`
- [email] `priya.sharma%40gmail.com` -> `callback url contact%3Dpriya.sharma%40gmail.com`
- [card] `4111.1111.1111.1111` -> `card number 4111.1111.1111.1111 rejected by validator`
- [aadhaar] `2345.6789.0124` -> `kyc id 2345.6789.0124 accepted`
- [gov_id] `ABCDE1234F` -> `pan card ABCDE1234F submitted for payout`
- [ip] `2001:db8:85a3::8a2e:370:7334` -> `client 2001:db8:85a3::8a2e:370:7334 connected`
- [secret_password] `Zebra#7781q` -> `config dump {"password": "Zebra#7781q", "port": 5432}`
- [secret_password] `Maple#4821x` -> `login with pwd Maple#4821x failed`
- [secret_password] `Winter2024!x` -> `mysql -u root -pWinter2024!x -h db-1`
- [secret_password] `p4ssW0rdX9` -> `connecting to redis://:p4ssW0rdX9@redis-1:6379/0`
