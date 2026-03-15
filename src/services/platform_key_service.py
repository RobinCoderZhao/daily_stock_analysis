# -*- coding: utf-8 -*-
"""Platform API Key management with AES-256-GCM encryption.

Master key from env: ENCRYPTION_MASTER_KEY (base64-encoded 32 bytes)
If not set, uses a derived key from JWT_SECRET_KEY (less secure but functional).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


def _get_master_key() -> bytes:
    """Get 32-byte master key for AES-256 encryption."""
    master = os.environ.get("ENCRYPTION_MASTER_KEY", "")
    if master:
        try:
            key = base64.b64decode(master)
            if len(key) == 32:
                return key
        except Exception:
            pass

    # Fallback: derive from JWT_SECRET_KEY
    jwt_secret = os.environ.get("JWT_SECRET_KEY", "default-insecure-key")
    return hashlib.sha256(jwt_secret.encode()).digest()


def _encrypt(plaintext: str) -> str:
    """Encrypt plaintext using AES-256-GCM. Returns base64(nonce + ciphertext + tag)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        # Fallback: base64 encode only (not secure, but works without cryptography)
        logger.warning(
            "cryptography package not installed. Using base64 encoding only. "
            "Install with: pip install cryptography"
        )
        return base64.b64encode(plaintext.encode()).decode()

    key = _get_master_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def _decrypt(ciphertext_b64: str) -> str:
    """Decrypt AES-256-GCM encrypted value."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        # Fallback: base64 decode
        return base64.b64decode(ciphertext_b64).decode()

    key = _get_master_key()
    data = base64.b64decode(ciphertext_b64)
    nonce = data[:12]
    ct = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


class PlatformKeyService:
    """Manage platform LLM/search API keys with encryption."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db = db_manager or DatabaseManager.get_instance()

    def add_key(
        self,
        provider: str,
        raw_key: str,
        priority: int = 0,
        daily_limit: Optional[int] = None,
        label: str = "",
    ) -> int:
        """Encrypt and store a new platform API key. Returns key ID."""
        from src.models.platform_key import PlatformApiKey

        encrypted = _encrypt(raw_key)

        with self._db.get_session() as session:
            key = PlatformApiKey(
                provider=provider,
                encrypted_key=encrypted,
                is_active=True,
                priority=priority,
                daily_limit=daily_limit,
                label=label or f"{provider}-key",
            )
            session.add(key)
            session.commit()
            logger.info(f"Added new API key for provider {provider} (id={key.id})")
            return key.id

    def get_active_key(self, provider: str) -> Optional[str]:
        """Get decrypted active key with highest priority.

        Returns None if no active key available.
        Implements round-robin via used_today count.
        """
        from src.models.platform_key import PlatformApiKey

        with self._db.get_session() as session:
            keys = (
                session.query(PlatformApiKey)
                .filter_by(provider=provider, is_active=True)
                .order_by(PlatformApiKey.priority.desc())
                .all()
            )

            for key in keys:
                # Skip keys that hit their daily limit
                if key.daily_limit is not None and key.used_today >= key.daily_limit:
                    continue

                # Increment usage
                key.used_today += 1
                session.commit()

                try:
                    return _decrypt(key.encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt key {key.id}: {e}")

            return None

    def list_keys(self, provider: Optional[str] = None) -> List[Dict]:
        """List keys (masked, no raw values returned)."""
        from src.models.platform_key import PlatformApiKey

        with self._db.get_session() as session:
            query = session.query(PlatformApiKey)
            if provider:
                query = query.filter_by(provider=provider)
            keys = query.order_by(PlatformApiKey.provider, PlatformApiKey.priority.desc()).all()
            return [k.to_dict(mask_key=True) for k in keys]

    def deactivate_key(self, key_id: int) -> bool:
        """Deactivate a key (soft delete)."""
        from src.models.platform_key import PlatformApiKey

        with self._db.get_session() as session:
            key = session.query(PlatformApiKey).filter_by(id=key_id).first()
            if not key:
                return False
            key.is_active = False
            session.commit()
            logger.info(f"Deactivated API key {key_id}")
            return True

    def rotate_daily_counts(self) -> None:
        """Reset used_today counters (daily cron job)."""
        from src.models.platform_key import PlatformApiKey

        with self._db.get_session() as session:
            keys = session.query(PlatformApiKey).filter(
                PlatformApiKey.used_today > 0
            ).all()
            for key in keys:
                key.used_today = 0
                key.last_rotated_at = datetime.now()
            session.commit()
            logger.info(f"Reset daily counts for {len(keys)} keys")

    def get_usage_stats(self) -> List[Dict]:
        """Get usage statistics grouped by provider."""
        from src.models.platform_key import PlatformApiKey

        with self._db.get_session() as session:
            keys = session.query(PlatformApiKey).filter_by(is_active=True).all()

            stats: Dict[str, Dict] = {}
            for k in keys:
                if k.provider not in stats:
                    stats[k.provider] = {
                        "provider": k.provider,
                        "total_keys": 0,
                        "active_keys": 0,
                        "total_used_today": 0,
                        "total_daily_limit": 0,
                    }
                s = stats[k.provider]
                s["total_keys"] += 1
                s["active_keys"] += 1
                s["total_used_today"] += k.used_today
                if k.daily_limit:
                    s["total_daily_limit"] += k.daily_limit

            return list(stats.values())
