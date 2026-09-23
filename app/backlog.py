"""Capa de datos sobre el backlog de pacientes Compensar — tabla `backlog` en Supabase.

Mantiene las mismas funciones (y firmas) que usan main.py y send_daily_batch.py, así que
el resto del código no necesita saber que la fuente es Supabase y no un CSV.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.db import get_client


@dataclass
class Patient:
    cedula: str
    nombre: str
    telefono: str
    sede: str
    estado: str
    ultimo_intento: str
    intentos: int


def _row_to_patient(row: dict) -> Patient:
    return Patient(
        cedula=row["cedula"],
        nombre=row["nombre"],
        telefono=row["telefono"],
        sede=row["sede"],
        estado=row["estado"],
        ultimo_intento=row.get("ultimo_intento") or "",
        intentos=row.get("intentos") or 0,
    )


def next_batch(limit: int) -> list[Patient]:
    """Los siguientes `limit` pacientes pendientes, para el envío diario de plantillas."""
    resp = (
        get_client()
        .table("backlog")
        .select("*")
        .eq("estado", "pendiente")
        .order("creado_en")
        .limit(limit)
        .execute()
    )
    return [_row_to_patient(row) for row in resp.data]


def find_by_phone(telefono: str) -> Optional[Patient]:
    resp = get_client().table("backlog").select("*").eq("telefono", telefono).limit(1).execute()
    return _row_to_patient(resp.data[0]) if resp.data else None


def find_by_cedula(cedula: str) -> Optional[Patient]:
    resp = get_client().table("backlog").select("*").eq("cedula", cedula).limit(1).execute()
    return _row_to_patient(resp.data[0]) if resp.data else None


def update_estado(telefono: str, estado: str, increment_intento: bool = False) -> None:
    patient = find_by_phone(telefono)
    update = {
        "estado": estado,
        "ultimo_intento": datetime.now(timezone.utc).isoformat(),
    }
    if increment_intento and patient is not None:
        update["intentos"] = patient.intentos + 1
    get_client().table("backlog").update(update).eq("telefono", telefono).execute()


def pendientes_count() -> int:
    """Cuántos pacientes quedan sin agendar — usado por el dashboard para el burn-down."""
    resp = (
        get_client()
        .table("backlog")
        .select("id", count="exact")
        .eq("estado", "pendiente")
        .execute()
    )
    return resp.count or 0
