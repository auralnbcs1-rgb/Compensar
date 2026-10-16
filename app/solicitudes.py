"""Capa de datos sobre `solicitudes` — un trámite de un paciente para uno de los 6
servicios de Aurora (evaluación y adaptación, prueba de audífono, control, evaluación
tinnitus, terapia tinnitus, mantenimiento). Independiente de `backlog`, que sigue
siendo solo el backlog de entrega de audífonos de Compensar (ver
`_sincronizar_backlog_si_aplica` en main.py para cómo se cruzan cuando aplica).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db import get_client

# clave = número de opción tal como aparece en el menú; valor = (código interno que se
# guarda en la base de datos, nombre para mostrar al paciente, si requiere autorización
# de servicio + cédula además de la orden clínica — las marcadas con * en el pedido original).
SERVICIOS = {
    "1": ("evaluacion_adaptacion", "Evaluación y adaptación de prótesis y ayudas auditivas", True),
    "2": ("prueba_audifono", "Prueba de Audífono (orden de Compensar)", False),
    "3": ("control", "Control (1er control 30 días posterior a la adaptación)", False),
    "4": ("evaluacion_tinnitus", "Evaluación Tinnitus", True),
    "5": ("terapia_tinnitus", "Terapia Tinnitus", True),
    "6": ("mantenimiento", "Mantenimiento", False),
}

NOMBRE_SERVICIO = {codigo: nombre for _, (codigo, nombre, _) in SERVICIOS.items()}

# true → orden clínica + autorización de servicio + cédula; false → solo orden clínica vigente.
DOCUMENTOS_REQUERIDOS: dict[bool, list[str]] = {
    True: ["orden_clinica", "autorizacion_servicio", "cedula"],
    False: ["orden_clinica"],
}

ESTADOS_ABIERTOS = ("pendiente_documentos", "orden_vencida", "requiere_humano")


@dataclass
class Solicitud:
    id: int
    cedula: str
    nombre: str
    telefono: str
    servicio: str
    requiere_autorizacion: bool
    estado: str
    fecha_nacimiento: str = ""
    direccion: str = ""
    regimen: str = ""
    telefono_2: str = ""
    correo: str = ""
    atendido_por: str = ""
    observaciones: str = ""
    actualizado_en: str = ""


def _row_to_solicitud(row: dict) -> Solicitud:
    return Solicitud(
        id=row["id"],
        cedula=row["cedula"],
        nombre=row["nombre"],
        telefono=row["telefono"],
        servicio=row["servicio"],
        requiere_autorizacion=row["requiere_autorizacion"],
        estado=row["estado"],
        fecha_nacimiento=row.get("fecha_nacimiento") or "",
        direccion=row.get("direccion") or "",
        regimen=row.get("regimen") or "",
        telefono_2=row.get("telefono_2") or "",
        correo=row.get("correo") or "",
        atendido_por=row.get("atendido_por") or "",
        observaciones=row.get("observaciones") or "",
        actualizado_en=row.get("actualizado_en") or "",
    )


def crear(
    cedula: str,
    nombre: str,
    telefono: str,
    servicio: str,
    requiere_autorizacion: bool,
    fecha_nacimiento: str = "",
    direccion: str = "",
    regimen: str = "",
    telefono_2: str = "",
    correo: str = "",
) -> Solicitud:
    resp = (
        get_client()
        .table("solicitudes")
        .insert(
            {
                "cedula": cedula,
                "nombre": nombre,
                "telefono": telefono,
                "servicio": servicio,
                "requiere_autorizacion": requiere_autorizacion,
                "fecha_nacimiento": fecha_nacimiento or None,
                "direccion": direccion,
                "regimen": regimen,
                "telefono_2": telefono_2,
                "correo": correo,
            }
        )
        .execute()
    )
    return _row_to_solicitud(resp.data[0])


def abierta_por_telefono(telefono: str) -> Optional[Solicitud]:
    """La solicitud en curso (sin cerrar) más reciente de este número, si hay una."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .eq("telefono", telefono)
        .in_("estado", list(ESTADOS_ABIERTOS))
        .order("creado_en", desc=True)
        .limit(1)
        .execute()
    )
    return _row_to_solicitud(resp.data[0]) if resp.data else None


def ultima_por_telefono(telefono: str) -> Optional[Solicitud]:
    """La solicitud más reciente de este número, esté abierta o ya cerrada — la usa el
    panel de chats para saber si el caso quedó pidiendo un asesor, o quién ya lo atendió,
    incluso después de que se marcó como atendida."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .eq("telefono", telefono)
        .order("creado_en", desc=True)
        .limit(1)
        .execute()
    )
    return _row_to_solicitud(resp.data[0]) if resp.data else None


def actualizar_estado(solicitud_id: int, estado: str) -> None:
    get_client().table("solicitudes").update(
        {"estado": estado, "actualizado_en": datetime.now(timezone.utc).isoformat()}
    ).eq("id", solicitud_id).execute()


def listas_para_agente(limit: int = 50) -> list[Solicitud]:
    """Solicitudes con documentos completos — la franja azul: listas para que el
    agente de atención al cliente las tome y agende."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .eq("estado", "documentos_completos")
        .order("actualizado_en", desc=True)
        .limit(limit)
        .execute()
    )
    return [_row_to_solicitud(row) for row in resp.data]


