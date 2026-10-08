"""Cálculos para el dashboard.

El bot no agenda citas — solo confirma interés y pasa al paciente a la cola del agente
de atención al cliente. Por eso el dashboard mide "confirmados" (resultado='interesado'
en registro_diario), no "agendados": el cierre real de la cita (fecha/hora) lo hace el
agente por fuera del bot. La meta de 70/día sigue siendo la referencia del negocio, pero
aquí funciona como meta de CONFIRMACIONES que alimentan esa cola, no de citas cerradas.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

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
    # Aurora: solicitudes de los 6 trámites (evaluación, prueba, control, tinnitus x2, mantenimiento).
    solicitudes_por_estado: dict[str, int] = field(default_factory=dict)
    listas_para_agente: list[SolicitudLista] = field(default_factory=list)
    # Cuántas solicitudes ha habido por trámite — histórico completo y las que siguen
    # abiertas ahora mismo (ambas claveadas por el código interno del servicio).
    servicio_totales: dict[str, int] = field(default_factory=dict)
    servicio_abiertas: dict[str, int] = field(default_factory=dict)
    # Cuántas solicitudes quedaron gestionadas (atendida o agendada por un agente) en
    # cada período — hoy, esta semana (desde el lunes), este mes.
    gestionados_hoy: int = 0
    gestionados_semana: int = 0
    gestionados_mes: int = 0


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

    servicio_totales = solicitudes_module.contar_por_servicio()
    servicio_abiertas = solicitudes_module.contar_por_servicio_abiertas()

    # Límites de hoy/semana/mes en UTC — coherente con cómo se guarda `actualizado_en`
    # (datetime.now(timezone.utc).isoformat() en solicitudes.marcar_gestionada).
    inicio_dia = datetime.combine(hoy, datetime.min.time(), tzinfo=timezone.utc)
    inicio_semana = inicio_dia - timedelta(days=hoy.weekday())  # lunes de esta semana
    inicio_mes_dt = datetime.combine(inicio_mes, datetime.min.time(), tzinfo=timezone.utc)

    gestionados_hoy = solicitudes_module.contar_gestionados_desde(inicio_dia.isoformat())
    gestionados_semana = solicitudes_module.contar_gestionados_desde(inicio_semana.isoformat())
    gestionados_mes = solicitudes_module.contar_gestionados_desde(inicio_mes_dt.isoformat())

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
        servicio_totales=servicio_totales,
        servicio_abiertas=servicio_abiertas,
        gestionados_hoy=gestionados_hoy,
        gestionados_semana=gestionados_semana,
        gestionados_mes=gestionados_mes,
    )
