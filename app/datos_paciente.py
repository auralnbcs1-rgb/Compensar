"""Datos adicionales del paciente que Aurora recolecta, uno por uno, antes de pedir los
documentos: fecha de nacimiento, dirección de residencia, régimen de salud, un segundo
número de teléfono de contacto, y correo electrónico.

Se piden con preguntas fijas (no las redacta Claude) por la misma razón que el menú:
son datos exactos que conviene no dejar en manos de que el modelo los recuerde bien.
Cada campo valida la respuesta y, si no la entiende, vuelve a preguntar con un mensaje
de error específico — así nunca se guarda un dato claramente mal formado.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

_FORMATOS_FECHA = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y")


def _parsear_fecha(texto: str) -> date | None:
    texto = texto.strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def validar_fecha_nacimiento(texto: str) -> tuple[bool, str]:
    fecha = _parsear_fecha(texto)
    if fecha is None or fecha >= date.today():
        return False, ""
    return True, fecha.isoformat()


def validar_direccion(texto: str) -> tuple[bool, str]:
    texto = texto.strip()
    return len(texto) >= 5, texto


_REGIMENES = ("contributivo", "subsidiado", "especial", "exceptuado")


def validar_regimen(texto: str) -> tuple[bool, str]:
    texto_normalizado = texto.strip().lower()
    for palabra in _REGIMENES:
        if palabra in texto_normalizado:
            return True, palabra
    # No usó ninguna de las palabras esperadas — igual guardamos lo que escribió en vez
    # de bloquear el flujo; un agente humano lo puede revisar si hace falta.
    return len(texto.strip()) >= 3, texto.strip()


def validar_telefono(texto: str) -> tuple[bool, str]:
    digitos = re.sub(r"\D", "", texto)
    return 7 <= len(digitos) <= 15, digitos


_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_correo(texto: str) -> tuple[bool, str]:
    texto = texto.strip()
    return bool(_PATRON_CORREO.match(texto)), texto


@dataclass
class Campo:
    clave: str
    pregunta: str
    error: str
    validar: Callable[[str], tuple[bool, str]]


# Orden en el que Aurora los pide — después de identificar cédula/nombre y antes de
# pedir los documentos.
CAMPOS: list[Campo] = [
    Campo(
        "fecha_nacimiento",
        "¿Cuál es tu fecha de nacimiento? (día/mes/año, ej. 15/03/1958)",
        "No logré leer esa fecha. ¿Me la escribes así: día/mes/año?",
        validar_fecha_nacimiento,
    ),
    Campo(
        "direccion",
        "¿Cuál es tu dirección de residencia?",
        "¿Me confirmas tu dirección completa?",
        validar_direccion,
    ),
    Campo(
        "regimen",
        "¿A qué régimen de salud perteneces — contributivo o subsidiado?",
        "¿Me confirmas tu régimen de salud (contributivo o subsidiado)?",
        validar_regimen,
    ),
    Campo(
        "telefono_2",
        "¿Me das un segundo número de teléfono de contacto?",
        "No logré leer ese número. ¿Me lo escribes solo con dígitos?",
        validar_telefono,
    ),
    Campo(
        "correo",
        "¿Cuál es tu correo electrónico?",
        "Ese correo no se ve válido. ¿Me lo vuelves a escribir?",
        validar_correo,
    ),
]
