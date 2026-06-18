from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date
from enum import Enum

FORMAT_VERSION = 1

TEAM_SEATS = 5

# Ed25519 public key — raw bytes, base64-encoded.
# The matching private key is kept offline; never commit it.
PUBLIC_KEY_B64 = "tJLH8c7Jdm7qnQBQM4O0byrOf8L1cGJGVXJ45avf0fU="


def _public_key_bytes() -> bytes:
    return base64.b64decode(PUBLIC_KEY_B64)


class Tier(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class LicenseInfo:
    licensee_name: str
    licensee_email: str
    tier: Tier
    seats: int          # 1 = Personal, TEAM_SEATS = Team, 0 = Enterprise (unlimited)
    updates_until: date
    issued_at: date
    format_version: int = FORMAT_VERSION

    @property
    def updates_expired(self) -> bool:
        return date.today() > self.updates_until

    @property
    def seats_display(self) -> str:
        if self.tier == Tier.ENTERPRISE:
            return "Unlimited"
        if self.tier == Tier.TEAM:
            return f"{self.seats} seats"
        return "Personal"

    @property
    def tier_display(self) -> str:
        return {
            Tier.PERSONAL: "Personal License",
            Tier.TEAM: f"Team License ({self.seats_display})",
            Tier.ENTERPRISE: "Enterprise License (Unlimited)",
        }[self.tier]
