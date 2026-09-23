"""Estado de conversación por número de teléfono — en memoria.

Dos cosas se guardan aquí:
1. El historial de la conversación con Claude durante la recolección de documentos de
   una solicitud (para que pueda responder preguntas o cerrar el caso).
2. Un "flujo pendiente" para cuando estamos armando una solicitud nueva y todavía no
   tenemos la cédula o el nombre del paciente (no coincide con el backlog) — no hace
   falta guardarlo en Supabase porque no es un dato permanente, solo dura mientras se
   completa el alta de la solicitud.

Implementación en memoria — sirve para desarrollo y para un solo proceso.
En producción con más de un worker, cambiar por Redis o una tabla de base de datos
(las firmas de estas funciones son las que hay que conservar).
"""
_conversations: dict[str, list[dict]] = {}
_flujo_pendiente: dict[str, dict] = {}

MAX_TURNS_KEPT = 20  # evita que el historial crezca sin límite en conversaciones largas


def get_history(phone: str) -> list[dict]:
    return _conversations.get(phone, [])


def append_turn(phone: str, role: str, content: str) -> None:
    history = _conversations.setdefault(phone, [])
    history.append({"role": role, "content": content})
    if len(history) > MAX_TURNS_KEPT:
        del history[: len(history) - MAX_TURNS_KEPT]


def clear(phone: str) -> None:
    _conversations.pop(phone, None)


def set_flujo(phone: str, datos: dict) -> None:
    _flujo_pendiente[phone] = datos


def get_flujo(phone: str) -> dict | None:
    return _flujo_pendiente.get(phone)


def clear_flujo(phone: str) -> None:
    _flujo_pendiente.pop(phone, None)
