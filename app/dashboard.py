"""Construye el HTML del dashboard (una sola página, sin dependencias externas).

Paleta: navy y teal de la identidad de marca de Aural (ver manual de marca), más un
par semántico verde/rojo reservado solo para el estado de la meta diaria — nunca
reutilizado como color de serie, siguiendo la regla de "status colors are reserved".

BLUE es un tercer color de estado, reservado solo para "documentos completos, listo
para el agente" (la franja azul que pidió Compensar) — WhatsApp Cloud API no permite
que el bot ponga etiquetas de color nativas de WhatsApp Business, así que esta franja
en el dashboard es la forma real de verlo: ver nota en README.md.
"""
import html
from datetime import date, datetime

from app.conversaciones import Conversacion, Mensaje
from app.stats import DashboardStats

NAVY = "#041E42"
GRAY = "#706F6F"
TEAL = "#10616F"       # acento — magnitud (barras)
GOOD = "#1E8E5A"        # meta cumplida
BEHIND = "#B3261E"      # por debajo de la meta
BLUE = "#1D5FB3"        # documentos completos — listo para el agente (franja azul)
SURFACE = "#FFFFFF"
MUTED_GRID = "#E4E4E4"

CHART_W = 640
CHART_H = 220
PAD_L = 36
PAD_B = 28
PAD_T = 16


def _fmt_dia(iso: str) -> str:
    d = datetime.fromisoformat(iso).date()
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    return f"{dias[d.weekday()]} {d.day}"


def _bar_chart_svg(stats: DashboardStats) -> str:
    valores = [c for _, c in stats.historial]
    maximo = max(valores + [stats.meta_diaria, 1])

    plot_w = CHART_W - PAD_L - 8
    plot_h = CHART_H - PAD_T - PAD_B
    n = len(stats.historial)
    bar_w = plot_w / n * 0.6
    gap = plot_w / n

    def y_de(valor: float) -> float:
        return PAD_T + plot_h - (valor / maximo * plot_h)

    bars = []
    labels = []
    for i, (fecha_iso, valor) in enumerate(stats.historial):
        x = PAD_L + i * gap + (gap - bar_w) / 2
        y = y_de(valor)
        h = (PAD_T + plot_h) - y
        color = GOOD if valor >= stats.meta_diaria else TEAL
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 0):.1f}" '
            f'rx="3" fill="{color}"><title>{fecha_iso}: {valor} confirmados</title></rect>'
        )
        if i % 2 == 0 or n <= 7:
            labels.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{CHART_H - 8}" font-size="10" '
                f'fill="{GRAY}" text-anchor="middle">{_fmt_dia(fecha_iso)}</text>'
            )

    meta_y = y_de(stats.meta_diaria)
    meta_line = (
        f'<line x1="{PAD_L}" y1="{meta_y:.1f}" x2="{CHART_W - 8}" y2="{meta_y:.1f}" '
        f'stroke="{NAVY}" stroke-width="1.5" stroke-dasharray="4,3" />'
        f'<text x="{CHART_W - 8}" y="{meta_y - 6:.1f}" font-size="10" fill="{NAVY}" '
        f'text-anchor="end">Meta: {stats.meta_diaria}/día</text>'
    )

    axis = f'<line x1="{PAD_L}" y1="{PAD_T + plot_h}" x2="{CHART_W - 8}" y2="{PAD_T + plot_h}" stroke="{MUTED_GRID}" stroke-width="1" />'

    return (
        f'<svg viewBox="0 0 {CHART_W} {CHART_H}" width="100%" height="{CHART_H}" '
        f'role="img" aria-label="Pacientes confirmados por día, últimos {n} días, comparado con la meta diaria">'
        f'{axis}{"".join(bars)}{meta_line}{"".join(labels)}'
        f"</svg>"
    )


