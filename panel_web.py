"""Panel web en vivo: métricas Alessia desde SQLite (sin Google Sheets)."""
from __future__ import annotations

import html
from datetime import datetime

import pytz

import storage

ZONA = pytz.timezone("America/Mexico_City")
META_CUPO = 100


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _filas(headers: list[str], rows: list[list], vacio: str) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    if not rows:
        body = f"<tr><td colspan='{len(headers)}'>{_esc(vacio)}</td></tr>"
    else:
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _color_barra(pct: float) -> str:
    if pct >= 90:
        return "#c64a49"
    if pct >= 70:
        return "#e08a2c"
    return "#2d8a5e"


def render_panel_html() -> str:
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
    hist = storage.metricas_resumen_historico()
    interes = storage.metricas_interes_heridas()
    ops = storage.resumen_metricas_operativas()
    faq = storage.top_preguntas_frecuentes(40)
    faq_h = storage.metricas_faq_heridas()
    recientes = storage.mensajes_recientes_pacientes(80)
    diarios = storage.metricas_mensajes_por_dia(21)
    interesados = storage.listar_interes_talleres_panel(80)
    pacientes = storage.listar_pacientes_panel(50)
    import_estado = storage.obtener_app_config("sheets_import_estado", "")
    import_resumen = storage.obtener_app_config("sheets_import_resumen", "")
    pestanas_imp = storage.listar_pestanas_importadas()
    inscritos_imp = [
        r
        for r in storage.listar_filas_importadas("Heridas_Inscritos", 200)
        if any(str(c).strip() for c in r)
        and "sin registros" not in " ".join(str(c).lower() for c in r)
    ]
    n_insc_imp = len(inscritos_imp)

    n_her = max(int(interes.get("interes_activo_relacionado") or 0), n_insc_imp)
    pct = min(100.0, (n_her / META_CUPO) * 100.0) if META_CUPO else 0.0
    color = _color_barra(pct)
    actividad = [d for d in diarios if d.get("mensajes") or d.get("menciones_heridas")][-14:]

    filas_act = [
        [d.get("dia"), d.get("mensajes"), d.get("menciones_heridas")] for d in reversed(actividad)
    ]
    filas_faq_h = [
        [
            f.get("pregunta"),
            f.get("veces"),
            (f.get("ultima_vez") or "")[:19],
            f.get("ejemplo_telefono"),
        ]
        for f in faq_h
    ]
    filas_faq = [
        [
            f.get("pregunta"),
            f.get("veces"),
            (f.get("ultima_vez") or "")[:19],
            f.get("ejemplo_telefono"),
        ]
        for f in faq
    ]
    filas_int = [
        [
            (r.get("creado_at") or "")[:19],
            r.get("nombre") or "",
            r.get("telefono"),
            r.get("taller_origen") or "",
            r.get("terapeuta") or "",
        ]
        for r in interesados
    ]
    filas_pac = [
        [
            (p.get("consentimiento_at") or "")[:19],
            p.get("nombre") or "",
            p.get("telefono"),
        ]
        for p in pacientes
    ]
    filas_msg = [
        [
            (m.get("creado_at") or "")[:19],
            m.get("telefono"),
            m.get("canal"),
            (m.get("contenido") or "")[:220],
        ]
        for m in recientes
    ]

    bloques_imp = []
    for meta in pestanas_imp:
        nombre = meta.get("pestana") or ""
        heads = meta.get("encabezados") or ["Columna"]
        rows = storage.listar_filas_importadas(nombre, 150)
        bloques_imp.append(
            f"<h2>Importado de Sheets · {_esc(nombre)} ({_esc(meta.get('filas', 0))} filas)</h2>"
            f"<div class='wrap'>{_filas(heads, rows, 'Sin filas')}</div>"
        )
    html_import = "".join(bloques_imp) or (
        "<p class='nota'>Aún no hay copia de Sheets. Cuando el equipo lance la importación única, "
        "aparece aquí y de ahí en adelante solo se actualiza esta base.</p>"
    )
    nota_import = import_estado or "sin importar"
    if import_resumen:
        nota_import = f"{nota_import} · {import_resumen}"

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="30"/>
<title>Panel Alessia · Inpulso 43</title>
<style>
  :root {{ --bg:#f4f0ea; --ink:#1c2430; --muted:#5b6570; --card:#fff; --line:#e4ddd3; --acc:#2d4f82; }}
  body {{ margin:0; font-family: "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--ink); }}
  main {{ max-width:1180px; margin:0 auto; padding:20px 14px 48px; }}
  h1 {{ font-size:1.45rem; margin:0 0 4px; }}
  h2 {{ font-size:1.02rem; margin:26px 0 8px; color:var(--acc); }}
  .sub {{ color:var(--muted); margin-bottom:16px; font-size:.92rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; }}
  .card b {{ display:block; font-size:1.35rem; color:var(--acc); }}
  .card span {{ color:var(--muted); font-size:.8rem; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); }}
  th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); font-size:.84rem; vertical-align:top; }}
  th {{ background:#e8eef6; position:sticky; top:0; }}
  .wrap {{ max-height:420px; overflow:auto; border:1px solid var(--line); }}
  .meta {{ color:var(--muted); font-size:.82rem; margin-top:18px; }}
  .barra-ext {{ background:#e6e6e8; height:22px; border-radius:4px; overflow:hidden; margin:8px 0 4px; }}
  .barra-int {{ height:100%; width:{pct:.1f}%; background:{color}; }}
  .nota {{ font-size:.85rem; color:var(--muted); margin:0 0 12px; }}
</style>
</head>
<body>
<main>
  <h1>Panel Alessia · Equipo Inpulso</h1>
  <p class="sub">Base en vivo (SQLite) · {_esc(ahora)} hora México · recarga cada 30 s · import Sheets: {_esc(nota_import)}</p>

  <div class="grid">
    <div class="card"><b>{_esc(hist.get('mensajes_totales', 0))}</b><span>Mensajes totales</span></div>
    <div class="card"><b>{_esc(hist.get('mensajes_pacientes', 0))}</b><span>Mensajes de pacientes</span></div>
    <div class="card"><b>{_esc(ops.get('conversaciones_activas', 0))}</b><span>Conversaciones</span></div>
    <div class="card"><b>{_esc(hist.get('pacientes', 0))}</b><span>Pacientes</span></div>
    <div class="card"><b>{_esc(hist.get('faq_veces_totales', 0))}</b><span>FAQ (veces)</span></div>
    <div class="card"><b>{_esc(hist.get('menciones_heridas_totales', 0))}</b><span>Menciones heridas</span></div>
    <div class="card"><b>{_esc(n_her)}</b><span>Interés heridas activo</span></div>
    <div class="card"><b>{_esc(interes.get('interes_7d_heridas', 0))}</b><span>Interés heridas 7 días</span></div>
    <div class="card"><b>{_esc(hist.get('interes_talleres_activo', 0))}</b><span>Interés talleres</span></div>
    <div class="card"><b>{_esc(ops.get('escalaciones_pendientes', 0))}</b><span>Escalaciones</span></div>
  </div>

  <h2>Taller heridas — cupo (interés Alessia vs meta {META_CUPO})</h2>
  <p class="nota">Barra 0–100 con interés Alessia + inscritos copiados del Sheet (una sola vez). Verde &lt;70%, naranja 70–89%, rojo ≥90%.</p>
  <div class="barra-ext"><div class="barra-int"></div></div>
  <p class="nota">{n_her} / {META_CUPO} · {pct:.1f}% · inscritos importados: {n_insc_imp}</p>

  <h2>Actividad Alessia (últimos días con movimiento)</h2>
  <div class="wrap">{_filas(["Fecha", "Mensajes", "Menciones heridas"], filas_act, "Sin actividad aún")}</div>

  <h2>Interesados en talleres (lista Alessia)</h2>
  <div class="wrap">{_filas(["Fecha", "Nombre", "WhatsApp", "Taller", "Terapeuta"], filas_int, "Sin interesados aún")}</div>

  <h2>FAQ heridas / HISTORIA</h2>
  <div class="wrap">{_filas(["Pregunta", "Veces", "Última", "WhatsApp"], filas_faq_h, "Sin FAQ de heridas aún")}</div>

  <h2>Todas las preguntas frecuentes</h2>
  <div class="wrap">{_filas(["Pregunta", "Veces", "Última", "WhatsApp"], filas_faq, "Sin FAQ aún")}</div>

  <h2>Pacientes registrados</h2>
  <div class="wrap">{_filas(["Alta", "Nombre", "WhatsApp"], filas_pac, "Sin pacientes aún")}</div>

  <h2>Últimos mensajes a Alessia</h2>
  <div class="wrap">{_filas(["Fecha", "WhatsApp", "Canal", "Mensaje"], filas_msg, "Sin mensajes aún")}</div>

  {html_import}

  <p class="meta">Solo personal Inpulso. No compartir el enlace fuera del equipo (incluye teléfonos de pacientes).</p>
</main>
</body>
</html>"""
