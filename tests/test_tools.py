from tools import (
    _extraer_montos_de_texto,
    _normalizar_telefono_digitos,
    validar_monto_pago,
)
from whatsapp import _partir_mensaje, normalizar_telefono

import pytest


def test_naturalizar_apertura_quita_ay():
    from whatsapp import naturalizar_apertura

    assert naturalizar_apertura("¡Ay, Alessandro! Hola mundo") == "Hola mundo"
    assert naturalizar_apertura("Ay, hola de nuevo! Qué linda noche.") == "Qué linda noche."


def test_limpiar_formato_whatsapp_elegante():
    from whatsapp import limpiar_formato_whatsapp

    sucio = (
        "*B. Canales Digitales:*\n"
        "* *Contenido Orgánico:* ideas\n"
        "**Testimonios:** casos reales\n"
        "- FAQ: responde dudas"
    )
    limpio = limpiar_formato_whatsapp(sucio)
    assert "**" not in limpio
    assert "* *" not in limpio
    assert "•" in limpio
    assert "*Testimonios:*" in limpio
    assert "*B. Canales Digitales:*" in limpio
    assert limpio.splitlines()[1].startswith("•")
    assert limpio.splitlines()[3].startswith("•")


def test_normalizar_telefono_whatsapp():
    assert normalizar_telefono("5213326505999") == "523326505999"


def test_normalizar_telefono_digitos():
    assert _normalizar_telefono_digitos("5213326505999") == "3326505999"
    assert _normalizar_telefono_digitos("+52 33 2650 5999") == "3326505999"


def test_extraer_montos_de_texto():
    assert 500.0 in _extraer_montos_de_texto("Online $400 MXN / Presencial $500 MXN")
    assert _extraer_montos_de_texto("$800") == [800.0]


def test_partir_mensaje_largo():
    texto = "a" * 5000
    partes = _partir_mensaje(texto, max_len=4000)
    assert len(partes) == 2
    assert all(len(p) <= 4000 for p in partes)
    assert "".join(partes) == texto


def test_validar_monto_rechaza_sin_inscripcion(monkeypatch):
    import tools

    monkeypatch.setattr(tools, "_obtener_inscripcion_pendiente", lambda t: None)
    ok, msg = validar_monto_pago("523326505999", 500.0)
    assert ok is False
    assert "PENDIENTE" in msg


def test_validar_monto_acepta_coincidencia(monkeypatch):
    import tools

    monkeypatch.setattr(
        tools,
        "_obtener_inscripcion_pendiente",
        lambda t: {"taller": "Taller X", "montos_esperados": [500.0]},
    )
    ok, msg = validar_monto_pago("523326505999", 500.0)
    assert ok is True


def test_validar_monto_rechaza_diferencia(monkeypatch):
    import tools

    monkeypatch.setattr(
        tools,
        "_obtener_inscripcion_pendiente",
        lambda t: {"taller": "Taller X", "montos_esperados": [500.0]},
    )
    ok, msg = validar_monto_pago("523326505999", 100.0)
    assert ok is False


def test_validar_fecha_cita_martes():
    from tools import validar_fecha_cita

    result = validar_fecha_cita("2026-06-02")
    assert "martes" in result
    assert "2026-06-02" in result


def test_identificar_terapeuta_sara():
    from config import identificar_terapeuta

    assert identificar_terapeuta("523310265936") == "Sara Rosales"
    assert identificar_terapeuta("5213310265936") == "Sara Rosales"


