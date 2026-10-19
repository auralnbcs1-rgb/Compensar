"""Clasificación de documentos con Claude vision.

Para cada imagen que manda un paciente, determina qué tipo de documento es (orden
clínica, autorización de servicio, cédula, o ninguno reconocible) y, según el tipo,
una sola validación — nunca las dos a la vez:

- autorizacion_servicio: se valida EN EL TIEMPO. Si el documento trae impresa su
  propia fecha de vencimiento ("VÁLIDO HASTA", "VIGENTE HASTA", etc. — lo normal en
  las autorizaciones de Compensar), esa fecha es la fuente de verdad: se usa tal cual,
  sin recalcular nada por nuestra cuenta. Si no trae esa fecha explícita, no se puede
  validar en el tiempo y queda en None (lo revisa un agente).

- orden_clinica: se valida por CONTENIDO, no por fecha. Debe especificar marca,
  modelo, tecnología, circuito, lateralidad y cantidad del audífono recetado — si le
  falta alguno de esos datos, no sirve para el trámite aunque esté "vigente" en el
  sentido de fecha.

En ambos casos, si no se puede leer el documento con la confianza suficiente para
decidir, el resultado queda en None — nunca se asume nada, lo revisa un agente humano.
"""
import base64
from dataclasses import dataclass
from datetime import date
from typing import Optional

from anthropic import Anthropic

from app.config import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

_MEDIA_TYPES_SOPORTADOS = {"image/jpeg", "image/png", "image/webp", "image/gif"}

CLASIFICAR_DOCUMENTO_TOOL = {
    "name": "clasificar_documento",
    "description": (
        "Reporta qué tipo de documento es la imagen y, según el tipo, lo necesario para "
        "validarlo: para autorizacion_servicio, su fecha de vencimiento si la trae impresa; "
        "para orden_clinica, los datos del audífono recetado. Nunca reportes un dato que no "
        "puedas leer con confianza — es mejor dejarlo vacío que adivinar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": ["orden_clinica", "autorizacion_servicio", "cedula", "sin_clasificar"],
                "description": "sin_clasificar si la imagen no es ninguno de los tres o es ilegible",
            },
            "fecha_expedicion": {
                "type": "string",
                "description": (
                    "Para orden_clinica o autorizacion_servicio: cuándo se expidió el "
                    "documento, formato AAAA-MM-DD, solo si se lee con confianza. Es solo "
                    "para referencia — no decide nada por sí sola."
                ),
            },
            "fecha_vencimiento": {
                "type": "string",
                "description": (
                    "SOLO para autorizacion_servicio, y SOLO si el documento trae impresa "
                    "explícitamente una fecha de hasta cuándo es válido (textos como 'VÁLIDO "
                    "HASTA', 'VIGENTE HASTA', 'VENCE EL'), en formato AAAA-MM-DD. NO es la "
                    "fecha de expedición/emisión que suele aparecer arriba del todo, junto al "
                    "número de autorización (esa va en fecha_expedicion, nunca aquí). En las "
                    "autorizaciones de Compensar, 'VÁLIDO HASTA' casi siempre va seguido de 8 "
                    "dígitos pegados sin separadores, en formato AAAAMMDD (ej. '20261229' = "
                    "29 de diciembre de 2026, NO el 20 de diciembre de 2026) — conviértelo tal "
                    "cual a AAAA-MM-DD. Si el documento no trae esa fecha impresa, no reportes "
                    "nada en este campo — no la deduzcas ni la calcules."
                ),
            },
            "marca": {"type": "string", "description": "Solo para orden_clinica: marca del audífono recetado"},
            "modelo": {"type": "string", "description": "Solo para orden_clinica: modelo del audífono recetado"},
            "tecnologia": {"type": "string", "description": "Solo para orden_clinica: tecnología/nivel recetado"},
            "circuito": {"type": "string", "description": "Solo para orden_clinica: circuito recetado"},
            "lateralidad": {
                "type": "string",
                "description": "Solo para orden_clinica: oído(s) — derecho, izquierdo o bilateral",
            },
            "cantidad": {"type": "string", "description": "Solo para orden_clinica: cantidad recetada"},
            "datos_completos": {
                "type": "boolean",
                "description": (
                    "SOLO para orden_clinica: true si la orden especifica los seis datos "
                    "(marca, modelo, tecnología, circuito, lateralidad y cantidad); false si "
                    "le falta alguno de esos datos. No lo reportes para los demás tipos."
                ),
            },
            "nota": {
                "type": "string",
                "description": (
                    "Qué observaste, para que un agente humano lo revise. Si es una "
                    "orden_clinica con datos_completos=false, di puntualmente cuáles de los "
                    "seis datos faltan."
                ),
            },
        },
        "required": ["tipo"],
    },
}


