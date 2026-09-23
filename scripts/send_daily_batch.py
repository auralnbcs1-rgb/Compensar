#!/usr/bin/env python3
"""OPCIONAL — el flujo normal del bot es inbound (el paciente escribe primero), así
que este script no hace falta para operar. Queda disponible por si más adelante se
quiere recordarle proactivamente a quien todavía no ha escrito: toma los siguientes N
pacientes "pendiente" del backlog y les envía la plantilla de primer contacto por
WhatsApp. Para usarlo hace falta una plantilla aprobada por Meta (ver WHATSAPP_TEMPLATE_NAME
en el .env) — sin eso, no lo corras.

Pensado para correr vía cron si se decide usarlo. Ejemplo a las 9:00 am hora Bogotá
(UTC-5 → 14:00 UTC):
    0 14 * * *  cd /ruta/al/proyecto && python scripts/send_daily_batch.py

Uso:
    python scripts/send_daily_batch.py [--dry-run] [--limit N]
"""
import argparse
import sys
import time

sys.path.insert(0, ".")  # permite correr el script desde la raíz del proyecto

from app import backlog
from app.config import settings
from app.whatsapp_client import send_template


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No envía mensajes, solo muestra qué haría")
    parser.add_argument("--limit", type=int, default=settings.daily_batch_size)
    args = parser.parse_args()

    pacientes = backlog.next_batch(args.limit)
    if not pacientes:
        print("No hay pacientes pendientes en el backlog.")
        return

    print(f"Enviando plantilla a {len(pacientes)} paciente(s)...")
    enviados, fallidos = 0, 0
    for p in pacientes:
        if args.dry_run:
            print(f"  [dry-run] {p.nombre} ({p.telefono}) — {p.sede}")
            continue
        try:
            send_template(p.telefono, p.nombre)
            backlog.update_estado(p.telefono, "contactado", increment_intento=True)
            enviados += 1
            print(f"  OK  {p.nombre} ({p.telefono})")
        except Exception as exc:  # noqa: BLE001 — se quiere loguear y seguir con el resto del lote
            fallidos += 1
            print(f"  ERROR  {p.nombre} ({p.telefono}): {exc}")
        time.sleep(1)  # margen simple frente a límites de tasa de la API

    if not args.dry_run:
        print(f"Listo: {enviados} enviados, {fallidos} fallidos.")


if __name__ == "__main__":
    main()
