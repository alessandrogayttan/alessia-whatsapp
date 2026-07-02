"""Diagnóstico de conexión Google Calendar — ejecutar antes de desplegar."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from google.auth.transport.requests import Request
from google.oauth2 import service_account


def main():
    print("=" * 60)
    print("DIAGNÓSTICO CALENDARIO GOOGLE")
    print("=" * 60)

    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
            fuente = "GOOGLE_SERVICE_ACCOUNT_JSON (env)"
        except json.JSONDecodeError:
            print("\nFAIL: GOOGLE_SERVICE_ACCOUNT_JSON no es JSON válido.")
            print("     Vuelve a pegar el archivo completo en DigitalOcean.")
            sys.exit(1)
    else:
        path = Path(config.SERVICE_ACCOUNT_FILE)
        if not path.is_file():
            print(f"\nFAIL: No hay JSON de Google ({path})")
            sys.exit(1)
        info = json.loads(path.read_text(encoding="utf-8"))
        fuente = path.name

    email = info.get("client_email", "")
    print(f"\nFuente:     {fuente}")
    print(f"Cuenta:     {email}")
    print(f"Proyecto:   {info.get('project_id', '?')}")

    print("\n[1] Autenticación con Google...")
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=config.SCOPES
        )
        creds.refresh(Request())
        print("    OK  Token obtenido")
    except Exception as e:
        print(f"    FAIL {e}")
        if "Invalid JWT Signature" in str(e):
            print(
                "\n>>> SOLUCIÓN: La llave está revocada. Genera una NUEVA:\n"
                "    1. https://console.cloud.google.com/iam-admin/serviceaccounts\n"
                "    2. Proyecto: agente-inpulso\n"
                f"    3. Cuenta: {email}\n"
                "    4. Pestana Claves > Agregar clave > JSON > Descargar\n"
                "    5. DigitalOcean → GOOGLE_SERVICE_ACCOUNT_JSON → pegar JSON completo\n"
                "    6. Redeploy\n"
            )
        sys.exit(1)

    print("\n[2] Lectura de calendarios...")
    from tools import verificar_acceso_calendarios

    fallos = verificar_acceso_calendarios(rapido=False)
    if fallos:
        print("    FAIL:")
        for f in fallos:
            print(f"      - {f}")
        print(
            f"\n>>> Comparte cada calendario con {email} como Editor en Google Calendar."
        )
        sys.exit(1)

    print(f"    OK  {', '.join(config.CALENDARIOS_CRITICOS)}")
    print("\nCalendario listo para Alessia.")


if __name__ == "__main__":
    main()
