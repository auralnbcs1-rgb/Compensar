"""Interpreta la respuesta del paciente al menú de Aurora sin depender de Claude para
los casos obvios (número exacto o palabras clave claras) — más rápido, más barato, y
más fácil de probar. Solo se recurre a Claude
(claude_client.interpretar_seleccion_menu) cuando esto no encuentra una coincidencia
clara.
"""
import re

from app.solicitudes import SERVICIOS

_PALABRAS_CLAVE = {
    "1": ["adaptacion", "protesis", "prostesis", "audifono nuevo", "ayuda auditiva", "entrega"],
    "2": ["prueba"],
    "4": ["control"],
    "5": ["terapia"],
}

_TABLA_TILDES = str.maketrans("áéíóúñ", "aeioun")


def _sin_tildes(texto: str) -> str:
    return texto.translate(_TABLA_TILDES)


def coincidencia_local(mensaje: str) -> str | None:
    """Devuelve el código del servicio (ver solicitudes.SERVICIOS) si el mensaje
    coincide claramente con una opción del menú por número o palabra clave; None si no
    hay una coincidencia clara (y hay que preguntarle a Claude o mostrar el menú)."""
    texto = _sin_tildes(mensaje.strip().lower())

    solo_numero = re.match(r"^\D*([1-5])\D*$", texto)
    if solo_numero:
        return SERVICIOS[solo_numero.group(1)][0]

    # tinnitus aparece en dos opciones (evaluación y terapia) — "terapia" desempata.
    if "tinnitus" in texto or "pitido" in texto or "zumbido" in texto:
        return SERVICIOS["5"][0] if "terapia" in texto else SERVICIOS["3"][0]

    for opcion, palabras in _PALABRAS_CLAVE.items():
        if any(palabra in texto for palabra in palabras):
            return SERVICIOS[opcion][0]

    return None
