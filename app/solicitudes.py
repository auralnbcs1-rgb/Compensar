"""Capa de datos sobre `solicitudes` — un trámite de un paciente para uno de los 5
servicios de Aurora (evaluación y adaptación, prueba de audífono, evaluación tinnitus,
control, terapia tinnitus). Independiente de `backlog`, que sigue siendo solo el
backlog de entrega de audífonos de Compensar (ver `_sincronizar_backlog_si_aplica` en
main.py para cómo se cruzan cuando aplica).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.db import get_client

# clave = número de opción tal como aparece en el menú; valor = (código interno que se
# guarda en la base de datos, nombre para mostrar al paciente, si requiere autorización
# de servicio + cédula además de la orden clínica — las marcadas con * en el pedido original).
SERVICIOS = {
    "1": ("evaluacion_adaptacion", "Evaluación y adaptación de prótesis y ayudas auditivas", True),
    "2": ("prueba_audifono", "Prueba de Audífono", False),
    "3": ("evaluacion_tinnitus", "Evaluación Tinnitus", True),
    "4": ("control", "Control (1er control 30 días posterior a la adaptación)", False),
    "5": ("terapia_tinnitus", "Terapia Tinnitus", True),
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


def contar_por_estado() -> dict[str, int]:
    resp = get_client().table("solicitudes").select("estado").execute()
    conteo: dict[str, int] = {}
    for row in resp.data:
        conteo[row["estado"]] = conteo.get(row["estado"], 0) + 1
    return conteo
