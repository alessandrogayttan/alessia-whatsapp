"""Instrucciones multimodales: imágenes, PDF, voz y comprobantes."""
from __future__ import annotations

from prompt_pagos import texto_cuentas_validas


def normalizar_mime_media(mime_type: str | None, tipo_mensaje: str = "") -> str:
    """Limpia mime de WhatsApp (p. ej. audio/ogg; codecs=opus → audio/ogg)."""
    raw = (mime_type or "").split(";")[0].strip().lower()
    if raw:
        return raw
    fallback = {
        "image": "image/jpeg",
        "video": "video/mp4",
        "audio": "audio/ogg",
        "voice": "audio/ogg",
        "document": "application/pdf",
    }
    return fallback.get(tipo_mensaje, "application/octet-stream")


def instruccion_vision_general() -> str:
    return (
        "MULTIMEDIA — IMAGEN/DOCUMENTO: "
        "Describe con precisión lo que ves (textos, montos, nombres, fechas, logos, estatus). "
        "Lee TODO el texto visible (OCR). No inventes datos que no aparezcan. "
        "Si está borroso o cortado, dilo y pide otra foto más clara."
    )


def instruccion_voz() -> str:
    return (
        "NOTA DE VOZ — OBLIGATORIO: "
        "1) Escucha el audio completo. "
        "2) Transcribe mentalmente con exactitud (nombres, fechas, montos, pedidos). "
        "3) Responde SOLO al contenido de la nota, como si te lo hubieran escrito. "
        "4) Si hay ruido o no se entiende una parte, confirma lo que sí captaste y pide aclarar lo faltante. "
        "5) No digas 'no puedo oír audios': sí puedes. "
        "6) Si piden agendar, pagar, taller o cita, actúa con las herramientas correspondientes."
    )


def instruccion_pdf_paciente(*, texto_extraido: str = "") -> str:
    base = (
        "DOCUMENTO PDF del paciente. Léelo completo. "
        "Si es comprobante de pago, aplica las reglas de comprobante. "
        "Si es otro documento, resume con precisión y pregunta qué necesita."
    )
    if texto_extraido:
        recorte = texto_extraido[:10000]
        return (
            f"{base}\n\n--- TEXTO EXTRAÍDO DEL PDF ---\n{recorte}\n--- FIN TEXTO ---\n"
            "Usa el texto extraído y el archivo adjunto; prioriza montos y datos bancarios legibles."
        )
    return base + " Si el PDF no es legible, pide que lo reenvíen como imagen clara."


def instruccion_comprobante_pago(*, telefono_paciente: str | None = None) -> str:
    prefijo = "[COMPROBANTE DE PAGO"
    if telefono_paciente:
        prefijo += f" — teléfono paciente: {telefono_paciente}"
    return (
        f"{prefijo}]. "
        "Analiza la imagen/PDF con precisión y EXTRAÉ: "
        "(a) monto en MXN (número), "
        "(b) CLABE/cuenta destino, "
        "(c) banco, "
        "(d) estatus (COMPLETADO/APLICADO/exitoso vs pendiente/rechazada), "
        "(e) fecha/hora si aparece, "
        "(f) nombre del ordenante si aparece. "
        f"Cuentas válidas Inpulso: {texto_cuentas_validas()}. "
        "REGLAS: "
        "1) Si estatus es COMPLETADO/APLICADO/exitoso y hay monto claro → "
        "OBLIGATORIO llamar confirmar_pago_comprobante(telefono, monto_comprobante) "
        "con el teléfono del paciente y el monto numérico (sin $ ni comas). "
        "2) PROHIBIDO confirmar a mano sin llamar la herramienta. "
        "3) PROHIBIDO confirmar si dice pendiente/rechazada, monto ilegible, "
        "o la cuenta no es de Inpulso. "
        "4) Si no hay inscripción previa y el pago parece válido, primero "
        "registrar_paciente_taller (si ya sabes el taller) y luego confirmar_pago_comprobante. "
        "5) Al paciente: confirma con calidez que su pago/inscripción quedó listo. "
        "PROHIBIDO mencionar IA, OCR, validación automática o robots."
    )


def instruccion_media_paciente(
    *,
    tipo_mensaje: str,
    caption: str = "",
    telefono: str = "",
    texto_pdf: str = "",
) -> str:
    partes: list[str] = []
    if tipo_mensaje in ("audio", "voice"):
        partes.append(instruccion_voz())
    elif tipo_mensaje == "document":
        partes.append(instruccion_pdf_paciente(texto_extraido=texto_pdf))
        partes.append(instruccion_comprobante_pago(telefono_paciente=telefono or None))
    elif tipo_mensaje == "image":
        partes.append(instruccion_vision_general())
        partes.append(instruccion_comprobante_pago(telefono_paciente=telefono or None))
    else:
        partes.append(
            f"Archivo tipo {tipo_mensaje}. Analízalo y responde según el pedido del paciente."
        )
    if caption.strip():
        partes.append(f"Texto/caption del paciente: {caption.strip()}")
    return " ".join(partes)
