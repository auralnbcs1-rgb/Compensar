"""
Formulario web de documentos + panel de gestión.
 
Rutas públicas (pacientes, sin login):
    GET/POST /documentos            formulario general (cédula, nombre, teléfono, trámite y documentos)
    GET/POST /documentos/{token}    link personal que manda Aurora: ya sabe quién es, solo pide lo que falta
 
Rutas del panel (agentes, con el mismo login de Supabase que /dashboard):
    GET  /dashboard/documentos                         lista + filtros + conteo por estado
    GET  /dashboard/documentos/{expediente_id}         detalle: datos, documentos, aprobar/rechazar, estado
    POST /dashboard/documentos/{expediente_id}/estado
    POST /dashboard/documentos/doc/{doc_id}/revisar
    GET  /dashboard/documentos/doc/{doc_id}/ver | /descargar
 
En main.py:  from app.formulario import router as formulario_router
             app.include_router(formulario_router)
"""
from __future__ import annotations
 
import html
import inspect
import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode
 
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
 
from app import expedientes as ex
 
log = logging.getLogger(__name__)
router = APIRouter()
 
COOKIE_SESION = "aurora_dashboard_session"
e = html.escape
 
# ====================================================================== estilos
CSS = """
:root{--navy:#0B2545;--teal:#0E8F86;--teal-l:#E3F4F2;--azul:#1D6FD8;--azul-l:#E6F0FC;--bg:#F4F7FB;
--card:#fff;--txt:#1B2B3A;--mut:#5D6B7A;--lin:#DCE3EC;--ok:#16794C;--ok-l:#E3F5EC;--warn:#A15C00;--warn-l:#FFF3DF;
--err:#B42318;--err-l:#FDECEA}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:var(--bg);color:var(--txt);font-size:15px;line-height:1.45}
a{color:var(--azul)}h1,h2,h3{color:var(--navy);margin:0 0 .4em}
.top{background:var(--navy);color:#fff;padding:14px 16px}.top b{font-size:17px}.top small{opacity:.75;display:block}
.wrap{max-width:640px;margin:0 auto;padding:16px}.wide{max-width:1180px}
.card{background:var(--card);border:1px solid var(--lin);border-radius:12px;padding:18px;margin-bottom:14px}
label{display:block;font-weight:600;margin:12px 0 4px;color:var(--navy)}
input[type=text],input[type=email],input[type=tel],input[type=date],select,textarea{width:100%;padding:10px 12px;
border:1px solid var(--lin);border-radius:8px;font:inherit;background:#fff}
input:focus,select:focus,textarea:focus{outline:2px solid var(--azul);border-color:transparent}
.hint{color:var(--mut);font-size:13px;margin-top:3px}
.btn{display:inline-block;border:0;border-radius:8px;padding:11px 18px;font:inherit;font-weight:600;cursor:pointer;
text-decoration:none;background:var(--teal);color:#fff}.btn.sec{background:#fff;color:var(--navy);border:1px solid var(--lin)}
.btn.err{background:var(--err)}.btn.sm{padding:6px 11px;font-size:13px}.btn.full{width:100%;margin-top:18px}
.slot{border:1px dashed var(--lin);border-radius:10px;padding:12px;margin-top:10px;background:#FAFCFE}
.slot h3{font-size:15px;margin:0}.alert{padding:12px 14px;border-radius:10px;margin-bottom:14px}
.alert.err{background:var(--err-l);color:var(--err)}.alert.ok{background:var(--ok-l);color:var(--ok)}
.alert.info{background:var(--azul-l);color:var(--navy)}
.tag{display:inline-block;font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;white-space:nowrap}
.t-ok{background:var(--ok-l);color:var(--ok)}.t-warn{background:var(--warn-l);color:var(--warn)}
.t-err{background:var(--err-l);color:var(--err)}.t-info{background:var(--azul-l);color:var(--azul)}
.t-mut{background:#EEF1F5;color:var(--mut)}.t-teal{background:var(--teal-l);color:var(--teal)}
.chk{display:flex;gap:8px;align-items:flex-start;font-weight:400;color:var(--txt)}.chk input{margin-top:4px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.chip{background:#fff;border:1px solid var(--lin);border-radius:10px;padding:8px 12px;text-decoration:none;color:var(--txt)}
.chip b{display:block;font-size:20px;color:var(--navy)}.chip.on{border-color:var(--teal);box-shadow:0 0 0 2px var(--teal-l)}
.filtros{display:grid;grid-template-columns:2fr 1.4fr 1.2fr 1fr 1fr auto;gap:8px;align-items:end}
.filtros label{margin:0 0 4px;font-size:12px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--lin);vertical-align:top}
th{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}tr:hover td{background:#FAFCFE}
.nav{display:flex;gap:16px;align-items:center;justify-content:space-between}.nav a{color:#fff;opacity:.85;text-decoration:none}
.nav a.on{opacity:1;font-weight:700}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.docs{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.doc{border:1px solid var(--lin);border-radius:10px;overflow:hidden;background:#fff;display:flex;flex-direction:column}
.doc .prev{height:170px;background:#EEF1F5;display:flex;align-items:center;justify-content:center;color:var(--mut)}
.doc .prev img{width:100%;height:100%;object-fit:cover}.doc .body{padding:10px 12px;flex:1}
.doc .body .tag,.slot .tag{align-self:flex-start;flex-shrink:0}
.doc .acc{padding:10px 12px;border-top:1px solid var(--lin);display:flex;flex-wrap:wrap;gap:6px}
.doc .acc form{display:flex;gap:6px;flex-wrap:wrap;width:100%}.doc .acc input[type=text]{flex:1;min-width:120px;padding:6px 8px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}dt{color:var(--mut)}dd{margin:0;font-weight:500}
.muted{color:var(--mut)}.copy{display:flex;gap:6px}.copy input{font-size:13px}
@media(max-width:820px){.filtros,.grid2{grid-template-columns:1fr}.hide-m{display:none}}
"""
 
 
def _pagina(titulo: str, cuerpo: str, *, panel: bool = False, usuario: str | None = None) -> HTMLResponse:
    if panel:
        top = f"""<div class="top"><div class="wrap wide nav"><div><b>Aurora · Panel</b>
<small>Compensar - Widex Colombia S.A.S.</small></div><div style="display:flex;gap:16px;flex-wrap:wrap">
<a href="/dashboard">Resumen</a><a href="/dashboard/chats">Chats</a>
<a class="on" href="/dashboard/documentos">Documentos</a>
<span class="muted" style="color:#fff;opacity:.6">{e(usuario or '')}</span><a href="/logout">Salir</a></div></div></div>"""
    else:
        top = """<div class="top"><div class="wrap"><b>Compensar - Widex Colombia S.A.S.</b>
<small>Envío de documentos para tu cita · Aurora</small></div></div>"""
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(titulo)}</title>
<meta name="robots" content="noindex"><style>{CSS}</style></head><body>{top}{cuerpo}</body></html>""")
 
 
# ====================================================================== auth del panel
def _usuario(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        return None
    try:
        from app.dashboard_auth import validar_token
 
        u = validar_token(token)
    except Exception:  # noqa: BLE001
        log.warning("validar_token falló", exc_info=True)
        return None
    if not u:
        return None
    if isinstance(u, str):
        return u
    if isinstance(u, dict):
        return u.get("email") or (u.get("user") or {}).get("email") or "agente"
    return getattr(u, "email", None) or getattr(getattr(u, "user", None), "email", None) or "agente"
 
 
def _al_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
 
 
# ====================================================================== lectura de archivos subidos
async def _leer_archivos(form, campo: str) -> tuple[list[tuple[bytes, str, str]], str | None]:
    """Devuelve [(contenido, mime, nombre)] de un input file (puede ser múltiple) y un error si lo hay."""
    out = []
    for f in form.getlist(campo):
        if not hasattr(f, "read") or not getattr(f, "filename", ""):
            continue
        contenido = await f.read()
        if not contenido:
            continue
        mime = (f.content_type or "").lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in ex.MIME_PERMITIDOS:
            return [], f"«{f.filename}» no es una foto (JPG/PNG) ni un PDF."
        if len(contenido) > ex.MAX_BYTES:
            return [], f"«{f.filename}» pesa más de 10 MB. Toma la foto de nuevo o comprime el PDF."
        out.append((contenido, mime, f.filename))
    return out, None
 
 
def _validar_fecha_orden(valor: str | None) -> tuple[str | None, str | None]:
    if not valor:
        return None, "Escribe la fecha de expedición que aparece en tu orden clínica."
    try:
        d = date.fromisoformat(valor)
    except ValueError:
        return None, "La fecha de expedición de la orden no es válida."
    if d > date.today():
        return None, "La fecha de expedición de la orden no puede ser futura."
    return d.isoformat(), None
 
 
async def _recolectar(form, tipos: list[str]) -> tuple[dict, str | None, str | None]:
    """Lee y valida los archivos de cada tipo. Devuelve (lotes, fecha_orden, error)."""
    lotes = {}
    for t in tipos + ["otro"]:
        archivos, err = await _leer_archivos(form, f"doc_{t}")
        if err:
            return {}, None, err
        if archivos:
            lotes[t] = archivos
    fecha_orden = None
    if "orden_clinica" in lotes:
        fecha_orden, err = _validar_fecha_orden(form.get("fecha_orden"))
        if err:
            return {}, None, err
    return lotes, fecha_orden, None
 
 
def _guardar(exp: dict, lotes: dict, fecha_orden: str | None) -> int:
    n = 0
    for t, archivos in lotes.items():
        for contenido, mime, nombre in archivos:
            path = ex.subir_archivo(exp["id"], t, contenido, mime)
            ex.agregar_documento(
                exp["id"], tipo=t, canal="formulario", storage_path=path, nombre_archivo=nombre,
                mime=mime, tamano=len(contenido), fecha_expedicion=fecha_orden if t == "orden_clinica" else None,
            )
            n += 1
    return n
 
 
# ====================================================================== formulario público
def _slot(tipo: str, *, requerido_en: list[str] | None = None, estado: str | None = None, motivo: str | None = None) -> str:
    info = ex.DOCS[tipo]
    multiple = " multiple" if tipo in ("cedula", "otro") else ""
    data = f' data-tramites="{" ".join(requerido_en)}"' if requerido_en is not None else ""
    marca = ""
    if estado == "aprobado":
        marca = '<span class="tag t-ok">Recibido ✓</span>'
    elif estado == "pendiente":
        marca = '<span class="tag t-info">Recibido · en revisión</span>'
    elif estado == "rechazado":
        marca = '<span class="tag t-err">Hay que enviarlo de nuevo</span>'
    elif estado == "falta":
        marca = '<span class="tag t-warn">Falta</span>'
    extra = ""
    if tipo == "orden_clinica":
        extra = """<label for="fecha_orden" style="font-size:14px">Fecha de expedición de la orden</label>
