"""Índice RAG de inpulso43.com (FTS5) — sitio + PDFs públicos."""
from __future__ import annotations

import io
import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests

import config
import storage
from inpulso_web_live import _PAGINAS, _fetch_pagina, _limpiar_html

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Alessia-Inpulso-RAG/1.0"
_CHUNK_SIZE = 600
_CHUNK_OVERLAP = 80
_last_index_ts = 0.0


def _partir_chunks(texto: str) -> list[str]:
    texto = re.sub(r"\s+", " ", (texto or "")).strip()
    if not texto:
        return []
    chunks = []
    i = 0
    while i < len(texto):
        fin = min(i + _CHUNK_SIZE, len(texto))
        chunks.append(texto[i:fin])
        if fin >= len(texto):
            break
        i = fin - _CHUNK_OVERLAP
    return chunks


def _extraer_pdfs_desde_html(html_text: str, base_url: str) -> list[str]:
    urls = set()
    for href in re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html_text, re.I):
        urls.add(urljoin(base_url, href))
    return sorted(urls)


def _texto_pdf(url: str) -> str:
    try:
        from pypdf import PdfReader

        res = _SESSION.get(url, timeout=30)
        res.raise_for_status()
        reader = PdfReader(io.BytesIO(res.content))
        paginas = []
        for page in reader.pages[:30]:
            paginas.append(page.extract_text() or "")
        return _limpiar_html(" ".join(paginas))
    except Exception as e:
        logger.debug("PDF no legible %s: %s", url, e)
        return ""


def _chunks_desde_pagina(clave: str) -> list[tuple[str, str, str]]:
    data = _fetch_pagina(clave, forzar=True)
    if data.get("error"):
        return []
    url = data.get("url", "")
    partes = []
    partes.extend(data.get("h1") or [])
    partes.extend(data.get("h2") or [])
    partes.extend(data.get("h3") or [])
    partes.extend(data.get("listas") or [])
    texto = " ".join(partes) + " " + (data.get("texto") or "")
    chunks = []
    for c in _partir_chunks(texto):
        chunks.append((f"web:{clave}", url, c))
    return chunks


def reindexar_sitio_inpulso(*, forzar: bool = False) -> int:
    """Reconstruye índice FTS desde inpulso43.com."""
    global _last_index_ts
    if (
        not config.ENABLE_INPULSO_RAG
        or (not forzar and time.time() - _last_index_ts < config.INPULSO_RAG_REINDEX_SECONDS)
    ):
        return storage.contar_chunks_rag()

    todos: list[tuple[str, str, str]] = []
    pdfs_vistos: set[str] = set()

    for clave in _PAGINAS:
        todos.extend(_chunks_desde_pagina(clave))
        try:
            url = f"{config.CLINICA_WEB_URL.rstrip('/')}/{_PAGINAS[clave]}"
            res = _SESSION.get(url, timeout=25)
            res.raise_for_status()
            for pdf_url in _extraer_pdfs_desde_html(res.text, url):
                pdfs_vistos.add(pdf_url)
        except Exception as e:
            logger.debug("PDF scan %s: %s", clave, e)

    for pdf_url in sorted(pdfs_vistos):
        pdf_text = _texto_pdf(pdf_url)
        for c in _partir_chunks(pdf_text):
            todos.append((f"pdf:{urlparse(pdf_url).path}", pdf_url, c))

    extra = (config.INPULSO_RAG_PDF_URLS or "").strip()
    for pdf_url in [u.strip() for u in extra.split(",") if u.strip()]:
        if pdf_url in pdfs_vistos:
            continue
        pdfs_vistos.add(pdf_url)
        pdf_text = _texto_pdf(pdf_url)
        for c in _partir_chunks(pdf_text):
            todos.append((f"pdf:{urlparse(pdf_url).path}", pdf_url, c))

    storage.limpiar_rag_indice()
    total = storage.insertar_chunks_rag(todos)
    _last_index_ts = time.time()
    logger.info("RAG inpulso reindexado: %s chunks", total)
    return total


def buscar_conocimiento_inpulso(consulta: str, limite: int = 8) -> str:
    """Búsqueda semántica ligera (FTS) sobre sitio y PDFs indexados."""
    if not config.ENABLE_INPULSO_RAG:
        return "RAG desactivado."
    if storage.contar_chunks_rag() == 0:
        reindexar_sitio_inpulso(forzar=True)
    filas = storage.buscar_rag_fts(consulta, limite=limite)
    if not filas:
        reindexar_sitio_inpulso(forzar=True)
        filas = storage.buscar_rag_fts(consulta, limite=limite)
    if not filas:
        return (
            f"No encontré fragmentos indexados para: {consulta}. "
            "INSTRUCCIÓN PARA LA IA: Usa consultar_sitio_inpulso para leer la página en vivo."
        )
    bloques = [f"Consulta: {consulta}\n"]
    for i, row in enumerate(filas, 1):
        bloques.append(
            f"[{i}] Fuente: {row['fuente']} | {row.get('url', '')}\n{row['chunk']}"
        )
    bloques.append(
        "\nINSTRUCCIÓN PARA LA IA: Usa estos fragmentos indexados del sitio oficial. "
        "No inventes datos que no aparezcan aquí."
    )
    return "\n\n".join(bloques)


def contexto_rag_para_mensaje(pista: str) -> str:
    if not config.ENABLE_INPULSO_RAG or not (pista or "").strip():
        return ""
    if storage.contar_chunks_rag() == 0:
        try:
            reindexar_sitio_inpulso()
        except Exception as e:
            logger.warning("RAG index falló: %s", e)
            return ""
    filas = storage.buscar_rag_fts(pista, limite=5)
    if not filas:
        return ""
    lineas = ["[Sistema: RAG inpulso43.com — fragmentos relevantes indexados]"]
    for row in filas:
        lineas.append(f"- ({row['fuente']}) {row['chunk'][:500]}")
    return "\n".join(lineas) + "\n"
