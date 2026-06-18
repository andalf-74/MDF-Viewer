"""Tests for the license module (LicenseInfo, LicenseManager)."""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from mdf_viewer.license.license_info import (
    FORMAT_VERSION,
    TEAM_SEATS,
    LicenseInfo,
    Tier,
    _public_key_bytes,
)
from mdf_viewer.license.license_manager import LicenseError, LicenseManager, _canonical_payload


# ---------------------------------------------------------------------------
# Helpers — generate a valid signed license file for tests
# ---------------------------------------------------------------------------

def _make_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _sign_payload(payload: dict, private_key: Ed25519PrivateKey) -> str:
    sig = private_key.sign(_canonical_payload(payload))
    return base64.b64encode(sig).decode()


def _write_license(
    tmp_path: Path,
    payload: dict,
    private_key: Ed25519PrivateKey,
    *,
    filename: str = "test.lic",
    override_sig: str | None = None,
) -> Path:
    sig = override_sig if override_sig is not None else _sign_payload(payload, private_key)
    data = {"payload": payload, "signature": sig}
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _default_payload(
    tier: str = "personal",
    seats: int = 1,
    updates_until: str | None = None,
) -> dict:
    if updates_until is None:
        updates_until = (date.today() + timedelta(days=365)).isoformat()
    return {
        "format_version": FORMAT_VERSION,
        "licensee_name": "Test User",
        "licensee_email": "test@example.com",
        "tier": tier,
        "seats": seats,
        "updates_until": updates_until,
        "issued_at": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Fixture: a private key whose PUBLIC key is patched into license_info
# ---------------------------------------------------------------------------

@pytest.fixture()
def key_pair(monkeypatch):
    """Returns (private_key, public_key_bytes); patches PUBLIC_KEY_B64 in license_info."""
    private_key = _make_private_key()
    pub_bytes = private_key.public_key().public_bytes(
        Encoding.Raw,
        __import__(
            "cryptography.hazmat.primitives.serialization",
            fromlist=["PublicFormat"],
        ).PublicFormat.Raw,
    )
    monkeypatch.setattr(
        "mdf_viewer.license.license_info.PUBLIC_KEY_B64",
        base64.b64encode(pub_bytes).decode(),
    )
    # Also patch in license_manager which imports _public_key_bytes
    monkeypatch.setattr(
        "mdf_viewer.license.license_manager._public_key_bytes",
        lambda: pub_bytes,
    )
    return private_key, pub_bytes


# ---------------------------------------------------------------------------
# LicenseInfo
# ---------------------------------------------------------------------------

class TestLicenseInfo:
    def test_updates_expired_false(self):
        info = LicenseInfo(
            licensee_name="A",
            licensee_email="a@b.com",
            tier=Tier.PERSONAL,
            seats=1,
            updates_until=date.today() + timedelta(days=1),
            issued_at=date.today(),
        )
        assert not info.updates_expired

    def test_updates_expired_true(self):
        info = LicenseInfo(
            licensee_name="A",
            licensee_email="a@b.com",
            tier=Tier.PERSONAL,
            seats=1,
            updates_until=date.today() - timedelta(days=1),
            issued_at=date.today(),
        )
        assert info.updates_expired

    def test_seats_display_personal(self):
        info = LicenseInfo("A", "a@b.com", Tier.PERSONAL, 1,
                           date.today(), date.today())
        assert info.seats_display == "Personal"

    def test_seats_display_team(self):
        info = LicenseInfo("A", "a@b.com", Tier.TEAM, TEAM_SEATS,
                           date.today(), date.today())
        assert info.seats_display == f"{TEAM_SEATS} seats"

    def test_seats_display_enterprise(self):
        info = LicenseInfo("A", "a@b.com", Tier.ENTERPRISE, 0,
                           date.today(), date.today())
        assert info.seats_display == "Unlimited"

    def test_tier_display_personal(self):
        info = LicenseInfo("A", "a@b.com", Tier.PERSONAL, 1,
                           date.today(), date.today())
        assert info.tier_display == "Personal License"

    def test_tier_display_team(self):
        info = LicenseInfo("A", "a@b.com", Tier.TEAM, TEAM_SEATS,
                           date.today(), date.today())
        assert f"{TEAM_SEATS} seats" in info.tier_display

    def test_tier_display_enterprise(self):
        info = LicenseInfo("A", "a@b.com", Tier.ENTERPRISE, 0,
                           date.today(), date.today())
        assert "Unlimited" in info.tier_display


# ---------------------------------------------------------------------------
# LicenseManager.verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_valid_personal_license(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload()
        path = _write_license(tmp_path, payload, private_key)
        manager = LicenseManager()
        info = manager.verify(path)
        assert info.licensee_name == "Test User"
        assert info.tier == Tier.PERSONAL
        assert info.seats == 1
        assert not info.updates_expired

    def test_valid_team_license(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload(tier="team", seats=TEAM_SEATS)
        path = _write_license(tmp_path, payload, private_key)
        info = LicenseManager().verify(path)
        assert info.tier == Tier.TEAM
        assert info.seats == TEAM_SEATS

    def test_valid_enterprise_license(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload(tier="enterprise", seats=0)
        path = _write_license(tmp_path, payload, private_key)
        info = LicenseManager().verify(path)
        assert info.tier == Tier.ENTERPRISE

    def test_expired_updates_still_valid(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload(
            updates_until=(date.today() - timedelta(days=1)).isoformat()
        )
        path = _write_license(tmp_path, payload, private_key)
        info = LicenseManager().verify(path)
        assert info.updates_expired

    def test_invalid_signature(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload()
        path = _write_license(tmp_path, payload, private_key, override_sig="AAAA")
        with pytest.raises(LicenseError, match="signature"):
            LicenseManager().verify(path)

    def test_tampered_payload(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload()
        path = _write_license(tmp_path, payload, private_key)
        # Tamper: change the name after signing
        data = json.loads(path.read_text())
        data["payload"]["licensee_name"] = "Hacker"
        path.write_text(json.dumps(data))
        with pytest.raises(LicenseError, match="signature"):
            LicenseManager().verify(path)

    def test_wrong_key(self, tmp_path, key_pair):
        _, _ = key_pair  # public key is patched to key_pair's key
        other_key = _make_private_key()
        payload = _default_payload()
        # Sign with a DIFFERENT private key
        path = _write_license(tmp_path, payload, other_key)
        with pytest.raises(LicenseError, match="signature"):
            LicenseManager().verify(path)

    def test_missing_file(self, tmp_path, key_pair):
        with pytest.raises(LicenseError, match="Cannot read"):
            LicenseManager().verify(tmp_path / "nonexistent.lic")

    def test_invalid_json(self, tmp_path, key_pair):
        p = tmp_path / "bad.lic"
        p.write_text("not json")
        with pytest.raises(LicenseError, match="Cannot read"):
            LicenseManager().verify(p)

    def test_missing_payload_field(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload()
        del payload["licensee_email"]
        path = _write_license(tmp_path, payload, private_key)
        with pytest.raises(LicenseError, match="missing or invalid"):
            LicenseManager().verify(path)

    def test_unknown_format_version(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload()
        payload["format_version"] = 99
        path = _write_license(tmp_path, payload, private_key)
        with pytest.raises(LicenseError, match="format version"):
            LicenseManager().verify(path)

    def test_invalid_tier(self, tmp_path, key_pair):
        private_key, _ = key_pair
        payload = _default_payload(tier="gold")
        path = _write_license(tmp_path, payload, private_key)
        with pytest.raises(LicenseError, match="missing or invalid"):
            LicenseManager().verify(path)

    def test_missing_structure(self, tmp_path, key_pair):
        p = tmp_path / "bad.lic"
        p.write_text(json.dumps({"foo": "bar"}))
        with pytest.raises(LicenseError, match="structure"):
            LicenseManager().verify(p)


# ---------------------------------------------------------------------------
# LicenseManager.import_license / load_stored
# ---------------------------------------------------------------------------

class TestImportAndLoad:
    def test_import_copies_to_app_data(self, tmp_path, key_pair, monkeypatch):
        private_key, _ = key_pair
        payload = _default_payload()
        src = _write_license(tmp_path, payload, private_key)

        dest_dir = tmp_path / "appdata"
        manager = LicenseManager()
        monkeypatch.setattr(manager, "stored_path", lambda: dest_dir / "license.lic")

        info = manager.import_license(src)
        assert info.licensee_name == "Test User"
        assert (dest_dir / "license.lic").exists()

    def test_import_invalid_raises(self, tmp_path, key_pair, monkeypatch):
        p = tmp_path / "bad.lic"
        p.write_text("not json")
        manager = LicenseManager()
        monkeypatch.setattr(manager, "stored_path", lambda: tmp_path / "license.lic")
        with pytest.raises(LicenseError):
            manager.import_license(p)

    def test_load_stored_returns_none_when_missing(self, tmp_path, monkeypatch):
        manager = LicenseManager()
        monkeypatch.setattr(manager, "stored_path", lambda: tmp_path / "license.lic")
        assert manager.load_stored() is None

    def test_load_stored_returns_info_when_valid(self, tmp_path, key_pair, monkeypatch):
        private_key, _ = key_pair
        payload = _default_payload()
        src = _write_license(tmp_path, payload, private_key)

        dest = tmp_path / "license.lic"
        manager = LicenseManager()
        monkeypatch.setattr(manager, "stored_path", lambda: dest)
        manager.import_license(src)

        info = manager.load_stored()
        assert info is not None
        assert info.tier == Tier.PERSONAL

    def test_load_stored_returns_none_on_corrupt(self, tmp_path, monkeypatch):
        dest = tmp_path / "license.lic"
        dest.write_text("corrupt")
        manager = LicenseManager()
        monkeypatch.setattr(manager, "stored_path", lambda: dest)
        assert manager.load_stored() is None