<input type="date" id="fecha_orden" name="fecha_orden" max="%s">
<div class="hint">Está impresa en la orden. Sirve para confirmar que sigue vigente.</div>""" % date.today().isoformat()
    motivo_html = f'<div class="hint" style="color:var(--err)">Motivo: {e(motivo)}</div>' if motivo else ""
    titulo = "¿Algún otro documento? (opcional)" if tipo == "otro" else info["nombre"]
    return f"""<div class="slot"{data}><div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
<h3>{e(titulo)}</h3>{marca}</div><div class="hint">{e(info['ayuda'])}</div>{motivo_html}
<input type="file" name="doc_{tipo}" accept="image/jpeg,image/png,image/webp,application/pdf"{multiple} style="margin-top:8px">
{extra}</div>"""
 
 
def _form_publico(valores: dict | None = None, error: str | None = None) -> HTMLResponse:
    v = {k: e(str(x)) for k, x in (valores or {}).items()}
    opciones = "".join(
        f'<option value="{k}"{" selected" if v.get("tramite") == k else ""}>{e(t["nombre"])}</option>'
        for k, t in ex.TRAMITES.items()
    )
    slots = "".join(
        _slot(t, requerido_en=[k for k, tr in ex.TRAMITES.items() if t in tr["docs"]])
        for t in ("orden_clinica", "autorizacion", "cedula")
    ) + _slot("otro", requerido_en=list(ex.TRAMITES))
    err = f'<div class="alert err">{e(error)}</div>' if error else ""
    cuerpo = f"""<div class="wrap"><div class="card"><h1>Envía tus documentos</h1>