def test_identificar_staff_oficial(monkeypatch):
    import config

    monkeypatch.setattr(
        config,
        "TERAPEUTAS_WHATSAPP",
        {
            "magui": "13476240818",
            "juan": "523331706274",
            "patricia": "523314995220",
            "rebeca": "523313837376",
            "betty": "523310122705",
            "ivan": "523312212406",
        },
    )

    assert config.identificar_terapeuta("+1 (347) 624-0818") == "Magui Cárdenas"
    assert config.identificar_terapeuta("+52 1 33 3170 6274") == "Juan Rosales"
    assert config.identificar_terapeuta("+52 1 33 1499 5220") == "Paty Velázquez"
    assert config.identificar_terapeuta("+52 1 33 1383 7376") == "Rebeca Torres"
    assert config.identificar_terapeuta("+52 1 33 1012 2705") == "Betty Martínez"
    assert config.identificar_terapeuta("+52 1 33 1221 2406") == "Ivan Navarro"


def test_es_evento_bloqueo():
    from tools import _es_evento_bloqueo

    assert _es_evento_bloqueo({"summary": "BLOQUEADO — Vacaciones", "start": {"dateTime": "x"}})
    assert _es_evento_bloqueo({"summary": "Paciente", "start": {"date": "2026-06-01"}})
    assert not _es_evento_bloqueo(
        {
            "summary": "DIEGO",
            "description": "Cita de Consulta. Teléfono: 523326505999",
            "start": {"dateTime": "2026-06-01T09:00:00-06:00"},
        }
    )


def _fijar_fecha_catalogo(monkeypatch, anio: int, mes: int, dia: int):
    import datetime

    import catalogo
    import pytz

    fijo = datetime.datetime(anio, mes, dia, 12, 0, tzinfo=pytz.timezone("America/Mexico_City"))

    class FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fijo

    monkeypatch.setattr(catalogo.datetime, "datetime", FakeDatetime)


def test_estado_taller_en_curso(monkeypatch):
    import catalogo

    _fijar_fecha_catalogo(monkeypatch, 2026, 6, 4)
    estado = catalogo.estado_taller("Lunes 1 y 8 de junio")
    assert estado["estado_taller"] == "en_curso"
    assert "YA ESTÁ EN CURSO" in estado["aviso_estado"]
    assert "08/06/2026" in estado["aviso_estado"]


def test_estado_taller_por_iniciar(monkeypatch):
    import catalogo

    _fijar_fecha_catalogo(monkeypatch, 2026, 5, 20)
    estado = catalogo.estado_taller("Lunes 1 y 8 de junio")
    assert estado["estado_taller"] == "por_iniciar"


def test_es_servicio_online():
    from tools import _es_servicio_online

    assert _es_servicio_online("Consulta online")
    assert _es_servicio_online("Terapia en línea")
    assert not _es_servicio_online("Consulta presencial")


def test_formatear_confirmacion_cita_online_incluye_pago():
    import datetime

    from tools import _formatear_confirmacion_cita

    fecha = datetime.datetime(2026, 6, 10, 10, 0)
    bloque = _formatear_confirmacion_cita(
        fecha, "Sara Rosales", "Consulta online", es_online=True
    )
    assert "en línea" in bloque.lower() or "en línea" in bloque
    assert "totalidad" in bloque.lower()
    assert "tarjeta" in bloque.lower()
    assert "botón" in bloque.lower()
    assert "zoom" in bloque.lower()
    assert "día de tu cita" in bloque.lower()
    assert "audífonos" in bloque.lower()


def test_normalizar_modalidad_presencial_y_online():
    from catalogo import _normalizar_modalidad_fila

    fila = _normalizar_modalidad_fila(
        {"terapeuta": "Sara Rosales", "tipo": "servicio", "nombre": "Terapia individual", "modalidad": "Presencial"}
    )
    assert "online" in fila["modalidad"].lower()

    mentora = _normalizar_modalidad_fila(
        {"terapeuta": "Mentoras", "tipo": "servicio", "nombre": "Sesión", "modalidad": "Presencial"}
    )
    assert "únicamente" in mentora["modalidad"].lower() or "unicamente" in mentora["modalidad"].lower()


