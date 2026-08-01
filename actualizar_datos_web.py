#!/usr/bin/env python3
"""Genera los datos estáticos que publica la app gratuita de Firebase Hosting."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONSULTOR = ROOT / "consultar_resultados_sanse.py"
DEFAULT_OUTPUT = ROOT / "public" / "data" / "resultados.json"
DEFAULT_DATES = ("2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02")
CATEGORIES = (
    "Cadete femenino",
    "Cadete masculino",
    "Infantil femenino",
    "Infantil masculino",
    "Juvenil femenino",
    "Juvenil masculino",
    "Sénior femenino",
    "Sénior masculino",
)


def iso_date(value: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Usa fechas con formato AAAA-MM-DD.") from exc


def convert_result(result: dict) -> dict:
    return {
        "date": result["fecha"],
        "time": result["hora"],
        "category": result["categoria"],
        "categoryCode": result["codigo_categoria"],
        "team": result["equipo"],
        "opponent": result["rival"],
        "phase": result["fase_grupo"],
        "jornada": result["jornada"],
        "score": result["resultado"],
        "outcome": result["balance"],
        "sets": result["sets"],
        "status": result["estado"],
        "venue": result["lugar"],
        "source": result["fuente"],
    }


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def without_generated_at(value: dict) -> dict:
    """Devuelve una copia comparable ignorando las fechas de actualización."""
    cleaned = dict(value)
    cleaned.pop("generatedAt", None)
    return cleaned


def query_date(date: str, timeout: float, workers: int) -> dict:
    command = [
        sys.executable,
        str(CONSULTOR),
        date,
        "--json",
        "--timeout",
        str(timeout),
        "--workers",
        str(workers),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode not in (0, 1) or not completed.stdout.strip():
        detail = completed.stderr.strip() or "El consultor no devolvió datos."
        raise RuntimeError(f"No se pudo actualizar {date}: {detail}")

    raw = json.loads(completed.stdout)
    warnings = raw.get("avisos", [])
    if warnings:
        raise RuntimeError(
            f"Consulta incompleta para {date}: " + "; ".join(warnings)
        )
    results = [convert_result(item) for item in raw.get("resultados", [])]
    victories = sum(item["outcome"] == "Victoria" for item in results)
    defeats = sum(item["outcome"] == "Derrota" for item in results)
    codes = {item["category"] for item in results}
    return {
        "date": date,
        "tournament": "Campeonato de España Laredo",
        "summary": {
            "matches": len(results),
            "victories": victories,
            "defeats": defeats,
            "others": len(results) - victories - defeats,
        },
        "results": results,
        "categoriesWithoutMatches": [name for name in CATEGORIES if name not in codes],
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Actualiza el archivo estático de resultados para Firebase Hosting."
    )
    parser.add_argument("fechas", nargs="*", type=iso_date, default=list(DEFAULT_DATES))
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    output = args.salida.resolve()
    existing = load_existing(output)
    days = existing.get("dates", {}) if isinstance(existing.get("dates"), dict) else {}
    changed_dates: list[str] = []

    for date in sorted(set(args.fechas)):
        print(f"Actualizando {date}...", file=sys.stderr)
        updated_day = query_date(date, args.timeout, args.workers)
        previous_day = days.get(date, {})
        if without_generated_at(previous_day) != without_generated_at(updated_day):
            days[date] = updated_day
            changed_dates.append(date)

    if not changed_dates and existing:
        print("Sin cambios en los resultados; no se modifica el archivo.")
        return 0

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for date in changed_dates:
        days[date]["generatedAt"] = generated_at
    dataset = {
        "tournament": "Campeonato de España Laredo",
        "generatedAt": generated_at,
        "categories": list(CATEGORIES),
        "dates": dict(sorted(days.items())),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    detail = ", ".join(changed_dates) if changed_dates else "archivo inicial"
    print(f"Datos guardados en {output} ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