<p class="muted" style="margin-top:0">Llena tus datos, elige el trámite y sube una foto clara de cada documento.
Un agente de atención al cliente te contactará para confirmar el día y la hora de tu cita.</p>
{err}<form method="post" enctype="multipart/form-data" id="f">
<label for="cedula">Número de cédula</label><input type="text" inputmode="numeric" id="cedula" name="cedula" required value="{v.get('cedula','')}">
<label for="nombre">Nombre completo</label><input type="text" id="nombre" name="nombre" required value="{v.get('nombre','')}">
<label for="telefono">Celular con WhatsApp</label><input type="tel" id="telefono" name="telefono" required placeholder="300 123 4567" value="{v.get('telefono','')}">
<label for="correo">Correo electrónico <span class="muted" style="font-weight:400">(opcional)</span></label>
<input type="email" id="correo" name="correo" value="{v.get('correo','')}">
<label for="tramite">Trámite</label><select id="tramite" name="tramite" required>
<option value="">Selecciona…</option>{opciones}</select>
<div id="docs" style="margin-top:6px">{slots}</div>
<label class="chk" style="margin-top:18px"><input type="checkbox" name="acepto" value="1" required{' checked' if v.get('acepto') else ''}>
<span>Autorizo el tratamiento de mis datos personales y documentos para gestionar mi cita, conforme a la Ley 1581 de 2012.</span></label>
<button class="btn full" type="submit">Enviar documentos</button></form></div>
<p class="muted" style="text-align:center;font-size:13px">Sedes: Usaquén y Javeriana · Lunes a jueves 7:30am–5:00pm · Viernes 7:30am–4:30pm</p></div>
<script>
const sel=document.getElementById('tramite');
function upd(){{document.querySelectorAll('#docs .slot').forEach(s=>{{
 const ok=sel.value&&s.dataset.tramites.split(' ').includes(sel.value);s.style.display=ok?'':'none';}});}}
