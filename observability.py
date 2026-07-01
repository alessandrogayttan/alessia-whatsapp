"""Observabilidad: Sentry y contadores de fallos."""
import logging
import time

import config

logger = logging.getLogger(__name__)

_sentry_inicializado = False
_fallos_gemini: dict[str, list[float]] = {}
_fallos_whatsapp: dict[str, list[float]] = {}


def init_sentry():
    global _sentry_inicializado
    if _sentry_inicializado or not config.SENTRY_DSN:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[FlaskIntegration()],
            environment=config.FLASK_ENV,
            traces_sample_rate=0.1 if config.IS_PRODUCTION else 0.0,
            send_default_pii=False,
        )
        _sentry_inicializado = True
        logger.info("Sentry inicializado")
    except ImportError:
        logger.warning("sentry-sdk no instalado; omitiendo Sentry")
    except Exception as e:
        logger.warning("No se pudo inicializar Sentry: %s", e)


def registrar_fallo_gemini(telefono: str):
    _registrar_fallo(_fallos_gemini, telefono)


def registrar_fallo_whatsapp(destino: str):
    _registrar_fallo(_fallos_whatsapp, destino)


def _registrar_fallo(store: dict[str, list[float]], clave: str):
    ahora = time.time()
    ventana = ahora - 3600
    historial = [t for t in store.get(clave, []) if t > ventana]
    historial.append(ahora)
    store[clave] = historial
    if len(historial) >= config.ALERTA_FALLOS_UMBRAL:
        logger.error(
            "ALERTA: %s fallos en la última hora para %s",
            len(historial),
            clave[:6] + "***",
        )
        if _sentry_inicializado:
            try:
                import sentry_sdk

                sentry_sdk.capture_message(
                    f"Alessia: {len(historial)} fallos recientes ({clave[:6]}***)",
                    level="error",
                )
            except Exception:
                pass


def metricas_fallos() -> dict:
    ahora = time.time()
    ventana = ahora - 3600

    def _contar(store):
        total = 0
        for ts_list in store.values():
            total += sum(1 for t in ts_list if t > ventana)
        return total

    return {
        "fallos_gemini_1h": _contar(_fallos_gemini),
        "fallos_whatsapp_1h": _contar(_fallos_whatsapp),
        "sentry_activo": _sentry_inicializado,
    }
