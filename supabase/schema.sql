-- Esquema para el proyecto de Supabase PROPIO del bot Compensar.
-- Importante: crea un proyecto de Supabase nuevo y separado del que usa
-- aural-booking-system — este bot no debe compartir base de datos con nada más de Aural.
--
-- Si ya corriste una versión anterior de este archivo, no lo vuelvas a correr entero:
-- usa supabase/migration_001_deriva_a_agente.sql en su lugar (ver ese archivo).
--
-- Cómo usarlo (instalación nueva): Supabase Dashboard → tu proyecto → SQL Editor →
-- pega este archivo completo → Run.

create table if not exists backlog (
    id           bigint generated always as identity primary key,
    cedula       text not null unique,
    nombre       text not null,
    telefono     text not null unique,     -- formato E.164 sin '+', ej: 573001234567
    sede         text not null,
    estado       text not null default 'pendiente'
                 check (estado in ('pendiente', 'contactado', 'requiere_agendamiento', 'no_interesado', 'requiere_humano', 'agendado')),
    intentos     integer not null default 0,
    ultimo_intento timestamptz,
    creado_en    timestamptz not null default now()
);

create index if not exists idx_backlog_estado on backlog (estado);
create index if not exists idx_backlog_telefono on backlog (telefono);

-- El bot nunca agenda una hora específica — "interesado" significa que el paciente
-- quiere la entrega y queda para que un agente de atención al cliente lo llame y
-- confirme día/hora. "agendado" es para cuando el agente marca manualmente que ya
-- cerró la cita (el bot no escribe ese valor).
create table if not exists registro_diario (
    id          bigint generated always as identity primary key,
    fecha       date not null default current_date,
    cedula      text not null,
    nombre      text not null,
    sede        text,       -- sede preferida que mencionó el paciente, si aplica
    hora_cita   text,       -- lo llena el agente humano cuando cierra la cita, no el bot
    resultado   text not null
                check (resultado in ('interesado', 'no_interesado', 'requiere_humano', 'agendado')),
    canal       text not null default 'bot_whatsapp_compensar',
    creado_en   timestamptz not null default now()
);

create index if not exists idx_registro_fecha on registro_diario (fecha);
create index if not exists idx_registro_resultado on registro_diario (resultado);

-- Vistas de conveniencia para el dashboard.
create or replace view v_interesados_por_dia as
select fecha, count(*) as total_interesados
from registro_diario
where resultado = 'interesado'
group by fecha
order by fecha;

create or replace view v_agendados_por_dia as
select fecha, count(*) as total_agendados
from registro_diario
where resultado = 'agendado'
group by fecha
order by fecha;

-- Row Level Security: el bot accede con la service role key (bypassa RLS), así que
-- se puede dejar RLS activo y sin políticas para bloquear cualquier acceso con la
-- clave pública (anon key) por si esa clave se llegara a exponer.
alter table backlog enable row level security;
alter table registro_diario enable row level security;
