"""Sincroniza talleres de inpulso43.com al catálogo de WhatsApp Business (Meta Commerce)."""
from __future__ import annotations

import logging
import re

import requests

import config
from catalogo_web import PAGINAS_SITIO, obtener_talleres_vigentes

logger = logging.getLogger(__name__)
GRAPH_VERSION = "v21.0"


def _precio_mxn_texto(precio: str) -> str:
    """Precio para Meta Catalog (ej. '400.00 MXN')."""
    texto = (precio or "").strip()
    if not texto:
        return "0.00 MXN"
    if "gratuito" in texto.lower() or texto.lower() == "gratis":
        return "0.00 MXN"
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", texto.replace(",", ""))
    if m:
        valor = float(m.group(1).replace(",", "."))
        return f"{valor:.2f} MXN"
    return "0.00 MXN"


def _descripcion_taller(taller: dict) -> str:
    partes = [
        taller.get("descripcion_web") or taller.get("temario", ""),
        f"Facilita: {taller.get('terapeuta', '')}".strip(),
        f"Fechas: {taller.get('fechas', '')}".strip(),
        f"Horario: {taller.get('horario', '')}".strip(),
        f"Modalidad: {taller.get('modalidad', '')}".strip(),
    ]
    if taller.get("cupo"):
        partes.append(str(taller["cupo"]))
    texto = "\n".join(p for p in partes if p and p != "Fechas:" and p != "Horario:")
    return texto[:4500]


def taller_a_item_catalogo(taller: dict) -> dict:
    """Convierte un taller vigente en item de catálogo Meta."""
    imagen = (
        taller.get("image_url")
        or config.CATALOGO_PRODUCT_IMAGE_URL
        or f"{config.CLINICA_WEB_URL}/logo.png"
    )
    lista_espera = "lista de espera" in (taller.get("cupo") or "").lower()
    return {
        "id": f"inpulso-{taller['id_web']}",
        "title": (taller.get("nombre") or "Taller Inpulso 43")[:150],
        "description": _descripcion_taller(taller),
        "availability": "out of stock" if lista_espera else "in stock",
        "condition": "new",
        "price": _precio_mxn_texto(taller.get("precio", "")),
        "image_link": imagen,
        "link": taller.get("url_web") or PAGINAS_SITIO["talleres"],
        "brand": "Inpulso 43",
    }


def obtener_catalog_id() -> str | None:
    """ID del catálogo vinculado al WABA (env o Graph API)."""
    if config.WHATSAPP_CATALOG_ID:
        return config.WHATSAPP_CATALOG_ID
    waba = config.WHATSAPP_BUSINESS_ACCOUNT_ID
    if not waba or not config.TOKEN_WHATSAPP:
        return None
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{waba}/product_catalogs"
    try:
        res = requests.get(
            url,
            params={"access_token": config.TOKEN_WHATSAPP},
            timeout=30,
        )
        if res.status_code != 200:
            logger.error("No se pudo leer catálogos WABA: %s", res.text[:400])
            return None
        data = res.json().get("data") or []
        if data:
            return data[0].get("id")
    except requests.RequestException as e:
        logger.error("Error consultando catálogo WABA: %s", e)
    return None


def sincronizar_talleres_a_catalogo(*, forzar_web: bool = False) -> dict:
    """
    Crea/actualiza productos en el catálogo de WhatsApp desde talleres vigentes.
    Requiere catálogo creado y vinculado en Meta Commerce Manager.
    """
    catalog_id = obtener_catalog_id()
    if not catalog_id:
        return {
            "ok": False,
            "error": (
                "WHATSAPP_CATALOG_ID o WHATSAPP_BUSINESS_ACCOUNT_ID no configurado, "
                "o el catálogo no está vinculado al WABA."
            ),
        }
    if not config.TOKEN_WHATSAPP:
        return {"ok": False, "error": "TOKEN_WHATSAPP vacío"}

    talleres = obtener_talleres_vigentes(forzar_web=forzar_web)
    requests_batch = [
        {"method": "UPDATE", "data": taller_a_item_catalogo(t)}
        for t in talleres
    ]
    if not requests_batch:
        return {"ok": True, "sincronizados": 0, "catalog_id": catalog_id}

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{catalog_id}/items_batch"
    try:
        res = requests.post(
            url,
            params={"access_token": config.TOKEN_WHATSAPP},
            json={"item_type": "PRODUCT_ITEM", "requests": requests_batch},
            timeout=60,
        )
        body = res.json() if res.text else {}
        if res.status_code != 200:
            logger.error("items_batch falló: %s", res.text[:500])
            return {"ok": False, "error": body.get("error", res.text[:200])}
        logger.info(
            "Catálogo WhatsApp sincronizado: %s talleres (catalog=%s)",
            len(requests_batch),
            catalog_id,
        )
        return {
            "ok": True,
            "catalog_id": catalog_id,
            "sincronizados": len(requests_batch),
            "handle": body.get("handle"),
        }
    except requests.RequestException as e:
        logger.error("Error sincronizando catálogo WhatsApp: %s", e)
        return {"ok": False, "error": str(e)}