sel.addEventListener('change',upd);upd();
document.getElementById('f').addEventListener('submit',ev=>{{const b=ev.target.querySelector('button');b.disabled=true;b.textContent='Enviando…';}});
</script>"""
    return _pagina("Envío de documentos", cuerpo)
 
 
@router.get("/documentos", response_class=HTMLResponse)
async def formulario_publico():
    return _form_publico()
 
 
@router.post("/documentos", response_class=HTMLResponse)
async def enviar_publico(request: Request):
    form = await request.form()
    valores = {k: form.get(k) or "" for k in ("cedula", "nombre", "telefono", "correo", "tramite", "acepto")}
    cedula = ex.normalizar_cedula(valores["cedula"])
    telefono = ex.normalizar_telefono(valores["telefono"])
    tramite = valores["tramite"]
    error = None
    if not cedula or not (5 <= len(cedula) <= 12):
        error = "Revisa el número de cédula."
    elif len(valores["nombre"].strip()) < 5:
        error = "Escribe tu nombre completo."
    elif not telefono or len(telefono) != 12:
        error = "Revisa tu número de celular (10 dígitos)."
    elif valores["correo"] and "@" not in valores["correo"]:
        error = "Revisa tu correo electrónico."
    elif tramite not in ex.TRAMITES:
        error = "Selecciona el trámite."
    elif not valores["acepto"]:
        error = "Debes autorizar el tratamiento de datos para continuar."
    if error:
        return _form_publico(valores, error)
 
    # Se valida todo antes de crear el expediente, para no dejar expedientes vacíos.
    lotes, fecha_orden, err = await _recolectar(form, ex.TRAMITES[tramite]["docs"])
    if err:
        return _form_publico(valores, err)
    if not lotes:
        return _form_publico(valores, "Adjunta al menos un documento.")
    exp = ex.obtener_o_crear(
        tramite=tramite, origen="formulario", telefono=telefono, cedula=cedula,
        nombre=valores["nombre"].strip(), correo=valores["correo"].strip() or None,
    )
    _guardar(exp, lotes, fecha_orden)
    return RedirectResponse(f"/documentos/{exp['token']}?ok=1", status_code=303)
 
 
# ====================================================================== link personal
def _pagina_personal(exp: dict, *, ok: bool = False, error: str | None = None) -> HTMLResponse:
    tramite = ex.TRAMITES[exp["tramite"]]
    docs = ex.documentos(exp["id"])
    por_tipo: dict[str, dict] = {}
    for d in sorted(docs, key=lambda x: x.get("creado_en") or ""):
        por_tipo[d["tipo"]] = d  # el más reciente de cada tipo
    slots = ""
    pendientes = 0
    for t in tramite["docs"]:
        d = por_tipo.get(t)
        estado = d["estado_revision"] if d else "falta"
        if estado in ("falta", "rechazado"):
            pendientes += 1
        slots += _slot(t, estado=estado, motivo=d.get("motivo_rechazo") if d and estado == "rechazado" else None)
    slots += _slot("otro")
    nombre = (exp.get("nombre") or "").split(" ")[0]
    saludo = f"Hola {e(nombre)}, " if nombre else ""
    avisos = ""
    if ok:
        avisos += '<div class="alert ok">¡Recibimos tus documentos! Los vamos a revisar.</div>'
    if error:
        avisos += f'<div class="alert err">{e(error)}</div>'
    if exp["estado"] == "documentos_completos":
        avisos += '<div class="alert ok">Tus documentos están completos. Un agente te contactará para confirmar el día y la hora de tu cita.</div>'
    elif exp["estado"] == "orden_vencida":
        avisos += f'<div class="alert err">Tu orden clínica tiene más de {ex.ORDEN_VIGENCIA_DIAS} días. Sube una orden vigente.</div>'
    elif exp["estado"] == "agendado":
        avisos += '<div class="alert info">Tu cita ya fue agendada. Si necesitas algo más, escríbenos por WhatsApp.</div>'
    elif pendientes:
        avisos += f'<div class="alert info">Te {"falta" if pendientes == 1 else "faltan"} {pendientes} documento{"s" if pendientes > 1 else ""}.</div>'
    cuerpo = f"""<div class="wrap"><div class="card"><h1>Tus documentos</h1>