@dataclass
class ClasificacionDocumento:
    tipo: str
    fecha_expedicion: Optional[date]
    # Para autorizacion_servicio: vigente en el tiempo. Para orden_clinica: trae los seis
    # datos del audífono recetado (marca/modelo/tecnología/circuito/lateralidad/cantidad).
    # None = no aplica (cedula/sin_clasificar) o no se pudo determinar con confianza.
    vigente: Optional[bool]
    nota: str


def clasificar(contenido: bytes, content_type: str, servicio_nombre: str) -> ClasificacionDocumento:
    media_type = content_type if content_type in _MEDIA_TYPES_SOPORTADOS else "image/jpeg"
    imagen_b64 = base64.b64encode(contenido).decode("ascii")

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=(
            "Clasificas documentos que pacientes de Compensar mandan por WhatsApp para el "
            f"trámite de '{servicio_nombre}'. Los tipos posibles son:\n"
            "- orden_clinica: una orden o remisión médica del médico tratante — suele traer "
            "diagnóstico, firma y/o sello médico.\n"
            "- autorizacion_servicio: un documento de autorización de Compensar o la EPS — "
            "suele encabezar con algo como 'AUTORIZACIÓN DE SERVICIOS', trae el logo de la "
            "EPS/caja de compensación, y lista los 'Servicios Autorizados'. No la confundas "
            "con una orden clínica solo porque ambas mencionan un procedimiento o servicio.\n"
            "- cedula: foto de la cédula de ciudadanía, por delante o por detrás.\n"
            "Si la imagen no es clara o no corresponde a ninguno de esos tres, usa "
            "sin_clasificar.\n\n"
            "La validación es distinta según el tipo — nunca mezcles las dos:\n"
            "- autorizacion_servicio se valida EN EL TIEMPO: busca si trae impresa una fecha "
            "explícita de hasta cuándo es válida ('VÁLIDO HASTA', 'VIGENTE HASTA', 'VENCE "
            "EL') y repórtala en fecha_vencimiento. Si no la trae impresa, deja ese campo "
            "vacío — nunca la inventes ni la deduzcas de otra fecha del documento. CUIDADO: "
            "las autorizaciones de Compensar suelen traer DOS fechas y no hay que "
            "confundirlas. Arriba del todo, junto al número de autorización, va la fecha en "
            "que se EXPIDIÓ el documento (ej. 'SEPTIEMBRE 30 DE 2026') — esa es solo "
            "fecha_expedicion, jamás la uses como vencimiento. Más abajo, junto a frases como "
            "'NO REQUIERE PAGO EN CONSULTORIO O INSTITUCIÓN', está la vigencia real, con el "
            "texto 'VÁLIDO HASTA' seguido de 8 dígitos pegados en formato AAAAMMDD sin "
            "separadores (ej. 'VÁLIDO HASTA 20261229' = 29 de diciembre de 2026) — esa es la "
            "que va en fecha_vencimiento, convertida a AAAA-MM-DD.\n"
            "- orden_clinica se valida por CONTENIDO, no por fecha: debe especificar marca, "
            "modelo, tecnología, circuito, lateralidad (oído derecho/izquierdo/bilateral) y "
            "cantidad del audífono recetado. Repórtalos en sus campos y marca "
            "datos_completos=true solo si los seis están presentes; si falta alguno, "
            "datos_completos=false y dilo en la nota.\n\n"
            "Nunca inventes un dato que no puedas leer con confianza en la imagen — es mejor "
            "dejarlo vacío."
        ),
        tools=[CLASIFICAR_DOCUMENTO_TOOL],
        tool_choice={"type": "tool", "name": "clasificar_documento"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": imagen_b64}},
                    {"type": "text", "text": "Clasifica este documento."},
                ],
            }
        ],
    )

    resultado: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "clasificar_documento":
            resultado = block.input

    tipo = resultado.get("tipo", "sin_clasificar")
    fecha_str = resultado.get("fecha_expedicion") or ""
    vencimiento_str = resultado.get("fecha_vencimiento") or ""
    nota = resultado.get("nota", "")

    fecha_expedicion = None
    if fecha_str:
        try:
            fecha_expedicion = date.fromisoformat(fecha_str)
        except ValueError:
            fecha_expedicion = None  # fecha ilegible — se ignora, no se adivina

    vigente = None
    if tipo == "autorizacion_servicio":
        if vencimiento_str:
            try:
                fecha_vencimiento = date.fromisoformat(vencimiento_str)
                vigente = fecha_vencimiento >= date.today()
            except ValueError:
                vigente = None  # fecha ilegible — que lo revise un agente
        # sin fecha de vencimiento impresa: no se puede validar en el tiempo, vigente=None
    elif tipo == "orden_clinica":
        datos_completos = resultado.get("datos_completos")
        vigente = datos_completos if isinstance(datos_completos, bool) else None

    return ClasificacionDocumento(tipo=tipo, fecha_expedicion=fecha_expedicion, vigente=vigente, nota=nota)
