"""Webhook de WhatsApp Cloud API para Aurora — el asistente de Compensar / Widex
Colombia S.A.S.

Flujo INBOUND: el paciente escribe primero. El primer mensaje siempre muestra el menú
de los 5 trámites de Aurora. Según la opción elegida, el bot pide la cédula (si no la
conocemos ya por el backlog de entrega de audífonos) y los documentos que ese trámite
necesita — orden clínica siempre; autorización de servicio y cédula además, para las
opciones marcadas con * en el menú. Los documentos se clasifican y la vigencia de la
orden se valida con Claude (vision, ver vision_client.py). Aurora **nunca** ofrece ni
confirma una hora de cita — solo avisa que un agente de atención al cliente se va a
comunicar, en las sedes/horario fijos de Usaquén y Javeriana.

Endpoints:
- GET  /webhook                          → verificación del webhook (Meta la llama al configurar la app)
- POST /webhook                          → mensajes entrantes de pacientes (texto e imágenes)
- GET  /login                            → formulario de ingreso al dashboard (correo/clave de Supabase Auth)
- POST /login                            → procesa el ingreso y deja la sesión en una cookie
- GET  /logout                           → cierra la sesión del dashboard
- GET  /dashboard                        → panel de seguimiento (requiere sesión)
- GET  /dashboard/chats                  → bandeja de conversaciones (requiere sesión)
- GET  /dashboard/chats/{telefono}       → una conversación completa, con caja para contestar
- POST /dashboard/chats/{telefono}/enviar   → un agente manda texto y/o una imagen (pausa a Aurora ahí)
- POST /dashboard/chats/{telefono}/reanudar → un agente le devuelve el control a Aurora en ese chat

Ejecutar en desarrollo:
    uvicorn app.main:app --reload --port 8000
"""
import re

from fastapi import FastAPI, File, Form, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app import backlog, chat_media, conversaciones, documentos, mensajes, registro, session_store, solicitudes
from app.claude_client import SolicitudContext, interpretar_seleccion_menu, next_turn
from app.config import settings
from app.dashboard import render_chat, render_dashboard, render_lista_chats, render_login
from app.dashboard_auth import COOKIE_NAME, iniciar_sesion, validar_token
from app.datos_paciente import CAMPOS
from app.menu_matcher import coincidencia_local
from app.stats import get_dashboard_stats
from app.vision_client import clasificar
from app.whatsapp_client import download_media, get_media_url, send_image, send_text, upload_media

app = FastAPI(title="Aurora - Compensar / Widex Colombia S.A.S.")


def _responder(phone: str, texto: str) -> None:
    """Manda un mensaje de Aurora Y lo deja registrado en el historial del panel de
    chats — usa esto (no send_text directo) en cualquier respuesta automática del bot."""
    send_text(phone, texto)
    conversaciones.registrar_saliente(phone, "texto", "aurora", contenido=texto)


@app.get("/webhook")
def verify_webhook(request: Request):
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.whatsapp_verify_token
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    entrante = _extract_message(body)
    if entrante is None:
        # Puede ser un evento de estado (entregado/leído) o un tipo que no manejamos aún.
        return {"status": "ignored"}

    phone = entrante["phone"]
    paciente = backlog.find_by_phone(phone)
    nombre_conocido = paciente.nombre if paciente else ""

    # Se registra el mensaje en el historial del panel de chats SIEMPRE, pase lo que
    # pase después — así el agente ve la conversación completa incluso si el bot no
    # llegó a contestar (chat pausado, tipo de adjunto no manejado, etc.).
    contenido_imagen: tuple[bytes, str] | None = None
    if entrante["type"] == "image":
        media_url = get_media_url(entrante["media_id"])
        contenido_imagen = download_media(media_url)
        storage_path = chat_media.subir_imagen(phone, contenido_imagen[0], contenido_imagen[1])
        conversaciones.registrar_entrante(phone, "imagen", storage_path=storage_path, nombre=nombre_conocido)
    else:
        conversaciones.registrar_entrante(phone, "texto", contenido=entrante["text"], nombre=nombre_conocido)

    if conversaciones.esta_pausada(phone):
        # Un agente tomó el control de este chat desde el panel — Aurora no contesta
        # automáticamente aquí hasta que lo reactive.
        return {"status": "pausado_para_agente"}

    solicitud_abierta = solicitudes.abierta_por_telefono(phone)

    if entrante["type"] == "image":
        contenido, content_type = contenido_imagen
        return _manejar_imagen(phone, solicitud_abierta, contenido, content_type)

    if solicitud_abierta is not None:
        return _manejar_texto_con_solicitud(phone, solicitud_abierta, entrante["text"])

    return _manejar_texto_sin_solicitud(phone, entrante["text"])


