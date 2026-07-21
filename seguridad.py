"""Utilidades de seguridad: contraseñas, comparación constante, políticas."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 260_000
_HASH_PREFIX = "pbkdf2_sha256"


def hash_clave(clave: str, *, salt: bytes | None = None) -> str:
    """Genera hash almacenables para EQUIPO_CLAVE_HASH."""
    if not clave:
        raise ValueError("clave vacía")
    sal = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        clave.encode("utf-8"),
        sal,
        _PBKDF2_ITERATIONS,
    )
    return f"{_HASH_PREFIX}${_PBKDF2_ITERATIONS}${sal.hex()}${digest.hex()}"


def verificar_clave(clave: str, secreto_configurado: str) -> bool:
    """
    Verifica contraseña de modo equipo.
    Acepta:
    - hash pbkdf2 (EQUIPO_CLAVE_HASH), o
    - texto plano (EQUIPO_CLAVE_ACCESO) con compare_digest.
    """
    if not clave or not secreto_configurado:
        return False
    secreto = secreto_configurado.strip()
    if secreto.startswith(f"{_HASH_PREFIX}$"):
        try:
            _, iter_s, salt_hex, digest_hex = secreto.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                clave.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iter_s),
            )
            return hmac.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError) as e:
            logger.error("EQUIPO_CLAVE_HASH inválido: %s", e)
            return False
    return hmac.compare_digest(clave.encode("utf-8"), secreto.encode("utf-8"))


def webhook_debe_verificar_firma(is_production: bool, app_secret: str) -> bool:
    """En producción siempre; en desarrollo solo si hay secret."""
    if is_production:
        return True
    return bool(app_secret)


def origen_web_permitido(
    *,
    is_production: bool,
    origin: str,
    referer: str,
    allowed: list[str],
) -> bool:
    """CORS estricto en producción: exige Origin/Referer de la lista."""
    if not is_production:
        return True
    origin_n = (origin or "").rstrip("/")
    referer_n = (referer or "").rstrip("/")
    if origin_n and origin_n in allowed:
        return True
    if referer_n:
        for a in allowed:
            if referer_n.startswith(a):
                return True
    return False


def metrics_requieren_secreto(is_production: bool) -> bool:
    return bool(is_production)


def cargar_cuentas_oficiales_desde_env(raw_json: str, fallback: dict) -> dict:
    """Prioriza CUENTAS_OFICIALES_JSON; si falta, usa fallback (solo no-prod idealmente)."""
    texto = (raw_json or "").strip()
    if not texto:
        return fallback
    try:
        data = __import__("json").loads(texto)
        if not isinstance(data, dict) or "BANORTE" not in data or "BANAMEX" not in data:
            logger.error("CUENTAS_OFICIALES_JSON inválido: faltan BANORTE/BANAMEX")
            return fallback
        return data
    except Exception as e:
        logger.error("No se pudo parsear CUENTAS_OFICIALES_JSON: %s", e)
        return fallback


def env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")
