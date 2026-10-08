def render_solicitudes_completas(items: list[tuple[Solicitud, list[dict]]], email: str = "") -> str:
    """Página aparte con el recuadro completo de cada paciente que ya tiene todos sus
    documentos — para verlos todos de un vistazo sin entrar chat por chat."""
    if items:
        tarjetas = "".join(_recuadro_paciente(s, docs) for s, docs in items)
    else:
        tarjetas = '<p class="fila-azul-vacio">Todavía no hay ninguna solicitud con documentos completos.</p>'

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Solicitudes completas — Aurora (Compensar)</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: {SURFACE};
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: {NAVY};
  }}
  .layout {{ display: flex; min-height: 100vh; }}
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

  .completas-col {{ flex: 1; min-width: 0; padding: 28px 32px 64px; max-width: 760px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitulo {{ color: {GRAY}; font-size: 13px; margin: 0 0 24px; }}
  .fila-azul-vacio {{ font-size: 13px; color: {GRAY}; }}

  .recuadro-paciente {{
    margin: 0 0 16px; padding: 14px 16px; border: 1px solid #D7E3F7; background: #EEF3FC;
    border-radius: 10px;
  }}
  .recuadro-titulo {{ font-size: 13px; font-weight: 700; color: {NAVY}; margin-bottom: 8px; }}
  .recuadro-datos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 4px 16px; margin-bottom: 8px; }}
  .dato-fila {{ font-size: 12.5px; }}
  .dato-etiqueta {{ color: {GRAY}; margin-right: 6px; }}
  .dato-valor {{ color: {NAVY}; font-weight: 600; }}
  .recuadro-documentos {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: {NAVY}; border-top: 1px solid #D7E3F7; padding-top: 8px; }}
  .doc-fila-vacio {{ font-size: 12px; color: {GRAY}; }}
</style>
</head>
<body>
  <div class="layout">
    {_sidebar("completas", email)}
    <div class="completas-col">
      <h1>Solicitudes con documentos completos</h1>
      <p class="subtitulo">{len(items)} paciente(s) listos para que el agente agende.</p>
      {tarjetas}
    </div>
  </div>
</body>
</html>"""
