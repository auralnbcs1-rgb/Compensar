# Aurora — Compensar / Widex Colombia S.A.S.

Bot de WhatsApp, **independiente**, para Compensar - Widex Colombia S.A.S. **Flujo inbound: el
paciente escribe primero** (no el bot) — igual que Amanda, pero para un objetivo distinto. En el
primer mensaje, Aurora muestra un menú con los 5 trámites del convenio y, según cuál elija el
paciente, recolecta los documentos que ese trámite necesita (orden clínica y, para algunos
trámites, también autorización de servicio y cédula), los clasifica y valida la vigencia de la
orden con Claude (vision). El bot **no agenda una fecha/hora**: cuando los documentos están
completos, deja al paciente listo para que un *agente de atención al cliente* lo contacte y cierre
el día y la hora exactos. Mismo motor conversacional (Claude + Python), sin compartir servidor,
base de datos ni credenciales con Amanda ni con ningún otro sistema de Aural — número propio,
Supabase propio, API key de Anthropic propia.

Incluye un dashboard web (`/dashboard`) con las confirmaciones del día/mes vs. una meta diaria, la
proyección de cuándo se vacía el backlog de entrega de audífonos, y una franja azul con las
solicitudes que ya tienen todos los documentos y están listas para el agente (ver la nota sobre
etiquetas de WhatsApp más abajo). El documento de arquitectura completo (con diagrama de flujo)
está en el proyecto "Compensar".

## El menú de Aurora

Primer mensaje que ve cualquier paciente que escribe:

1. Evaluación y adaptación de prótesis y ayudas auditivas *
2. Prueba de Audífono
3. Evaluación Tinnitus *
4. Control (1er control 30 días posterior a la adaptación)
5. Terapia Tinnitus *

Las opciones marcadas con **\*** necesitan **orden clínica + autorización de servicio + cédula**;
las demás solo necesitan la **orden clínica vigente**. Aurora interpreta la respuesta del paciente
(número exacto, palabra clave, o texto libre vía Claude si hace falta), y una vez identifica el
trámite pide la cédula (si el teléfono no coincide ya con el backlog de entrega de audífonos).

### Datos que pide antes de los documentos

Con la cédula y el nombre ya resueltos, Aurora pide uno por uno (con preguntas fijas, no las redacta
Claude, para que sean siempre exactas y con la validación puesta):

- Fecha de nacimiento
- Dirección de residencia
- Régimen de salud (contributivo / subsidiado / especial / exceptuado)
- Un segundo número de teléfono de contacto
- Correo electrónico

Si una respuesta no pasa la validación (una fecha que no se puede leer, un correo sin `@`, etc.), el
bot vuelve a preguntar ese mismo campo con un mensaje de error puntual — nunca avanza con un dato mal
formado. La excepción es el régimen: si el paciente no usa ninguna de las palabras esperadas, Aurora
igual guarda lo que escribió (no vale la pena bloquear el flujo por eso) para que un agente lo revise
si hace falta. Estos campos viven en `app/datos_paciente.py` — ahí se agregan, quitan o ajustan.

Con eso resuelto, pide los documentos del trámite.

### Vigencia de la orden clínica

Claude (vision) intenta leer la fecha de expedición de la orden clínica y la compara contra
`ORDEN_VIGENCIA_DIAS` (90 días por defecto en `.env.example`) para decidir si sigue vigente. **Este
número de días es un valor por defecto — Compensar debe confirmar cuál es la vigencia real que
aplica**, y se ajusta cambiando esa variable de entorno. Si Claude no logra leer la fecha con
confianza, no asume nada: el documento queda registrado para que un agente humano lo revise.

### Documentos "en otro color" — nota importante sobre WhatsApp

El pedido original era que, al completarse los documentos de un paciente, esa conversación
cambiara de color con las **etiquetas nativas de WhatsApp Business** (las de Meta Business Suite).
**Investigamos y confirmamos que WhatsApp Cloud API no tiene ningún endpoint para que un bot
asigne esas etiquetas automáticamente** — son manuales, solo se pueden poner a mano desde la app o
Meta Business Suite, no desde programación. No es una limitación de este proyecto: es una
restricción de la plataforma de WhatsApp.

Como alternativa **que sí es técnicamente posible hoy**, el dashboard (`/dashboard`) tiene una
franja azul — "Listos para el agente" — con cada paciente en cuanto Aurora recibe todo lo que
hace falta. Es el mismo efecto práctico (saber al instante quién ya está listo) sin depender de
algo que la API de WhatsApp no permite automatizar.

## Panel de chats — leer y contestar cada conversación (`/dashboard/chats`)

