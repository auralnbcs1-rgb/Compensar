"""Capa de datos sobre `documentos` — cada imagen que un paciente manda para una
solicitud (orden clínica, autorización de servicio, cédula), guardada en Supabase
Storage (bucket privado) y registrada en la tabla `documentos`.
"""
import uuid
from datetime import date
from typing import Optional

from app.config import settings
from app.db import get_client


def subir_imagen(solicitud_id: int, contenido: bytes, content_type: str) -> str:
    """Sube la imagen al bucket privado `documentos-pacientes` y devuelve su ruta
    dentro del bucket (storage_path)."""
    ext = "png" if "png" in content_type else "jpg"
    path = f"{solicitud_id}/{uuid.uuid4().hex}.{ext}"
    get_client().storage.from_(settings.storage_bucket_documentos).upload(
        path, contenido, {"content-type": content_type}
    )
    return path


def registrar(
    solicitud_id: int,
    tipo: str,
    storage_path: str,
    fecha_detectada: Optional[date] = None,
    vigente: Optional[bool] = None,
    nota_ia: str = "",
) -> None:
    get_client().table("documentos").insert(
        {
            "solicitud_id": solicitud_id,
            "tipo": tipo,
            "storage_path": storage_path,
            "fecha_detectada": fecha_detectada.isoformat() if fecha_detectada else None,
            "vigente": vigente,
            "nota_ia": nota_ia,
        }
    ).execute()


def tipos_recibidos(solicitud_id: int) -> set[str]:
    """Qué tipos de documento ya llegaron para esta solicitud."""
    resp = get_client().table("documentos").select("tipo").eq("solicitud_id", solicitud_id).execute()
    return {row["tipo"] for row in resp.data if row["tipo"] != "sin_clasificar"}


def ultima_orden_vigente(solicitud_id: int) -> Optional[bool]:
    """`vigente` de la orden clínica más reciente registrada para esta solicitud, o
    None si todavía no hay ninguna (o no se pudo determinar)."""
    resp = (
        get_client()
        .table("documentos")
        .select("vigente")
        .eq("solicitud_id", solicitud_id)
        .eq("tipo", "orden_clinica")
        .order("creado_en", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["vigente"] if resp.data else None
