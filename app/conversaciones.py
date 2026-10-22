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
from datetime import date, datetime, timezone
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
    pausada_en: str = ""  # desde cuándo un agente tiene el control (solo si pausada=True)


@dataclass
class Mensaje:
    id: int
    direccion: str  # entrante | saliente
    tipo: str  # texto | imagen
    contenido: str
    storage_path: Optional[str]
    enviado_por: str  # paciente | aurora | correo del agente
    creado_en: str
    estado_entrega: str = ""  # "" (sin dato aún) | sent | delivered | read | failed — solo saliente
    error_entrega: str = ""  # motivo que dio Meta cuando estado_entrega == "failed"


def _row_to_conversacion(row: dict) -> Conversacion:
    return Conversacion(
        telefono=row["telefono"],
        nombre=row.get("nombre") or "",
        pausada=bool(row.get("pausada", False)),
        pausada_por=row.get("pausada_por") or "",
        ultimo_mensaje_en=row.get("ultimo_mensaje_en") or "",
        ultimo_mensaje_extracto=row.get("ultimo_mensaje_extracto") or "",
        notas=row.get("notas") or "",
        pausada_en=row.get("pausada_en") or "",
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
        estado_entrega=row.get("estado_entrega") or "",
        error_entrega=row.get("error_entrega") or "",
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
    telefono: str,
    tipo: str,
    enviado_por: str,
    contenido: str = "",
    storage_path: Optional[str] = None,
    wa_message_id: str = "",
) -> None:
    """`wa_message_id` es el ID (wamid...) que WhatsApp devuelve al aceptar el envío —
    se guarda para poder relacionar este mensaje con el evento de estado (entregado o
    fallido) que Meta manda después, por separado, al webhook (ver
    marcar_estado_entrega más abajo y _extract_status en main.py)."""
    _touch(telefono, contenido if (tipo == "texto" and contenido) else "📷 Imagen")
    get_client().table("mensajes").insert(
        {
            "telefono": telefono,
            "direccion": "saliente",
            "tipo": tipo,
            "contenido": contenido,
            "storage_path": storage_path,
            "enviado_por": enviado_por,
            "wa_message_id": wa_message_id or None,
        }
    ).execute()


def listar(busqueda: str = "", limit: int = 500) -> tuple[list[Conversacion], bool]:
    """Bandeja de chats para el panel, ordenada por el mensaje más reciente primero.
    Paginada de verdad: en vez de subir el tope cada vez que el historial crece (lo que
    tarde o temprano vuelve a poner lento el panel), trae como mucho `limit` chats y
    dice si hay más — el botón "Cargar más" del panel (ver render_lista_chats en
    dashboard.py) pide de 500 en 500 según haga falta, sin perder nada del historial:
    todo sigue guardado en Supabase, solo que no se trae de una sola vez.

    Devuelve (chats, hay_mas). Para saber si hay más sin tener que contar toda la
    tabla en cada carga, se pide un chat de más (`limit + 1`); si llega, se descarta
    y se marca hay_mas=True."""
    query = get_client().table("conversaciones").select("*").order("ultimo_mensaje_en", desc=True).limit(limit + 1)
    if busqueda:
        termino = busqueda.strip()
        query = query.or_(f"telefono.ilike.%{termino}%,nombre.ilike.%{termino}%")
    resp = query.execute()
    filas = resp.data
    hay_mas = len(filas) > limit
    return [_row_to_conversacion(row) for row in filas[:limit]], hay_mas


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


def pausadas(limit: int = 100) -> list[Conversacion]:
    """Chats que un agente ya tomó (le quitó el control a Aurora) y que siguen así —
    todavía no los reactivó ni los cerró. Para el panel de Reportes, ordenados del que
    lleva más tiempo tomado al que menos, para que no se queden olvidados."""
    resp = (
        get_client()
        .table("conversaciones")
        .select("*")
        .eq("pausada", True)
        .order("pausada_en")
        .limit(limit)
        .execute()
    )
    return [_row_to_conversacion(row) for row in resp.data]


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


def marcar_estado_entrega(wa_message_id: str, estado: str, error: str = "") -> None:
    """Guarda el resultado real de un mensaje saliente (sent/delivered/read/failed) que
    llegó por el webhook de estados de WhatsApp — independiente del 200 OK que Meta da
    al momento de mandarlo, que solo confirma que lo recibió para procesar, no que se
    entregó. Si no encontramos el mensaje (por ejemplo uno viejo, de antes de guardar
    wa_message_id), no hace nada — no hay nada que actualizar."""
    if not wa_message_id:
        return
    get_client().table("mensajes").update(
        {"estado_entrega": estado, "error_entrega": error or None}
    ).eq("wa_message_id", wa_message_id).execute()


def mensajes_entrantes_entre(desde: date, hasta: date, limit: int = 1500) -> list[str]:
    """Texto de los mensajes que escribieron los pacientes (entrantes, tipo texto)
    entre `desde` y `hasta` — para el Excel de Reportes, que le pide a Claude que los
    agrupe por tema ("lo que más preguntaron"). Solo el texto, sin teléfono ni nombre:
    no hace falta identificar a nadie para sacar los temas más comunes."""
    inicio = datetime.combine(desde, datetime.min.time(), tzinfo=timezone.utc)
    fin = datetime.combine(hasta, datetime.max.time(), tzinfo=timezone.utc)
    resp = (
        get_client()
        .table("mensajes")
        .select("contenido")
        .eq("direccion", "entrante")
        .eq("tipo", "texto")
        .gte("creado_en", inicio.isoformat())
        .lte("creado_en", fin.isoformat())
        .order("creado_en")
        .limit(limit)
        .execute()
    )
    return [row["contenido"].strip() for row in resp.data if row.get("contenido") and row["contenido"].strip()]
