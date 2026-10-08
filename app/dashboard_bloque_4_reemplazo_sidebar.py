def _sidebar(activo: str, email: str) -> str:
    """Barra lateral de navegación — inspirada en el panel de Amanda (Chats / Salir).
    Incluye Chats, Completas (recuadro de cada paciente con documentos completos) y
    Reportes (confirmaciones, trámites por volumen, gestionados por período)."""
    def item(href: str, etiqueta: str, clave: str) -> str:
        activo_cls = " sb-activo" if clave == activo else ""
        return f'<a class="sb-item{activo_cls}" href="{href}">{etiqueta}</a>'

    return f"""
  <nav class="sidebar">
    <div class="sb-logo">A</div>
    <div class="sb-nav">
      {item("/dashboard/chats", "Chats", "chats")}
      {item("/dashboard/completas", "Completas", "completas")}
      {item("/dashboard/reportes", "Reportes", "reportes")}
    </div>
    <a class="sb-item sb-salir" href="/logout" title="{html.escape(email)}">Salir</a>
  </nav>"""
