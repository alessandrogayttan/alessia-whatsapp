"""Panel web en vivo: métricas Alessia desde SQLite (sin Google Sheets)."""
from __future__ import annotations

import html
import re
from datetime import datetime

import pytz

import storage

ZONA = pytz.timezone("America/Mexico_City")
META_CUPO = 100

_NOMBRES_PESTANA = {
    "Heridas_Inscritos": "Heridas · inscritos",
    "Heridas_Interesados": "Heridas · interesados",
    "FAQ_Pacientes": "FAQ pacientes",
    "Inscripciones": "Inscripciones",
    "PagosCitas": "Pagos de citas",
    "Conocimiento": "Conocimiento clínico",
    "Lista_Espera": "Lista de espera",
}


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _clase_estado(texto: str) -> str:
    t = unicodedata_fold(texto)
    if re.search(r"\bpagad", t) or t in {"paid", "ok pago"}:
        return "pill pill-ok"
    if re.search(r"\bpendiente|\bespera", t):
        return "pill pill-warn"
    if re.search(r"\bcancel|\brechaz|\bfallo|\berror", t):
        return "pill pill-bad"
    if re.search(r"\binscrit", t):
        return "pill pill-info"
    return ""


def unicodedata_fold(texto: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _celda(valor) -> str:
    s = "" if valor is None else str(valor)
    cls = _clase_estado(s)
    if cls:
        return f'<td><span class="{cls}">{_esc(s)}</span></td>'
    return f"<td>{_esc(s)}</td>"


def _tabla(headers: list[str], rows: list[list], vacio: str) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    if not rows:
        body = f"<tr><td colspan='{len(headers)}' class='vacio'>{_esc(vacio)}</td></tr>"
    else:
        body = "".join(
            "<tr>" + "".join(_celda(c) for c in row) + "</tr>" for row in rows
        )
    return (
        f"<div class='sheet'><table><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _seccion(kicker: str, titulo: str, cuerpo: str, nota: str = "") -> str:
    n = f"<p class='nota'>{_esc(nota)}</p>" if nota else ""
    return (
        f"<section class='block'>"
        f"<p class='kicker'>{_esc(kicker)}</p>"
        f"<h2>{_esc(titulo)}</h2>{n}{cuerpo}</section>"
    )


def _color_barra(pct: float) -> str:
    if pct >= 90:
        return "#b42318"
    if pct >= 70:
        return "#b54708"
    return "#067647"


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
    diag = storage.diagnostico_db()
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
        clave = meta.get("pestana") or ""
        titulo = _NOMBRES_PESTANA.get(clave, clave)
        heads = meta.get("encabezados") or ["Columna"]
        rows = storage.listar_filas_importadas(clave, 150)
        n = meta.get("filas", 0)
        bloques_imp.append(
            _seccion(
                "Copia histórica de Sheets",
                f"{titulo} · {n} filas",
                _tabla(heads, rows, "Sin filas en esta tabla"),
            )
        )
    html_import = "".join(bloques_imp) or _seccion(
        "Copia histórica de Sheets",
        "Sin importación todavía",
        "<p class='nota'>Cuando se lance la importación única, las tablas aparecen aquí.</p>",
    )
    nota_import = import_estado or "sin importar"
    if import_resumen:
        nota_import = f"{nota_import} · {import_resumen}"
    db_txt = (
        f"{diag.get('ruta')} · {int(diag.get('bytes') or 0)} bytes · "
        f"persistente={'sí' if diag.get('persistente') else 'NO'} · "
        f"filas import {diag.get('filas_import', 0)}"
    )
    aviso_db = ""
    if not diag.get("persistente"):
        aviso_db = (
            "<div class='alert'>La base no está en /data. Cada deploy borra los ceros. "
            "En DigitalOcean, DATABASE_PATH debe ser /data/alessia.db y el volumen alessia-data montado en /data.</div>"
        )
    elif int(diag.get("filas_import") or 0) == 0:
        aviso_db = (
            "<div class='alert'>La base persistente está vacía. Vuelve a abrir una vez el enlace de importación "
            "(con forzar=1). Después de este arreglo, no debería volver a cero.</div>"
        )

    kpis = [
        (hist.get("mensajes_totales", 0), "Mensajes totales"),
        (hist.get("mensajes_pacientes", 0), "Mensajes de pacientes"),
        (ops.get("conversaciones_activas", 0), "Conversaciones"),
        (hist.get("pacientes", 0), "Pacientes"),
        (hist.get("faq_veces_totales", 0), "FAQ (veces)"),
        (hist.get("menciones_heridas_totales", 0), "Menciones heridas"),
        (n_her, "Cupo heridas (conteo)"),
        (interes.get("interes_7d_heridas", 0), "Interés heridas 7 días"),
        (hist.get("interes_talleres_activo", 0), "Interés talleres"),
        (ops.get("escalaciones_pendientes", 0), "Escalaciones"),
        (n_insc_imp, "Inscritos importados"),
    ]
    html_kpis = "".join(
        f"<div class='kpi'><b>{_esc(v)}</b><span>{_esc(l)}</span></div>" for v, l in kpis
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="30"/>
<title>Panel Alessia · Inpulso 43</title>
<style>
  :root {{
    --bg:#f3f1ec; --ink:#122033; --muted:#5c6b7a; --card:#fff;
    --line:#e2e0d8; --acc:#1f4e79; --ok:#067647; --okbg:#ecfdf3;
    --warn:#b54708; --warnbg:#fff6ed; --bad:#b42318; --badbg:#fef3f2;
    --info:#175cd3; --infobg:#eff8ff;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--ink);
    font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
    background:
      radial-gradient(900px 280px at 10% -10%, #d9e6f5 0%, transparent 55%),
      var(--bg);
  }}
  header.top {{
    background:#122033; color:#f7f4ee; padding:22px 20px 18px;
    border-bottom:3px solid #c4a574;
  }}
  header.top h1 {{ margin:0; font-size:1.35rem; font-weight:600; letter-spacing:.02em; }}
  header.top .sub {{ margin:8px 0 0; color:#c9d4e0; font-size:.82rem; }}
  main {{ max-width:1240px; margin:0 auto; padding:22px 16px 56px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(148px,1fr)); gap:10px; margin:18px 0 8px; }}
  .kpi {{
    background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:14px 12px; box-shadow:0 1px 0 rgba(18,32,51,.04);
  }}
  .kpi b {{ display:block; font-size:1.45rem; font-variant-numeric:tabular-nums; color:var(--acc); }}
  .kpi span {{ display:block; margin-top:4px; color:var(--muted); font-size:.72rem; letter-spacing:.04em; text-transform:uppercase; }}
  .block {{
    background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:16px 16px 12px; margin:16px 0; box-shadow:0 8px 24px rgba(18,32,51,.04);
  }}
  .kicker {{
    margin:0 0 4px; font-size:.7rem; letter-spacing:.14em; text-transform:uppercase;
    color:#8a6a3b; font-weight:600;
  }}
  h2 {{ font-size:1.05rem; margin:0 0 10px; font-weight:600; }}
  .nota {{ font-size:.82rem; color:var(--muted); margin:0 0 10px; }}
  .sheet {{ max-height:440px; overflow:auto; border:1px solid var(--line); border-radius:8px; }}
  table {{ width:100%; border-collapse:separate; border-spacing:0; }}
  th, td {{
    text-align:left; padding:9px 11px; font-size:.84rem; vertical-align:top;
    border-bottom:1px solid var(--line);
  }}
  th {{
    position:sticky; top:0; background:#1f4e79; color:#fff; font-weight:600;
    font-size:.75rem; letter-spacing:.04em; text-transform:uppercase; z-index:1;
  }}
  tbody tr:nth-child(even) {{ background:#faf8f4; }}
  tbody tr:hover {{ background:#eef4fb; }}
  td.vacio {{ color:var(--muted); font-style:italic; }}
  .pill {{
    display:inline-block; padding:2px 9px; border-radius:999px; font-size:.75rem;
    font-weight:650; letter-spacing:.03em; text-transform:uppercase;
  }}
  .pill-ok {{ background:var(--okbg); color:var(--ok); }}
  .pill-warn {{ background:var(--warnbg); color:var(--warn); }}
  .pill-bad {{ background:var(--badbg); color:var(--bad); }}
  .pill-info {{ background:var(--infobg); color:var(--info); }}
  .barra-ext {{ background:#ece9e2; height:14px; border-radius:99px; overflow:hidden; }}
  .barra-int {{ height:100%; width:{pct:.1f}%; background:{color}; }}
  .alert {{
    background:#fef3f2; color:#b42318; border:1px solid #fecdca;
    padding:10px 12px; border-radius:8px; margin:12px 0; font-size:.88rem;
  }}
  nav.toc {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 0; }}
  nav.toc a {{
    color:#d7c4a3; font-size:.75rem; text-decoration:none; border:1px solid #3a4d63;
    padding:4px 8px; border-radius:999px;
  }}
</style>
</head>
<body>
<header class="top">
  <h1>Inpulso 43 · Panel analítico Alessia</h1>
  <p class="sub">{_esc(ahora)} hora México · cada 30 s · {_esc(nota_import)} · {_esc(db_txt)}</p>
  <nav class="toc">
    <a href="#kpis">Resumen</a>
    <a href="#cupo">Cupo heridas</a>
    <a href="#vivo">Actividad en vivo</a>
    <a href="#historico">Histórico Sheets</a>
  </nav>
</header>
<main>
  {aviso_db}
  <div id="kpis" class="kpis">{html_kpis}</div>

  <section class="block" id="cupo">
    <p class="kicker">Taller heridas</p>
    <h2>Ocupación vs meta {META_CUPO}</h2>
    <p class="nota">Conteo combinado (interés Alessia + inscritos importados). Verde &lt;70% · ámbar 70–89% · rojo ≥90%.</p>
    <div class="barra-ext"><div class="barra-int"></div></div>
    <p class="nota">{n_her} de {META_CUPO} · {pct:.1f}% · {n_insc_imp} inscritos en la copia de Sheets</p>
  </section>

  <div id="vivo">
  {_seccion("Operación en vivo", "Actividad por día", _tabla(["Fecha", "Mensajes", "Menciones heridas"], filas_act, "Sin actividad aún"))}
  {_seccion("Operación en vivo", "Interesados en talleres", _tabla(["Fecha", "Nombre", "WhatsApp", "Taller", "Terapeuta"], filas_int, "Sin interesados aún"))}
  {_seccion("Operación en vivo", "FAQ heridas / HISTORIA", _tabla(["Pregunta", "Veces", "Última", "WhatsApp"], filas_faq_h, "Sin FAQ de heridas aún"))}
  {_seccion("Operación en vivo", "Todas las preguntas frecuentes", _tabla(["Pregunta", "Veces", "Última", "WhatsApp"], filas_faq, "Sin FAQ aún"))}
  {_seccion("Operación en vivo", "Pacientes registrados", _tabla(["Alta", "Nombre", "WhatsApp"], filas_pac, "Sin pacientes aún"))}
  {_seccion("Operación en vivo", "Últimos mensajes", _tabla(["Fecha", "WhatsApp", "Canal", "Mensaje"], filas_msg, "Sin mensajes aún"))}
  </div>

  <div id="historico">{html_import}</div>

  <p class="meta">Uso interno Inpulso. El enlace incluye teléfonos; no compartir fuera del equipo. Pagado se marca en verde, pendiente en ámbar, cancelado en rojo.</p>
</main>
</body>
</html>"""
