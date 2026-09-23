"""Cliente delgado sobre WhatsApp Cloud API (Meta Graph API).

El flujo del bot es inbound (el paciente escribe primero), así que en operación normal
solo se usa send_text(). send_template() se deja lista para un caso opcional a futuro
—por ejemplo recordarle a quien todavía no ha escrito— pero requiere una plantilla
aprobada en Meta Business Suite y no es necesaria para poner el bot en marcha.
"""
import httpx
from app.config import settings

GRAPH_API_VERSION = "v20.0"


def _base_url() -> str:
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_phone_number_id}/messages"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }


def send_template(to_phone: str, patient_name: str) -> dict:
    """Envía la plantilla de primer contacto (categoría Utility) a un paciente del backlog.

    `patient_name` reemplaza la variable {{1}} de la plantilla. Ajusta los `parameters`
    si la plantilla aprobada en Meta usa más variables.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": settings.whatsapp_template_name,
            "language": {"code": settings.whatsapp_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": patient_name}],
                }
            ],
        },
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(_base_url(), headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


def send_text(to_phone: str, body: str) -> dict:
    """Envía un mensaje de texto libre (solo dentro de la ventana de 24h)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body},
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(_base_url(), headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


def _media_upload_url() -> str:
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_phone_number_id}/media"


def upload_media(contenido: bytes, content_type: str) -> str:
    """Sube un archivo a WhatsApp (paso obligatorio antes de poder mandarlo) y devuelve
    su media_id — lo usa el panel de chats cuando un agente adjunta una imagen."""
    files = {"file": ("imagen", contenido, content_type)}
    data = {"messaging_product": "whatsapp"}
    with httpx.Client(timeout=30) as client:
        resp = client.post(_media_upload_url(), headers=_auth_headers(), data=data, files=files)
        resp.raise_for_status()
        return resp.json()["id"]


def send_image(to_phone: str, media_id: str, caption: str = "") -> dict:
    """Manda una imagen ya subida (media_id de upload_media) — usado por el panel de
    chats cuando un agente contesta con una foto."""
    image_payload: dict = {"id": media_id}
    if caption:
        image_payload["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "image",
        "image": image_payload,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(_base_url(), headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


def mark_read(message_id: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    with httpx.Client(timeout=15) as client:
        client.post(_base_url(), headers=_headers(), json=payload)


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {settings.whatsapp_access_token}"}


def get_media_url(media_id: str) -> str:
    """Los adjuntos de WhatsApp no traen una URL directa: primero hay que pedirle a la
    API la URL temporal (válida unos minutos) para ese media_id."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    with httpx.Client(timeout=15) as client:
        resp = client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.json()["url"]


def download_media(media_url: str) -> tuple[bytes, str]:
    """Descarga el contenido de un adjunto (imagen) de WhatsApp. Devuelve
    (contenido_binario, content_type) — la URL exige el mismo Bearer token de la API,
    no es pública."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(media_url, headers=_auth_headers())
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "image/jpeg")
