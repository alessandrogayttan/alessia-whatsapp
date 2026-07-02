"""
Sube el logo de Inpulso como foto de perfil del número de WhatsApp Business.

Uso:
  python scripts/actualizar_foto_perfil_whatsapp.py
  python scripts/actualizar_foto_perfil_whatsapp.py ruta/a/imagen.png

Requiere en .env (o variables de entorno):
  TOKEN_WHATSAPP, ID_TELEFONO, META_APP_ID

La imagen debe ser PNG o JPG, entre 192x192 y 640x640 px.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

GRAPH_VERSION = "v21.0"
DEFAULT_IMAGE = ROOT / "assets" / "inpulso-whatsapp-profile.png"
FALLBACK_IMAGE = ROOT / "assets" / "inpulso-logo.png"


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        f.read(16)
        return struct.unpack(">II", f.read(8))


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        f.read(2)
        while True:
            marker = f.read(2)
            if len(marker) < 2:
                break
            while marker[0] != 0xFF:
                marker = marker[1:] + f.read(1)
            kind = marker[1]
            if kind in (0xC0, 0xC1, 0xC2):
                f.read(3)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            length = struct.unpack(">H", f.read(2))[0]
            f.read(length - 2)


def _image_dimensions(path: Path) -> tuple[int, int]:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return _png_dimensions(path)
    if suffix in (".jpg", ".jpeg"):
        return _jpeg_dimensions(path)
    raise ValueError(f"Formato no soportado: {suffix}")


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    raise ValueError(f"Formato no soportado: {suffix}")


def _validar_imagen(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"No existe la imagen: {path}")
    ancho, alto = _image_dimensions(path)
    if ancho != alto:
        raise ValueError(
            f"La imagen debe ser cuadrada (actual: {ancho}x{alto}). "
            f"Usa assets/inpulso-whatsapp-profile.png"
        )
    if ancho < 192 or ancho > 640:
        raise ValueError(
            f"WhatsApp exige entre 192 y 640 px (actual: {ancho}x{alto})."
        )


def _resolver_imagen(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    if DEFAULT_IMAGE.is_file():
        return DEFAULT_IMAGE
    return FALLBACK_IMAGE.resolve()


def _subir_handle(token: str, app_id: str, image_path: Path) -> str:
    data = image_path.read_bytes()
    mime = _mime_type(image_path)
    headers = {"Authorization": f"Bearer {token}"}

    session = requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{app_id}/uploads",
        headers=headers,
        json={
            "file_name": image_path.name,
            "file_length": len(data),
            "file_type": mime,
        },
        timeout=60,
    )
    if session.status_code >= 400:
        raise RuntimeError(
            f"Error iniciando subida ({session.status_code}): {session.text}"
        )

    upload_id = session.json().get("id")
    if not upload_id:
        raise RuntimeError(f"Meta no devolvió upload id: {session.text}")

    upload = requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{upload_id}",
        headers={
            **headers,
            "file_offset": "0",
            "Content-Type": mime,
        },
        data=data,
        timeout=120,
    )
    if upload.status_code >= 400:
        raise RuntimeError(
            f"Error subiendo imagen ({upload.status_code}): {upload.text}"
        )

    handle = upload.json().get("h")
    if not handle:
        raise RuntimeError(f"Meta no devolvió handle: {upload.text}")
    return handle


def _actualizar_perfil(token: str, phone_id: str, handle: str) -> dict:
    response = requests.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_id}/whatsapp_business_profile",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "profile_picture_handle": handle,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Error actualizando perfil ({response.status_code}): {response.text}"
        )
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"raw": response.text}


def _obtener_perfil(token: str, phone_id: str) -> dict:
    response = requests.get(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_id}/whatsapp_business_profile",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "about,description,profile_picture_url,websites"},
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Error leyendo perfil ({response.status_code}): {response.text}"
        )
    data = response.json()
    return data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data


def main() -> int:
    load_dotenv(ROOT / ".env")

    token = config.TOKEN_WHATSAPP
    phone_id = config.ID_TELEFONO
    app_id = config.META_APP_ID

    if not token or not phone_id:
        print("FALTA: TOKEN_WHATSAPP e ID_TELEFONO en .env")
        return 1

    image_path = _resolver_imagen(sys.argv[1] if len(sys.argv) > 1 else None)
    try:
        _validar_imagen(image_path)
    except (OSError, ValueError) as e:
        print(f"Imagen inválida: {e}")
        return 1

    ancho, _ = _image_dimensions(image_path)
    print(f"Imagen: {image_path.name} ({ancho}x{ancho})")
    print(f"Número ID: {phone_id}")

    try:
        handle = _subir_handle(token, app_id, image_path)
        print("OK  Imagen subida a Meta")
        resultado = _actualizar_perfil(token, phone_id, handle)
        print("OK  Perfil actualizado:", json.dumps(resultado, ensure_ascii=False))
        perfil = _obtener_perfil(token, phone_id)
        url = perfil.get("profile_picture_url", "")
        if url:
            print("OK  Foto visible en:", url[:80] + ("..." if len(url) > 80 else ""))
        else:
            print(
                "Nota: Meta puede tardar unos minutos en mostrar la foto en WhatsApp."
            )
    except Exception as e:
        print(f"ERROR: {e}")
        print(
            "\nSi falla por permisos, sube la foto manualmente:\n"
            "  Meta Business Suite → Configuración de WhatsApp → Perfil → Foto\n"
            f"  Imagen lista: {DEFAULT_IMAGE}"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
