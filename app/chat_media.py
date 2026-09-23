"""Imágenes del panel de chats (lo que manda el paciente, y lo que manda un agente desde
el dashboard) — se guardan en el MISMO bucket privado que ya usa documentos.py
(`SUPABASE_STORAGE_BUCKET`), bajo su propio prefijo (`chat/...`), para no obligar a
crear un bucket aparte en Supabase. No tiene nada que ver con la validación de
documentos del trámite (orden clínica, etc.) — es solo el respaldo de lo que se ve en
el historial del chat.
"""
import uuid

from app.config import settings
from app.db import get_client


def subir_imagen(telefono: str, contenido: bytes, content_type: str) -> str:
    ext = "png" if "png" in content_type else "jpg"
    path = f"chat/{telefono}/{uuid.uuid4().hex}.{ext}"
    get_client().storage.from_(settings.storage_bucket_documentos).upload(
        path, contenido, {"content-type": content_type}
    )
    return path


def url_firmada(storage_path: str, segundos: int = 3600) -> str:
    """URL temporal para mostrar la imagen en el dashboard — el bucket es privado, así
    que no hay una URL pública fija."""
    resp = get_client().storage.from_(settings.storage_bucket_documentos).create_signed_url(
        storage_path, segundos
    )
    if isinstance(resp, dict):
        return resp.get("signedURL") or resp.get("signedUrl") or ""
    return getattr(resp, "signed_url", "") or ""
