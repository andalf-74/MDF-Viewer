from __future__ import annotations

import base64
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.exceptions import InvalidSignature

from mdf_viewer.license.license_info import (
    FORMAT_VERSION,
    LicenseInfo,
    Tier,
    _public_key_bytes,
)


class LicenseError(Exception):
    pass


def _config_dir() -> Path:
    if sys.platform == "win32":
        import os
        return Path(os.environ["APPDATA"]) / "mdf-viewer"
    return Path.home() / ".config" / "mdf-viewer"


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _verify_and_parse(path: Path) -> LicenseInfo:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseError(f"Cannot read license file: {exc}") from exc

    payload = data.get("payload")
    sig_b64 = data.get("signature")
    if not isinstance(payload, dict) or not isinstance(sig_b64, str):
        raise LicenseError("Invalid license file structure.")

    version = payload.get("format_version")
    if version != FORMAT_VERSION:
        raise LicenseError(
            f"Unsupported license format version {version!r} "
            f"(expected {FORMAT_VERSION})."
        )

    try:
        signature = base64.b64decode(sig_b64)
    except Exception as exc:
        raise LicenseError("Malformed signature encoding.") from exc

    pub_key = Ed25519PublicKey.from_public_bytes(_public_key_bytes())
    try:
        pub_key.verify(signature, _canonical_payload(payload))
    except InvalidSignature:
        raise LicenseError("License signature is invalid.")

    try:
        return LicenseInfo(
            licensee_name=payload["licensee_name"],
            licensee_email=payload["licensee_email"],
            tier=Tier(payload["tier"]),
            seats=int(payload["seats"]),
            updates_until=date.fromisoformat(payload["updates_until"]),
            issued_at=date.fromisoformat(payload["issued_at"]),
            format_version=version,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise LicenseError(f"License file has missing or invalid fields: {exc}") from exc


class LicenseManager:
    def stored_path(self) -> Path:
        return _config_dir() / "license.lic"

    def verify(self, path: Path) -> LicenseInfo:
        """Parse and verify a license file. Raises LicenseError on any failure."""
        return _verify_and_parse(path)

    def import_license(self, path: Path) -> LicenseInfo:
        """Verify then copy license to app data. Raises LicenseError on failure."""
        info = _verify_and_parse(path)
        dest = self.stored_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        return info

    def load_stored(self) -> LicenseInfo | None:
        """Load the stored license. Returns None if missing or invalid (never raises)."""
        path = self.stored_path()
        if not path.exists():
            return None
        try:
            return _verify_and_parse(path)
        except LicenseError:
            return None

    def export_license(self, dest: Path) -> None:
        """Copy the stored license file to dest. Raises LicenseError if not stored."""
        src = self.stored_path()
        if not src.exists():
            raise LicenseError("No stored license found.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
