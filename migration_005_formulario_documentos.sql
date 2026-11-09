-- migration_005_formulario_documentos.sql
-- Formulario web de documentos + panel de gestión.
-- Crea un "expediente" por paciente y trámite, y una tabla única de documentos
-- donde quedan juntos los que llegan por el formulario web y los que llegan por WhatsApp (Aurora).
-- Correr una sola vez en Supabase → SQL Editor.

create extension if not exists pgcrypto;

create table if not exists expedientes (
    id              uuid primary key default gen_random_uuid(),
    token           text not null unique,              -- link personal /documentos/{token}
    origen          text not null default 'formulario', -- formulario | whatsapp
    telefono        text,                               -- formato 57XXXXXXXXXX (igual que WhatsApp)
    cedula          text,
    nombre          text,
    correo          text,
    tramite         text not null,                      -- ver TRAMITES en app/expedientes.py
    estado          text not null default 'pendiente_documentos',
                    -- pendiente_documentos | en_revision | documentos_completos
                    -- | orden_vencida | requiere_humano | agendado
    notas           text,
    actualizado_por text,
    creado_en       timestamptz not null default now(),
    actualizado_en  timestamptz not null default now()
);

create index if not exists expedientes_telefono_idx on expedientes (telefono);
create index if not exists expedientes_cedula_idx   on expedientes (cedula);
create index if not exists expedientes_estado_idx   on expedientes (estado);
create index if not exists expedientes_creado_idx   on expedientes (creado_en desc);

create table if not exists expediente_docs (
    id               uuid primary key default gen_random_uuid(),
    expediente_id    uuid not null references expedientes(id) on delete cascade,
    tipo             text not null,      -- orden_clinica | autorizacion | cedula | otro
    canal            text not null,      -- formulario | whatsapp
    storage_path     text not null,      -- ruta dentro del bucket documentos-pacientes
    nombre_archivo   text,
    mime             text,
    tamano           integer,
    fecha_expedicion date,               -- solo orden clínica
    estado_revision  text not null default 'pendiente',  -- pendiente | aprobado | rechazado
    motivo_rechazo   text,
    revisado_por     text,
    revisado_en      timestamptz,
    creado_en        timestamptz not null default now()
);

create index if not exists expediente_docs_exp_idx on expediente_docs (expediente_id);

-- Solo el backend (service role) toca estas tablas. Con RLS activo y sin políticas,
-- nadie con la anon key puede leerlas ni escribirlas.
alter table expedientes     enable row level security;
alter table expediente_docs enable row level security;
