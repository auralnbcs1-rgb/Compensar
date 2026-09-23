-- Migración: el bot ya no agenda una fecha/hora específica — solo confirma interés
-- y deja al paciente en la cola de un agente de atención al cliente, que agenda por
-- fuera del bot. Corre esto UNA VEZ si ya habías creado las tablas con la versión
-- anterior de schema.sql (si es una instalación nueva, usa schema.sql directamente
-- y no esta migración).
--
-- Cómo usarlo: Supabase Dashboard → tu proyecto → SQL Editor → pega este archivo
-- completo → Run.

-- backlog.estado: agrega 'requiere_agendamiento' a los valores permitidos.
alter table backlog drop constraint if exists backlog_estado_check;
alter table backlog add constraint backlog_estado_check
    check (estado in ('pendiente', 'contactado', 'requiere_agendamiento', 'no_interesado', 'requiere_humano', 'agendado'));

-- registro_diario.resultado: 'interesado' reemplaza a 'sin_respuesta' y 'reagendar_pendiente'
-- como el resultado normal del bot; 'agendado' se conserva por si el agente lo marca a mano.
alter table registro_diario drop constraint if exists registro_diario_resultado_check;
alter table registro_diario add constraint registro_diario_resultado_check
    check (resultado in ('interesado', 'no_interesado', 'requiere_humano', 'agendado'));

-- Vista nueva para el dashboard: cuántos pacientes confirmaron interés cada día
-- (quedan en la cola del agente), separado de los que el agente ya marcó "agendado".
create or replace view v_interesados_por_dia as
select fecha, count(*) as total_interesados
from registro_diario
where resultado = 'interesado'
group by fecha
order by fecha;
