def _fmt_fecha_corta(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


_NOMBRE_DOC_RECUADRO = {
    "orden_clinica": "Orden clínica",
    "autorizacion_servicio": "Autorización de servicio",
    "cedula": "Foto de cédula",
}


def _fila_dato(etiqueta: str, valor: str) -> str:
    if not valor:
        return ""
    return (
        f'<div class="dato-fila"><span class="dato-etiqueta">{html.escape(etiqueta)}</span>'
        f'<span class="dato-valor">{html.escape(str(valor))}</span></div>'
    )


def _fila_documento(doc: dict) -> str:
    nombre = _NOMBRE_DOC_RECUADRO.get(doc.get("tipo"), doc.get("tipo", ""))
    extra = ""
    if doc.get("tipo") == "orden_clinica":
        if doc.get("vigente") is True:
            extra = " · vigente"
        elif doc.get("vigente") is False:
            extra = " · vencida"
    return f'<div class="doc-fila">✅ {html.escape(nombre)}{extra}</div>'


def _recuadro_paciente(solicitud: Solicitud, documentos_lista: list[dict]) -> str:
    """Recuadro con toda la información que Aurora ya recolectó de este paciente —
    datos personales + documentos recibidos. Se usa tanto en el chat individual (cuando
    ya tiene todo) como en la lista de "Solicitudes completas"."""
    nombre_servicio = NOMBRE_SERVICIO.get(solicitud.servicio, solicitud.servicio)
    docs_html = "".join(_fila_documento(d) for d in documentos_lista) or (
        '<div class="doc-fila-vacio">Sin documentos registrados.</div>'
    )
    filas = "".join(
        [
            _fila_dato("Trámite", nombre_servicio),
            _fila_dato("Cédula", solicitud.cedula),
            _fila_dato("Teléfono", solicitud.telefono),
            _fila_dato("Segundo teléfono", solicitud.telefono_2),
            _fila_dato("Correo", solicitud.correo),
            _fila_dato("Fecha de nacimiento", _fmt_fecha_corta(solicitud.fecha_nacimiento)),
            _fila_dato("Dirección", solicitud.direccion),
            _fila_dato("Régimen", solicitud.regimen),
        ]
    )
    return f"""
    <div class="recuadro-paciente">
      <div class="recuadro-titulo">{html.escape(solicitud.nombre)} — información completa</div>
      <div class="recuadro-datos">{filas}</div>
      <div class="recuadro-documentos">{docs_html}</div>
    </div>"""
