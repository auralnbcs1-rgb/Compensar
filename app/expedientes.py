"""
Expedientes de documentos: un expediente por paciente + trámite, con todos sus documentos,
lleguen por el formulario web (/documentos) o por WhatsApp (Aurora).

Funciones que usa Aurora (ver INTEGRACION.md):
    link_personal(telefono, tramite, cedula=None, nombre=None)      -> URL para mandar por WhatsApp
    registrar_documento_whatsapp(telefono, tramite, tipo, storage_path, ...)
    documentos_recibidos(telefono, tramite)                          -> {"orden_clinica", ...}
    faltantes(telefono, tramite)                                     -> ["autorizacion_servicio", ...]
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

BUCKET = os.environ.get("DOCUMENTOS_BUCKET", "documentos-pacientes")
MAX_BYTES = 10 * 1024 * 1024  # 10 MB por archivo
MIME_PERMITIDOS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}

# Trámites de Aurora que piden documentos (mismos códigos que solicitudes.SERVICIOS).
# Control, Mantenimiento, Entrega Compensar y Valoración particular no piden documentos,
# así que no aparecen en el formulario. Los marcados con * en el menú piden orden clínica
# + autorización de servicio + cédula; Prueba de Audífono solo orden clínica.
TRAMITES: dict[str, dict] = {
    "evaluacion_adaptacion": {
        "nombre": "Evaluación y adaptación de prótesis y ayudas auditivas",
        "docs": ["orden_clinica", "autorizacion_servicio", "cedula"],
    },
    "prueba_audifono": {"nombre": "Prueba de Audífono", "docs": ["orden_clinica"]},
    "evaluacion_tinnitus": {
        "nombre": "Evaluación Tinnitus",
        "docs": ["orden_clinica", "autorizacion_servicio", "cedula"],
    },
    "terapia_tinnitus": {
        "nombre": "Terapia Tinnitus",
        "docs": ["orden_clinica", "autorizacion_servicio", "cedula"],
    },
}

DOCS: dict[str, dict] = {
    "orden_clinica": {"nombre": "Orden clínica", "ayuda": "Foto completa y legible de la orden del médico."},
    "autorizacion_servicio": {"nombre": "Autorización de servicio", "ayuda": "Emitida por Compensar, vigente."},
    "cedula": {"nombre": "Cédula", "ayuda": "Foto por ambas caras (puedes subir dos archivos)."},
    "otro": {"nombre": "Otro documento", "ayuda": ""},
}

ESTADOS: dict[str, str] = {
    "pendiente_documentos": "Faltan documentos",
    "en_revision": "En revisión",
    "documentos_completos": "Listo para el agente",
    "orden_vencida": "Autorización vencida",
    "requiere_humano": "Requiere agente",
    "agendado": "Agendado",
}
# Estados que el sistema recalcula solo. Los demás los pone un agente a mano y se respetan.
ESTADOS_AUTOMATICOS = {"pendiente_documentos", "en_revision", "documentos_completos", "orden_vencida"}

# ------------------------------------------------------------------ cliente Supabase
_client = None


def set_client(client) -> None:
    """Permite inyectar el cliente (lo usa main.py si quiere reutilizar el de app/db.py, y los tests)."""
    global _client
    _client = client


def sb():
    global _client
    if _client is None:
        from supabase import create_client

        url = key = None
        try:  # mismas credenciales que el resto de Aurora (app/config.py)
            from app.config import settings

            url = getattr(settings, "supabase_url", None)
            for attr in ("supabase_service_role_key", "supabase_service_key", "supabase_key"):
                key = key or getattr(settings, attr, None)
        except Exception:  # noqa: BLE001
            pass
        url = url or os.environ["SUPABASE_URL"]
        key = (
            key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ["SUPABASE_KEY"]
        )
        _client = create_client(url, key)
    return _client


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ utilidades
def normalizar_telefono(tel: str | None) -> str | None:
    if not tel:
        return None
    d = re.sub(r"\D", "", tel)
    if len(d) == 10 and d.startswith("3"):
        d = "57" + d
    return d or None


def normalizar_cedula(ced: str | None) -> str | None:
    if not ced:
        return None
    d = re.sub(r"\D", "", ced)
    return d or None




def public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


# ------------------------------------------------------------------ expedientes
def obtener_por_token(token: str) -> dict | None:
    r = sb().table("expedientes").select("*").eq("token", token).limit(1).execute()
    return r.data[0] if r.data else None


def obtener(expediente_id: str) -> dict | None:
    r = sb().table("expedientes").select("*").eq("id", expediente_id).limit(1).execute()
    return r.data[0] if r.data else None


def _buscar_abierto(*, tramite: str, telefono: str | None = None, cedula: str | None = None) -> dict | None:
    """Expediente del mismo trámite que todavía no está agendado (por teléfono o por cédula)."""
    for campo, valor in (("telefono", telefono), ("cedula", cedula)):
        if not valor:
            continue
        r = (
            sb().table("expedientes").select("*")
            .eq(campo, valor).eq("tramite", tramite).neq("estado", "agendado")
            .order("creado_en", desc=True).limit(1).execute()
        )
        if r.data:
            return r.data[0]
    return None


def obtener_o_crear(
    *, tramite: str, origen: str, telefono: str | None = None, cedula: str | None = None,
    nombre: str | None = None, correo: str | None = None,
) -> dict:
    if tramite not in TRAMITES:
        raise ValueError(f"Trámite desconocido: {tramite}")
    telefono = normalizar_telefono(telefono)
    cedula = normalizar_cedula(cedula)
    exp = _buscar_abierto(tramite=tramite, telefono=telefono, cedula=cedula)
    if exp:
        # Completa datos que antes no teníamos, sin pisar los que ya estaban.
        cambios = {
            k: v for k, v in
            {"telefono": telefono, "cedula": cedula, "nombre": nombre, "correo": correo}.items()
            if v and not exp.get(k)
        }
        if cambios:
            cambios["actualizado_en"] = _ahora()
            sb().table("expedientes").update(cambios).eq("id", exp["id"]).execute()
            exp.update(cambios)
        return exp
    fila = {
        "token": secrets.token_urlsafe(24),
        "origen": origen,
        "telefono": telefono,
        "cedula": cedula,
        "nombre": nombre,
        "correo": correo,
        "tramite": tramite,
        "estado": "pendiente_documentos",
    }
    r = sb().table("expedientes").insert(fila).execute()
    return r.data[0]


def listar(
    *, q: str | None = None, tramite: str | None = None, estado: str | None = None,
    desde: str | None = None, hasta: str | None = None, limite: int = 1000,
) -> list[dict]:
    query = sb().table("expedientes").select("*")
    if tramite:
        query = query.eq("tramite", tramite)
    if estado:
        query = query.eq("estado", estado)
    if desde:
        query = query.gte("creado_en", f"{desde}T00:00:00")
    if hasta:
        query = query.lte("creado_en", f"{hasta}T23:59:59")
    filas = query.order("creado_en", desc=True).limit(limite).execute().data or []
    if q:
        qn = q.strip().lower()
        qd = re.sub(r"\D", "", qn)
        filas = [
            f for f in filas
            if qn in (f.get("nombre") or "").lower()
            or (qd and (qd in (f.get("cedula") or "") or qd in (f.get("telefono") or "")))
        ]
    if filas:
        ids = [f["id"] for f in filas]
        docs = sb().table("expediente_docs").select("expediente_id,estado_revision").in_("expediente_id", ids).execute().data or []
        conteo: dict[str, dict] = {}
        for d in docs:
            c = conteo.setdefault(d["expediente_id"], {"total": 0, "pendiente": 0, "rechazado": 0})
            c["total"] += 1
            if d["estado_revision"] in c:
                c[d["estado_revision"]] += 1
        for f in filas:
            f["_docs"] = conteo.get(f["id"], {"total": 0, "pendiente": 0, "rechazado": 0})
    return filas


def contar_por_estado() -> dict[str, int]:
    filas = sb().table("expedientes").select("estado").execute().data or []
    out = {k: 0 for k in ESTADOS}
    for f in filas:
        out[f["estado"]] = out.get(f["estado"], 0) + 1
    return out


def cambiar_estado(expediente_id: str, estado: str, por: str, notas: str | None = None) -> None:
    if estado not in ESTADOS:
        raise ValueError(estado)
    cambios = {"estado": estado, "actualizado_por": por, "actualizado_en": _ahora()}
    if notas is not None:
        cambios["notas"] = notas
    sb().table("expedientes").update(cambios).eq("id", expediente_id).execute()
    _sincronizar_solicitud(obtener(expediente_id))


# ------------------------------------------------------------------ documentos
def documentos(expediente_id: str) -> list[dict]:
    r = (
        sb().table("expediente_docs").select("*")
        .eq("expediente_id", expediente_id).order("creado_en", desc=True).execute()
    )
    return r.data or []


def obtener_documento(doc_id: str) -> dict | None:
    r = sb().table("expediente_docs").select("*").eq("id", doc_id).limit(1).execute()
    return r.data[0] if r.data else None


def subir_archivo(expediente_id: str, tipo: str, contenido: bytes, mime: str) -> str:
    ext = MIME_PERMITIDOS[mime]
    path = f"formulario/{expediente_id}/{tipo}/{uuid.uuid4().hex}.{ext}"
    sb().storage.from_(BUCKET).upload(path, contenido, {"content-type": mime})
    return path


def agregar_documento(
    expediente_id: str, *, tipo: str, canal: str, storage_path: str, nombre_archivo: str | None = None,
    mime: str | None = None, tamano: int | None = None, fecha_detectada: str | None = None,
    vigente: bool | None = None, nota_ia: str | None = None,
    estado_revision: str = "pendiente", revisado_por: str | None = None,
) -> dict:
    """`fecha_detectada`, `vigente` y `nota_ia` vienen de vision_client.clasificar — la misma
    lectura que hace Aurora con las imágenes de WhatsApp (la autorización se valida por la
    fecha de vencimiento impresa; la orden clínica no vence)."""
    fila = {
        "expediente_id": expediente_id,
        "tipo": tipo if tipo in DOCS else "otro",
        "canal": canal,
        "storage_path": storage_path,
        "nombre_archivo": nombre_archivo,
        "mime": mime,
        "tamano": tamano,
        "fecha_detectada": fecha_detectada or None,
        "vigente": vigente,
        "nota_ia": nota_ia,
        "estado_revision": estado_revision,
    }
    if revisado_por:
        fila["revisado_por"] = revisado_por
        fila["revisado_en"] = _ahora()
    r = sb().table("expediente_docs").insert(fila).execute()
    recalcular_estado(expediente_id)
    return r.data[0]


def revisar_documento(doc_id: str, *, aprobado: bool, por: str, motivo: str | None = None) -> dict:
    cambios = {
        "estado_revision": "aprobado" if aprobado else "rechazado",
        "motivo_rechazo": None if aprobado else (motivo or "No es legible o no corresponde"),
        "revisado_por": por,
        "revisado_en": _ahora(),
    }
    sb().table("expediente_docs").update(cambios).eq("id", doc_id).execute()
    doc = obtener_documento(doc_id)
    recalcular_estado(doc["expediente_id"])
    return doc


def url_firmada(storage_path: str, segundos: int = 600, descargar: str | None = None) -> str | None:
    try:
        bucket = sb().storage.from_(BUCKET)
        if descargar:
            r = bucket.create_signed_url(storage_path, segundos, {"download": descargar})
        else:
            r = bucket.create_signed_url(storage_path, segundos)
        return r.get("signedURL") or r.get("signedUrl") or r.get("signed_url")
    except Exception:  # noqa: BLE001
        log.exception("No se pudo firmar %s", storage_path)
        return None


def _vigentes_por_tipo(docs: list[dict]) -> dict[str, list[dict]]:
    """Documentos no rechazados, agrupados por tipo (más reciente primero)."""
    out: dict[str, list[dict]] = {}
    for d in sorted(docs, key=lambda x: x.get("creado_en") or "", reverse=True):
        if d["estado_revision"] != "rechazado":
            out.setdefault(d["tipo"], []).append(d)
    return out


def recalcular_estado(expediente_id: str) -> str:
    exp = obtener(expediente_id)
    if not exp:
        return ""
    if exp["estado"] not in ESTADOS_AUTOMATICOS:
        return exp["estado"]  # lo puso un agente a mano: no se toca
    requeridos = TRAMITES[exp["tramite"]]["docs"]
    todos = sorted(documentos(expediente_id), key=lambda x: x.get("creado_en") or "", reverse=True)
    por_tipo = _vigentes_por_tipo(todos)
    ultima_aut = next((d for d in todos if d["tipo"] == "autorizacion_servicio"), None)
    if "autorizacion_servicio" in requeridos and ultima_aut and ultima_aut.get("vigente") is False:
        nuevo = "orden_vencida"  # la última autorización que llegó está vencida (lo leyó Aurora)
    elif any(t not in por_tipo for t in requeridos):
        nuevo = "pendiente_documentos"
    else:
        if "autorizacion_servicio" in requeridos:
            vig = por_tipo["autorizacion_servicio"][0].get("vigente")  # lo que leyó vision
        else:
            vig = True  # solo orden clínica, que no vence
        if vig is False:
            nuevo = "orden_vencida"
        elif all(por_tipo[t][0]["estado_revision"] == "aprobado" for t in requeridos) and vig is not None:
            nuevo = "documentos_completos"
        else:
            nuevo = "en_revision"
    if nuevo != exp["estado"]:
        sb().table("expedientes").update({"estado": nuevo, "actualizado_en": _ahora()}).eq("id", expediente_id).execute()
        exp["estado"] = nuevo
        _sincronizar_solicitud(exp)
    return nuevo


# ------------------------------------------------------------------ sincronización con `solicitudes`
# Solo se tocan solicitudes abiertas en estados de documentos — nunca una ya gestionada
# (atendida/agendada/no_interesado) ni una que un agente tiene en 'requiere_humano'.
_ESTADOS_SOLICITUD_TOCABLES = ["pendiente_documentos", "orden_vencida", "documentos_completos"]
_MAPEO_SOLICITUD = {
    "pendiente_documentos": "pendiente_documentos",
    "en_revision": "pendiente_documentos",
    "documentos_completos": "documentos_completos",  # aparece en la franja azul de Chats
    "orden_vencida": "orden_vencida",
}


def _sincronizar_solicitud(exp: dict | None) -> None:
    """Refleja el estado del expediente en la tabla `solicitudes` de Aurora (si existe y coincide el teléfono).
    Se desactiva con EXPEDIENTES_SYNC_SOLICITUDES=0. Nunca rompe el flujo si algo no cuadra."""
    if not exp or os.environ.get("EXPEDIENTES_SYNC_SOLICITUDES", "1") != "1" or not exp.get("telefono"):
        return
    if exp["estado"] not in _MAPEO_SOLICITUD:
        return
    try:
        (
            sb().table("solicitudes")
            .update({"estado": _MAPEO_SOLICITUD[exp["estado"]]})
            .eq("telefono", exp["telefono"]).eq("servicio", exp["tramite"])
            .in_("estado", _ESTADOS_SOLICITUD_TOCABLES).execute()
        )
    except Exception:  # noqa: BLE001
        log.warning("No se pudo sincronizar solicitudes para %s", exp.get("telefono"), exc_info=True)


# ------------------------------------------------------------------ funciones para Aurora
def link_personal(telefono: str, tramite: str, cedula: str | None = None, nombre: str | None = None) -> str:
    """Crea (o reutiliza) el expediente del paciente y devuelve su link personal para subir documentos."""
    exp = obtener_o_crear(tramite=tramite, origen="whatsapp", telefono=telefono, cedula=cedula, nombre=nombre)
    return f"{public_base_url()}/documentos/{exp['token']}"


def registrar_documento_whatsapp(
    telefono: str, tramite: str, tipo: str, storage_path: str, *, mime: str | None = None,
    fecha_detectada: str | None = None, vigente: bool | None = None, nota_ia: str | None = None,
    validado_por_aurora: bool = False,
    cedula: str | None = None, nombre: str | None = None,
) -> dict | None:
    """Copia al expediente un documento que Aurora ya guardó y clasificó (no vuelve a subir el archivo).
    Pásale lo mismo que a documentos.registrar: fecha_detectada, vigente y nota_ia de la clasificación.
    Si `validado_por_aurora` es True, entra aprobado (Claude vision lo clasificó con confianza)."""
    try:
        exp = obtener_o_crear(tramite=tramite, origen="whatsapp", telefono=telefono, cedula=cedula, nombre=nombre)
        return agregar_documento(
            exp["id"], tipo=tipo, canal="whatsapp", storage_path=storage_path, mime=mime,
            fecha_detectada=fecha_detectada, vigente=vigente, nota_ia=nota_ia,
            estado_revision="aprobado" if validado_por_aurora else "pendiente",
            revisado_por="Aurora" if validado_por_aurora else None,
        )
    except Exception:  # noqa: BLE001
        log.exception("No se pudo registrar documento de WhatsApp en expediente")
        return None


def documentos_recibidos(telefono: str, tramite: str) -> set[str]:
    """Tipos de documento ya recibidos (por cualquier canal) y no rechazados."""
    exp = _buscar_abierto(tramite=tramite, telefono=normalizar_telefono(telefono))
    if not exp:
        return set()
    return set(_vigentes_por_tipo(documentos(exp["id"])))


def faltantes(telefono: str, tramite: str) -> list[str]:
    recibidos = documentos_recibidos(telefono, tramite)
    return [t for t in TRAMITES[tramite]["docs"] if t not in recibidos]