# ---------------------------------------------------------------------------
# Sin solicitud abierta: mostrar/interpretar el menú, y armar el alta (cédula/nombre)
# ---------------------------------------------------------------------------

def _manejar_texto_sin_solicitud(phone: str, mensaje: str) -> dict:
    flujo = session_store.get_flujo(phone)

    if flujo and flujo.get("paso") == "esperando_cedula":
        return _recibir_cedula_nueva_solicitud(phone, flujo, mensaje)

    if flujo and flujo.get("paso") == "esperando_nombre":
        return _recibir_nombre_nueva_solicitud(phone, flujo, mensaje)

    if flujo and flujo.get("paso") == "esperando_dato":
        return _recibir_dato(phone, flujo, mensaje)

    codigo_servicio = coincidencia_local(mensaje) or interpretar_seleccion_menu(mensaje)

    if codigo_servicio is None:
        paciente = backlog.find_by_phone(phone)
        _responder(phone, mensajes.menu_inicial(paciente.nombre if paciente else ""))
        return {"status": "menu_enviado"}

    return _iniciar_solicitud(phone, codigo_servicio)


def _iniciar_solicitud(phone: str, codigo_servicio: str) -> dict:
    paciente = backlog.find_by_phone(phone)

    if paciente is not None:
        _comenzar_recoleccion_datos(phone, codigo_servicio, paciente.cedula, paciente.nombre)
        return {"status": "recolectando_datos"}

    session_store.set_flujo(phone, {"paso": "esperando_cedula", "servicio": codigo_servicio})
    _responder(phone, "Para continuar, ¿me compartes tu número de cédula?")
    return {"status": "esperando_cedula"}


def _recibir_cedula_nueva_solicitud(phone: str, flujo: dict, mensaje: str) -> dict:
    cedula = _extraer_cedula(mensaje)
    if cedula is None:
        _responder(phone, "No logré leer esa cédula. ¿Me la puedes escribir solo con números?")
        return {"status": "cedula_invalida"}

    codigo_servicio = flujo["servicio"]
    paciente = backlog.find_by_cedula(cedula)
    if paciente is not None:
        _comenzar_recoleccion_datos(phone, codigo_servicio, cedula, paciente.nombre)
        return {"status": "recolectando_datos"}

    session_store.set_flujo(phone, {"paso": "esperando_nombre", "servicio": codigo_servicio, "cedula": cedula})
    _responder(phone, "¿Cuál es tu nombre completo?")
    return {"status": "esperando_nombre"}


def _recibir_nombre_nueva_solicitud(phone: str, flujo: dict, mensaje: str) -> dict:
    nombre = mensaje.strip()
    if len(nombre) < 3:
        _responder(phone, "¿Me confirmas tu nombre completo?")
        return {"status": "nombre_invalido"}

    _comenzar_recoleccion_datos(phone, flujo["servicio"], flujo["cedula"], nombre)
    return {"status": "recolectando_datos"}