def test_catalogo_web_talleres_completos():
    from catalogo_web import CONTACTO_WEB, EQUIPO_WEB, PAGINAS_SITIO, TALLERES_WEB, filas_catalogo_dict

    assert "talleres.php" in PAGINAS_SITIO["talleres"]
    assert len(TALLERES_WEB) == 4
    assert len(EQUIPO_WEB) == 9
    assert "+52 33 1469 9772" in CONTACTO_WEB["telefonos"]
    filas = filas_catalogo_dict()
    talleres = [f for f in filas if f["tipo"] == "taller"]
    assert len(talleres) == 4
    nombres = " ".join(t["nombre"].lower() for t in talleres)
    assert "heridas del pasado" in nombres
    assert "carver" in nombres or "hablamos de amor" in nombres
    assert "alianza" in nombres
    assert "volver a encontrarnos" in nombres


def test_alias_taller_heridas_resuelve_taller_vigente():
    from catalogo_web import id_web_desde_texto

    assert id_web_desde_texto("taller del niño") == "sanando-heridas"
    assert id_web_desde_texto("taller de heridas") == "sanando-heridas"
    assert id_web_desde_texto("heridas del pasado") == "sanando-heridas"


def test_estado_taller_lista_espera():
    import catalogo

    estado = catalogo.estado_taller(
        "30 de agosto de 2026",
        "Lista de espera abierta — escribir HISTORIA por WhatsApp",
    )
    assert estado["estado_taller"] == "lista_espera"
    assert "HISTORIA" in estado["aviso_estado"]


def test_sincronizar_catalogo_desactiva_nombre_viejo(monkeypatch):
    import catalogo_sync

    taller_vigente = {
        "id_web": "sanando-heridas",
        "terapeuta": "Juan y Sara Rosales",
        "nombre": "Sanando tus heridas del pasado",
        "nombre_corto_web": "Sanando heridas",
        "fechas": "30 de agosto de 2026",
        "horario": "Por confirmar",
        "modalidad": "Presencial + online",
        "precio": "Consultar",
        "cupo": "Lista de espera",
        "temario": "Vivencial",
        "descripcion_web": "Taller",
        "url_web": "https://inpulso43.com/talleres.php",
    }

    class FakeValues:
        def update(self, **kwargs):
            fake.last_update = kwargs
            return self

        def append(self, **kwargs):
            fake.last_append = kwargs
            return self

        def execute(self):
            return {}

    class FakeSpreadsheets:
        def values(self):
            return FakeValues()

    class FakeService:
        def spreadsheets(self):
            return FakeSpreadsheets()

    fake = FakeService()
    monkeypatch.setattr(catalogo_sync, "config", type("C", (), {"ID_HOJA_CALCULO": "sheet1"})())
    monkeypatch.setattr(
        catalogo_sync,
        "obtener_talleres_vigentes",
        lambda **k: [taller_vigente],
    )
    monkeypatch.setattr(
        catalogo_sync,
        "_filas_crudas_catalogo",
        lambda: [
            ["Juan", "taller", "Taller de heridas del pasado", "", "", "", "", "", "", "SI"],
        ],
    )
    monkeypatch.setattr(catalogo_sync, "get_sheets_service", lambda: fake)
    monkeypatch.setattr(catalogo_sync, "invalidar_cache", lambda: None)
    monkeypatch.setattr(catalogo_sync, "invalidar_cache_web", lambda: None)
    monkeypatch.setattr(catalogo_sync, "cargar_talleres_publicados_web", lambda **k: {})

    resultado = catalogo_sync.sincronizar_catalogo_desde_web(forzar_lectura_web=False)

    assert resultado["ok"] is True
    assert resultado["actualizados"] == 1
    assert resultado["desactivados"] == 0


def test_formatear_evento_cita():
    from tools import _formatear_evento_cita

    evento = {
        "summary": "MARÍA LÓPEZ",
        "description": "Cita de Terapia con Sara Rosales. Teléfono: 523311122233",
        "start": {"dateTime": "2026-06-01T10:00:00-06:00"},
    }
    texto = _formatear_evento_cita(evento)
    assert "10:00" in texto
    assert "MARÍA LÓPEZ" in texto
    assert "523311122233" in texto