Además del panel de estadísticas, `/dashboard/chats` es una bandeja de conversaciones como la de
Amanda: lista cada chat (nombre o número, buscable), y al entrar a uno se ve el historial completo
— lo que escribió el paciente, lo que contestó Aurora, y lo que escribió un agente — con una caja
para escribir texto y mandar/ver imágenes directamente ahí.

En cuanto un agente manda algo desde ese panel, **el chat queda "a su cargo"**: Aurora deja de
contestar sola en esa conversación (para que las dos no le hablen al paciente al mismo tiempo)
hasta que alguien le dé a "Reactivar Aurora". El resto de conversaciones sigue funcionando normal.

No hace falta crear ningún bucket nuevo en Supabase para esto — las imágenes del chat se guardan en
el mismo bucket privado `documentos-pacientes` que ya usan los documentos del trámite, bajo su
propio prefijo. Sí hace falta correr `supabase/migration_004_conversaciones.sql` (ver "Puesta en
marcha" abajo) — crea las tablas `conversaciones` y `mensajes` donde vive este historial.

## Cómo identifica al paciente

Como el paciente escribe primero, puede hacerlo desde el número que tenemos guardado en el backlog
de entrega de audífonos o desde otro (WhatsApp de un familiar, número nuevo, etc.):

1. Si el teléfono que escribe coincide con `backlog.telefono` → se identifica directo, sin pedirle
   cédula ni nombre.
2. Si no coincide y ya sabemos qué trámite quiere → el bot pide la cédula; si coincide con
   `backlog.cedula` toma el nombre de ahí, si no, pregunta el nombre completo.

## Qué hace y qué no hace el bot

Aurora: muestra el menú de trámites, identifica al paciente, pide y clasifica los documentos que
cada trámite necesita, valida la vigencia de la orden clínica, informa las sedes y el horario
general (fijos: **Usaquén y Javeriana**, lunes a jueves 7:30am–5:00pm, viernes 7:30am–4:30pm), y
avisa que un agente humano se va a comunicar quien tiene todo completo.

El bot **no** ofrece horas específicas ni confirma una cita — eso lo hace siempre un agente humano
por fuera del bot (llamada o el mismo chat). Cada solicitud (tabla `solicitudes`) queda en uno de
estos estados: `pendiente_documentos`, `documentos_completos` (franja azul — lista para el agente),
`orden_vencida`, `requiere_humano`, o `agendado` (marcado a mano por el agente). Para el trámite
específico de "Evaluación y adaptación de prótesis y ayudas auditivas", si el paciente está en el
backlog de entrega de audífonos de Compensar, al completarse los documentos también se refleja ahí
(`registro_diario` + `backlog.estado`), para que la meta de 70/día del backlog original la siga
contando.

## Estructura

```
compensar-bot/
├── app/
│   ├── main.py            # Webhook de WhatsApp (menú, documentos, imágenes) + /dashboard
│   ├── claude_client.py   # Conversación con Claude durante la recolección de documentos
│   ├── vision_client.py   # Clasificación de documentos + vigencia de la orden, con Claude vision
│   ├── menu_matcher.py    # Interpreta la respuesta del paciente al menú (número/palabra clave)
│   ├── datos_paciente.py  # Campos + validaciones: fecha nacimiento, dirección, régimen, teléfono 2, correo
│   ├── mensajes.py        # Textos fijos: menú, documentos requeridos, sedes/horario
│   ├── whatsapp_client.py # Envío de mensajes + descarga de imágenes vía WhatsApp Cloud API
│   ├── db.py               # Cliente único de Supabase
│   ├── backlog.py         # Capa de datos del backlog de entrega de audífonos (tabla `backlog`)
│   ├── solicitudes.py     # Capa de datos de los 5 trámites de Aurora (tabla `solicitudes`)
│   ├── documentos.py      # Capa de datos + Storage de los documentos (tabla `documentos`)
│   ├── conversaciones.py  # Historial de cada chat + control de pausa (tablas `conversaciones`/`mensajes`)
│   ├── chat_media.py      # Sube/firma las imágenes del panel de chats (mismo bucket que documentos.py)
│   ├── registro.py        # Escribe resultados en `registro_diario` (Supabase)
│   ├── stats.py            # Cálculos del dashboard (confirmaciones, ritmo, proyección, solicitudes)
│   ├── dashboard.py        # HTML + SVG del dashboard y del panel de chats (sin dependencias externas)
│   ├── session_store.py   # Historial de conversación + alta de solicitud en curso
│   ├── config.py           # Variables de entorno
│   └── system_prompt.md   # Prompt de Aurora durante la recolección de documentos
├── supabase/
│   ├── schema.sql                            # Esquema completo — instalación nueva
│   ├── migration_001_deriva_a_agente.sql     # El bot no agenda hora, solo confirma interés
│   ├── migration_002_aurora_servicios.sql    # Tablas `solicitudes` y `documentos` + bucket de Storage
│   ├── migration_003_datos_paciente.sql      # Columnas de datos del paciente (solo si ya corriste migration_002 antes)
│   └── migration_004_conversaciones.sql      # Tablas `conversaciones`/`mensajes` — panel de chats (/dashboard/chats)
├── data/
│   └── backlog_sample.csv # Ejemplo de estructura para importar el backlog
├── scripts/
│   ├── import_backlog_csv.py  # Migración única de un CSV (ej. PENDIENTES exportado) a Supabase
│   └── send_daily_batch.py    # OPCIONAL — recordatorio proactivo, no hace falta para operar
├── requirements.txt
├── Procfile             # Comando de arranque para Railway (o cualquier host tipo Heroku/Nixpacks)
├── .gitignore           # Evita subir .env, venv/ y __pycache__/ al repositorio
└── .env.example
```

## Puesta en marcha

1. **Crea el proyecto de Supabase propio** (en supabase.com, separado del que usa
   aural-booking-system). En su SQL Editor corre, en este orden:
   - `supabase/schema.sql` completo si es instalación nueva (si ya lo corriste antes, sáltalo).
   - `supabase/migration_001_deriva_a_agente.sql` si venías de una versión anterior del esquema.
   - `supabase/migration_002_aurora_servicios.sql` — crea `solicitudes` y `documentos` (corre esto
     una sola vez, sin importar si es instalación nueva o no).
   - `supabase/migration_003_datos_paciente.sql` — **solo si ya habías corrido migration_002 antes**
     de que se agregaran las columnas de fecha de nacimiento/dirección/régimen/teléfono 2/correo (si
     vas a correr migration_002 por primera vez, ya las trae incluidas).
   - `supabase/migration_004_conversaciones.sql` — crea `conversaciones` y `mensajes`, el historial
     que usa el panel `/dashboard/chats` (corre esto una sola vez, sin importar si es instalación
     nueva o no).
   - Luego, desde **Storage → New bucket**, crea el bucket **`documentos-pacientes`** como
     **privado** (Public bucket: NO) — ahí se guardan las fotos de las órdenes/cédulas, y también
     las imágenes del panel de chats (bajo su propio prefijo `chat/...`, no hace falta otro bucket).
   Copia la *Project URL* y la *service role key* (Project Settings → API).
2. `python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` y completa las credenciales — WhatsApp (número nuevo, ver abajo),
   Anthropic, Supabase, y revisa `ORDEN_VIGENCIA_DIAS` con Compensar (90 días es solo un valor
   de partida). El dashboard **no** necesita variables propias — su login usa Supabase Auth
   (ver el paso 8 y la sección de abajo).
5. Migra el backlog actual de entrega de audífonos: exporta la pestaña PENDIENTES a CSV con
   columnas `cedula,nombre,telefono,sede` y corre
   `python scripts/import_backlog_csv.py ese_archivo.csv`
6. Levanta el servidor: `uvicorn app.main:app --reload --port 8000`
7. Expón el puerto públicamente (por ejemplo con `ngrok http 8000` mientras pruebas) y registra
   esa URL + el `WHATSAPP_VERIFY_TOKEN` como webhook en Meta Business Suite — pide permisos de
   mensajes de **texto e imagen**.
8. Crea al menos un usuario para entrar al dashboard (ver abajo) y entra a
   `https://tu-dominio/login`.

### Quién puede entrar al dashboard (Supabase Auth)

El login del dashboard (`/login`) verifica correo y clave contra **Supabase Auth** — el mismo
proyecto de Supabase de este bot, no uno aparte. Los perfiles se crean y se borran ahí, no con
variables de entorno:

1. En tu proyecto de Supabase, ve a **Authentication → Users → Add user**.
2. Escribe el correo y la clave de la persona.
3. Marca **"Auto Confirm User"** al crearlo — si no, Supabase le manda un correo de
   confirmación y la persona no puede entrar hasta darle clic al link.

Para agregar o quitar a alguien más adelante, entras a esa misma pantalla — no hay que tocar
Railway ni redesplegar nada. Cada sesión del dashboard dura 8 horas; después de eso, o si la
persona entra a `/logout`, tiene que volver a iniciar sesión.

Como el flujo es inbound, **no necesitas una plantilla aprobada por Meta para arrancar** — basta
con que el número nuevo esté dado de alta y el webhook conectado. La plantilla
(`send_daily_batch.py`) queda solo como opción a futuro si algún día quieres recordarle a quien
todavía no ha escrito.

Si cambian las sedes o el horario, se editan directo en `app/mensajes.py` (sedes/horario) y
`app/system_prompt.md` (para que Claude conteste igual si el paciente pregunta).

## Desplegar en Railway (producción)

El proyecto ya trae lo necesario para desplegarse en [Railway](https://railway.com) tal cual:
`Procfile` (le dice a Railway cómo arrancar el servidor) y `.gitignore` (para no subir `.env` ni
`venv/` al repositorio). Pasos:

1. **Sube la carpeta `compensar-bot` a un repositorio de GitHub** (puede ser privado). Importante:
   el repositorio debe tener `requirements.txt` y `Procfile` en su raíz — si subes esta carpeta tal
   cual, ya queda así.
   ```
   cd compensar-bot
   git init
   git add .
   git commit -m "Aurora - bot Compensar"
   ```
   Luego crea el repositorio vacío en GitHub y sigue las instrucciones que te da para conectarlo y
   hacer el primer `git push` (o usa GitHub Desktop si prefieres no usar la terminal).
2. **Crea una cuenta en [railway.com](https://railway.com)** (puedes entrar con tu cuenta de
   GitHub) y arranca un **proyecto nuevo** — uno propio, no dentro del proyecto donde esté Amanda si
   la tienes ahí, para mantener todo independiente.
3. **New Project → Deploy from GitHub repo** → elige el repositorio que acabas de crear. Railway
   detecta automáticamente que es una app de Python y usa el `Procfile` para arrancarla — no
   necesitas configurar nada más ahí.
4. **Variables de entorno**: en el servicio que se creó, ve a la pestaña **Variables** y agrega ahí,
   una por una (o pegando el archivo completo con el botón "Raw Editor"), todas las que están en
   `.env.example` con tus valores reales — WhatsApp, Anthropic, Supabase, etc. (el dashboard no
   necesita variable propia; sus usuarios se crean en Supabase, ver la sección de arriba).
5. **Genera el dominio público**: en la pestaña **Settings** del servicio, busca **Networking** →
   **Generate Domain**. Te da una URL tipo `https://tu-app.up.railway.app` — esa es la que vas a
   registrar en Meta Business Suite como webhook (agregándole `/webhook` al final), y donde vas a
   entrar para ver `/dashboard`.
6. **Deja el servicio en 1 réplica** (es lo normal por defecto, no lo subas): como el bot guarda el
   historial de conversación en memoria, con más de una réplica cada una tendría su propia memoria y
   el bot se confundiría entre conversaciones.
7. Railway construye y despliega solo. Cuando termine, entra a
   `https://tu-app.up.railway.app/login` con el correo/clave que creaste en Supabase Authentication.
8. Cada vez que quieras actualizar el bot más adelante, basta con hacer `git push` de los cambios —
   Railway vuelve a desplegar automáticamente.

## Lo que falta antes de producción

Esto es un scaffold funcional, no un sistema listo para producción. Antes de usarlo con pacientes
reales falta, como mínimo:

- Número de WhatsApp nuevo dado de alta en un WABA propio (no el de Amanda) y conectado al webhook
- Hospedaje propio (servidor independiente del de Amanda), con HTTPS
- Bucket `documentos-pacientes` creado en Supabase Storage (paso 1 de arriba)
- Confirmar con Compensar el valor real de `ORDEN_VIGENCIA_DIAS`
- Definir cómo se entera el paciente de que debe escribirle a este número (folleto, mensaje de un
  asesor, etc.)
- Definir cómo ve el agente de atención al cliente su cola de trabajo — hoy es la franja azul del
  `/dashboard` ("Listos para el agente") más las filas de Supabase (`solicitudes` donde
  `estado = 'documentos_completos'`, y `backlog` donde `estado = 'requiere_agendamiento'` para el
  caso de entrega de audífonos) — se pueden ver directo en el Table Editor de Supabase mientras no
  haya una vista dedicada
- Revisar con un caso real que Claude vision clasifica bien los documentos típicos de Compensar
  (fotos con mala luz, celulares distintos, etc.) antes de confiar el flujo completo a la IA
- Migración `supabase/migration_004_conversaciones.sql` corrida (panel de chats, `/dashboard/chats`)
- Probar con un lote pequeño antes de escalar

El documento "Bot Compensar por WhatsApp" (en el proyecto Compensar) tiene el detalle completo de
la arquitectura y el checklist actualizado.
