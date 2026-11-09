# Formulario de documentos + panel de gestión — cómo integrarlo en Aurora

Qué agrega:

- **`/documentos`**: formulario público. El paciente llena cédula, nombre, celular, correo y trámite, y sube sus documentos (foto o PDF, máx. 10 MB).
- **`/documentos/{token}`**: link personal que manda Aurora por WhatsApp. Ya sabe quién es el paciente, le muestra qué documentos recibió, cuáles faltan y cuáles fueron rechazados (con el motivo), y le deja subir solo eso.
- **`/dashboard/documentos`**: panel para los agentes, con el mismo login de Supabase. Tiene conteo por estado, búsqueda por nombre, cédula o teléfono, filtros por trámite, estado y fechas, y un detalle por paciente donde se puede ver, descargar, aprobar o rechazar cada documento (con aviso opcional por WhatsApp), cambiar el estado y dejar notas.
- **Un solo expediente por paciente y trámite.** Lo que llega por la web y lo que llega por WhatsApp queda junto, en el mismo bucket `documentos-pacientes`. Aurora puede consultar qué ya se recibió para no volver a pedirlo.

## Archivos

| Archivo | Qué es |
|---|---|
| `app/expedientes.py` | Capa de datos y funciones que usa Aurora (nuevo) |
| `app/formulario.py` | Rutas y páginas del formulario y del panel (nuevo) |
| `supabase/migration_005_formulario_documentos.sql` | Tablas `expedientes` y `expediente_docs` (nuevo) |
| `tests/test_formulario.py` | 8 pruebas con un Supabase falso (nuevo) |

Copia las cuatro rutas tal cual dentro del repo `compensar-bot-aurora`. No reemplazan ningún archivo existente.

## Paso 1 — Base de datos

En Supabase → **SQL Editor**, pega y corre `migration_005_formulario_documentos.sql`. Crea las dos tablas con RLS activado: solo el backend las puede leer y escribir.

No hace falta un bucket nuevo. Los archivos van al mismo `documentos-pacientes`, bajo la carpeta `formulario/`.

## Paso 2 — `main.py` (2 líneas)

Junto a los demás imports:

```python
from app.formulario import router as formulario_router
```

Después de crear `app = FastAPI(...)`:

```python
app.include_router(formulario_router)
```

## Paso 3 — Variables en Railway

| Variable | Valor |
|---|---|
| `PUBLIC_BASE_URL` | El dominio público de Aurora en Railway, sin `/` al final. Ej.: `https://aurora-compensar.up.railway.app` |
| `ORDEN_VIGENCIA_DIAS` | Ya la tienes (90 por defecto). Se usa la misma. |
| `EXPEDIENTES_SYNC_SOLICITUDES` | Opcional. `1` (por defecto) refleja el estado en `solicitudes`, así quien completa por la web aparece en la franja azul del `/dashboard`. `0` lo apaga. |

`app/expedientes.py` se conecta a Supabase con `SUPABASE_URL` y la service key. Busca, en este orden, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SERVICE_KEY` y `SUPABASE_KEY`. Si en Railway la tienes con otro nombre, hay dos opciones: crear una de esas variables con el mismo valor, o agregar esta línea en `main.py`:

```python
from app import expedientes
expedientes.set_client(<el cliente de Supabase que ya crea app/db.py>)
```

## Paso 4 — Dependencia

Verifica que `requirements.txt` tenga `python-multipart`. Lo necesita FastAPI para recibir archivos y probablemente ya está, porque el panel de chats sube imágenes.

## Paso 5 — Enlace en el menú del dashboard

En `app/dashboard.py`, donde están los enlaces del encabezado ("Resumen" y "Chats"), agrega:

```html
<a href="/dashboard/documentos">Documentos</a>
```

## Paso 6 — Conectar a Aurora (3 puntos en el flujo)

```python
from app import expedientes
tramite = expedientes.tramite_desde_menu(opcion_del_menu)   # 1–5 → "evaluacion_adaptacion", etc.
```

**a) Cuando Aurora pide los documentos**, agrega el link personal al mensaje:

```python
link = expedientes.link_personal(telefono, tramite, cedula=cedula, nombre=nombre)
texto += f"\n\nSi te queda más fácil, también puedes subirlos aquí: {link}"
```

**b) Cuando Aurora guarda un documento que llegó por WhatsApp** (después de clasificarlo con vision y subirlo al bucket), regístralo también en el expediente:

```python
expedientes.registrar_documento_whatsapp(
    telefono, tramite,
    tipo,                  # "orden_clinica" | "autorizacion" | "cedula" | "otro"
    storage_path,          # la ruta que ya usó en el bucket
    mime="image/jpeg",
    fecha_expedicion=fecha_orden_iso_o_None,   # solo para la orden clínica, "AAAA-MM-DD"
    validado_por_aurora=True,                  # True si vision lo leyó con confianza
)
```

Si vision devuelve otros nombres para el tipo, tradúcelos a esos cuatro. Cualquier tipo desconocido queda como `otro`.

Esta función nunca rompe el flujo. Si algo falla, lo deja en el log y sigue.

**c) Antes de pedir documentos o de decir cuáles faltan**, consulta lo que ya llegó por cualquier canal:

```python
faltan = expedientes.faltantes(telefono, tramite)   # ej. ["autorizacion", "cedula"]
```

Así, si el paciente ya subió la orden por la web, Aurora no se la vuelve a pedir por WhatsApp.

## Cómo funcionan los estados

| Estado | Cuándo |
|---|---|
| Faltan documentos | Falta algún documento requerido, o alguno fue rechazado |
| En revisión | Están todos, pero falta que un agente apruebe alguno (o la orden no tiene fecha) |
| Listo para el agente | Todos aprobados y la orden vigente. Aparece en la franja azul del `/dashboard` |
| Orden vencida | La fecha de expedición supera `ORDEN_VIGENCIA_DIAS` |
| Requiere agente / Agendado | Solo los pone un agente a mano, y el sistema no los cambia solo |

Los documentos que suben los pacientes por la web entran como **Por revisar**. Los que Aurora valida con vision pueden entrar **Aprobados** (`validado_por_aurora=True`).

## Cosas a tener en cuenta

- **Aviso de rechazo por WhatsApp.** Usa la función de envío de texto de `app/whatsapp_client.py` (intenta `send_text`, `send_message`, `enviar_texto` o `enviar_mensaje`). Si la ventana de 24 horas está cerrada, WhatsApp no lo entrega y el panel te avisa para que le escribas con una plantilla desde Chats.
- **Texto de tratamiento de datos.** El formulario pide autorización con base en la Ley 1581 de 2012. Confirma con Compensar si quieren su propio texto o un enlace a su política de privacidad. Está en `_form_publico()` dentro de `app/formulario.py`.
- **Cómo llegan los pacientes al formulario.** El link general `/documentos` se puede copiar desde el panel. Sirve para el perfil de WhatsApp, correos de Compensar, un QR en las sedes, etc.
- **Búsqueda.** El panel filtra en el servidor los últimos 1.000 expedientes. Si algún día pasan de ese número, se mueve la búsqueda a la consulta de Supabase.

## Probar

Desde la raíz del repo:

```bash
pip install pytest httpx
python -m pytest tests/test_formulario.py -q
```

Las 8 pruebas cubren:

- Formulario público y sus validaciones.
- Reutilización del expediente del mismo paciente.
- Link personal con documentos llegados por WhatsApp y por la web.
- Aprobar, rechazar y avisar.
- Cambio de estado manual.
- Sincronización con `solicitudes`.
- Orden vencida y link inválido.
