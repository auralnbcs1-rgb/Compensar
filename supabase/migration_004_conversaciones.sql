-- Panel de "Chats" del dashboard: bandeja de conversaciones + historial completo de
-- cada una (lo que escribe el paciente, lo que contesta Aurora, y lo que escribe un
-- agente humano desde el panel). Sin esto, el historial de cada chat solo vivía en
-- memoria del proceso (session_store.py) y se perdía al reiniciar, y no había forma de
-- saber si un agente humano "tomó el control" de una conversación.
--
-- No hace falta crear ningún bucket nuevo en Supabase Storage: las imágenes del chat
-- se guardan en el mismo bucket privado que ya usan los documentos del trámite
-- (SUPABASE_STORAGE_BUCKET, por defecto "documentos-pacientes"), bajo su propio
-- prefijo ("chat/..."), para no duplicar configuración.

create table if not exists conversaciones (
  telefono text primary key,
  nombre text not null default '',
  pausada boolean not null default false,
  pausada_por text,
  pausada_en timestamptz,
  ultimo_mensaje_en timestamptz not null default now(),
  ultimo_mensaje_extracto text not null default ''
);

create table if not exists mensajes (
  id bigint generated always as identity primary key,
  telefono text not null references conversaciones (telefono),
  direccion text not null check (direccion in ('entrante', 'saliente')),
  tipo text not null check (tipo in ('texto', 'imagen')),
  contenido text not null default '',
  storage_path text,
  enviado_por text not null default '',  -- 'paciente' | 'aurora' | correo del agente
  creado_en timestamptz not null default now()
);

create index if not exists mensajes_telefono_creado_idx on mensajes (telefono, creado_en);
