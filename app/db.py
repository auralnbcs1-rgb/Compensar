"""Cliente único de Supabase, compartido por backlog.py, registro.py y el dashboard.

Usa la service role key (nunca la anon key) porque el bot corre server-side y necesita
poder leer/escribir sin las restricciones de Row Level Security. Por eso SUPABASE_KEY
nunca debe exponerse al navegador ni subirse a un repo público — vive solo en el .env
del servidor.
"""
from functools import lru_cache

from supabase import create_client, Client

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Faltan SUPABASE_URL / SUPABASE_KEY en el .env — crea el proyecto de Supabase "
            "propio del bot y copia sus credenciales (ver README)."
        )
    return create_client(settings.supabase_url, settings.supabase_key)
