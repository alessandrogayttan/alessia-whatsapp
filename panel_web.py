"""Panel web en vivo: métricas Alessia desde SQLite (sin depender del Sheet)."""
from __future__ import annotations

import html
from datetime import datetime

import pytz

import config
import storage

ZONA = pytz.timezone(config.ZONA_MEXICO)


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def render_panel_html() -> str:
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
    hist = storage.metricas_resumen_historico()
    interes = storage.metricas_interes_heridas()
    faq = storage.top_preguntas_frecuentes(15)
    recientes = storage.mensajes_recientes_pacientes(20)
    heridas_ok = storage.obtener_app_config("heridas_sync_ok", "—")
    analytics_ok = storage.obtener_app_config("analytics_sync_ok", "—")
    auto_err = storage.obtener_app_config("hojas_auto_sync_error", "")

    filas_faq = "".join(
        f"<tr><td>{_esc(f.get('pregunta'))}</td>"
        f"<td>{_esc(f.get('veces'))}</td>"
        f"<td>{_esc(f.get('ejemplo_telefono'))}</td></tr>"
        for f in faq
    ) or "<tr><td colspan='3'>Sin FAQ aún</td></tr>"

    filas_msg = "".join(
        f"<tr><td>{_esc((m.get('creado_at') or '')[:19])}</td>"
        f"<td>{_esc(m.get('telefono'))}</td>"
        f"<td>{_esc((m.get('contenido') or '')[:180])}</td></tr>"
        for m in recientes
    ) or "<tr><td colspan='3'>Sin mensajes aún</td></tr>"

    aviso_err = (
        f"<p class='err'>Último error sync Sheet: {_esc(auto_err)}</p>" if auto_err else ""
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="30"/>
<title>Panel Alessia · Inpulso 43</title>
<style>
  :root {{ --bg:#f6f3ee; --ink:#1c2430; --muted:#5b6570; --card:#fff; --line:#e4ddd3; --acc:#2d4f82; }}
  body {{ margin:0; font-family: "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--ink); }}
  main {{ max-width:960px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ font-size:1.6rem; margin:0 0 4px; }}
  .sub {{ color:var(--muted); margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
  .card b {{ display:block; font-size:1.4rem; color:var(--acc); }}
  .card span {{ color:var(--muted); font-size:.85rem; }}
  h2 {{ font-size:1.05rem; margin:28px 0 10px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-size:.9rem; vertical-align:top; }}
  th {{ background:#eef2f7; }}
  .meta {{ color:var(--muted); font-size:.85rem; }}
  .err {{ color:#a33; }}
</style>
</head>
<body>
<main>
  <h1>Panel Alessia · Equipo Inpulso</h1>
  <p class="sub">En vivo desde internet (no es tu computadora) · {_esc(ahora)} hora México · se actualiza cada 30 s</p>
  {aviso_err}
  <div class="grid">
    <div class="card"><b>{_esc(hist.get('mensajes_totales', 0))}</b><span>Mensajes guardados</span></div>
    <div class="card"><b>{_esc(hist.get('mensajes_pacientes', 0))}</b><span>Mensajes de pacientes</span></div>
    <div class="card"><b>{_esc(hist.get('faq_veces_totales', 0))}</b><span>Preguntas FAQ (veces)</span></div>
    <div class="card"><b>{_esc(interes.get('interes_7d_heridas', 0))}</b><span>Interés heridas (7 d)</span></div>
    <div class="card"><b>{_esc(hist.get('interes_talleres_activo', 0))}</b><span>Interés talleres activo</span></div>
    <div class="card"><b>{_esc(hist.get('pacientes', 0))}</b><span>Pacientes registrados</span></div>
  </div>
  <p class="meta">Último sync Sheet — Heridas: {_esc(heridas_ok)} · Analytics: {_esc(analytics_ok)}</p>
  <h2>Preguntas frecuentes (top)</h2>
  <table><thead><tr><th>Pregunta</th><th>Veces</th><th>WhatsApp</th></tr></thead>
  <tbody>{filas_faq}</tbody></table>
  <h2>Últimos mensajes a Alessia</h2>
  <table><thead><tr><th>Fecha</th><th>WhatsApp</th><th>Mensaje</th></tr></thead>
  <tbody>{filas_msg}</tbody></table>
  <p class="meta">Solo personal Inpulso. Cualquier celular o PC con este enlace. No compartir fuera del equipo.</p>
</main>
</body>
</html>"""