def _comenzar_recoleccion_datos(phone: str, codigo_servicio: str, cedula: str, nombre: str) -> None:
    """Después de saber quién es el paciente y qué trámite quiere, Aurora pide, uno por
    uno, los datos adicionales de CAMPOS (fecha de nacimiento, dirección, régimen,
    segundo teléfono, correo) antes de pasar a pedir los documentos."""
    session_store.set_flujo(
        phone,
        {
            "paso": "esperando_dato",
            "servicio": codigo_servicio,
            "cedula": cedula,
            "nombre": nombre,
            "datos": {},
            "campo_index": 0,
        },
    )
    _responder(phone, mensajes.pedir_dato(CAMPOS[0].pregunta, primero=True))


def _recibir_dato(phone: str, flujo: dict, mensaje: str) -> dict:
    campo_index = flujo["campo_index"]
    campo = CAMPOS[campo_index]
    valido, valor = campo.validar(mensaje)

    if not valido:
        _responder(phone, campo.error)
        return {"status": f"dato_invalido:{campo.clave}"}

    flujo["datos"][campo.clave] = valor
    siguiente_index = campo_index + 1

    if siguiente_index < len(CAMPOS):
        flujo["campo_index"] = siguiente_index
        session_store.set_flujo(phone, flujo)
        _responder(phone, mensajes.pedir_dato(CAMPOS[siguiente_index].pregunta))
        return {"status": f"dato_recibido:{campo.clave}"}

    session_store.clear_flujo(phone)
    _crear_solicitud_y_pedir_documentos(phone, flujo["cedula"], flujo["nombre"], flujo["servicio"], flujo["datos"])
    return {"status": "solicitud_iniciada"}


def _crear_solicitud_y_pedir_documentos(phone: str, cedula: str, nombre: str, codigo_servicio: str, datos: dict) -> None:
    nombre_servicio, requiere_auth = _datos_servicio(codigo_servicio)
    solicitudes.crear(
        cedula=cedula,
        nombre=nombre,
        telefono=phone,
        servicio=codigo_servicio,
        requiere_autorizacion=requiere_auth,
        fecha_nacimiento=datos.get("fecha_nacimiento", ""),
        direccion=datos.get("direccion", ""),
        regimen=datos.get("regimen", ""),
        telefono_2=datos.get("telefono_2", ""),
        correo=datos.get("correo", ""),
    )
    _responder(phone, mensajes.pedir_documentos(nombre_servicio, requiere_auth))


# ---------------------------------------------------------------------------
# Imágenes: clasificación + vigencia + avance de la solicitud
# ---------------------------------------------------------------------------

def _manejar_imagen(phone: str, solicitud, contenido: bytes, content_type: str) -> dict:
    if solicitud is None:
        _responder(phone, mensajes.sin_solicitud_activa())
        return {"status": "imagen_sin_solicitud"}

    nombre_servicio, _ = _datos_servicio(solicitud.servicio)

    clasificacion = clasificar(contenido, content_type, nombre_servicio)

    if clasificacion.tipo == "sin_clasificar":
        _responder(phone, mensajes.documento_no_reconocido())
        return {"status": "documento_no_reconocido"}

    storage_path = documentos.subir_imagen(solicitud.id, contenido, content_type)
    documentos.registrar(
        solicitud_id=solicitud.id,
        tipo=clasificacion.tipo,
        storage_path=storage_path,
        fecha_detectada=clasificacion.fecha_expedicion,
        vigente=clasificacion.vigente,
        nota_ia=clasificacion.nota,
    )

    if clasificacion.tipo == "orden_clinica" and clasificacion.vigente is False:
        solicitudes.actualizar_estado(solicitud.id, "orden_vencida")
        _responder(phone, mensajes.orden_vencida())
        return {"status": "orden_vencida"}

    recibidos = documentos.tipos_recibidos(solicitud.id)
    requeridos = set(solicitudes.DOCUMENTOS_REQUERIDOS[solicitud.requiere_autorizacion])
    faltantes = requeridos - recibidos

    if faltantes:
        solicitudes.actualizar_estado(solicitud.id, "pendiente_documentos")
        _responder(phone, mensajes.documento_recibido_faltan(sorted(faltantes)))
        return {"status": "documento_recibido"}

    if documentos.ultima_orden_vigente(solicitud.id) is False:
        solicitudes.actualizar_estado(solicitud.id, "orden_vencida")
        _responder(phone, mensajes.orden_vencida())
        return {"status": "orden_vencida"}

    solicitudes.actualizar_estado(solicitud.id, "documentos_completos")
    _responder(phone, mensajes.documentos_completos(nombre_servicio))
    _sincronizar_backlog_si_aplica(solicitud)
    return {"status": "documentos_completos"}


