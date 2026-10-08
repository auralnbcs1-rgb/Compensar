def _fila_lista_azul(nombre: str, cedula: str, servicio_nombre: str, telefono: str, regimen: str) -> str:
    detalle = " · ".join(x for x in [telefono, regimen] if x)
    return f"""
    <div class="fila-azul">
      <div class="fila-azul-nombre">{nombre} <span class="fila-azul-cedula">· CC {cedula}</span></div>
      <div class="fila-azul-servicio">{servicio_nombre}</div>
      {f'<div class="fila-azul-detalle">{detalle}</div>' if detalle else ""}
    </div>"""


def _fila_servicio(nombre: str, total: int, abiertas: int) -> str:
    return f"<tr><td>{html.escape(nombre)}</td><td>{total}</td><td>{abiertas}</td></tr>"


def render_dashboard(stats: DashboardStats, email: str = "") -> str:
    color_hoy = GOOD if stats.confirmados_hoy >= stats.meta_diaria else BEHIND
    proyeccion = (
        f"{int(stats.dias_para_vaciar_backlog)} días al ritmo actual"
        if stats.dias_para_vaciar_backlog is not None
        else "sin datos suficientes aún"
    )

    tabla_filas = "".join(
        f"<tr><td>{fecha}</td><td>{valor}</td></tr>" for fecha, valor in reversed(stats.historial)
    )

    documentos_completos = stats.solicitudes_por_estado.get("documentos_completos", 0)
    pendiente_docs = stats.solicitudes_por_estado.get("pendiente_documentos", 0)
    orden_vencida = stats.solicitudes_por_estado.get("orden_vencida", 0)

    filas_azules = "".join(
        _fila_lista_azul(s.nombre, s.cedula, s.servicio_nombre, s.telefono, s.regimen)
        for s in stats.listas_para_agente
    )
    if not filas_azules:
        filas_azules = '<p class="fila-azul-vacio">Todavía no hay ninguna solicitud con documentos completos.</p>'

    # Por trámite: histórico completo (desde siempre) vs. las que siguen abiertas ahora.
    filas_servicio = "".join(
        _fila_servicio(nombre, stats.servicio_totales.get(codigo, 0), stats.servicio_abiertas.get(codigo, 0))
        for codigo, nombre in NOMBRE_SERVICIO.items()
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Dashboard — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 32px 24px 64px; background: {SURFACE};
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: {NAVY};
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitulo {{ color: {GRAY}; font-size: 13px; margin: 0 0 28px; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; max-width: 960px; }}
  .tile {{ border: 1px solid {MUTED_GRID}; border-radius: 10px; padding: 16px 18px; }}
  .tile-titulo {{ font-size: 12px; color: {GRAY}; margin-bottom: 6px; }}
  .tile-valor {{ font-size: 28px; font-weight: 700; line-height: 1.1; }}
  .tile-nota {{ font-size: 12px; color: {GRAY}; margin-top: 4px; }}
  .panel {{ max-width: 700px; border: 1px solid {MUTED_GRID}; border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
  .panel h2 {{ font-size: 14px; margin: 0 0 4px; }}
  .panel-nota {{ font-size: 12px; color: {GRAY}; margin: 0 0 14px; }}
  details {{ margin-top: 14px; font-size: 13px; color: {GRAY}; }}
  table {{ border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
  td {{ padding: 3px 12px 3px 0; }}
  .fila-azul {{
    border-left: 4px solid {BLUE}; background: #EEF3FC; border-radius: 0 6px 6px 0;
    padding: 8px 12px; margin-bottom: 8px;
  }}
  .fila-azul-nombre {{ font-size: 13px; font-weight: 600; color: {NAVY}; }}
  .fila-azul-cedula {{ font-weight: 400; color: {GRAY}; }}
  .fila-azul-servicio {{ font-size: 12px; color: {BLUE}; margin-top: 2px; }}
  .fila-azul-detalle {{ font-size: 12px; color: {GRAY}; margin-top: 2px; }}
  .fila-azul-vacio {{ font-size: 13px; color: {GRAY}; }}
  footer {{ margin-top: 40px; font-size: 12px; color: {GRAY}; }}
</style>
</head>
<body>
  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
    <h1>Aurora — Compensar / Widex Colombia S.A.S.</h1>
    {f'<div style="font-size:12px; color:{GRAY};">{email} · <a href="/logout" style="color:{GRAY};">cerrar sesión</a></div>' if email else ""}
  </div>
  <p class="subtitulo">Actualizado {date.today().isoformat()} · datos de Supabase, sin depender del Excel</p>
  <p class="subtitulo">Aurora recolecta documentos y confirma interés — el agente de atención al cliente cierra la cita (fecha/hora) por fuera del bot.</p>
  <p class="subtitulo"><a href="/dashboard/chats" style="color:{NAVY}; font-weight:600;">Ver conversaciones →</a> · <a href="/dashboard/completas" style="color:{NAVY}; font-weight:600;">Ver solicitudes completas →</a></p>

  <div class="tiles">
    {_tile("Confirmados hoy", f"{stats.confirmados_hoy} / {stats.meta_diaria}", "meta diaria de confirmaciones", color_hoy)}
    {_tile("Confirmados este mes", str(stats.confirmados_mes))}
    {_tile("Pendientes en backlog", str(stats.pendientes))}
    {_tile("Backlog se vacía en", proyeccion, f"ritmo: {stats.ritmo_diario_promedio}/día")}
  </div>

  <div class="tiles">
    {_tile("Documentos completos", str(documentos_completos), "listos para el agente", BLUE)}
    {_tile("Esperando documentos", str(pendiente_docs))}
    {_tile("Orden vencida", str(orden_vencida), "hay que pedir una nueva")}
  </div>

  <div class="tiles">
    {_tile("Gestionados hoy", str(stats.gestionados_hoy), "atendidos + agendados", GOOD)}
    {_tile("Gestionados esta semana", str(stats.gestionados_semana))}
    {_tile("Gestionados este mes", str(stats.gestionados_mes))}
  </div>

  <div class="panel">
    <h2>Solicitudes por trámite</h2>
    <p class="panel-nota">
      "Histórico" cuenta todas las solicitudes que ha habido de ese trámite desde siempre
      (abiertas y cerradas). "Abiertas" son las que siguen en curso ahora mismo.
    </p>
    <table>
      <tr><td><strong>Trámite</strong></td><td><strong>Histórico</strong></td><td><strong>Abiertas</strong></td></tr>
      {filas_servicio}
    </table>
  </div>

  <div class="panel">
    <h2>Listos para el agente (documentos completos)</h2>
    <p class="panel-nota">
      WhatsApp Cloud API no deja que el bot ponga la etiqueta de color nativa de WhatsApp
      Business — esta franja azul es el equivalente: en cuanto Aurora recibe todo lo que
      hace falta, el paciente aparece aquí.
    </p>
    {filas_azules}
  </div>

  <div class="panel">
    <h2>Confirmados por día (últimos {len(stats.historial)} días) vs. meta</h2>
    {_bar_chart_svg(stats)}
    <details>
      <summary>Ver como tabla</summary>
      <table>
        <tr><td><strong>Fecha</strong></td><td><strong>Confirmados</strong></td></tr>
        {tabla_filas}
      </table>
    </details>
  </div>

  <footer>Aurora — Compensar / Widex Colombia S.A.S. Proyecto independiente, base de datos propia en Supabase.</footer>
</body>
</html>"""
