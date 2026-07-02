import config
import storage
from message_queue import encolar_mensaje_texto, procesar_cola


def test_cola_mensajes_procesa_texto(db_temp, monkeypatch):
    procesados = []

    def fake_procesar(telefono, contenido):
        procesados.append((telefono, contenido))

    monkeypatch.setattr("chat.procesar_mensaje_ia", fake_procesar)

    encolar_mensaje_texto("523326505999", "ctx:hola paciente")
    n = procesar_cola(max_items=5)

    assert n == 1
    assert procesados == [("523326505999", "ctx:hola paciente")]
    assert storage.contar_cola_pendiente() == 0


def test_cola_reintenta_fallidos(db_temp, monkeypatch):
    intentos = {"n": 0}

    def falla_primero(telefono, contenido):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("fallo simulado")

    monkeypatch.setattr("chat.procesar_mensaje_ia", falla_primero)

    msg_id = encolar_mensaje_texto("523326505999", "test")
    assert msg_id > 0

    procesar_cola(max_items=1)
    with storage._transaction() as conn:
        row = conn.execute(
            "SELECT estado, intentos FROM cola_mensajes WHERE id = ?", (msg_id,)
        ).fetchone()
    assert row["intentos"] == 1
    assert row["estado"] == "pendiente"
