"""Pruebas del formulario y el panel con un Supabase falso en memoria.
Correr desde la raíz del proyecto:  python -m pytest tests/test_formulario.py -q
"""
import sys
import types
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ------------------------------------------------------------------ Supabase falso
class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, db, tabla):
        self.db, self.t = db, tabla
        self.filtros, self.op, self.payload, self._order, self._limit = [], "select", None, None, None

    def select(self, *_a): self.op = "select"; return self
    def insert(self, p): self.op, self.payload = "insert", p; return self
    def update(self, p): self.op, self.payload = "update", p; return self
    def eq(self, c, v): self.filtros.append(lambda r: r.get(c) == v); return self
    def neq(self, c, v): self.filtros.append(lambda r: r.get(c) != v); return self
    def in_(self, c, vs): self.filtros.append(lambda r: r.get(c) in vs); return self
    def gte(self, c, v): self.filtros.append(lambda r: (r.get(c) or "") >= v); return self
    def lte(self, c, v): self.filtros.append(lambda r: (r.get(c) or "") <= v); return self
    def order(self, c, desc=False): self._order = (c, desc); return self
    def limit(self, n): self._limit = n; return self

    def execute(self):
        filas = self.db.setdefault(self.t, [])
        if self.op == "insert":
            self.db["_n"] = self.db.get("_n", 0) + 1
            ahora = (datetime.now(timezone.utc) + timedelta(microseconds=self.db["_n"])).isoformat()
            fila = {"id": str(uuid.uuid4()), "creado_en": ahora, "actualizado_en": ahora, **self.payload}
            filas.append(fila)
            return _Res([dict(fila)])
        sel = [r for r in filas if all(f(r) for f in self.filtros)]
        if self.op == "update":
            for r in sel:
                r.update(self.payload)
            return _Res([dict(r) for r in sel])
        if self._order:
            c, d = self._order
            sel.sort(key=lambda r: r.get(c) or "", reverse=d)
        if self._limit:
            sel = sel[: self._limit]
        return _Res([dict(r) for r in sel])


class _Bucket:
    def __init__(self, store): self.store = store
    def upload(self, path, data, opts=None): self.store[path] = data
    def create_signed_url(self, path, seg, opts=None):
        return {"signedURL": f"https://fake.storage/{path}" + (f"?download={opts['download']}" if opts else "")}


class FakeSB:
    def __init__(self):
        self.db, self.files = {}, {}
        self.storage = types.SimpleNamespace(from_=lambda b: _Bucket(self.files))

    def table(self, t): return _Q(self.db, t)


# ------------------------------------------------------------------ módulos de Aurora simulados
enviados = []
auth = types.ModuleType("app.dashboard_auth")
auth.validar_token = lambda t: {"email": "agente@aural.co"} if t == "ok" else None
wa = types.ModuleType("app.whatsapp_client")
wa.send_text = lambda to, body: enviados.append((to, body)) or {"messages": [{"id": "x"}]}
sys.modules["app.dashboard_auth"] = auth
sys.modules["app.whatsapp_client"] = wa

from app import expedientes as ex  # noqa: E402
from app.formulario import router  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
HOY = date.today().isoformat()


@pytest.fixture
def ctx(monkeypatch):
    fake = FakeSB()
    fake.db["solicitudes"] = [{"id": "s1", "telefono": "573001112233", "estado": "pendiente_documentos"}]
    ex.set_client(fake)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://aurora.test")
    enviados.clear()
    app = FastAPI()
    app.include_router(router)
    return fake, TestClient(app)


def _datos(**kw):
    d = {"cedula": "1.020.304.050", "nombre": "María Pérez Gómez", "telefono": "300 111 2233",
         "correo": "maria@correo.com", "tramite": "prueba_audifono", "acepto": "1", "fecha_orden": HOY}
    d.update(kw)
    return d


def test_formulario_publico_carga(ctx):
    _, c = ctx
    r = c.get("/documentos")
    assert r.status_code == 200 and "Envía tus documentos" in r.text and "Ley 1581" in r.text


