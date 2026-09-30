"""Capa de datos sobre `conversaciones` y `mensajes` — el historial completo de cada
chat de WhatsApp (lo que escribe el paciente, lo que contesta Aurora, y lo que escribe
un agente humano desde el panel), para el panel "Chats" del dashboard.

Es independiente de session_store.py: session_store guarda en memoria solo el turno
en curso (para darle contexto a Claude) y se pierde si el proceso se reinicia; esto es
el registro permanente en Supabase, y además es lo que decide si un agente humano
"tomó el control" de una conversación (pausada=true) — mientras está así, Aurora deja
de responder automáticamente ahí (ver main.py).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.db import get_client


@dataclass
class Conversacion:
    telefono: str
    nombre: str
    pausada: bool
    pausada_por: str
    ultimo_mensaje_en: str
    ultimo_mensaje_extracto: str
    notas: str = ""


@dataclass
class Mensaje:
    id: int
    direccion: str  # entrante | saliente
    tipo: str  # texto | imagen
    contenido: str
    storage_path: Optional[str]
    enviado_por: str  # paciente | aurora | correo del agente
    creado_en: str


def _row_to_conversacion(row: dict) -> Conversacion:
    return Conversacion(
        telefono=row["telefono"],
        nombre=row.get("nombre") or "",
        pausada=bool(row.get("pausada", False)),
        pausada_por=row.get("pausada_por") or "",
        ultimo_mensaje_en=row.get("ultimo_mensaje_en") or "",
        ultimo_mensaje_extracto=row.get("ultimo_mensaje_extracto") or "",
        notas=row.get("notas") or "",
    )


def _row_to_mensaje(row: dict) -> Mensaje:
    return Mensaje(
        id=row["id"],
        direccion=row["direccion"],
        tipo=row["tipo"],
        contenido=row.get("contenido") or "",
        storage_path=row.get("storage_path"),
        enviado_por=row.get("enviado_por") or "",
        creado_en=row.get("creado_en") or "",
    )


def _touch(telefono: str, extracto: str, nombre: str = "") -> None:
    """Crea o actualiza la fila de `conversaciones` con el último mensaje, para poder
    ordenar la bandeja por recencia sin consultar `mensajes` cada vez. No pisa el
    nombre ya guardado si esta vez no lo conocemos."""
    payload = {
        "telefono": telefono,
        "ultimo_mensaje_en": datetime.now(timezone.utc).isoformat(),
        "ultimo_mensaje_extracto": extracto[:120],
    }
    if nombre:
        payload["nombre"] = nombre
    get_client().table("conversaciones").upsert(payload).execute()


def ya_registrado(wa_message_id: str) -> bool:
    """True si ya guardamos un mensaje entrante con este ID de WhatsApp. Meta reintenta
    la entrega del webhook si nuestra respuesta tarda más de unos segundos (pasa sobre
    todo con imágenes, por la clasificación con Claude) — sin este chequeo, el mismo
    mensaje del paciente queda registrado dos veces y Aurora le contesta dos veces."""
    if not wa_message_id:
        return False
    resp = (
        get_client()
        .table("mensajes")
        .select("id")
        .eq("wa_message_id", wa_message_id)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def registrar_entrante(
    telefono: str,
    tipo: str,
    contenido: str = "",
    storage_path: Optional[str] = None,
    nombre: str = "",
    wa_message_id: str = "",
) -> None:
    # `mensajes.telefono` tiene llave foránea a `conversaciones.telefono` — hay que
    # asegurar la fila de conversaciones ANTES de insertar el mensaje, o falla en el
    # primer mensaje de un número nuevo.
    _touch(telefono, contenido if tipo == "texto" else "📷 Imagen", nombre=nombre)
    get_client().table("mensajes").insert(
        {
            "telefono": telefono,
            "direccion": "entrante",
            "tipo": tipo,
            "contenido": contenido,
            "storage_path": storage_path,
            "enviado_por": "paciente",
            "wa_message_id": wa_message_id or None,
        }
    ).execute()


def registrar_saliente(
    telefono: str, tipo: str, enviado_por: str, contenido: str = "", storage_path: Optional[str] = None
) -> None:
    _touch(telefono, contenido if (tipo == "texto" and contenido) else "📷 Imagen")
    get_client().table("mensajes").insert(
        {
            "telefono": telefono,
            "direccion": "saliente",
            "tipo": tipo,
            "contenido": contenido,
            "storage_path": storage_path,
            "enviado_por": enviado_por,
        }
    ).execute()


def listar(busqueda: str = "", limit: int = 200) -> list[Conversacion]:
    query = get_client().table("conversaciones").select("*").order("ultimo_mensaje_en", desc=True).limit(limit)
    if busqueda:
        termino = busqueda.strip()
        query = query.or_(f"telefono.ilike.%{termino}%,nombre.ilike.%{termino}%")
    resp = query.execute()
    return [_row_to_conversacion(row) for row in resp.data]


def obtener(telefono: str) -> Optional[Conversacion]:
    resp = get_client().table("conversaciones").select("*").eq("telefono", telefono).limit(1).execute()
    return _row_to_conversacion(resp.data[0]) if resp.data else None


def historial(telefono: str, limit: int = 300) -> list[Mensaje]:
    resp = (
        get_client()
        .table("mensajes")
        .select("*")
        .eq("telefono", telefono)
        .order("creado_en")
        .limit(limit)
        .execute()
    )
    return [_row_to_mensaje(row) for row in resp.data]


def pausar(telefono: str, agente_email: str) -> None:
    """Un agente tomó el control del chat desde el panel — Aurora deja de responder
    automáticamente aquí hasta que alguien lo reactive."""
    get_client().table("conversaciones").update(
        {"pausada": True, "pausada_por": agente_email, "pausada_en": datetime.now(timezone.utc).isoformat()}
    ).eq("telefono", telefono).execute()


def reanudar(telefono: str) -> None:
    get_client().table("conversaciones").update(
        {"pausada": False, "pausada_por": None, "pausada_en": None}
    ).eq("telefono", telefono).execute()


def esta_pausada(telefono: str) -> bool:
    conv = obtener(telefono)
    return conv.pausada if conv else False


def actualizar_nombre(telefono: str, nombre: str) -> None:
    """El agente le pone (o corrige) el nombre a una conversación desde el panel —
    útil cuando el paciente escribe antes de que su solicitud quede asociada a un
    nombre conocido, o cuando llegó por un canal donde no lo dio."""
    get_client().table("conversaciones").update({"nombre": nombre or None}).eq("telefono", telefono).execute()


def actualizar_notas(telefono: str, notas: str) -> None:
    """Notas libres del agente sobre este chat — disponibles en cualquier conversación,
    a diferencia de las observaciones de una solicitud (que solo existen mientras hay
    un trámite abierto). Se editan desde el botón "Observaciones" del panel."""
    get_client().table("conversaciones").update({"notas": notas.strip() or None}).eq("telefono", telefono).execute()
