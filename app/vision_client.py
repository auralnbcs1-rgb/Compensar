"""Clasificación de documentos con Claude vision.

Para cada imagen que manda un paciente, determina qué tipo de documento es (orden
clínica, autorización de servicio, cédula, o ninguno reconocible) y, según el tipo, si
sigue vigente — nunca las dos validaciones a la vez:

- orden_clinica: vigente por EXPEDICIÓN — su fecha_expedicion, si se alcanza a leer con
  confianza, comparada contra ORDEN_VIGENCIA_DIAS.
- autorizacion_servicio: vigente por FECHA DE VENCIMIENTO — si el documento trae impresa
  su propia fecha de "VÁLIDO HASTA" / "VIGENTE HASTA", esa es la fuente de verdad: se usa
  tal cual, sin recalcular nada por nuestra cuenta. Si no la trae, no se puede validar y
  queda en None.

Nunca asume vigencia cuando no puede leer la fecha que corresponde — ese caso queda para
que lo revise un agente humano (vigente=None).
"""
import base64
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from anthropic import Anthropic

from app.config import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

_MEDIA_TYPES_SOPORTADOS = {"image/jpeg", "image/png", "image/webp", "image/gif"}

CLASIFICAR_DOCUMENTO_TOOL = {
    "name": "clasificar_documento",
    "description": (
        "Reporta qué tipo de documento es la imagen y, según el tipo, la fecha que "
        "corresponda: para orden_clinica, su fecha de expedición; para "
        "autorizacion_servicio, su fecha de vencimiento si la trae impresa. Si no puedes "
        "leer una fecha con confianza, no la reportes — es mejor dejarla vacía que adivinar."
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
                "description": "Solo para orden_clinica: formato AAAA-MM-DD, solo si se lee con confianza",
            },
            "fecha_vencimiento": {
                "type": "string",
                "description": (
                    "SOLO para autorizacion_servicio, y SOLO si el documento trae impresa "
                    "explícitamente una fecha de hasta cuándo es válido (textos como 'VÁLIDO "
                    "HASTA', 'VIGENTE HASTA', 'VENCE EL'), en formato AAAA-MM-DD. NO es la "
                    "fecha de expedición/emisión que suele aparecer arriba del todo, junto al "
                    "número de autorización (ignórala para este campo). En las autorizaciones "
                    "de Compensar, 'VÁLIDO HASTA' casi siempre va seguido de 8 dígitos pegados "
                    "sin separadores, en formato AAAAMMDD (ej. '20261229' = 29 de diciembre de "
                    "2026, NO el 20 de diciembre de 2026) — conviértelo tal cual a AAAA-MM-DD. "
                    "Si el documento no trae esa fecha impresa, no reportes nada en este campo "
                    "— no la deduzcas ni la calcules."
                ),
            },
            "nota": {"type": "string", "description": "Qué observaste — para que un agente humano lo revise"},
        },
        "required": ["tipo"],
    },
}


@dataclass
class ClasificacionDocumento:
    tipo: str
    fecha_expedicion: Optional[date]
    vigente: Optional[bool]  # None = no aplica (no es orden ni autorización) o no se pudo determinar
    nota: str


def clasificar(contenido: bytes, content_type: str, servicio_nombre: str) -> ClasificacionDocumento:
    media_type = content_type if content_type in _MEDIA_TYPES_SOPORTADOS else "image/jpeg"
    imagen_b64 = base64.b64encode(contenido).decode("ascii")

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=(
            "Clasificas documentos que pacientes de Compensar mandan por WhatsApp para el "
            f"trámite de '{servicio_nombre}'. Los tipos posibles son: orden_clinica (una "
            "orden o remisión médica del médico tratante), autorizacion_servicio (un "
            "documento de autorización de Compensar o la EPS — suele encabezar con algo "
            "como 'AUTORIZACIÓN DE SERVICIOS', trae el logo de la EPS/caja de compensación, "
            "y lista los 'Servicios Autorizados'; no la confundas con una orden clínica solo "
            "porque ambas mencionan un procedimiento o servicio), o cedula (foto de la "
            "cédula de ciudadanía, por delante o por detrás). Si la imagen no es clara o no "
            "corresponde a ninguno de esos tres, usa sin_clasificar.\n\n"
            "La validación es distinta según el tipo — nunca mezcles las dos:\n"
            "- orden_clinica: reporta su fecha_expedicion (AAAA-MM-DD) solo si la lees con "
            "confianza — nunca la inventes.\n"
            "- autorizacion_servicio: busca si trae impresa una fecha explícita de hasta "
            "cuándo es válida ('VÁLIDO HASTA', 'VIGENTE HASTA', 'VENCE EL') y repórtala en "
            "fecha_vencimiento. CUIDADO: estos documentos de Compensar suelen traer DOS "
            "fechas y no hay que confundirlas. Arriba del todo, junto al número de "
            "autorización, va la fecha en que se EXPIDIÓ el documento (ej. 'SEPTIEMBRE 30 DE "
            "2026') — esa NO es la vigencia, ignórala para este campo. Más abajo, junto a "
            "frases como 'NO REQUIERE PAGO EN CONSULTORIO O INSTITUCIÓN', está la vigencia "
            "real, con el texto 'VÁLIDO HASTA' seguido de 8 dígitos pegados sin separadores "
            "en formato AAAAMMDD (ej. 'VÁLIDO HASTA 20261229' = 29 de diciembre de 2026) — "
            "conviértelo a AAAA-MM-DD. Si no trae esa fecha impresa, deja fecha_vencimiento "
            "vacío — no la inventes ni la deduzcas de otra fecha del documento.\n\n"
            "Nunca inventes una fecha que no puedas leer con confianza en la imagen."
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
    vigente = None
    if tipo == "orden_clinica" and fecha_str:
        try:
            fecha_expedicion = date.fromisoformat(fecha_str)
            limite = date.today() - timedelta(days=settings.orden_vigencia_dias)
            vigente = fecha_expedicion >= limite
        except ValueError:
            fecha_expedicion = None
            vigente = None  # fecha ilegible — que lo revise un agente, no se asume nada
    elif tipo == "autorizacion_servicio" and vencimiento_str:
        try:
            fecha_vencimiento = date.fromisoformat(vencimiento_str)
            vigente = fecha_vencimiento >= date.today()
        except ValueError:
            vigente = None  # fecha ilegible — que lo revise un agente, no se asume nada
        # sin fecha de vencimiento impresa: no se puede validar, vigente se queda en None

    return ClasificacionDocumento(tipo=tipo, fecha_expedicion=fecha_expedicion, vigente=vigente, nota=nota)
