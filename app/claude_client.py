"""Wrapper sobre la API de Anthropic para Aurora (texto — la clasificación de imágenes
está en vision_client.py).

Dos usos:
1. interpretar_seleccion_menu — fallback para cuando el paciente no contesta con un
   número ni con una palabra clave obvia (ver menu_matcher.coincidencia_local, que se
   intenta primero porque es más barato y determinístico).
2. next_turn — la conversación mientras se recolectan documentos de una solicitud ya
   iniciada: responde preguntas del paciente y puede cerrar el caso (no_interesado /
   requiere_humano). Aurora NUNCA agenda una fecha/hora específica — solo confirma
   trámites y documentos, y deja al paciente listo para un agente de atención al
   cliente.
"""
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

from app.config import settings
from app.solicitudes import SERVICIOS

_client = Anthropic(api_key=settings.anthropic_api_key)

with open(settings.system_prompt_path, encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read()

SELECCIONAR_SERVICIO_TOOL = {
    "name": "seleccionar_servicio",
    "description": "Identifica a cuál de los 5 trámites del menú se refiere el mensaje del paciente, si se puede.",
    "input_schema": {
        "type": "object",
        "properties": {
            "codigo": {
                "type": "string",
                "enum": [codigo for codigo, _, _ in SERVICIOS.values()] + ["ninguno"],
                "description": "'ninguno' si el mensaje no corresponde claramente a ninguna opción del menú",
            },
        },
        "required": ["codigo"],
    },
}


def interpretar_seleccion_menu(mensaje: str) -> Optional[str]:
    """Fallback con Claude para cuando coincidencia_local() no encuentra nada obvio."""
    opciones = "\n".join(f"{op}. {nombre}" for op, (_, nombre, _) in SERVICIOS.items())
    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=128,
        system=(
            "Un paciente le escribió a Aurora, el asistente de WhatsApp de Compensar - "
            f"Widex Colombia S.A.S. Estas son las opciones del menú:\n{opciones}\n\n"
            "Identifica a cuál se refiere el mensaje del paciente, si es que se refiere a "
            "alguna con claridad. No adivines si el mensaje es ambiguo o no tiene nada que "
            "ver con el menú."
        ),
        tools=[SELECCIONAR_SERVICIO_TOOL],
        tool_choice={"type": "tool", "name": "seleccionar_servicio"},
        messages=[{"role": "user", "content": mensaje}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "seleccionar_servicio":
            codigo = block.input.get("codigo")
            return codigo if codigo and codigo != "ninguno" else None
    return None


CERRAR_SOLICITUD_TOOL = {
    "name": "cerrar_solicitud",
    "description": (
        "Reporta que el paciente ya no quiere continuar con el trámite, o que el caso "
        "necesita que lo atienda directamente un asesor humano (algo que Aurora no puede "
        "resolver). Llama esta herramienta una sola vez, cuando la conversación llega a "
        "ese cierre. Nunca reportes una fecha/hora de cita: Aurora no agenda."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "resultado": {"type": "string", "enum": ["no_interesado", "requiere_humano"]},
            "nota": {"type": "string", "description": "Motivo o contexto adicional para el agente humano"},
        },
        "required": ["resultado"],
    },
}


@dataclass
class SolicitudContext:
    nombre: str
    servicio_nombre: str
    documentos_faltantes: list[str]


def _context_block(ctx: SolicitudContext) -> str:
    faltan = ", ".join(ctx.documentos_faltantes) if ctx.documentos_faltantes else "ninguno (ya están completos)"
    return (
        f"[Contexto de la solicitud — no mostrar este bloque tal cual al paciente]\n"
        f"Nombre: {ctx.nombre}\n"
        f"Trámite: {ctx.servicio_nombre}\n"
        f"Documentos que todavía faltan: {faltan}"
    )


@dataclass
class TurnResult:
    reply_text: str
    resultado: Optional[dict] = None  # payload de cerrar_solicitud, si Claude lo llamó


def next_turn(ctx: SolicitudContext, history: list[dict], user_message: str) -> TurnResult:
    system = _SYSTEM_PROMPT + "\n\n" + _context_block(ctx)
    messages = list(history) + [{"role": "user", "content": user_message}]

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=system,
        tools=[CERRAR_SOLICITUD_TOOL],
        messages=messages,
    )

    reply_text = ""
    resultado = None
    for block in response.content:
        if block.type == "text":
            reply_text += block.text
        elif block.type == "tool_use" and block.name == "cerrar_solicitud":
            resultado = block.input

    return TurnResult(reply_text=reply_text.strip(), resultado=resultado)