def _tile(titulo: str, valor: str, nota: str = "", color: str = NAVY) -> str:
    return f"""
    <div class="tile">
      <div class="tile-titulo">{titulo}</div>
      <div class="tile-valor" style="color:{color}">{valor}</div>
      {f'<div class="tile-nota">{nota}</div>' if nota else ""}
    </div>"""


def render_login(error: str = "") -> str:
    """Página de login del dashboard — correo/clave verificados contra Supabase Auth
    (ver app/dashboard_auth.py). Los perfiles se administran desde Supabase
    (Authentication → Users), no desde variables de entorno."""
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Ingresar — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: {SURFACE}; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: {NAVY};
  }}
  .caja {{ border: 1px solid {MUTED_GRID}; border-radius: 10px; padding: 32px; width: 100%; max-width: 320px; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  .subtitulo {{ color: {GRAY}; font-size: 13px; margin: 0 0 20px; }}
  label {{ display: block; font-size: 13px; color: {GRAY}; margin-bottom: 4px; }}
  input {{
    width: 100%; box-sizing: border-box; padding: 8px 10px; margin-bottom: 14px;
    border: 1px solid {MUTED_GRID}; border-radius: 6px; font-size: 14px;
  }}
  button {{
    width: 100%; padding: 9px; background: {NAVY}; color: {SURFACE}; border: none;
    border-radius: 6px; font-size: 14px; cursor: pointer;
  }}
  .error {{ color: {BEHIND}; font-size: 13px; margin: 0 0 14px; }}
</style>
</head>
<body>
  <div class="caja">
    <h1>Aurora — Compensar</h1>
    <p class="subtitulo">Entra con tu correo y clave</p>
    {f'<p class="error">{error}</p>' if error else ""}
    <form method="post" action="/login">
      <label for="email">Correo</label>
      <input type="email" id="email" name="email" required autofocus />
      <label for="password">Clave</label>
      <input type="password" id="password" name="password" required />
      <button type="submit">Entrar</button>
    </form>
  </div>
</body>
</html>"""


def _fila_lista_azul(nombre: str, cedula: str, servicio_nombre: str, telefono: str, regimen: str) -> str:
    detalle = " · ".join(x for x in [telefono, regimen] if x)
    return f"""
    <div class="fila-azul">
      <div class="fila-azul-nombre">{nombre} <span class="fila-azul-cedula">· CC {cedula}</span></div>
      <div class="fila-azul-servicio">{servicio_nombre}</div>
      {f'<div class="fila-azul-detalle">{detalle}</div>' if detalle else ""}
    </div>"""


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
  <p class="subtitulo"><a href="/dashboard/chats" style="color:{NAVY}; font-weight:600;">Ver conversaciones →</a></p>

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


# ---------------------------------------------------------------------------
# Panel de chats — bandeja de conversaciones + entrar a escribir/mandar imágenes como
# agente (equivalente al inbox de Amanda). Reusa NAVY/GRAY/TEAL/SURFACE/MUTED_GRID.
# ---------------------------------------------------------------------------

def _fmt_hora(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.strftime("%d %b %I:%M %p").lstrip("0").replace(" 0", " ")


def _avatar(telefono: str) -> str:
    return html.escape(telefono[-2:]) if telefono else "??"


def _sidebar(activo: str, email: str) -> str:
    """Barra lateral de navegación — inspirada en el panel de Amanda (Chats / Reportes / Salir),
    con lo que sí existe en Aurora: no hay 'Agendados' porque Aurora no agenda citas."""
    def item(href: str, etiqueta: str, clave: str) -> str:
        activo_cls = " sb-activo" if clave == activo else ""
        return f'<a class="sb-item{activo_cls}" href="{href}">{etiqueta}</a>'

    return f"""
  <nav class="sidebar">
    <div class="sb-logo">A</div>
    <div class="sb-nav">
      {item("/dashboard/chats", "Chats", "chats")}
      {item("/dashboard", "Reportes", "reportes")}
    </div>
    <a class="sb-item sb-salir" href="/logout" title="{html.escape(email)}">Salir</a>
  </nav>"""


def _fila_chat(conv: Conversacion) -> str:
    titulo = html.escape(conv.nombre) if conv.nombre else conv.telefono
    subtitulo = f" · {conv.telefono}" if conv.nombre else ""
    extracto = html.escape(conv.ultimo_mensaje_extracto)
    if conv.pausada:
        badge = f'<span class="badge badge-pausada">Tú tienes el control{" · " + html.escape(conv.pausada_por) if conv.pausada_por else ""}</span>'
    else:
        badge = '<span class="badge badge-activa">● Aurora activa</span>'
    return f"""
    <a class="fila-chat" href="/dashboard/chats/{conv.telefono}" target="chatframe">
      <div class="fila-chat-avatar">{_avatar(conv.telefono)}</div>
      <div class="fila-chat-cuerpo">
        <div class="fila-chat-encabezado">
          <span class="fila-chat-titulo">{titulo}<span class="fila-chat-sub">{subtitulo}</span></span>
          <span class="fila-chat-hora">{_fmt_hora(conv.ultimo_mensaje_en)}</span>
        </div>
        <div class="fila-chat-extracto">{extracto}</div>
        {badge}
      </div>
    </a>"""


_PLACEHOLDER_IFRAME = (
    "data:text/html;charset=utf-8,"
    "<body style='margin:0;height:100vh;display:flex;align-items:center;justify-content:center;"
    "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:%23706F6F;"
    "background:%23FAFAFA;font-size:14px;'>Selecciona una conversaci%C3%B3n para empezar</body>"
)


def render_lista_chats(chats: list[Conversacion], email: str = "", busqueda: str = "", estado: str = "todas") -> str:
    if estado == "activas":
        chats = [c for c in chats if not c.pausada]
    elif estado == "pausadas":
        chats = [c for c in chats if c.pausada]

    filas = "".join(_fila_chat(c) for c in chats)
    if not filas:
        filas = '<p class="fila-azul-vacio">No hay conversaciones que coincidan.</p>'

    def opcion(valor: str, etiqueta: str) -> str:
        sel = " selected" if estado == valor else ""
        return f'<option value="{valor}"{sel}>{etiqueta}</option>'

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Conversaciones — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: {SURFACE};
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: {NAVY};
  }}
  .layout {{ display: flex; height: 100vh; }}

  .sidebar {{
    width: 76px; flex: none; background: {NAVY}; display: flex; flex-direction: column;
    align-items: center; padding: 16px 0;
  }}
  .sb-logo {{
    width: 34px; height: 34px; border-radius: 8px; background: {TEAL}; color: {SURFACE};
    display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 15px;
    margin-bottom: 28px;
  }}
  .sb-nav {{ display: flex; flex-direction: column; gap: 4px; flex: 1; width: 100%; }}
  .sb-item {{
    display: block; text-align: center; color: #B7C2D4; text-decoration: none; font-size: 11px;
    padding: 10px 4px; margin: 0 8px; border-radius: 8px;
  }}
  .sb-item:hover {{ background: rgba(255,255,255,0.08); color: {SURFACE}; }}
  .sb-activo {{ background: rgba(255,255,255,0.14); color: {SURFACE}; font-weight: 600; }}
  .sb-salir {{ color: #8592A6; }}

  .lista-col {{
    width: 360px; flex: none; border-right: 1px solid {MUTED_GRID}; display: flex; flex-direction: column;
    height: 100vh;
  }}
  .lista-header {{ padding: 20px 18px 12px; border-bottom: 1px solid {MUTED_GRID}; }}
  .lista-header h1 {{ font-size: 17px; margin: 0; }}
  .lista-conteo {{ font-size: 12px; color: {GRAY}; margin: 2px 0 14px; }}
  form.buscar {{ margin: 0 0 8px; }}
  form.buscar input {{
    width: 100%; padding: 9px 12px; border: 1px solid {MUTED_GRID};
    border-radius: 8px; font-size: 13px;
  }}
  form.buscar select {{
    width: 100%; margin-top: 8px; padding: 8px 10px; border: 1px solid {MUTED_GRID};
    border-radius: 8px; font-size: 13px; background: {SURFACE}; color: {NAVY};
  }}
  .lista-scroll {{ overflow-y: auto; flex: 1; padding: 8px 10px 24px; }}

  .fila-chat {{
    display: flex; gap: 10px; border-radius: 10px; padding: 10px 10px;
    margin-bottom: 4px; text-decoration: none; color: inherit;
  }}
  .fila-chat:hover {{ background: #F3F5F8; }}
  .fila-chat-avatar {{
    flex: none; width: 38px; height: 38px; border-radius: 50%; background: {TEAL}; color: {SURFACE};
    display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700;
  }}
  .fila-chat-cuerpo {{ min-width: 0; flex: 1; }}
  .fila-chat-encabezado {{ display: flex; justify-content: space-between; align-items: baseline; gap: 6px; }}
  .fila-chat-titulo {{ font-size: 13.5px; font-weight: 600; color: {NAVY}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .fila-chat-sub {{ font-weight: 400; color: {GRAY}; font-size: 11.5px; }}
  .fila-chat-hora {{ font-size: 10.5px; color: {GRAY}; white-space: nowrap; flex: none; }}
  .fila-chat-extracto {{
    font-size: 12.5px; color: {GRAY}; margin: 2px 0 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .badge {{ display: inline-block; font-size: 10.5px; padding: 2px 8px; border-radius: 999px; }}
  .badge-activa {{ background: #E6F4EF; color: {GOOD}; }}
  .badge-pausada {{ background: #FCEFEA; color: {BEHIND}; }}
  .fila-azul-vacio {{ font-size: 13px; color: {GRAY}; padding: 12px 8px; }}

  .detalle-col {{ flex: 1; min-width: 0; }}
  .detalle-col iframe {{ width: 100%; height: 100vh; border: none; display: block; }}
</style>
</head>
<body>
  <div class="layout">
    {_sidebar("chats", email)}
    <div class="lista-col">
      <div class="lista-header">
        <h1>Aurora</h1>
        <div class="lista-conteo">{len(chats)} conversación(es)</div>
        <form class="buscar" method="get" action="/dashboard/chats">
          <input type="text" name="q" value="{html.escape(busqueda)}" placeholder="Buscar por nombre o número…" />
          <select name="estado" onchange="this.form.submit()">
            {opcion("todas", "Todas")}
            {opcion("activas", "Aurora activa")}
            {opcion("pausadas", "Requieren atención")}
          </select>
        </form>
      </div>
      <div class="lista-scroll">{filas}</div>
    </div>
    <div class="detalle-col">
      <iframe name="chatframe" src="{_PLACEHOLDER_IFRAME}" title="Conversación"></iframe>
    </div>
  </div>
</body>
</html>"""


def _burbuja(m: Mensaje) -> str:
    from app.chat_media import url_firmada  # import diferido: evita ciclos si algún día chat_media crece

    es_entrante = m.direccion == "entrante"
    if es_entrante:
        quien = "Paciente"
    elif m.enviado_por == "aurora":
        quien = "Aurora"
    else:
        quien = m.enviado_por or "Agente"

    if m.tipo == "imagen" and m.storage_path:
        cuerpo = f'<img src="{url_firmada(m.storage_path)}" alt="Imagen del chat" style="max-width:220px; border-radius:8px; display:block;" />'
        if m.contenido:
            cuerpo += f'<div style="margin-top:4px;">{html.escape(m.contenido)}</div>'
    else:
        cuerpo = html.escape(m.contenido).replace("\n", "<br>")

    lado = "burbuja-izq" if es_entrante else "burbuja-der"
    return f"""
    <div class="burbuja {lado}">
      <div class="burbuja-quien">{html.escape(quien)} · {_fmt_hora(m.creado_en)}</div>
      <div class="burbuja-cuerpo">{cuerpo}</div>
    </div>"""


def render_chat(conv: Conversacion, historial: list[Mensaje], email: str = "") -> str:
    titulo = html.escape(conv.nombre) if conv.nombre else conv.telefono
    burbujas = "".join(_burbuja(m) for m in historial) or '<p class="fila-azul-vacio">Todavía no hay mensajes.</p>'

    if conv.pausada:
        estado_html = f"""
      <span class="badge badge-pausada">Tú tienes el control{" · " + html.escape(conv.pausada_por) if conv.pausada_por else ""}</span>
      <form method="post" action="/dashboard/chats/{conv.telefono}/reanudar" style="display:inline;">
        <button type="submit" class="boton-secundario">Reactivar Aurora</button>
      </form>"""
    else:
        estado_html = '<span class="badge badge-activa">Aurora activa</span>'

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{titulo} — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 32px 24px 64px; background: {SURFACE}; max-width: 640px;
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: {NAVY};
  }}
  h1 {{ font-size: 20px; margin: 0 0 6px; }}
  .badge {{ display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; margin-right: 8px; }}
  .badge-activa {{ background: #E6F4EF; color: {GOOD}; }}
  .badge-pausada {{ background: #FCEFEA; color: {BEHIND}; }}
  .boton-secundario {{
    font-size: 11px; padding: 3px 10px; border-radius: 999px; border: 1px solid {MUTED_GRID};
    background: {SURFACE}; color: {NAVY}; cursor: pointer;
  }}
  .estado {{ margin: 10px 0 20px; }}
  .hilo {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }}
  .burbuja {{ max-width: 78%; border-radius: 10px; padding: 8px 12px; font-size: 13px; }}
  .burbuja-izq {{ align-self: flex-start; background: {SURFACE}; border: 1px solid {MUTED_GRID}; }}
  .burbuja-der {{ align-self: flex-end; background: #EEF3FC; border: 1px solid #D7E3F7; }}
  .burbuja-quien {{ font-size: 10px; color: {GRAY}; margin-bottom: 3px; }}
  .burbuja-cuerpo {{ color: {NAVY}; white-space: pre-wrap; }}
  form.enviar {{
    position: sticky; bottom: 0; background: {SURFACE}; border-top: 1px solid {MUTED_GRID};
    padding-top: 12px;
  }}
  form.enviar textarea {{
    width: 100%; box-sizing: border-box; padding: 9px 12px; border: 1px solid {MUTED_GRID};
    border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical; min-height: 44px;
  }}
  form.enviar .fila-envio {{ display: flex; align-items: center; gap: 10px; margin-top: 8px; }}
  form.enviar button {{
    padding: 9px 18px; background: {NAVY}; color: {SURFACE}; border: none; border-radius: 6px;
    font-size: 14px; cursor: pointer;
  }}
  .nota-envio {{ font-size: 11px; color: {GRAY}; margin-top: 6px; }}
</style>
</head>
<body>
  <a href="/dashboard/chats" style="color:{GRAY}; font-size:12px;">← Conversaciones</a>
  <h1>{titulo}{f' <span style="font-weight:400; color:{GRAY}; font-size:14px;">· {conv.telefono}</span>' if conv.nombre else ""}</h1>
  <div class="estado">{estado_html}</div>

  <div class="hilo">{burbujas}</div>

  <form class="enviar" method="post" action="/dashboard/chats/{conv.telefono}/enviar" enctype="multipart/form-data">
    <textarea name="texto" placeholder="Escribe un mensaje…"></textarea>
    <div class="fila-envio">
      <input type="file" name="imagen" accept="image/*" />
      <button type="submit">Enviar</button>
    </div>
    <p class="nota-envio">Al enviar, este chat queda a tu cargo — Aurora deja de contestar aquí hasta que le des a "Reactivar Aurora".</p>
  </form>
</body>
</html>"""