def _sincronizar_backlog_si_aplica(solicitud) -> None:
    """Si la solicitud es de 'Evaluación y adaptación de prótesis y ayudas auditivas' y
    el paciente está en el backlog de entrega de audífonos de Compensar, refleja el
    avance ahí también — así la meta de 70/día y el dashboard del backlog lo siguen
    contando, sin que el paciente tenga que pasar por dos procesos separados."""
    if solicitud.servicio != "evaluacion_adaptacion":
        return
    paciente = backlog.find_by_phone(solicitud.telefono)
    if paciente is None:
        return
    registro.registrar(cedula=paciente.cedula, nombre=paciente.nombre, sede="", resultado="interesado")
    backlog.update_estado(solicitud.telefono, "requiere_agendamiento")


# ---------------------------------------------------------------------------
# Texto con una solicitud ya abierta: conversación con Claude (dudas / cierre)
# ---------------------------------------------------------------------------

def _manejar_texto_con_solicitud(phone: str, solicitud, mensaje: str) -> dict:
    nombre_servicio, _ = _datos_servicio(solicitud.servicio)
    faltantes = sorted(
        set(solicitudes.DOCUMENTOS_REQUERIDOS[solicitud.requiere_autorizacion]) - documentos.tipos_recibidos(solicitud.id)
    )
    ctx = SolicitudContext(nombre=solicitud.nombre, servicio_nombre=nombre_servicio, documentos_faltantes=faltantes)

    history = session_store.get_history(phone)
    turn = next_turn(ctx, history, mensaje)

    session_store.append_turn(phone, "user", mensaje)
    if turn.reply_text:
        session_store.append_turn(phone, "assistant", turn.reply_text)
        _responder(phone, turn.reply_text)

    if turn.resultado:
        resultado = turn.resultado["resultado"]  # no_interesado | requiere_humano
        solicitudes.actualizar_estado(solicitud.id, resultado)
        session_store.clear(phone)

    return {"status": "ok"}


def _datos_servicio(codigo_servicio: str) -> tuple[str, bool]:
    for _, (codigo, nombre, requiere_auth) in solicitudes.SERVICIOS.items():
        if codigo == codigo_servicio:
            return nombre, requiere_auth
    raise ValueError(f"Servicio desconocido: {codigo_servicio}")


# ---------------------------------------------------------------------------
# Dashboard — login con Supabase Auth (perfiles administrados desde Supabase, no desde
# variables de entorno; ver app/dashboard_auth.py)
# ---------------------------------------------------------------------------

def _dashboard_email(request: Request) -> str | None:
    """Correo de la persona si su cookie de sesión sigue siendo válida en Supabase Auth;
    None si no hay cookie, expiró, o el token ya no es válido."""
    token = request.cookies.get(COOKIE_NAME)
    return validar_token(token) if token else None


@app.get("/login", response_class=HTMLResponse)
def login_form():
    return render_login()


@app.post("/login")
def login_submit(email: str = Form(...), password: str = Form(...)):
    sesion = iniciar_sesion(email, password)
    if sesion is None:
        return HTMLResponse(render_login("Correo o clave incorrectos."), status_code=401)

    respuesta = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    respuesta.set_cookie(
        COOKIE_NAME,
        sesion.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 8,  # 8 horas — vuelve a pedir login pasado ese tiempo
    )
    return respuesta


