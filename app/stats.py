"""Cálculos para el dashboard.

El bot no agenda citas — solo confirma interés y pasa al paciente a la cola del agente
de atención al cliente. Por eso el dashboard mide "confirmados" (resultado='interesado'
en registro_diario), no "agendados": el cierre real de la cita (fecha/hora) lo hace el
agente por fuera del bot. La meta de 70/día sigue siendo la referencia del negocio, pero
aquí funciona como meta de CONFIRMACIONES que alimentan esa cola, no de citas cerradas.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import solicitudes as solicitudes_module
from app.backlog import pendientes_count
from app.config import settings
from app.db import get_client

DIAS_HISTORIAL = 14  # ventana para calcular el ritmo diario promedio


@dataclass
class SolicitudLista:
    nombre: str
    cedula: str
    servicio_nombre: str
    telefono: str
    regimen: str


@dataclass
class DashboardStats:
    confirmados_hoy: int
    meta_diaria: int
    confirmados_mes: int
    pendientes: int
    ritmo_diario_promedio: float
    dias_para_vaciar_backlog: float | None  # None = sin datos suficientes para proyectar
    historial: list[tuple[str, int]]  # [(fecha_iso, confirmados_ese_dia), ...] orden ascendente
    # Aurora: solicitudes de los 5 trámites (evaluación, prueba, tinnitus, control, terapia).
    solicitudes_por_estado: dict[str, int] = field(default_factory=dict)
    listas_para_agente: list[SolicitudLista] = field(default_factory=list)


def _confirmados_en(desde: date, hasta: date) -> int:
    resp = (
        get_client()
        .table("registro_diario")
        .select("id", count="exact")
        .eq("resultado", "interesado")
        .gte("fecha", desde.isoformat())
        .lte("fecha", hasta.isoformat())
        .execute()
    )
    return resp.count or 0


def _historial_diario(dias: int) -> list[tuple[str, int]]:
    desde = date.today() - timedelta(days=dias - 1)
    resp = (
        get_client()
        .table("registro_diario")
        .select("fecha")
        .eq("resultado", "interesado")
        .gte("fecha", desde.isoformat())
        .execute()
    )
    conteo: dict[str, int] = {(desde + timedelta(days=i)).isoformat(): 0 for i in range(dias)}
    for row in resp.data:
        conteo[row["fecha"]] = conteo.get(row["fecha"], 0) + 1
    return sorted(conteo.items())


def get_dashboard_stats() -> DashboardStats:
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    historial = _historial_diario(DIAS_HISTORIAL)
    total_historial = sum(c for _, c in historial)
    ritmo_promedio = total_historial / DIAS_HISTORIAL if DIAS_HISTORIAL else 0.0

    pendientes = pendientes_count()
    dias_restantes = (pendientes / ritmo_promedio) if ritmo_promedio > 0 else None

    solicitudes_por_estado = solicitudes_module.contar_por_estado()
    listas_para_agente = [
        SolicitudLista(
            nombre=s.nombre,
            cedula=s.cedula,
            servicio_nombre=solicitudes_module.NOMBRE_SERVICIO.get(s.servicio, s.servicio),
            telefono=s.telefono,
            regimen=s.regimen,
        )
        for s in solicitudes_module.listas_para_agente(limit=20)
    ]

    return DashboardStats(
        confirmados_hoy=_confirmados_en(hoy, hoy),
        meta_diaria=settings.daily_goal,
        confirmados_mes=_confirmados_en(inicio_mes, hoy),
        pendientes=pendientes,
        ritmo_diario_promedio=round(ritmo_promedio, 1),
        dias_para_vaciar_backlog=round(dias_restantes, 0) if dias_restantes is not None else None,
        historial=historial,
        solicitudes_por_estado=solicitudes_por_estado,
        listas_para_agente=listas_para_agente,
    )