<p class="muted" style="margin-top:0">{saludo}este es tu link personal para el trámite <b>{e(tramite['nombre'])}</b>.
Guárdalo: puedes volver a entrar para ver cómo va o enviar lo que falte.</p>
{avisos}<form method="post" enctype="multipart/form-data" id="f">{slots}
<button class="btn full" type="submit">Enviar</button></form></div>
<p class="muted" style="text-align:center;font-size:13px">Sedes: Usaquén y Javeriana · Lunes a jueves 7:30am–5:00pm · Viernes 7:30am–4:30pm</p></div>
<script>document.getElementById('f').addEventListener('submit',ev=>{{const b=ev.target.querySelector('button');b.disabled=true;b.textContent='Enviando…';}});</script>"""
    return _pagina("Tus documentos", cuerpo)
 
 
def _no_encontrado() -> HTMLResponse:
    r = _pagina("Link no válido", """<div class="wrap"><div class="card"><h1>Este link no es válido</h1>
<p>Puede que esté incompleto. Pídele a Aurora por WhatsApp un link nuevo, o
<a href="/documentos">envía tus documentos aquí</a>.</p></div></div>""")
    r.status_code = 404
    return r
 
 
@router.get("/documentos/{token}", response_class=HTMLResponse)
async def formulario_personal(token: str, ok: int = 0):
    exp = ex.obtener_por_token(token)
    if not exp:
        return _no_encontrado()
    return _pagina_personal(exp, ok=bool(ok))
 
 
@router.post("/documentos/{token}", response_class=HTMLResponse)
async def enviar_personal(token: str, request: Request):
    exp = ex.obtener_por_token(token)
    if not exp:
        return _no_encontrado()
    form = await request.form()
    lotes, fecha_orden, err = await _recolectar(form, ex.TRAMITES[exp["tramite"]]["docs"])
    if err:
        return _pagina_personal(exp, error=err)
    if not lotes:
        return _pagina_personal(exp, error="No adjuntaste ningún archivo.")
    _guardar(exp, lotes, fecha_orden)
    return RedirectResponse(f"/documentos/{token}?ok=1", status_code=303)
 
 
# ====================================================================== panel
def _tag_estado(estado: str) -> str:
    clase = {
        "pendiente_documentos": "t-warn", "en_revision": "t-info", "documentos_completos": "t-teal",
        "orden_vencida": "t-err", "requiere_humano": "t-err", "agendado": "t-ok",
    }.get(estado, "t-mut")
    return f'<span class="tag {clase}">{e(ex.ESTADOS.get(estado, estado))}</span>'
 
 
def _tag_rev(estado: str) -> str:
    return {
        "aprobado": '<span class="tag t-ok">Aprobado</span>',
        "rechazado": '<span class="tag t-err">Rechazado</span>',
    }.get(estado, '<span class="tag t-info">Por revisar</span>')
 
 
_BOGOTA = timezone(timedelta(hours=-5))
 
 
def _fecha(iso: str | None) -> str:
    """Fecha y hora en hora de Bogotá (Supabase guarda en UTC)."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(_BOGOTA).strftime("%d/%m/%Y %I:%M %p").lower()
    except ValueError:
        return iso
 
 