@app.get("/logout")
def logout():
    respuesta = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    respuesta.delete_cookie(COOKIE_NAME)
    return respuesta


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    email = _dashboard_email(request)
    if email is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    stats = get_dashboard_stats()
    return render_dashboard(stats, email=email)


# ---------------------------------------------------------------------------
# Dashboard — panel de chats: bandeja de conversaciones + entrar a escribir/mandar
# imágenes como agente (equivalente al inbox de Amanda). Al mandar algo desde acá, el
# chat queda "pausado" — Aurora deja de contestar sola ahí hasta que se reanude.
# ---------------------------------------------------------------------------

@app.get("/dashboard/chats", response_class=HTMLResponse)
def lista_chats(request: Request, q: str = "", estado: str = "todas"):
    email = _dashboard_email(request)
    if email is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    chats = conversaciones.listar(busqueda=q)
    return render_lista_chats(chats, email=email, busqueda=q, estado=estado)


@app.get("/dashboard/chats/{telefono}", response_class=HTMLResponse)
def ver_chat(telefono: str, request: Request):
    email = _dashboard_email(request)
    if email is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    conv = conversaciones.obtener(telefono)
    if conv is None:
        return RedirectResponse(url="/dashboard/chats", status_code=status.HTTP_303_SEE_OTHER)
    historial = conversaciones.historial(telefono)
    return render_chat(conv, historial, email=email)


@app.post("/dashboard/chats/{telefono}/enviar")
async def enviar_mensaje_agente(
    telefono: str,
    request: Request,
    texto: str = Form(""),
    imagen: UploadFile | None = File(None),
):
    email = _dashboard_email(request)
    if email is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Tomar el control de un chat siempre lo pausa — así Aurora no le contesta al
    # paciente al mismo tiempo que el agente.
    conversaciones.pausar(telefono, email)

    if imagen is not None and imagen.filename:
        contenido = await imagen.read()
        content_type = imagen.content_type or "image/jpeg"
        storage_path = chat_media.subir_imagen(telefono, contenido, content_type)
        media_id = upload_media(contenido, content_type)
        send_image(telefono, media_id, caption=texto.strip())
        conversaciones.registrar_saliente(telefono, "imagen", email, contenido=texto.strip(), storage_path=storage_path)
    elif texto.strip():
        send_text(telefono, texto.strip())
        conversaciones.registrar_saliente(telefono, "texto", email, contenido=texto.strip())

    return RedirectResponse(url=f"/dashboard/chats/{telefono}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/dashboard/chats/{telefono}/reanudar")
def reanudar_aurora(telefono: str, request: Request):
    email = _dashboard_email(request)
    if email is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    conversaciones.reanudar(telefono)
    return RedirectResponse(url=f"/dashboard/chats/{telefono}", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Utilidades del webhook
# ---------------------------------------------------------------------------

def _extraer_cedula(texto: str) -> str | None:
    """Saca solo los dígitos de la respuesta del paciente (la gente escribe la cédula
    con puntos, espacios o precedida de texto: "1.234.567.890", "mi cc es 1234567890")."""
    digitos = re.sub(r"\D", "", texto)
    return digitos if 6 <= len(digitos) <= 10 else None


def _extract_message(body: dict) -> dict | None:
    """Extrae el mensaje entrante del payload de WhatsApp Cloud API. Devuelve None si
    no es un mensaje que manejamos (evento de estado, o un tipo de adjunto distinto a
    imagen: audio, documento, ubicación, etc.)."""
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            return None
        msg = messages[0]
        phone = msg["from"]
        tipo = msg.get("type", "text")

        if tipo == "image":
            media_id = msg.get("image", {}).get("id")
            if not media_id:
                return None
            return {"phone": phone, "type": "image", "media_id": media_id}

        if tipo == "text":
            text = msg.get("text", {}).get("body", "")
            if not text:
                return None
            return {"phone": phone, "type": "text", "text": text}

        return None
    except (KeyError, IndexError):
        return None
