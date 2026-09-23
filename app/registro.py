"""Registro de resultados — tabla `registro_diario` en Supabase.

El bot nunca agenda una fecha/hora: "interesado" es el resultado normal cuando el
paciente sigue queriendo la entrega, y lo deja en la cola del agente de atención al
cliente, que agenda por fuera del bot (llamada o chat) y confirma el día y la hora.
"agendado" existe como valor válido para cuando el agente marca manualmente que ya
cerró la cita — el bot mismo no lo usa.
"""
from datetime import datetime, timezone

from app.db import get_client


def registrar(
    cedula: str,
    nombre: str,
    sede: str = "",
    resultado: str = "interesado",
) -> None:
    """resultado ∈ {"interesado", "no_interesado", "requiere_humano", "agendado"}
    (el bot solo escribe los primeros tres; "agendado" queda para uso manual del agente)."""
    get_client().table("registro_diario").insert(
        {
            "fecha": datetime.now(timezone.utc).date().isoformat(),
            "cedula": cedula,
            "nombre": nombre,
            "sede": sede,
            "resultado": resultado,
            "canal": "bot_whatsapp_compensar",
        }
    ).execute()
