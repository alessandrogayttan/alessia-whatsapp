"""Tests conocimiento clínico + FAQ."""
import storage
from conocimiento import (
    buscar_conocimiento_clinica,
    guardar_conocimiento,
    listar_conocimiento,
    parece_consulta_informativa,
    registrar_consulta_paciente,
)


def test_guardar_y_buscar_conocimiento(db_temp):
    msg = guardar_conocimiento(
        "taller heridas",
        "El taller Sanando tus heridas cuesta $2500 y empieza el 15 de agosto.",
        palabras_clave="heridas precio fecha",
        quien="test",
        sync_sheets=False,
    )
    assert "ÉXITO" in msg
    hallado = buscar_conocimiento_clinica("cuánto cuesta el taller de heridas")
    assert "2500" in hallado
    assert "heridas" in hallado.lower()
    listado = listar_conocimiento()
    assert "taller heridas" in listado.lower()


def test_parece_consulta_y_registra_faq(db_temp):
    assert parece_consulta_informativa("¿Cuánto cuesta la sesión?")
    assert not parece_consulta_informativa("ok")
    registrar_consulta_paciente("¿Cuánto cuesta la sesión individual?", "523311111111")
    registrar_consulta_paciente("¿Cuánto cuesta la sesión individual?", "523311111111")
    top = storage.top_preguntas_frecuentes(10)
    assert top
    assert top[0]["veces"] >= 2
