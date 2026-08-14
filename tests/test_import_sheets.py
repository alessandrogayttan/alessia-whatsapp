def test_import_sheets_copia_faq_y_inscritos(db_temp, monkeypatch):
    import config
    import import_sheets
    import storage

    class FakeSheets:
        def spreadsheets(self):
            return self

        def values(self):
            return self

        def get(self, spreadsheetId, range):
            self._range = range
            return self

        def execute(self):
            r = self._range
            if r.startswith("Heridas_Inscritos"):
                return {
                    "values": [
                        ["Fecha", "Nombre", "WhatsApp", "Correo", "Modalidad", "Estatus pago"],
                        ["2026-01-01", "Ana", "5213310000001", "a@x.com", "presencial", "PAGADO"],
                    ]
                }
            if r.startswith("FAQ_Pacientes"):
                return {
                    "values": [
                        ["Pregunta", "Veces", "Ultima_vez", "Respuesta_oficial", "Estado", "Notas", "WhatsApp"],
                        ["cuanto cuesta el taller", "4", "2026-01-02", "", "", "", "5213310000001"],
                    ]
                }
            if r.startswith("Heridas_Interesados"):
                return {
                    "values": [
                        ["Fecha", "Nombre", "WhatsApp", "Consulta", "Fuente", "Estado", "Notas"],
                        ["2026-01-03", "Luis", "5213310000002", "heridas", "wa", "interes", ""],
                    ]
                }
            return {"values": []}

    monkeypatch.setattr(config, "ID_HOJA_CALCULO", "sheet-test")
    monkeypatch.setattr(import_sheets, "get_sheets_service", lambda: FakeSheets())

    out = import_sheets.ejecutar_importacion_sheets()
    assert out["ok"] is True
    assert out["resumen"]["Heridas_Inscritos"] == 1
    assert out["resumen"]["FAQ_Pacientes"] == 1
    faqs = storage.top_preguntas_frecuentes(10)
    assert faqs[0]["pregunta"] == "cuanto cuesta el taller"
    assert faqs[0]["veces"] == 4
    filas = storage.listar_filas_importadas("Heridas_Inscritos")
    assert filas[0][1] == "Ana"
    html = __import__("panel_web").render_panel_html()
    assert "Ana" in html
    assert "inscritos" in html.lower()


def test_lanzar_no_repite_si_ya_ok(db_temp):
    import storage
    from import_sheets import lanzar_importacion_una_vez

    storage.guardar_app_config("sheets_import_estado", "ok")
    storage.guardar_app_config("sheets_import_resumen", "FAQ_Pacientes:1")
    out = lanzar_importacion_una_vez(forzar=False)
    assert out["estado"] == "ya_importado"
