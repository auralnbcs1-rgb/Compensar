"""Login del /dashboard con Supabase Auth — así cualquiera con acceso a Compensar entra
con su propio correo y clave, y los perfiles se administran directo desde el Supabase de
este proyecto (Authentication → Users), igual que en aural-booking-system, sin tocar
variables de entorno ni redesplegar cada vez que se agrega o se quita a alguien.

No hace falta ninguna credencial nueva en el .env: usa el mismo cliente de Supabase
(SUPABASE_URL/SUPABASE_KEY) que ya tiene el resto del proyecto — Authentication es un
servicio que viene incluido en cualquier proyecto de Supabase, no algo aparte que haya
que contratar o activar.
"""
from dataclasses import dataclass
from typing import Optional

from app.db import get_client

# Nombre de la cookie donde se guarda la sesión del dashboard (el access_token que
# devuelve Supabase Auth al iniciar sesión).
COOKIE_NAME = "aurora_dashboard_session"


@dataclass
class SesionDashboard:
    email: str
    access_token: str


def iniciar_sesion(email: str, password: str) -> Optional[SesionDashboard]:
    """Verifica el correo/clave contra Supabase Auth. None si no son válidos (correo no
    existe, clave incorrecta, usuario no confirmado, etc. — no hace falta distinguir el
    motivo, el login solo vuelve a pedir los datos)."""
    try:
        resp = get_client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return None
    if resp is None or resp.session is None or resp.user is None:
        return None
    return SesionDashboard(email=resp.user.email, access_token=resp.session.access_token)


def validar_token(access_token: str) -> Optional[str]:
    """Si el token de la cookie sigue siendo válido en Supabase Auth, devuelve el correo
    de la persona; None si expiró o no es válido (hay que volver a /login)."""
    if not access_token:
        return None
    try:
        resp = get_client().auth.get_user(access_token)
    except Exception:
        return None
    return resp.user.email if resp and resp.user else None
