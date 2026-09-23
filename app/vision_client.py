"""Clasificación de documentos con Claude vision.

Para cada imagen que manda un paciente, determina: qué tipo de documento es (orden
clínica, autorización de servicio, cédula, o ninguno reconocible) y, si es una orden
clínica, la fecha de expedición (si se alcanza a leer con confianza) y si sigue vigente
según ORDEN_VIGENCIA_DIAS. Nunca asume vigencia cuando no puede leer la fecha — ese caso
queda para que lo revise un agente humano (vigente=None).
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
        "Reporta qué tipo de documento es la imagen y, si es una orden clínica, la fecha "
        "de expedición que alcances a leer (formato AAAA-MM-DD). Si no puedes leer la "
        "fecha con confianza, no la reportes — es mejor dejarla vacía que adivinar."
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
            "nota": {"type": "string", "description": "Qué observaste — para que un agente humano lo revise"},
        },
        "required": ["tipo"],
    },
}


@dataclass
class ClasificacionDocumento:
    tipo: str
    fecha_expedicion: Optional[date]
    vigente: Optional[bool]  # None = no aplica (no es orden) o no se pudo determinar
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
            "orden o remisión médica), autorizacion_servicio (un documento de autorización "
            "de Compensar o la EPS), o cedula (foto de la cédula de ciudadanía, por delante "
            "o por detrás). Si la imagen no es clara o no corresponde a ninguno de esos "
            "tres, usa sin_clasificar. Nunca inventes una fecha que no puedas leer con "
            "confianza en la imagen."
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

    return ClasificacionDocumento(tipo=tipo, fecha_expedicion=fecha_expedicion, vigente=vigente, nota=nota)
