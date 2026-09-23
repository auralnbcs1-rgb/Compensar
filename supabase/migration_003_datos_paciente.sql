-- Migración: datos adicionales del paciente que Aurora ahora recolecta por chat antes
-- de pedir los documentos — fecha de nacimiento, dirección de residencia, régimen de
-- salud, un segundo teléfono de contacto, y correo electrónico.
--
-- Corre esto SOLO SI ya habías corrido migration_002_aurora_servicios.sql antes de que
-- se agregaran estas columnas (si vas a correr migration_002 por primera vez, ya las
-- trae incluidas y no hace falta este archivo).
--
-- Cómo usarlo: Supabase Dashboard → tu proyecto → SQL Editor → pega este archivo
-- completo → Run.

alter table solicitudes add column if not exists fecha_nacimiento date;
alter table solicitudes add column if not exists direccion text default '';
alter table solicitudes add column if not exists regimen text default '';
alter table solicitudes add column if not exists telefono_2 text default '';
alter table solicitudes add column if not exists correo text default '';