def test_cambiar_servicio_cita_actualiza_evento(monkeypatch):
    import tools

    cita = {
        "event_id": "evt-1",
        "calendar_id": "cal-sara",
        "fecha": "2026-07-02",
        "hora": "18:00",
        "especialista": "Sara Rosales",
        "servicio": "Consulta individual presencial",
        "resumen": "ALESSANDRO GAYTÁN",
    }
    evento = {
        "id": "evt-1",
        "summary": "ALESSANDRO GAYTÁN",
        "description": "Cita de Consulta individual presencial con Sara Rosales. Teléfono: 523326505999",
        "start": {"dateTime": "2026-07-02T18:00:00"},
        "end": {"dateTime": "2026-07-02T19:00:00"},
    }
    patched = {}

    class FakeEvents:
        def get(self, calendarId, eventId):
            return self

        def patch(self, calendarId, eventId, body):
            patched["body"] = body
            return self

        def execute(self):
            return evento if "body" not in patched else patched["body"]

    class FakeService:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr(tools, "listar_citas_futuras_por_telefono", lambda tel: [cita])
    monkeypatch.setattr(tools, "get_calendar_service", lambda: FakeService())
    monkeypatch.setattr(tools, "ejecutar_con_reintento", lambda fn, label: fn())
    monkeypatch.setattr(tools, "_invalidar_cache_agenda", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_invalidar_cache_citas", lambda *a, **k: None)

    resultado = tools.cambiar_servicio_cita(
        "523326505999",
        "Consulta de pareja presencial",
        "2026-07-02T18:00:00",
    )

    assert "ÉXITO" in resultado
    assert "pareja" in patched["body"]["description"].lower()
    assert "Consulta individual" not in patched["body"]["description"]


def test_reagendar_atomica_mismo_horario_usa_cambiar_servicio(monkeypatch):
    import tools

    llamadas = []

    def fake_cambiar(telefono, servicio, fecha_hora=""):
        llamadas.append((telefono, servicio, fecha_hora))
        return "ÉXITO cambio"

    monkeypatch.setattr(
        tools,
        "listar_citas_futuras_por_telefono",
        lambda tel: [
            {
                "event_id": "evt-1",
                "calendar_id": "cal-sara",
                "fecha": "2026-07-02",
                "hora": "18:00",
                "especialista": "Sara Rosales",
                "servicio": "Consulta individual presencial",
            }
        ],
    )
    monkeypatch.setattr(tools, "cambiar_servicio_cita", fake_cambiar)
    monkeypatch.setattr(
        tools,
        "agendar_cita",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe agendar")),
    )

    resultado = tools.reagendar_cita_atomica(
        "523326505999",
        "2026-07-02T18:00:00",
        "Alessandro Gaytán",
        "Sara Rosales",
        "Consulta de pareja presencial",
    )

    assert resultado == "ÉXITO cambio"
    assert len(llamadas) == 1


def test_reagendar_ofrece_opciones_sin_cancelar(monkeypatch):
    import experiencia

    monkeypatch.setattr(
        experiencia,
        "listar_citas_futuras_por_telefono",
        lambda tel: [{"fecha": "2026-06-10", "hora": "10:00", "especialista": "Sara Rosales"}],
    )
    monkeypatch.setattr(
        experiencia,
        "consultar_agenda",
        lambda fecha, esp: f"Espacios DISPONIBLES para sara el {fecha} (Citas de 1 hora): 12:00, 13:00",
    )

    resultado = experiencia.reagendar_cita_inteligente("523326505999")

    assert "sigue reservada" in resultado
    assert "agenda primero la nueva cita" in resultado
    assert "Cita cancelada" not in resultado