def test_envio_publico_crea_expediente_y_redirige_a_link_personal(ctx):
    fake, c = ctx
    r = c.post("/documentos", data=_datos(), files={"doc_orden_clinica": ("orden.png", PNG, "image/png")},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/documentos/")
    exp = fake.db["expedientes"][0]
    assert exp["telefono"] == "573001112233" and exp["cedula"] == "1020304050" and exp["origen"] == "formulario"
    doc = fake.db["expediente_docs"][0]
    assert doc["tipo"] == "orden_clinica" and doc["fecha_expedicion"] == HOY and doc["canal"] == "formulario"
    assert len(fake.files) == 1
    assert exp["estado"] == "en_revision"  # completo pero falta que un agente apruebe
    r2 = c.get(r.headers["location"])
    assert "Recibimos tus documentos" in r2.text and "en revisión" in r2.text


def test_validaciones_publico(ctx):
    fake, c = ctx
    assert "Revisa el número de cédula" in c.post("/documentos", data=_datos(cedula="12")).text
    assert "Adjunta al menos un documento" in c.post("/documentos", data=_datos()).text
    r = c.post("/documentos", data=_datos(), files={"doc_orden_clinica": ("x.txt", b"hola", "text/plain")})
    assert "no es una foto" in r.text
    r = c.post("/documentos", data=_datos(fecha_orden=""), files={"doc_orden_clinica": ("o.png", PNG, "image/png")})
    assert "fecha de expedición" in r.text
    assert "autorizar el tratamiento" in c.post("/documentos", data=_datos(acepto="")).text
    assert "expedientes" not in fake.db or not fake.db["expedientes"]


def test_mismo_paciente_reutiliza_expediente(ctx):
    fake, c = ctx
    d = _datos(tramite="evaluacion_tinnitus")
    c.post("/documentos", data=d, files={"doc_orden_clinica": ("o.png", PNG, "image/png")})
    c.post("/documentos", data=d, files={"doc_autorizacion": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert len(fake.db["expedientes"]) == 1 and len(fake.db["expediente_docs"]) == 2
    assert fake.db["expedientes"][0]["estado"] == "pendiente_documentos"  # falta la cédula


def test_aurora_link_y_documento_whatsapp(ctx):
    fake, c = ctx
    url = ex.link_personal("573001112233", "evaluacion_adaptacion", cedula="1020304050", nombre="María Pérez")
    assert url.startswith("https://aurora.test/documentos/")
    ex.registrar_documento_whatsapp("573001112233", "evaluacion_adaptacion", "orden_clinica",
                                    "573001112233/orden.jpg", mime="image/jpeg", fecha_expedicion=HOY,
                                    validado_por_aurora=True)
    assert ex.faltantes("573001112233", "evaluacion_adaptacion") == ["autorizacion", "cedula"]
    token = url.rsplit("/", 1)[1]
    page = c.get(f"/documentos/{token}").text
    assert "Recibido ✓" in page and "faltan 2 documentos" in page
    # El paciente completa por la web
    r = c.post(f"/documentos/{token}", files=[("doc_autorizacion", ("a.pdf", b"%PDF", "application/pdf")),
                                               ("doc_cedula", ("c1.png", PNG, "image/png")),
                                               ("doc_cedula", ("c2.png", PNG, "image/png"))], follow_redirects=False)
    assert r.status_code == 303
    assert ex.faltantes("573001112233", "evaluacion_adaptacion") == []
    assert len(fake.db["expedientes"]) == 1  # mismo expediente para WhatsApp y web


def test_flujo_panel_aprobar_rechazar_estado(ctx):
    fake, c = ctx
    c.post("/documentos", data=_datos(), files={"doc_orden_clinica": ("o.png", PNG, "image/png")})
    exp = fake.db["expedientes"][0]
    doc = fake.db["expediente_docs"][0]

    assert c.get("/dashboard/documentos", follow_redirects=False).headers["location"] == "/login"
    c.cookies.set("aurora_dashboard_session", "ok")

    lista = c.get("/dashboard/documentos").text
    assert "María Pérez Gómez" in lista and "1 por revisar" in lista
    assert "María" in c.get("/dashboard/documentos?q=1020304050").text
    assert "No hay expedientes" in c.get("/dashboard/documentos?q=zzz").text
    assert "No hay expedientes" in c.get("/dashboard/documentos?tramite=terapia_tinnitus").text

    det = c.get(f"/dashboard/documentos/{exp['id']}").text
    assert "Vigente" in det and "https://fake.storage/formulario/" in det

    # Rechazar con aviso por WhatsApp
    r = c.post(f"/dashboard/documentos/doc/{doc['id']}/revisar",
               data={"accion": "rechazar", "motivo": "Foto borrosa", "avisar": "1"}, follow_redirects=False)
    assert "msg=avisado" in r.headers["location"]
    assert enviados and enviados[0][0] == "573001112233" and "Foto borrosa" in enviados[0][1]
    assert fake.db["expedientes"][0]["estado"] == "pendiente_documentos"

    # Aprobar → listo para el agente y se refleja en solicitudes (franja azul)
    c.post(f"/dashboard/documentos/doc/{doc['id']}/revisar", data={"accion": "aprobar"})
    assert fake.db["expedientes"][0]["estado"] == "documentos_completos"
    assert fake.db["solicitudes"][0]["estado"] == "documentos_completos"
    assert fake.db["expediente_docs"][0]["revisado_por"] == "agente@aural.co"

    # Estado manual
    c.post(f"/dashboard/documentos/{exp['id']}/estado", data={"estado": "agendado", "notas": "Usaquén, jueves 8am"})
    e2 = fake.db["expedientes"][0]
    assert e2["estado"] == "agendado" and e2["notas"] == "Usaquén, jueves 8am"
    assert fake.db["solicitudes"][0]["estado"] == "agendado"

    # Descargar
    r = c.get(f"/dashboard/documentos/doc/{doc['id']}/descargar", follow_redirects=False)
    assert r.status_code == 302 and "download=orden_clinica_1020304050" in r.headers["location"]


def test_orden_vencida(ctx):
    fake, c = ctx
    vieja = (date.today() - timedelta(days=200)).isoformat()
    c.post("/documentos", data=_datos(fecha_orden=vieja), files={"doc_orden_clinica": ("o.png", PNG, "image/png")})
    assert fake.db["expedientes"][0]["estado"] == "orden_vencida"


def test_link_invalido(ctx):
    _, c = ctx
    assert c.get("/documentos/noexiste").status_code == 404
