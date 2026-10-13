"""Presencia de agentes en el panel — para mostrar quién está conectado ahora mismo.

No hay websockets en este servicio, así que no hay forma de "saber" en tiempo real
quién tiene el panel abierto. En su lugar, cada página del panel manda un "heartbeat"
por JavaScript (ver el <script> al final de cada render_* en dashboard.py) cada 30
segundos a POST /dashboard/heartbeat, que actualiza `ultimo_visto` para ese agente en
la tabla `agentes_presencia`. Se considera "conectado" a cualquier agente que haya
mandado un heartbeat en los últimos VENTANA_MINUTOS — si cierra la pestaña o se le cae
la conexión, simplemente deja de aparecer en cuanto pasa ese tiempo, sin necesidad de
un evento de "desconexión" explícito.

Tabla en Supabase (crear una sola vez, ver instrucciones aparte):
    agentes_presencia
      email          text primary key
      ultimo_visto   timestamptz not null
"""
import logging
from datetime import datetime, timedelta, timezone

from app.db import get_client

logger = logging.getLogger("presencia")

VENTANA_MINUTOS = 2  # sin heartbeat en este tiempo => se considera desconectado


def marcar_activo(email: str) -> None:
    """Registra que este agente mandó un heartbeat ahora. No tumba la petición si
    Supabase falla — la presencia es solo un indicador visual, no algo crítico."""
    if not email:
        return
    try:
        get_client().table("agentes_presencia").upsert(
            {"email": email, "ultimo_visto": datetime.now(timezone.utc).isoformat()}
        ).execute()
    except Exception:
        logger.exception("No se pudo registrar el heartbeat de presencia para email=%r", email)


def listar_conectados() -> list[str]:
    """Emails de los agentes que mandaron un heartbeat en los últimos VENTANA_MINUTOS,
    ordenados alfabéticamente. Devuelve [] si algo falla, en vez de romper el panel."""
    desde = datetime.now(timezone.utc) - timedelta(minutes=VENTANA_MINUTOS)
    try:
        resp = (
            get_client()
            .table("agentes_presencia")
            .select("email")
            .gte("ultimo_visto", desde.isoformat())
            .execute()
        )
    except Exception:
        logger.exception("No se pudo leer la lista de agentes conectados")
        return []
    return sorted({row["email"] for row in resp.data})
