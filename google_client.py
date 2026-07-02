import json
import logging
import time

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)

_creds = None
_calendar = None
_sheets = None
_creds_verificadas = False


class GoogleCalendarError(Exception):
    """Fallo al acceder a Google Calendar tras reintentos."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        calendar_id: str | None = None,
        reason: str | None = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.calendar_id = calendar_id
        self.reason = reason


def reset_google_clients():
    global _creds, _calendar, _sheets, _creds_verificadas
    _creds = None
    _calendar = None
    _sheets = None
    _creds_verificadas = False


def get_credentials():
    global _creds
    if _creds is None:
        if config.GOOGLE_SERVICE_ACCOUNT_JSON:
            try:
                info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError as e:
                raise GoogleCalendarError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON inválido (JSON mal formado). "
                    "Vuelve a pegarlo completo en DigitalOcean."
                ) from e
            _creds = service_account.Credentials.from_service_account_info(
                info, scopes=config.SCOPES
            )
        else:
            _creds = service_account.Credentials.from_service_account_file(
                config.SERVICE_ACCOUNT_FILE,
                scopes=config.SCOPES,
            )
    return _creds


def verificar_credenciales_google() -> None:
    """Fuerza refresh del token; falla temprano si la llave está revocada o mal pegada."""
    global _creds_verificadas
    if _creds_verificadas:
        return
    creds = get_credentials()
    try:
        creds.refresh(Request())
    except Exception as e:
        reset_google_clients()
        raise GoogleCalendarError(
            "No se pudo autenticar con Google (cuenta de servicio). "
            "Revisa GOOGLE_SERVICE_ACCOUNT_JSON o comparte los calendarios con la cuenta de servicio."
        ) from e
    _creds_verificadas = True


def get_calendar_service():
    global _calendar
    verificar_credenciales_google()
    if _calendar is None:
        _calendar = build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)
    return _calendar


def get_sheets_service():
    global _sheets
    verificar_credenciales_google()
    if _sheets is None:
        _sheets = build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)
    return _sheets


def ejecutar_con_reintento(operation, descripcion: str = "google_api"):
    """Ejecuta una llamada a Google API con reintentos y reset de cliente."""
    ultimo_error: Exception | None = None
    intentos = config.CALENDAR_API_RETRIES
    for intento in range(1, intentos + 1):
        try:
            return operation()
        except HttpError as e:
            ultimo_error = e
            status = e.resp.status if e.resp else None
            logger.warning(
                "%s HttpError %s (intento %s/%s): %s",
                descripcion,
                status,
                intento,
                intentos,
                e,
            )
            reset_google_clients()
            if intento < intentos:
                time.sleep(
                    min(
                        config.CALENDAR_RETRY_PAUSE_SECONDS * (1.5 ** (intento - 1)),
                        15,
                    )
                )
        except Exception as e:
            ultimo_error = e
            logger.warning("%s error (intento %s/%s): %s", descripcion, intento, intentos, e)
            reset_google_clients()
            if intento < intentos:
                time.sleep(
                    min(
                        config.CALENDAR_RETRY_PAUSE_SECONDS * (1.5 ** (intento - 1)),
                        15,
                    )
                )

    if isinstance(ultimo_error, HttpError):
        status = ultimo_error.resp.status if ultimo_error.resp else None
        raise GoogleCalendarError(
            f"Google API falló: {ultimo_error}",
            http_status=status,
            reason=str(ultimo_error),
        ) from ultimo_error
    raise GoogleCalendarError(
        f"Google API falló: {ultimo_error}",
        reason=str(ultimo_error) if ultimo_error else "desconocido",
    ) from ultimo_error


def email_cuenta_servicio() -> str:
    """Email de la cuenta de servicio (para compartir calendarios)."""
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            return json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON).get("client_email", "")
        except json.JSONDecodeError:
            return ""
    try:
        with open(config.SERVICE_ACCOUNT_FILE, encoding="utf-8") as f:
            return json.load(f).get("client_email", "")
    except OSError:
        return ""
