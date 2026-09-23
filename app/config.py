"""Carga de configuración desde variables de entorno (.env)."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # WhatsApp Cloud API
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_business_account_id: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    whatsapp_template_name: str = os.getenv("WHATSAPP_TEMPLATE_NAME", "compensar_recordatorio_entrega")
    whatsapp_template_lang: str = os.getenv("WHATSAPP_TEMPLATE_LANG", "es_CO")

    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    # Supabase (proyecto PROPIO de este bot — no el de aural-booking-system)
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")  # service role key, nunca la anon key

    # Metas de agendamiento
    daily_batch_size: int = int(os.getenv("DAILY_BATCH_SIZE", "70"))
    daily_goal: int = int(os.getenv("DAILY_GOAL", "70"))

    # Aurora: documentos (Supabase Storage) y vigencia de la orden clínica
    storage_bucket_documentos: str = os.getenv("SUPABASE_STORAGE_BUCKET", "documentos-pacientes")
    orden_vigencia_dias: int = int(os.getenv("ORDEN_VIGENCIA_DIAS", "90"))

    # Servidor
    port: int = int(os.getenv("PORT", "8000"))

    # Dashboard: el login (/login) ya no usa variables de entorno — verifica correo/clave
    # contra Supabase Auth del mismo proyecto (ver app/dashboard_auth.py). Los perfiles se
    # crean y se borran desde Supabase (Authentication → Users), no desde aquí.

    @property
    def system_prompt_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), "system_prompt.md")


settings = Settings()
