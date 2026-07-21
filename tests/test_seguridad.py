"""Tests de políticas de seguridad."""
import hmac

import config
from seguridad import (
    hash_clave,
    metrics_requieren_secreto,
    origen_web_permitido,
    verificar_clave,
    webhook_debe_verificar_firma,
)


def test_hash_y_verificar_clave_pbkdf2():
    h = hash_clave("secreto-fuerte")
    assert h.startswith("pbkdf2_sha256$")
    assert verificar_clave("secreto-fuerte", h) is True
    assert verificar_clave("otra", h) is False


def test_verificar_clave_texto_plano_compare_digest():
    assert verificar_clave("abc", "abc") is True
    assert verificar_clave("abc", "abd") is False
    assert verificar_clave("", "abc") is False


def test_webhook_fail_closed_en_produccion():
    assert webhook_debe_verificar_firma(True, "") is True
    assert webhook_debe_verificar_firma(True, "secret") is True
    assert webhook_debe_verificar_firma(False, "") is False
    assert webhook_debe_verificar_firma(False, "secret") is True


def test_origen_web_estricto_produccion():
    allowed = ["https://inpulso43.com", "https://www.inpulso43.com"]
    assert origen_web_permitido(
        is_production=True,
        origin="https://inpulso43.com",
        referer="",
        allowed=allowed,
    )
    assert not origen_web_permitido(
        is_production=True,
        origin="https://evil.example",
        referer="",
        allowed=allowed,
    )
    assert origen_web_permitido(
        is_production=False,
        origin="",
        referer="",
        allowed=allowed,
    )


def test_metrics_requieren_secreto_solo_prod():
    assert metrics_requieren_secreto(True) is True
    assert metrics_requieren_secreto(False) is False


def test_secreto_health_compare_digest_compatible():
    """Sanity: comparación constante usada en endpoints de health."""
    secret = "health-secret-test"
    assert hmac.compare_digest("health-secret-test", secret)
    assert not hmac.compare_digest("otro", secret)


def test_cuentas_desde_env_en_tests():
    assert config.CUENTAS_OFICIALES["BANORTE"]["clabe"]
    assert config.CUENTAS_OFICIALES["BANAMEX"]["clabe"]
