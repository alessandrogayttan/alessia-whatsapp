"""
Crea las hojas 'Conocimiento' y 'FAQ_Pacientes' en tu Google Sheet.

Uso:
  python scripts/inicializar_conocimiento.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from conocimiento import inicializar_hojas_conocimiento


def main():
    if not config.ID_HOJA_CALCULO:
        print("Configura ID_HOJA_CALCULO en .env")
        sys.exit(1)
    print(inicializar_hojas_conocimiento())
    print(
        "\nCómo usarlo:\n"
        "1) Equipo en WhatsApp (MODO EQUIPO): «El taller X cuesta $Y…» → hoja Conocimiento\n"
        "2) FAQ_Pacientes se llena sola con lo más preguntado; tú escribes Respuesta_oficial\n"
        "3) En el siguiente sync, esas respuestas pasan a conocimiento para pacientes\n"
    )


if __name__ == "__main__":
    main()