def _dia(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso and len(iso) >= 10 else (iso or "")
 
 
@router.get("/dashboard/documentos", response_class=HTMLResponse)
async def panel_lista(request: Request, q: str = "", tramite: str = "", estado: str = "", desde: str = "", hasta: str = ""):
    usuario = _usuario(request)
    if not usuario:
        return _al_login()
    filas = ex.listar(q=q or None, tramite=tramite or None, estado=estado or None, desde=desde or None, hasta=hasta or None)
    conteo = ex.contar_por_estado()
    base = {"q": q, "tramite": tramite, "desde": desde, "hasta": hasta}
    chips = "".join(
        f'<a class="chip{" on" if estado == k else ""}" href="/dashboard/documentos?{urlencode({**base, "estado": "" if estado == k else k})}">'
        f"<b>{conteo.get(k, 0)}</b>{e(n)}</a>"
        for k, n in ex.ESTADOS.items()
    )
    op_tram = '<option value="">Todos</option>' + "".join(
        f'<option value="{k}"{" selected" if tramite == k else ""}>{e(t["nombre"])}</option>' for k, t in ex.TRAMITES.items()
    )
    op_est = '<option value="">Todos</option>' + "".join(
        f'<option value="{k}"{" selected" if estado == k else ""}>{e(n)}</option>' for k, n in ex.ESTADOS.items()
    )
    if filas:
        trs = ""
        for f in filas:
            c = f.get("_docs", {})
            docs_txt = f'{c.get("total", 0)} archivo{"s" if c.get("total", 0) != 1 else ""}'
            if c.get("pendiente"):
                docs_txt += f' · <span class="tag t-info">{c["pendiente"]} por revisar</span>'
            if c.get("rechazado"):
                docs_txt += f' · <span class="tag t-err">{c["rechazado"]} rechazado{"s" if c["rechazado"] > 1 else ""}</span>'
            canal = "Formulario" if f.get("origen") == "formulario" else "WhatsApp"
            trs += f"""<tr onclick="location='/dashboard/documentos/{f['id']}'" style="cursor:pointer">
<td><a href="/dashboard/documentos/{f['id']}"><b>{e(f.get('nombre') or 'Sin nombre')}</b></a>
<div class="muted" style="font-size:13px">CC {e(f.get('cedula') or '—')} · {e(f.get('telefono') or '—')}</div></td>
<td>{e(ex.TRAMITES.get(f['tramite'], {}).get('nombre', f['tramite']))}</td>
<td>{_tag_estado(f['estado'])}</td><td style="font-size:13px">{docs_txt}</td>
<td class="hide-m muted" style="font-size:13px">{canal}</td>
<td class="hide-m muted" style="font-size:13px">{_fecha(f.get('creado_en'))}</td></tr>"""
        tabla = f"""<table><thead><tr><th>Paciente</th><th>Trámite</th><th>Estado</th><th>Documentos</th>
<th class="hide-m">Llegó por</th><th class="hide-m">Fecha</th></tr></thead><tbody>{trs}</tbody></table>"""
    else:
        tabla = '<p class="muted" style="margin:8px 0">No hay expedientes con esos filtros.</p>'
    link_form = f"{ex.public_base_url()}/documentos"
    cuerpo = f"""<div class="wrap wide"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:6px 0 12px">
<h1 style="margin:0">Documentos de pacientes</h1>
<div class="copy" style="min-width:300px"><input type="text" readonly value="{e(link_form)}" id="lf">
<button class="btn sec sm" onclick="navigator.clipboard.writeText(document.getElementById('lf').value);this.textContent='Copiado'">Copiar link del formulario</button></div></div>
<div class="chips">{chips}</div>
<div class="card"><form class="filtros" method="get">
<div><label>Buscar</label><input type="text" name="q" placeholder="Nombre, cédula o teléfono" value="{e(q)}"></div>
<div><label>Trámite</label><select name="tramite">{op_tram}</select></div>
<div><label>Estado</label><select name="estado">{op_est}</select></div>
<div><label>Desde</label><input type="date" name="desde" value="{e(desde)}"></div>
<div><label>Hasta</label><input type="date" name="hasta" value="{e(hasta)}"></div>
<div style="display:flex;gap:6px"><button class="btn sm" type="submit">Filtrar</button>
<a class="btn sec sm" href="/dashboard/documentos">Limpiar</a></div></form></div>
<div class="card" style="padding:6px 12px;overflow-x:auto">{tabla}</div>
<p class="muted" style="font-size:13px">{len(filas)} resultado{'s' if len(filas) != 1 else ''}</p></div>"""
    return _pagina("Documentos · Aurora", cuerpo, panel=True, usuario=usuario)
 
 
@router.get("/dashboard/documentos/{expediente_id}", response_class=HTMLResponse)
async def panel_detalle(expediente_id: str, request: Request, msg: str = ""):
    usuario = _usuario(request)
    if not usuario:
        return _al_login()
    exp = ex.obtener(expediente_id)
    if not exp:
        return _pagina("No encontrado", '<div class="wrap"><div class="card"><h1>Expediente no encontrado</h1>'
                       '<a href="/dashboard/documentos">Volver</a></div></div>', panel=True, usuario=usuario)
    tramite = ex.TRAMITES.get(exp["tramite"], {"nombre": exp["tramite"], "docs": []})
    docs = ex.documentos(expediente_id)
    recibidos = {d["tipo"] for d in docs if d["estado_revision"] != "rechazado"}
    checklist = "".join(
        f'<li>{"✅" if t in recibidos else "⬜"} {e(ex.DOCS[t]["nombre"])}</li>' for t in tramite["docs"]
    )
    tarjetas = ""
    for d in docs:
        ver = f"/dashboard/documentos/doc/{d['id']}/ver"
        if (d.get("mime") or "").startswith("image/"):
            url = ex.url_firmada(d["storage_path"])
            prev = f'<a href="{ver}" target="_blank"><img src="{e(url or "")}" alt="{e(d["tipo"])}" loading="lazy"></a>'
        else:
            prev = f'<a href="{ver}" target="_blank" style="text-decoration:none;font-weight:600">📄 Abrir PDF</a>'
        extra = ""
        if d["tipo"] == "orden_clinica":
            vig = ex.orden_vigente(d.get("fecha_expedicion"))
            if d.get("fecha_expedicion"):
                extra = f'<div style="font-size:13px">Expedida: {_dia(d["fecha_expedicion"])} · ' + (
                    '<span class="tag t-ok">Vigente</span>' if vig else '<span class="tag t-err">Vencida</span>') + "</div>"
            else:
                extra = '<div style="font-size:13px"><span class="tag t-warn">Sin fecha — revisar a mano</span></div>'
        motivo = f'<div style="font-size:13px;color:var(--err)">Motivo: {e(d["motivo_rechazo"])}</div>' if d.get("motivo_rechazo") else ""
        rev = f'<div class="muted" style="font-size:12px">Revisado por {e(d["revisado_por"])}</div>' if d.get("revisado_por") else ""
        tarjetas += f"""<div class="doc"><div class="prev">{prev}</div><div class="body">
<div style="display:flex;justify-content:space-between;gap:6px"><b>{e(ex.DOCS.get(d['tipo'], {}).get('nombre', d['tipo']))}</b>{_tag_rev(d['estado_revision'])}</div>
<div class="muted" style="font-size:12px">{'Formulario web' if d['canal'] == 'formulario' else 'WhatsApp'} · {_fecha(d.get('creado_en'))}</div>
{extra}{motivo}{rev}</div><div class="acc">
<form method="post" action="/dashboard/documentos/doc/{d['id']}/revisar"><input type="hidden" name="accion" value="aprobar">
<button class="btn sm" type="submit">Aprobar</button>
<a class="btn sec sm" href="/dashboard/documentos/doc/{d['id']}/descargar">Descargar</a></form>
<form method="post" action="/dashboard/documentos/doc/{d['id']}/revisar"><input type="hidden" name="accion" value="rechazar">
<input type="text" name="motivo" placeholder="Motivo del rechazo" required>
<label class="chk" style="margin:0;font-size:12px;width:100%"><input type="checkbox" name="avisar" value="1" checked>Avisar al paciente por WhatsApp</label>
<button class="btn err sm" type="submit">Rechazar</button></form></div></div>"""
    if not tarjetas:
        tarjetas = '<p class="muted">Todavía no hay documentos.</p>'
    op_est = "".join(f'<option value="{k}"{" selected" if exp["estado"] == k else ""}>{e(n)}</option>' for k, n in ex.ESTADOS.items())
    link = f"{ex.public_base_url()}/documentos/{exp['token']}"
    aviso = {"ok": '<div class="alert ok">Cambios guardados.</div>',
             "avisado": '<div class="alert ok">Documento rechazado y paciente avisado por WhatsApp.</div>',
             "noavisado": '<div class="alert err">Documento rechazado, pero no se pudo avisar por WhatsApp '
                          '(¿ventana de 24 horas cerrada?). Escríbele desde Chats con el link personal.</div>'}.get(msg, "")
    chat = f'<a class="btn sec sm" href="/dashboard/chats/{quote(exp["telefono"])}">Abrir chat de WhatsApp</a>' if exp.get("telefono") else ""
    cuerpo = f"""<div class="wrap wide"><p style="margin:6px 0 10px"><a href="/dashboard/documentos">← Documentos</a></p>{aviso}
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
<h1 style="margin:0">{e(exp.get('nombre') or 'Sin nombre')}</h1><div>{_tag_estado(exp['estado'])} {chat}</div></div>
<p class="muted" style="margin-top:4px">{e(tramite['nombre'])}</p>
<div class="grid2"><div class="card"><h2 style="font-size:16px">Datos</h2><dl>
<dt>Cédula</dt><dd>{e(exp.get('cedula') or '—')}</dd><dt>Celular</dt><dd>{e(exp.get('telefono') or '—')}</dd>
<dt>Correo</dt><dd>{e(exp.get('correo') or '—')}</dd><dt>Llegó por</dt><dd>{'Formulario web' if exp.get('origen') == 'formulario' else 'WhatsApp (Aurora)'}</dd>
<dt>Creado</dt><dd>{_fecha(exp.get('creado_en'))}</dd><dt>Actualizado</dt><dd>{_fecha(exp.get('actualizado_en'))}{(' · ' + e(exp['actualizado_por'])) if exp.get('actualizado_por') else ''}</dd></dl>
<h2 style="font-size:16px;margin-top:14px">Requeridos</h2><ul style="margin:0;padding-left:4px;list-style:none">{checklist}</ul>
<label style="font-size:13px">Link personal del paciente</label><div class="copy"><input type="text" readonly value="{e(link)}" id="lp">
<button class="btn sec sm" onclick="navigator.clipboard.writeText(document.getElementById('lp').value);this.textContent='Copiado'">Copiar</button></div></div>
<div class="card"><h2 style="font-size:16px">Estado del expediente</h2>
<form method="post" action="/dashboard/documentos/{exp['id']}/estado"><select name="estado">{op_est}</select>
<label for="notas" style="font-size:13px">Notas internas</label><textarea id="notas" name="notas" rows="4">{e(exp.get('notas') or '')}</textarea>
<button class="btn" type="submit" style="margin-top:10px">Guardar</button></form>
<p class="hint">Faltan documentos / En revisión / Listo para el agente / Orden vencida se actualizan solos al aprobar o rechazar.
«Requiere agente» y «Agendado» solo los pones tú y el sistema los respeta.</p></div></div>
<h2 style="font-size:17px">Documentos ({len(docs)})</h2><div class="docs">{tarjetas}</div></div>"""
    return _pagina(f"{exp.get('nombre') or 'Expediente'} · Documentos", cuerpo, panel=True, usuario=usuario)
 
 
@router.post("/dashboard/documentos/{expediente_id}/estado")
async def panel_estado(expediente_id: str, request: Request):
    usuario = _usuario(request)
    if not usuario:
        return _al_login()
    form = await request.form()
    estado = form.get("estado") or ""
    if estado not in ex.ESTADOS:
        return RedirectResponse(f"/dashboard/documentos/{expediente_id}", status_code=303)
    ex.cambiar_estado(expediente_id, estado, usuario, notas=form.get("notas"))
    if estado in ex.ESTADOS_AUTOMATICOS:
        ex.recalcular_estado(expediente_id)
    return RedirectResponse(f"/dashboard/documentos/{expediente_id}?msg=ok", status_code=303)
 
 
async def _avisar_whatsapp(telefono: str, texto: str) -> bool:
    try:
        from app import whatsapp_client as wa
    except Exception:  # noqa: BLE001
        return False
    for nombre in ("send_text", "send_message", "enviar_texto", "enviar_mensaje"):
        fn = getattr(wa, nombre, None)
        if not fn:
            continue
        try:
            r = fn(telefono, texto)
            if inspect.isawaitable(r):
                r = await r
            if r is False:
                return False
            if isinstance(r, dict) and r.get("error"):
                return False
            # Si existe, queda también en el historial del panel de chats.
            try:
                from app import conversaciones as conv
                for reg in ("registrar_mensaje", "guardar_mensaje", "agregar_mensaje"):
                    g = getattr(conv, reg, None)
                    if g:
                        rr = g(telefono, "agente", texto)
                        if inspect.isawaitable(rr):
                            await rr
                        break
            except Exception:  # noqa: BLE001
                log.info("No se registró el aviso en el historial del chat", exc_info=True)
            return True
        except Exception:  # noqa: BLE001
            log.warning("No se pudo avisar por WhatsApp a %s", telefono, exc_info=True)
            return False
    return False
 
 
@router.post("/dashboard/documentos/doc/{doc_id}/revisar")
async def panel_revisar(doc_id: str, request: Request):
    usuario = _usuario(request)
    if not usuario:
        return _al_login()
    form = await request.form()
    aprobado = form.get("accion") == "aprobar"
    doc = ex.revisar_documento(doc_id, aprobado=aprobado, por=usuario, motivo=form.get("motivo"))
    msg = "ok"
    if not aprobado and form.get("avisar"):
        exp = ex.obtener(doc["expediente_id"])
        if exp and exp.get("telefono"):
            nombre_doc = ex.DOCS.get(doc["tipo"], {}).get("nombre", "documento")
            texto = (
                f"Hola{(' ' + exp['nombre'].split(' ')[0]) if exp.get('nombre') else ''}, revisamos tu *{nombre_doc}* "
                f"y necesitamos que lo envíes de nuevo.\nMotivo: {doc.get('motivo_rechazo')}\n\n"
                f"Puedes enviarlo por aquí o en este link: {ex.public_base_url()}/documentos/{exp['token']}"
            )
            msg = "avisado" if await _avisar_whatsapp(exp["telefono"], texto) else "noavisado"
    return RedirectResponse(f"/dashboard/documentos/{doc['expediente_id']}?msg={msg}", status_code=303)
 
 
@router.get("/dashboard/documentos/doc/{doc_id}/ver")
async def panel_ver(doc_id: str, request: Request):
    if not _usuario(request):
        return _al_login()
    doc = ex.obtener_documento(doc_id)
    url = ex.url_firmada(doc["storage_path"]) if doc else None
    return RedirectResponse(url, status_code=302) if url else HTMLResponse("No disponible", status_code=404)
 
 
@router.get("/dashboard/documentos/doc/{doc_id}/descargar")
async def panel_descargar(doc_id: str, request: Request):
    if not _usuario(request):
        return _al_login()
    doc = ex.obtener_documento(doc_id)
    if not doc:
        return HTMLResponse("No disponible", status_code=404)
    exp = ex.obtener(doc["expediente_id"]) or {}
    ext = ex.MIME_PERMITIDOS.get(doc.get("mime") or "", doc["storage_path"].rsplit(".", 1)[-1])
    nombre = f"{doc['tipo']}_{exp.get('cedula') or exp.get('telefono') or 'paciente'}_{doc['id'][:6]}.{ext}"
    url = ex.url_firmada(doc["storage_path"], descargar=nombre)
    return RedirectResponse(url, status_code=302) if url else HTMLResponse("No disponible", status_code=404)
 
