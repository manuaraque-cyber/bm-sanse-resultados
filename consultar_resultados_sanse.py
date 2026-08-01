#!/usr/bin/env python3
"""Consulta los resultados de BM Sanse en el Campeonato de España de Laredo.

Solo usa la biblioteca estándar de Python. La fuente de datos es la web oficial
de resultados de la RFEBM/iSquad.

Ejemplos:
    python3 consultar_resultados_sanse.py 2026-07-31
    python3 consultar_resultados_sanse.py 31/07/2026 --json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable


DEFAULT_SEED_URL = (
    "https://resultadosbalonmano.isquad.es/competicion.php?"
    "id_superficie=2&seleccion=0&id_categoria=2878&"
    "id_competicion=210667&id=1038943"
)
RESULTS_BASE = "https://resultadosbalonmano.isquad.es"
CALENDAR_URL = (
    "https://balonmano.isquad.es/json/competicion_google_calendar.php"
)
USER_AGENT = "BM-Sanse-Resultados/1.0 (+consulta publica RFEBM)"

CATEGORY_NAMES = {
    "CF": "Cadete femenino",
    "CM": "Cadete masculino",
    "IF": "Infantil femenino",
    "IM": "Infantil masculino",
    "JF": "Juvenil femenino",
    "JM": "Juvenil masculino",
    "SF": "Sénior femenino",
    "SM": "Sénior masculino",
}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def key(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", compact(text))
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", ascii_text.upper()).strip()


def parse_date(value: str) -> dt.date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        "Fecha no válida. Usa AAAA-MM-DD o DD/MM/AAAA."
    )


def fetch(url: str, timeout: float, attempts: int = 3) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "es"},
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.7 * (2**attempt))
    raise RuntimeError(f"No se pudo consultar {url}: {last_error}")


class SelectOptionsParser(HTMLParser):
    def __init__(self, select_id: str):
        super().__init__(convert_charrefs=True)
        self.select_id = select_id
        self.inside_select = False
        self.option_value: str | None = None
        self.option_text: list[str] = []
        self.options: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        if tag == "select" and attributes.get("id") == self.select_id:
            self.inside_select = True
        elif tag == "option" and self.inside_select:
            self.option_value = attributes.get("value")
            self.option_text = []

    def handle_data(self, data: str):
        if self.option_value is not None:
            self.option_text.append(data)

    def handle_endtag(self, tag: str):
        if tag == "option" and self.option_value is not None:
            label = compact("".join(self.option_text))
            if self.option_value and label:
                self.options.append((self.option_value, label))
            self.option_value = None
            self.option_text = []
        elif tag == "select" and self.inside_select:
            self.inside_select = False


class MatchRowsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_match_row = False
        self.in_cell = False
        self.cell_text: list[str] = []
        self.cells: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "tr" and "partido" in classes:
            self.in_match_row = True
            self.cells = []
        elif tag == "td" and self.in_match_row:
            self.in_cell = True
            self.cell_text = []

    def handle_data(self, data: str):
        if self.in_cell:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str):
        if tag == "td" and self.in_cell:
            self.cells.append(compact(" ".join(self.cell_text)))
            self.in_cell = False
            self.cell_text = []
        elif tag == "tr" and self.in_match_row:
            if self.cells:
                self.rows.append(self.cells)
            self.in_match_row = False


def select_options(page: str, select_id: str) -> list[tuple[str, str]]:
    parser = SelectOptionsParser(select_id)
    parser.feed(page)
    return parser.options


@dataclass(frozen=True)
class Competition:
    id: str
    label: str
    code: str
    category: str


@dataclass(frozen=True)
class CalendarEvent:
    competition: Competition
    start: dt.datetime
    phase: str
    jornada: int
    local: str
    visitor: str
    calendar_status: str


def discover_competitions(seed_page: str) -> list[Competition]:
    discovered: list[Competition] = []
    for competition_id, label in select_options(seed_page, "competiciones_playa"):
        if "LAREDO" not in key(label):
            continue
        code = compact(label).split("-", 1)[0].strip().upper()
        discovered.append(
            Competition(
                id=competition_id,
                label=label,
                code=code,
                category=CATEGORY_NAMES.get(code, code),
            )
        )
    if not discovered:
        raise RuntimeError("No se encontraron las categorías del campeonato de Laredo.")
    return discovered


def unfold_ics(ics: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", ics)


def ics_value(block: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}(?:;[^:]*)?:(.*)$", block, re.M)
    if not match:
        return ""
    return (
        match.group(1)
        .strip()
        .replace(r"\,", ",")
        .replace(r"\;", ";")
        .replace(r"\n", " ")
        .replace(r"\\", "\\")
    )


def parse_calendar(ics: str, competition: Competition) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    seen: set[tuple[str, str]] = set()
    unfolded = unfold_ics(ics)
    for block in re.findall(r"BEGIN:VEVENT\s*(.*?)\s*END:VEVENT", unfolded, re.S):
        start_raw = ics_value(block, "DTSTART")
        summary = compact(ics_value(block, "SUMMARY"))
        status = compact(ics_value(block, "DESCRIPTION"))
        start_match = re.match(r"(\d{8})T(\d{4,6})", start_raw)
        summary_match = re.match(
            r"^(.*?)\s+-\s+J(\d+)\s+-\s+(.*?)\s+vs\s+(.*?)$",
            summary,
            re.I,
        )
        if not start_match or not summary_match:
            continue
        clock = start_match.group(2).ljust(6, "0")
        start = dt.datetime.strptime(start_match.group(1) + clock, "%Y%m%d%H%M%S")
        dedupe = (start_raw, key(summary))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        events.append(
            CalendarEvent(
                competition=competition,
                start=start,
                phase=compact(summary_match.group(1)),
                jornada=int(summary_match.group(2)),
                local=compact(summary_match.group(3)),
                visitor=compact(summary_match.group(4)),
                calendar_status=status,
            )
        )
    return events


def phase_id(phase: str, phases: Iterable[tuple[str, str]]) -> str | None:
    wanted = key(phase)
    ranked: list[tuple[int, str]] = []
    for identifier, label in phases:
        candidate = key(label)
        if candidate == wanted:
            score = 120
        elif candidate.endswith(" " + wanted):
            score = 80
        elif wanted in candidate:
            score = 40
        else:
            continue

        # "GRUPO F" puede existir tanto en la fase previa como en la
        # principal. El calendario omite ese prefijo, así que se desambigua
        # de forma explícita.
        if re.fullmatch(r"GRUPO [A-Z0-9]+", wanted):
            if "FASE PRINCIPAL" in candidate:
                score += 35
            if "PREVIA" in candidate:
                score -= 35
        elif wanted.startswith("PREVIA GRUPO") and "FASE PREVIA" in candidate:
            score += 35
        elif wanted == "ELIMINATORIAS FASE CONSOLACION":
            score += 25 if "FASE INTERMEDIA" in candidate else 0
        elif wanted == "FASE CONSOLACION":
            score += 25 if "FASE DE CLASIFICACION" in candidate else 0
        elif wanted == "ELIMINATORIAS PREVIAS":
            score += 25 if "FASE FINAL" in candidate else 0
        ranked.append((score, identifier))
    return max(ranked, default=(0, ""))[1] or None


def competition_url(category_id: str, competition_id: str) -> str:
    query = urllib.parse.urlencode(
        {
            "id_superficie": 2,
            "seleccion": 0,
            "id_categoria": category_id,
            "id_competicion": competition_id,
        }
    )
    return f"{RESULTS_BASE}/competicion.php?{query}"


def result_url(
    category_id: str, competition_id: str, tournament_id: str, jornada: int
) -> str:
    return competition_url(category_id, competition_id) + "&" + urllib.parse.urlencode(
        {"id": tournament_id, "jornada": jornada}
    )


def pair(raw: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*-\s*(\d+)", raw)
    return (int(match.group(1)), int(match.group(2))) if match else None


def choose_row(event: CalendarEvent, rows: list[list[str]]) -> list[str] | None:
    wanted_date = event.start.strftime("%d/%m/%Y")
    wanted_time = event.start.strftime("%H:%M").lstrip("0")
    candidates: list[tuple[int, list[str]]] = []
    for row in rows:
        if len(row) < 8 or "SANSE" not in key(row[0]):
            continue
        row_time = key(row[5])
        if key(wanted_date) not in row_time:
            continue
        score = 0
        for team in (event.local, event.visitor):
            team_key = key(team)
            if team_key and team_key in key(row[0]):
                score += len(team_key)
        if wanted_time in compact(row[5]).lstrip("0"):
            score += 1000
        candidates.append((score, row))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def event_result(event: CalendarEvent, row: list[str], source_url: str) -> dict:
    sanse_is_local = "SANSE" in key(event.local)
    sanse_team = event.local if sanse_is_local else event.visitor
    opponent = event.visitor if sanse_is_local else event.local

    raw_sets = row[1:4]
    sets: list[str] = []
    for raw_set in raw_sets:
        parsed = pair(raw_set)
        if not parsed:
            continue
        left, right = parsed if sanse_is_local else parsed[::-1]
        sets.append(f"{left}-{right}")

    raw_score = pair(row[4])
    sanse_score: int | None = None
    opponent_score: int | None = None
    outcome = "Pendiente"
    if raw_score:
        sanse_score, opponent_score = raw_score if sanse_is_local else raw_score[::-1]
        if sanse_score > opponent_score:
            outcome = "Victoria"
        elif sanse_score < opponent_score:
            outcome = "Derrota"
        else:
            outcome = "Empate"

    return {
        "fecha": event.start.strftime("%Y-%m-%d"),
        "hora": event.start.strftime("%H:%M"),
        "categoria": event.competition.category,
        "codigo_categoria": event.competition.code,
        "equipo": sanse_team,
        "rival": opponent,
        "fase_grupo": event.phase,
        "jornada": event.jornada,
        "resultado": (
            f"{sanse_score}-{opponent_score}" if sanse_score is not None else "-"
        ),
        "balance": outcome,
        "sets": sets,
        "estado": row[7] or event.calendar_status,
        "lugar": row[6],
        "fuente": source_url,
    }


def print_text(results: list[dict], target_date: dt.date, warnings: list[str]) -> None:
    print(f"BM Sanse — Campeonato de España Laredo — {target_date:%d/%m/%Y}")
    print("=" * 72)
    if not results:
        print("No se encontraron partidos de BM Sanse para esa fecha.")
    for result in results:
        sets = ", ".join(result["sets"]) or "sin marcador"
        print(
            f'{result["hora"]} | {result["categoria"]} | {result["equipo"]} '
            f'vs {result["rival"]}'
        )
        print(
            f'  {result["balance"]} {result["resultado"]} | Sets: {sets} | '
            f'{result["fase_grupo"]}, J{result["jornada"]} | {result["estado"]}'
        )
    if results:
        victories = sum(r["balance"] == "Victoria" for r in results)
        defeats = sum(r["balance"] == "Derrota" for r in results)
        pending = len(results) - victories - defeats
        print("-" * 72)
        print(
            f"Total: {len(results)} partidos | {victories} victorias | "
            f"{defeats} derrotas | {pending} pendientes/otros"
        )
    if warnings:
        print("\nAvisos:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Consulta los resultados de BM Sanse de una fecha en el Campeonato "
            "de España Laredo de balonmano playa."
        )
    )
    parser.add_argument("fecha", type=parse_date, help="AAAA-MM-DD o DD/MM/AAAA")
    parser.add_argument(
        "--seed-url",
        default=DEFAULT_SEED_URL,
        help="URL de una categoría del Campeonato de España Laredo",
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    seed_query = urllib.parse.parse_qs(urllib.parse.urlparse(args.seed_url).query)
    category_id = seed_query.get("id_categoria", [""])[0]
    if not category_id:
        parser.error("La URL semilla debe contener id_categoria.")

    warnings: list[str] = []
    try:
        seed_page = fetch(args.seed_url, args.timeout)
        competitions = discover_competitions(seed_page)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    def load_competition(competition: Competition):
        calendar = fetch(
            CALENDAR_URL + "?" + urllib.parse.urlencode(
                {"id_competicion": competition.id}
            ),
            args.timeout,
        )
        page = fetch(competition_url(category_id, competition.id), args.timeout)
        return competition, parse_calendar(calendar, competition), select_options(
            page, "torneos_playa"
        )

    loaded: dict[str, tuple[list[CalendarEvent], list[tuple[str, str]]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(load_competition, comp): comp for comp in competitions}
        for future, comp in list(futures.items()):
            try:
                _, events, phases = future.result()
                loaded[comp.id] = (events, phases)
            except Exception as exc:  # Se informa y se continúa con las demás categorías.
                warnings.append(f"{comp.category}: {exc}")

    relevant: list[tuple[CalendarEvent, str, str]] = []
    for competition in competitions:
        if competition.id not in loaded:
            continue
        events, phases = loaded[competition.id]
        for event in events:
            if event.start.date() != args.fecha:
                continue
            if "SANSE" not in key(event.local + " " + event.visitor):
                continue
            tournament_id = phase_id(event.phase, phases)
            if not tournament_id:
                warnings.append(
                    f"Sin fase/grupo para {event.competition.code}: {event.phase}"
                )
                continue
            url = result_url(
                category_id, event.competition.id, tournament_id, event.jornada
            )
            relevant.append((event, tournament_id, url))

    pages: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch, url, args.timeout): url for _, _, url in relevant}
        for future, url in list(futures.items()):
            try:
                pages[url] = future.result()
            except Exception as exc:
                warnings.append(str(exc))

    results: list[dict] = []
    for event, _, url in relevant:
        if url not in pages:
            continue
        row_parser = MatchRowsParser()
        row_parser.feed(pages[url])
        row = choose_row(event, row_parser.rows)
        if row is None:
            warnings.append(
                f"No se encontró la fila de {event.local} vs {event.visitor} ({url})"
            )
            continue
        results.append(event_result(event, row, url))

    results.sort(key=lambda item: (item["fecha"], item["hora"], item["categoria"], item["equipo"]))
    if args.json:
        print(json.dumps({"resultados": results, "avisos": warnings}, ensure_ascii=False, indent=2))
    else:
        print_text(results, args.fecha, warnings)
    return 0 if not warnings else 1


if __name__ == "__main__":
    raise SystemExit(main())
