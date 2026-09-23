-- Migración: Aurora — menú de 5 servicios de Compensar-Widex Colombia S.A.S. con
-- recolección de documentos (orden clínica, autorización de servicio, cédula).
-- Corre esto UNA VEZ, después de schema.sql y migration_001_deriva_a_agente.sql.
--
-- Cómo usarlo: Supabase Dashboard → tu proyecto → SQL Editor → pega este archivo
-- completo → Run. Luego crea el bucket de Storage "documentos-pacientes" (ver nota
-- al final) desde Storage → New bucket, privado (no público).

-- Una solicitud = un trámite de un paciente para uno de los 5 servicios. Es
-- independiente de `backlog` (que sigue siendo solo para la entrega de audífonos
-- del backlog PENDIENTES de Compensar).
create table if not exists solicitudes (
    id              bigint generated always as identity primary key,
    cedula          text not null,
    nombre          text not null,
    telefono        text not null,
    servicio        text not null
                    check (servicio in (
                        'evaluacion_adaptacion',   -- 1. Evaluación y adaptación de prótesis y ayudas auditivas *
                        'prueba_audifono',         -- 2. Prueba de Audífono
                        'evaluacion_tinnitus',     -- 3. Evaluación Tinnitus *
                        'control',                 -- 4. Control (1er control 30 días posterior a la adaptación)
                        'terapia_tinnitus'         -- 5. Terapia Tinnitus *
                    )),
    -- true para los servicios marcados con * (necesitan orden + autorización + cédula);
    -- false para los que solo necesitan orden vigente (prueba_audifono, control).
    requiere_autorizacion boolean not null,
    -- Datos adicionales del paciente que Aurora recolecta por chat antes de pedir los
    -- documentos (ver migration_003_datos_paciente.sql si ya habías corrido este
    -- archivo antes de que se agregaran estas columnas).
    fecha_nacimiento date,
    direccion       text default '',
    regimen         text default '',   -- contributivo / subsidiado / especial / exceptuado
    telefono_2      text default '',   -- segundo número de contacto (distinto del de WhatsApp)
    correo          text default '',
    estado          text not null default 'pendiente_documentos'
                    check (estado in (
                        'pendiente_documentos',   -- esperando que el paciente mande los documentos
                        'documentos_completos',   -- todo lo requerido llegó y la orden se ve vigente — LISTO PARA EL AGENTE
                        'orden_vencida',           -- la orden que mandó ya no está vigente, hay que pedirle una nueva
                        'requiere_humano',         -- documento ilegible, dudoso, o cualquier caso que no pudo resolver el bot
                        'agendado'                 -- el agente ya marcó que cerró la cita (uso manual, el bot no escribe esto)
                    )),
    creado_en       timestamptz not null default now(),
    actualizado_en  timestamptz not null default now()
);

create index if not exists idx_solicitudes_estado on solicitudes (estado);
create index if not exists idx_solicitudes_telefono on solicitudes (telefono);

-- Un documento = una imagen que mandó el paciente para una solicitud.
create table if not exists documentos (
    id              bigint generated always as identity primary key,
    solicitud_id    bigint not null references solicitudes (id) on delete cascade,
    tipo            text not null
                    check (tipo in ('orden_clinica', 'autorizacion_servicio', 'cedula', 'sin_clasificar')),
    storage_path    text not null,   -- ruta dentro del bucket "documentos-pacientes"
    fecha_detectada date,             -- fecha que Claude leyó en la orden clínica, si aplica
    vigente         boolean,          -- true/false si es una orden y se pudo evaluar; null si no aplica o no se pudo leer
    nota_ia         text,             -- lo que Claude entendió/observó del documento, para que el agente lo revise
    creado_en       timestamptz not null default now()
);

create index if not exists idx_documentos_solicitud on documentos (solicitud_id);

alter table solicitudes enable row level security;
alter table documentos enable row level security;

-- NOTA sobre el bucket de Storage (esto se hace desde la interfaz de Supabase, no con SQL):
-- Storage → New bucket → nombre "documentos-pacientes" → Public bucket: NO (privado).
-- El bot sube y lee con la service role key, que no respeta las políticas de RLS del
-- bucket, así que no hace falta configurar políticas para que el bot funcione — pero
-- mantenlo privado para que nadie más pueda leer las fotos de cédulas/órdenes por su URL.