def requieren_asesor(limit: int = 50) -> list[Solicitud]:
    """Solicitudes que Aurora marcó como 'requiere_humano' — la franja naranja: el
    paciente pidió (o necesita) que un asesor lo atienda directamente. Deja de
    aparecer aquí en cuanto un agente la marca como atendida con `marcar_gestionada`."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .eq("estado", "requiere_humano")
        .order("actualizado_en", desc=True)
        .limit(limit)
        .execute()
    )
    return [_row_to_solicitud(row) for row in resp.data]


# De qué estado sale cada botón del panel, y a cuál lo deja — 'requiere_humano' (franja
# naranja) lo cierra un agente que ya atendió al paciente; 'documentos_completos'
# (franja azul) lo cierra un agente que ya agendó la cita.
GESTION_DESTINO = {
    "requiere_humano": "atendida",
    "documentos_completos": "agendada",
}


def destino_gestion(estado: str) -> Optional[str]:
    """A qué estado queda una solicitud cuando un agente la marca como gestionada desde
    el botón "Gestionado" del panel — disponible en CUALQUIER chat, no solo naranja/azul.
    Las dos transiciones con nombre propio (GESTION_DESTINO) significan lo mismo que
    siempre; cualquier otro estado abierto (pendiente_documentos, orden_vencida) se cierra
    como 'atendida' genérica — el agente ya se encargó del caso por fuera del flujo normal.
    Si ya está en un estado gestionado (atendida/agendada), no hay nada que hacer: None."""
    if estado in GESTION_DESTINO:
        return GESTION_DESTINO[estado]
    if estado in ESTADOS_GESTIONADOS:
        return None
    return "atendida"


def marcar_gestionada(solicitud_id: int, agente_email: str, estado_final: str, observaciones: str = "") -> None:
    """Un agente confirma que ya gestionó este caso — lo atendió (venía de
    'requiere_humano') o lo agendó (venía de 'documentos_completos') — y deja
    registrado quién lo hizo y qué hizo (observaciones), para que se vea en el panel."""
    get_client().table("solicitudes").update(
        {
            "estado": estado_final,
            "atendido_por": agente_email,
            "observaciones": observaciones.strip() or None,
            "actualizado_en": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", solicitud_id).execute()


def contar_por_estado() -> dict[str, int]:
    resp = get_client().table("solicitudes").select("estado").execute()
    conteo: dict[str, int] = {}
    for row in resp.data:
        conteo[row["estado"]] = conteo.get(row["estado"], 0) + 1
    return conteo


def contar_por_servicio() -> dict[str, int]:
    """Cuántas solicitudes ha habido por trámite, histórico completo (abiertas y
    cerradas, desde siempre) — para el dashboard de "cuántos necesitan cada servicio"."""
    resp = get_client().table("solicitudes").select("servicio").execute()
    conteo: dict[str, int] = {}
    for row in resp.data:
        conteo[row["servicio"]] = conteo.get(row["servicio"], 0) + 1
    return conteo


def contar_por_servicio_abiertas() -> dict[str, int]:
    """Lo mismo que `contar_por_servicio`, pero solo entre las solicitudes que siguen
    abiertas ahora mismo (ESTADOS_ABIERTOS) — el panorama actual, no el histórico."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("servicio")
        .in_("estado", list(ESTADOS_ABIERTOS))
        .execute()
    )
    conteo: dict[str, int] = {}
    for row in resp.data:
        conteo[row["servicio"]] = conteo.get(row["servicio"], 0) + 1
    return conteo


# Estados en los que queda una solicitud una vez que un agente la gestiona desde el
# panel (ver GESTION_DESTINO) — se usan para contar "cuántos se gestionan" por período.
ESTADOS_GESTIONADOS = ("atendida", "agendada")


def contar_gestionados_desde(desde_iso: str) -> int:
    """Cuántas solicitudes quedaron gestionadas (atendida o agendada por un agente,
    ver `marcar_gestionada`) desde esta fecha/hora en adelante (ISO, UTC) — para los
    conteos de hoy/semana/mes del dashboard."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("id", count="exact")
        .in_("estado", list(ESTADOS_GESTIONADOS))
        .gte("actualizado_en", desde_iso)
        .execute()
    )
    return resp.count or 0


def gestionadas(limit: int = 50) -> list[Solicitud]:
    """Solicitudes ya gestionadas por un agente (atendida o agendada, ver
    `marcar_gestionada`) — para el filtro "Gestionados" del panel de chats, separado
    de las que siguen con franja de color (naranja/azul)."""
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .in_("estado", list(ESTADOS_GESTIONADOS))
        .order("actualizado_en", desc=True)
        .limit(limit)
        .execute()
    )
    return [_row_to_solicitud(row) for row in resp.data]


def esperando_documentos_demorados(horas: int = 72, limit: int = 100) -> list[Solicitud]:
    """Solicitudes en 'pendiente_documentos' que llevan más de `horas` sin que el
    paciente mande nada nuevo (actualizado_en no se mueve) — los casos que se están
    quedando atrás esperando documentos, para el panel de Reportes."""
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    resp = (
        get_client()
        .table("solicitudes")
        .select("*")
        .eq("estado", "pendiente_documentos")
        .lte("actualizado_en", limite.isoformat())
        .order("actualizado_en")
        .limit(limit)
        .execute()
    )
    return [_row_to_solicitud(row) for row in resp.data]
