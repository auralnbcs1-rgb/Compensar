"""Imágenes del panel de chats (lo que manda el paciente, y lo que manda un agente desde
el dashboard) — se guardan en el MISMO bucket privado que ya usa documentos.py
(`SUPABASE_STORAGE_BUCKET`), bajo su propio prefijo (`chat/...`), para no obligar a
crear un bucket aparte en Supabase. No tiene nada que ver con la validación de
documentos del trámite (orden clínica, etc.) — es solo el respaldo de lo que se ve en
el historial del chat.
"""
import logging
import uuid

from app.config import settings
from app.db import get_client

logger = logging.getLogger("chat_media")


def subir_imagen(telefono: str, contenido: bytes, content_type: str) -> str:
    """Devuelve "" si Supabase no logra guardar la imagen (en vez de tumbar todo el
    webhook con un error 500) — el mensaje se sigue registrando igual, solo que el
    panel avisa que esa imagen puntual no se pudo guardar en vez de mostrarla."""
    ext = "png" if "png" in content_type else "jpg"
    path = f"chat/{telefono}/{uuid.uuid4().hex}.{ext}"
    try:
        get_client().storage.from_(settings.storage_bucket_documentos).upload(
            path, contenido, {"content-type": content_type}
        )
    except Exception:
        logger.exception("No se pudo subir la imagen a storage_path=%r (bucket=%r)", path, settings.storage_bucket_documentos)
        return ""
    return path


def url_firmada(storage_path: str, segundos: int = 3600) -> str:
    """URL temporal para mostrar la imagen en el dashboard — el bucket es privado, así
    que no hay una URL pública fija. Si Supabase no logra firmarla (el archivo no está,
    hubo un error de permisos, etc.) devuelve "" en vez de tumbar toda la conversación
    con un error 500 — el chat se sigue viendo, solo sin esa imagen puntual."""
    try:
        resp = get_client().storage.from_(settings.storage_bucket_documentos).create_signed_url(
            storage_path, segundos
        )
    except Exception:
        logger.exception("No se pudo firmar la URL para storage_path=%r (bucket=%r)", storage_path, settings.storage_bucket_documentos)
        return ""
    if isinstance(resp, dict):
        url = resp.get("signedURL") or resp.get("signedUrl") or ""
        if not url:
            logger.warning(
                "create_signed_url no devolvió URL para storage_path=%r (bucket=%r) — respuesta: %r",
                storage_path, settings.storage_bucket_documentos, resp,
            )
        return url
    url = getattr(resp, "signed_url", "") or ""
    if not url:
        logger.warning(
            "create_signed_url no devolvió URL para storage_path=%r (bucket=%r) — respuesta: %r",
            storage_path, settings.storage_bucket_documentos, resp,
        )
    return url
