#!/usr/bin/env python3
"""Importa un CSV (por ejemplo, una exportación de la pestaña PENDIENTES) a la tabla
`backlog` de Supabase. Pensado para la migración inicial única del backlog actual.

El CSV debe tener columnas: cedula, nombre, telefono, sede
(estado se deja en "pendiente" para todas las filas nuevas).

Uso:
    python scripts/import_backlog_csv.py ruta/al/backlog_exportado.csv
"""
import csv
import sys

sys.path.insert(0, ".")

from app.db import get_client  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/import_backlog_csv.py <archivo.csv>")
        sys.exit(1)

    path = sys.argv[1]
    client = get_client()

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            {
                "cedula": row["cedula"].strip(),
                "nombre": row["nombre"].strip(),
                "telefono": row["telefono"].strip(),
                "sede": row["sede"].strip(),
                "estado": "pendiente",
            }
            for row in reader
            if row.get("cedula") and row.get("telefono")
        ]

    if not rows:
        print("No se encontraron filas válidas en el CSV.")
        return

    # upsert por cédula: si se corre dos veces no duplica pacientes.
    result = client.table("backlog").upsert(rows, on_conflict="cedula").execute()
    print(f"Importados/actualizados {len(result.data)} pacientes en Supabase.")


if __name__ == "__main__":
    main()
