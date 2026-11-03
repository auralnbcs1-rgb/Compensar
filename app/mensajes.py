"""Textos fijos que manda Aurora directamente (sin pasar por Claude).

El menú, la lista de documentos requeridos y las sedes/horario se escriben aquí a
propósito, en vez de dejar que el modelo los redacte cada vez: así son siempre exactos
y no dependen de que el modelo "se acuerde bien". Claude solo entra a conversar en lo
que no es texto fijo (dudas del paciente, cierre del caso) — ver claude_client.py.
"""
from app.solicitudes import DOCUMENTOS_REQUERIDOS, SERVICIOS

_NOMBRE_DOC = {
    "orden_clinica": "la *orden clínica* (vigente)",
    "autorizacion_servicio": "la *autorización de servicio*",
    "cedula": "la foto de tu *cédula*",
}

SEDES_HORARIO = (
    "Sedes: *Usaquén* y *Javeriana*.\n"
    "Horario: lunes a jueves de 7:30am a 5:00pm, viernes de 7:30am a 4:30pm."
)


def menu_inicial(nombre: str = "") -> str:
    saludo = f"¡Hola, {nombre}! " if nombre else "¡Hola! "
    lineas = [
        f"{saludo}Soy *Aurora*, el asistente de WhatsApp de *Compensar - Widex Colombia S.A.S.*",
        "¿Para cuál de estos trámites me escribes hoy?",
        "",
    ]
    for opcion, (_, nombre_servicio, requiere_auth) in SERVICIOS.items():
        marca = " *" if requiere_auth else ""
        lineas.append(f"{opcion}. {nombre_servicio}{marca}")
    lineas += [
        "",
        "Contesta solo con el número de la opción.",
        "(*) esas opciones necesitan orden clínica, autorización de servicio y cédula — "
        "las demás solo con la orden clínica vigente.",
    ]
    return "\n".join(lineas)


def pedir_dato(pregunta: str, primero: bool = False) -> str:
    if primero:
        return f"Ya casi — necesito unos datos más.\n\n{pregunta}"
    return pregunta


def pedir_documentos(nombre_servicio: str, requiere_auth: bool) -> str:
    tipos = DOCUMENTOS_REQUERIDOS[requiere_auth]
    lista = "\n".join(f"- {_NOMBRE_DOC[t]}" for t in tipos)
    return (
        f"Perfecto, *{nombre_servicio}*. Para continuar necesito que me mandes, en fotos claras:\n"
        f"{lista}\n\n"
        "Las puedes mandar una por una o todas juntas, como te quede más fácil."
    )


def documento_recibido_faltan(faltantes: list[str]) -> str:
    lista = ", ".join(_NOMBRE_DOC[t] for t in faltantes)
    return f"Recibido ✅. Todavía me falta: {lista}."


def recordatorio_documentos(nombre_servicio: str, faltantes: list[str]) -> str:
    """Recordatorio automático — lo manda el sistema solo, sin que el paciente escriba
    nada, cuando pasan varias horas sin ninguna novedad en una solicitud que se quedó
    en 'pendiente_documentos' (ver _tarea_recordatorios en main.py). Se manda una sola
    vez por solicitud."""
    lista = "\n".join(f"- {_NOMBRE_DOC[t]}" for t in faltantes)
    return (
        f"¡Hola! 👋 Te escribo para recordarte que para continuar con tu trámite de "
        f"*{nombre_servicio}* todavía me falta que me mandes, en fotos claras:\n{lista}\n\n"
        "Cuando puedas, aquí te espero 🙂"
    )


def documentos_completos(nombre_servicio: str) -> str:
    return (
        f"¡Listo! Ya tengo todos tus documentos para *{nombre_servicio}*. Un agente de "
        "atención al cliente te va a contactar para confirmar el día y la hora — yo no "
        "agendo citas directamente. Podemos demorarnos hasta *48 horas* en responderte, "
        f"gracias por tu paciencia 🙏\n\n{SEDES_HORARIO}"
    )


def autorizacion_vencida() -> str:
    return (
        "Tu *autorización de servicio* ya no está vigente. ¿Me puedes mandar una más "
        "reciente? Si no tienes una nueva, un agente humano te va a ayudar — podemos "
        "demorarnos hasta *48 horas* en responderte."
    )


def documento_no_reconocido() -> str:
    return "No logré identificar bien esa imagen 🧐. ¿Me la puedes volver a mandar, bien clara y completa?"


def sin_solicitud_activa() -> str:
    return "Antes de mandarme fotos, cuéntame para cuál trámite es — contesta con el número de la lista que te mandé arriba."
