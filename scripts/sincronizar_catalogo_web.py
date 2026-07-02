"""
Sincroniza la pestaña Catalogo en Google Sheets con inpulso43.com.

Ejecutar manualmente: python scripts/sincronizar_catalogo_web.py
En producción también corre automáticamente cada 30 minutos (scheduler).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from catalogo_sync import sincronizar_catalogo_desde_web


def main():
    resultado = sincronizar_catalogo_desde_web(forzar_lectura_web=True)
    if not resultado.get("ok"):
        print("Error:", resultado.get("error", "desconocido"))
        sys.exit(1)
    print(
        f"Listo — {resultado['talleres']} talleres web | "
        f"{resultado['actualizados']} actualizados | "
        f"{resultado['agregados']} agregados | "
        f"{resultado['desactivados']} desactivados"
    )


if __name__ == "__main__":
    main()
