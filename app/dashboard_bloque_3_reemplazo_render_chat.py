def render_chat(
    conv: Conversacion,
    historial: list[Mensaje],
    email: str = "",
    solicitud: Optional[Solicitud] = None,
    documentos_lista: Optional[list[dict]] = None,
) -> str:
    titulo = html.escape(conv.nombre) if conv.nombre else conv.telefono
    nombre_valor = html.escape(conv.nombre) if conv.nombre else ""
    burbujas = "".join(_burbuja(m) for m in historial) or '<p class="fila-vacio">Todavía no hay mensajes.</p>'

    if conv.pausada:
        boton_estado = f"""
      <form method="post" action="/dashboard/chats/{conv.telefono}/reanudar" style="display:inline;">
        <button type="submit" class="boton-primario">Reactivar Aurora</button>
      </form>"""
    else:
        boton_estado = f"""
      <form method="post" action="/dashboard/chats/{conv.telefono}/pausar" style="display:inline;">
        <button type="submit" class="boton-primario">Pausar Aurora</button>
      </form>"""

    # Badge informativo según el estado de la solicitud (si hay una) — solo para que se
    # vea de un vistazo; no depende de esto para poder anotar observaciones.
    badge_gestion = ""
    if solicitud is not None and solicitud.estado == "requiere_humano":
        badge_gestion = '<div class="badge badge-naranja-chat">🟠 Requiere asesor</div>'
    elif solicitud is not None and solicitud.estado == "documentos_completos":
        badge_gestion = '<div class="badge badge-azul-chat">🔵 Documentos completos — falta agendar</div>'
    elif solicitud is not None and solicitud.estado in ("atendida", "agendada") and solicitud.atendido_por:
        etiqueta = "Atendida" if solicitud.estado == "atendida" else "Agendada"
        nota = f' — {html.escape(solicitud.observaciones)}' if solicitud.observaciones else ""
        badge_gestion = f'<div class="badge badge-hecho">✅ {etiqueta} por {html.escape(solicitud.atendido_por)}{nota}</div>'

    # Recuadro con toda la información del paciente — se muestra en cuanto la solicitud
    # tiene documentos completos (o ya se agendó a partir de ahí); no antes, porque
    # todavía puede faltar algo.
    mostrar_recuadro = solicitud is not None and solicitud.estado in ("documentos_completos", "agendada")
    recuadro_html = _recuadro_paciente(solicitud, documentos_lista or []) if mostrar_recuadro else ""

    # Observaciones: un solo botón, disponible en CUALQUIER chat (no solo naranja/azul).
    # Guarda una nota libre en la conversación; si además hay un caso naranja o azul
    # abierto, de paso lo cierra (atendida/agendada) con esa misma nota.
    nota_valor = html.escape(conv.notas) if conv.notas else ""
    gestion_dropdown = f"""
        <details class="editar-caja">
          <summary>Observaciones</summary>
          <div class="editar-panel panel-ancho">
            <form method="post" action="/dashboard/chats/{conv.telefono}/observaciones">
              <label for="observaciones">Observaciones de este chat</label>
              <textarea id="observaciones" name="observaciones" placeholder="Escribe aquí lo que hiciste o lo que necesites recordar…">{nota_valor}</textarea>
              <button type="submit">Guardar</button>
            </form>
          </div>
        </details>"""

    # Gestionado: botón rápido de un solo clic, aparte del dropdown de Observaciones —
    # solo se ve cuando el chat tiene un color activo (naranja/azul) y sirve para
    # quitárselo sin tener que escribir nada. Guarda igual las observaciones que ya
    # hubiera, no las borra.
    boton_gestionado = ""
    if solicitud is not None and solicitud.estado in GESTION_DESTINO:
        boton_gestionado = f"""
        <form method="post" action="/dashboard/chats/{conv.telefono}/gestionado" style="display:inline;">
          <button type="submit" class="boton-gestionado" title="Quita el color de este chat — marca el caso como ya gestionado">Gestionado</button>
        </form>"""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{titulo} — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: {SURFACE};
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: {NAVY};
  }}
  .marco {{ display: flex; flex-direction: column; height: 100vh; }}

  .cabecera {{
    display: flex; align-items: center; gap: 12px; padding: 16px 24px; border-bottom: 1px solid {MUTED_GRID};
    flex: none; flex-wrap: wrap; row-gap: 10px;
  }}
  .cabecera-avatar {{
    width: 40px; height: 40px; border-radius: 50%; background: {NAVY}; color: {SURFACE};
    display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex: none;
  }}
  .cabecera-cuerpo {{ min-width: 220px; flex: 1; }}
  .cabecera-cuerpo h1 {{ font-size: 16px; margin: 0; }}
  .cabecera-telefono {{ font-size: 12px; color: {GRAY}; margin-top: 1px; }}
  .badge {{ display: inline-block; font-size: 11px; margin-top: 3px; }}
  .badge-pausada {{ color: {BEHIND}; }}
  .cabecera-acciones {{ display: flex; align-items: center; gap: 8px; flex: none; }}

  .editar-caja {{ position: relative; }}
  .editar-caja summary {{
    font-size: 11px; padding: 6px 14px; border-radius: 999px; border: 1px solid {MUTED_GRID};
    background: {SURFACE}; color: {NAVY}; cursor: pointer; white-space: nowrap; list-style: none;
  }}
  .editar-caja summary::-webkit-details-marker {{ display: none; }}
  .editar-caja summary:hover {{ background: #F3F5F8; }}
  .editar-caja[open] summary {{ background: #F3F5F8; }}
  .editar-panel {{
    position: absolute; top: calc(100% + 6px); right: 0; background: {SURFACE};
    border: 1px solid {MUTED_GRID}; border-radius: 10px; padding: 12px; box-shadow: 0 4px 16px rgba(4,30,66,0.12);
    z-index: 10; width: 240px;
  }}
  .editar-panel label {{ font-size: 11px; color: {GRAY}; display: block; margin-bottom: 5px; }}
  .editar-panel input {{
    width: 100%; font-size: 13px; padding: 7px 10px; border: 1px solid {MUTED_GRID}; border-radius: 6px;
  }}
  .editar-panel button {{
    margin-top: 8px; width: 100%; font-size: 12px; padding: 7px 0; border-radius: 6px; border: none;
    background: {NAVY}; color: {SURFACE}; cursor: pointer;
  }}
  .editar-panel button:hover {{ background: #0A2E56; }}

  .boton-primario {{
    font-size: 12px; padding: 7px 16px; border-radius: 6px; border: none;
    background: {NAVY}; color: {SURFACE}; cursor: pointer; white-space: nowrap;
  }}
  .boton-primario:hover {{ background: #0A2E56; }}

  .boton-gestionado {{
    font-size: 12px; padding: 7px 16px; border-radius: 6px; border: 1px solid {GOOD};
    background: {SURFACE}; color: {GOOD}; cursor: pointer; white-space: nowrap; font-weight: 600;
  }}
  .boton-gestionado:hover {{ background: #EAF7F0; }}

  .badge-naranja-chat, .badge-azul-chat, .badge-hecho {{
    display: inline-block; font-size: 11px; margin-top: 3px; font-weight: 600;
  }}
  .badge-naranja-chat {{ color: {ORANGE}; }}
  .badge-azul-chat {{ color: {BLUE}; }}
  .badge-hecho {{ color: {GOOD}; }}

  .panel-ancho {{ width: 300px; }}
  .editar-panel textarea {{
    width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid {MUTED_GRID};
    border-radius: 6px; font-size: 13px; font-family: inherit; resize: vertical; min-height: 60px;
    margin-bottom: 8px;
  }}

  .recuadro-paciente {{
    margin: 14px 24px 0; padding: 14px 16px; border: 1px solid #D7E3F7; background: #EEF3FC;
    border-radius: 10px;
  }}
  .recuadro-titulo {{ font-size: 13px; font-weight: 700; color: {NAVY}; margin-bottom: 8px; }}
  .recuadro-datos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 4px 16px; margin-bottom: 8px; }}
  .dato-fila {{ font-size: 12.5px; }}
  .dato-etiqueta {{ color: {GRAY}; margin-right: 6px; }}
  .dato-valor {{ color: {NAVY}; font-weight: 600; }}
  .recuadro-documentos {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: {NAVY}; border-top: 1px solid #D7E3F7; padding-top: 8px; }}
  .doc-fila-vacio {{ font-size: 12px; color: {GRAY}; }}

  .hilo-scroll {{ flex: 1; overflow-y: auto; padding: 20px 24px; background: #FAFBFC; }}
  .hilo {{ display: flex; flex-direction: column; gap: 10px; max-width: 640px; margin: 0 auto; }}
  .burbuja {{ max-width: 78%; border-radius: 12px; padding: 9px 13px; font-size: 13.5px; box-shadow: 0 1px 1px rgba(4,30,66,0.05); }}
  .burbuja-izq {{ align-self: flex-start; background: {SURFACE}; border: 1px solid {MUTED_GRID}; }}
  .burbuja-der {{ align-self: flex-end; background: #EEF3FC; border: 1px solid #D7E3F7; }}
  .burbuja-quien {{ font-size: 10px; color: {GRAY}; margin-bottom: 3px; }}
  .burbuja-cuerpo {{ color: {NAVY}; white-space: pre-wrap; }}
  .fila-vacio {{ font-size: 13px; color: {GRAY}; text-align: center; margin-top: 60px; }}

  form.enviar {{ flex: none; background: {SURFACE}; border-top: 1px solid {MUTED_GRID}; padding: 14px 24px; }}
  form.enviar textarea {{
    width: 100%; box-sizing: border-box; padding: 10px 13px; border: 1px solid {MUTED_GRID};
    border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical; min-height: 44px;
  }}
  form.enviar .fila-envio {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; }}
  .input-archivo-oculto {{ display: none; }}
  .adjuntar {{
    font-size: 19px; cursor: pointer; padding: 6px 9px; border-radius: 6px; flex: none; line-height: 1;
    display: inline-flex; align-items: center; justify-content: center;
  }}
  .adjuntar:hover {{ background: #F3F5F8; }}
  .nombre-archivo {{ font-size: 12px; color: {GRAY}; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  form.enviar button[type=submit] {{
    padding: 9px 20px; background: {NAVY}; color: {SURFACE}; border: none; border-radius: 6px;
    font-size: 14px; cursor: pointer; flex: none;
  }}
  form.enviar button[type=submit]:hover {{ background: #0A2E56; }}
  .nota-envio {{ font-size: 11px; color: {GRAY}; margin-top: 6px; }}
</style>
</head>
<body>
  <div class="marco">
    <div class="cabecera">
      <div class="cabecera-avatar">{_avatar(conv.telefono)}</div>
      <div class="cabecera-cuerpo">
        <h1>{titulo}</h1>
        {f'<div class="cabecera-telefono">{conv.telefono}</div>' if conv.nombre else ""}
        {f'<div class="badge badge-pausada">Tú tienes el control{" · " + html.escape(conv.pausada_por) if conv.pausada_por else ""}</div>' if conv.pausada else ""}
        {badge_gestion}
      </div>
      <div class="cabecera-acciones">
        <details class="editar-caja">
          <summary>Editar</summary>
          <div class="editar-panel">
            <form method="post" action="/dashboard/chats/{conv.telefono}/nombre">
              <label for="nombre">Nombre del paciente</label>
              <input type="text" id="nombre" name="nombre" value="{nombre_valor}" placeholder="Añadir nombre…" />
              <button type="submit">Guardar</button>
            </form>
          </div>
        </details>
        {gestion_dropdown}
        {boton_gestionado}
        {boton_estado}
      </div>
    </div>

    {recuadro_html}

    <div class="hilo-scroll"><div class="hilo">{burbujas}</div></div>

    <form class="enviar" method="post" action="/dashboard/chats/{conv.telefono}/enviar" enctype="multipart/form-data">
      <textarea name="texto" placeholder="Escribe un mensaje…"></textarea>
      <div class="fila-envio">
        <label class="adjuntar" for="imagen-input" title="Adjuntar imagen">📎</label>
        <input
          type="file" id="imagen-input" name="imagen" accept="image/*" class="input-archivo-oculto"
          onchange="document.getElementById('nombre-archivo').textContent = this.files[0] ? this.files[0].name : '';"
        />
        <span id="nombre-archivo" class="nombre-archivo"></span>
        <button type="submit">Enviar</button>
      </div>
      <p class="nota-envio">Al enviar, este chat queda a tu cargo — Aurora deja de contestar aquí hasta que le des a "Reactivar Aurora".</p>
    </form>
  </div>
</body>
</html>"""
