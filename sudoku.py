import typer
from typing import List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import time
import random
import copy
import json
from datetime import datetime

app = typer.Typer(add_completion=False, invoke_without_command=True, help=(
    "Ein Sudoku-CLI mit Typer: lösen, generieren, spielen – jetzt mit Seed & Import/Export.\n"
    "Eingabeformat zum Lösen: 9 Zeilen, mit '|' getrennt. Leerfelder als '.' oder '0'."
))

Grid = List[List[int]]

# globale Statistik-Variablen (für einfachen Solver)
steps_counter = 0

#############################################
# Parsing, I/O & Ausgabe
#############################################

def parse_grid(rows: str) -> Grid:
    parts = [p.strip() for p in rows.strip().split("|")]
    if len(parts) != 9:
        raise typer.BadParameter("Es müssen genau 9 Zeilen mit '|' getrennt übergeben werden.")

    grid: Grid = []
    for idx, row in enumerate(parts):
        row = row.replace(" ", "")
        if len(row) != 9:
            raise typer.BadParameter(f"Zeile {idx+1} hat nicht 9 Zeichen (gefunden: {len(row)}).")
        parsed_row: List[int] = []
        for ch in row:
            if ch in ".0":
                parsed_row.append(0)
            elif ch.isdigit() and ch != '0':
                val = int(ch)
                if 1 <= val <= 9:
                    parsed_row.append(val)
                else:
                    raise typer.BadParameter("Ziffern müssen 1-9 sein.")
            else:
                raise typer.BadParameter("Nur Ziffern 1-9, '.' oder '0' erlaubt.")
        grid.append(parsed_row)
    return grid


def grid_to_pipe(grid: Grid) -> str:
    return "|".join("".join(str(c) if c else "." for c in r) for r in grid)


def count_givens(grid: Grid) -> int:
    return sum(1 for r in grid for c in r if c != 0)


def load_puzzle_from_file(path: Path) -> Grid:
    if not path.exists():
        raise typer.BadParameter(f"Datei nicht gefunden: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"JSON ungültig: {e}")
        if isinstance(data, dict):
            if "puzzle" in data and isinstance(data["puzzle"], str):
                return parse_grid(data["puzzle"]) 
            if "grid" in data and isinstance(data["grid"], list):
                # grid als 2D-Array (0 für leer)
                rows = []
                for row in data["grid"]:
                    if not (isinstance(row, list) and len(row) == 9):
                        raise typer.BadParameter("JSON 'grid' muss 9 Listen mit je 9 Zahlen enthalten.")
                    rows.append("".join(str(x) if x != 0 else "." for x in row))
                return parse_grid("|".join(rows))
        raise typer.BadParameter("JSON muss 'puzzle' (Pipe-String) oder 'grid' (2D-Array) enthalten.")
    # TXT: Pipe-String oder 9 Zeilen
    if "|" in text:
        return parse_grid(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 9:
        return parse_grid("|".join(lines))
    raise typer.BadParameter("Textdatei muss entweder Pipe-String oder 9 Zeilen enthalten.")


def export_puzzle(
    puzzle: Grid,
    solution: Grid,
    difficulty: str,
    seed: Optional[int],
    out: Optional[Path],
    export_fmt: str,
) -> Path:
    export_fmt = export_fmt.lower()
    if export_fmt not in {"json", "txt"}:
        raise typer.BadParameter("--export muss 'json' oder 'txt' sein.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if out is None:
        out = Path(f"sudoku_{difficulty}_{seed if seed is not None else 'rand'}_{ts}.{export_fmt}")
    out.parent.mkdir(parents=True, exist_ok=True)

    if export_fmt == "txt":
        out.write_text(grid_to_pipe(puzzle), encoding="utf-8")
    else:
        payload = {
            "format": 1,
            "difficulty": difficulty,
            "seed": seed,
            "puzzle": grid_to_pipe(puzzle),
            "solution": grid_to_pipe(solution),
            "clues": count_givens(puzzle),
            "generated_at": ts,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# === Darstellung: Meta ohne Rahmen, Spielfeld mit Pipes & Rahmen ===

def print_grid(grid: Grid, pretty: bool = True) -> None:
    if not pretty:
        typer.echo(grid_to_pipe(grid))
        return

    # Meta-Header (nur Text, keine Pipes/Rahmen)
    header_tokens: List[str] = []
    for j in range(9):
        if j % 3 == 0 and j != 0:
            header_tokens.append(' ')
        header_tokens.append(str(j + 1))
    header_content = ' '.join(header_tokens)

    blue = "\033[94m"
    reset = "\033[0m"

    prefix_len = len(f"{1:>2}  ")
    # exakt über der ersten Zelle (nach "| ") beginnen
    typer.echo(' ' * (prefix_len + 2) + f"{blue}{header_content}{reset}")

    # Spielfeld-Rahmen dynamisch
    sample_tokens = []
    for j in range(9):
        if j % 3 == 0 and j != 0:
            sample_tokens.append('|')
        sample_tokens.append('.')
    sample_cells = ' '.join(sample_tokens)
    grid_line = f"| {sample_cells} |"

    top_border = ' ' * prefix_len + '+' + '-' * (len(grid_line) - 2) + '+'
    typer.echo(top_border)

    # horizontale Block-Trennlinie an Zellenbreite ausrichten
    block_sample = ' '.join(['.'] * 3)   # " . . . " -> Länge 5
    sep_group = '-' * len(block_sample)
    sep_content = f"{sep_group} + {sep_group} + {sep_group}"
    sep_line = ' ' * prefix_len + f"| {sep_content} |"

    for i, row in enumerate(grid):
        if i % 3 == 0 and i != 0:
            typer.echo(sep_line)
        tokens: List[str] = []
        for j, val in enumerate(row):
            if j % 3 == 0 and j != 0:
                tokens.append('|')
            tokens.append(str(val) if val != 0 else '.')
        cells = ' '.join(tokens)
        row_line = f"{blue}{i+1:>2}{reset}  " + f"| {cells} |"
        typer.echo(row_line)

    typer.echo(top_border)

#############################################
# Solver
#############################################

def find_empty(grid: Grid) -> Optional[Tuple[int, int]]:
    for i in range(9):
        for j in range(9):
            if grid[i][j] == 0:
                return i, j
    return None


def is_valid(grid: Grid, r: int, c: int, val: int) -> bool:
    if any(grid[r][x] == val for x in range(9)):
        return False
    if any(grid[x][c] == val for x in range(9)):
        return False
    br, bc = (r // 3) * 3, (c // 3) * 3
    for i in range(br, br + 3):
        for j in range(bc, bc + 3):
            if grid[i][j] == val:
                return False
    return True


def solve_backtrack(grid: Grid) -> bool:
    global steps_counter
    empty = find_empty(grid)
    if not empty:
        return True
    r, c = empty
    candidates = list(range(1, 10))
    random.shuffle(candidates)
    for val in candidates:
        steps_counter += 1
        if is_valid(grid, r, c, val):
            grid[r][c] = val
            if solve_backtrack(grid):
                return True
            grid[r][c] = 0
    return False


def solve_count(grid: Grid, limit: int = 2) -> int:
    count = 0

    def _bt() -> bool:
        nonlocal count
        empty = find_empty(grid)
        if not empty:
            count += 1
            return count >= limit
        r, c = empty
        for v in range(1, 10):
            if is_valid(grid, r, c, v):
                grid[r][c] = v
                if _bt():
                    return True
                grid[r][c] = 0
        return False

    _bt()
    return count

#############################################
# Generator
#############################################

def generate_full_solution() -> Grid:
    global steps_counter
    grid: Grid = [[0] * 9 for _ in range(9)]
    steps_counter = 0
    solve_backtrack(grid)
    return grid


def dig_holes_for_puzzle(full: Grid, clues_target: int) -> Grid:
    puzzle = copy.deepcopy(full)
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    for r, c in cells:
        if count_givens(puzzle) <= clues_target:
            break
        backup = puzzle[r][c]
        puzzle[r][c] = 0
        tmp = copy.deepcopy(puzzle)
        solutions = solve_count(tmp, limit=2)
        if solutions != 1:
            puzzle[r][c] = backup
    return puzzle


def generate_puzzle(difficulty: str = "medium") -> Grid:
    difficulty = difficulty.lower()
    clues_map = {"easy": 36, "medium": 30, "hard": 24}
    clues_target = clues_map.get(difficulty, 30)
    full = generate_full_solution()
    puzzle = dig_holes_for_puzzle(full, clues_target)
    return puzzle

#############################################
# Spielen
#############################################

def is_complete(grid: Grid) -> bool:
    return all(all(cell != 0 for cell in row) for row in grid)


def play_cli(puzzle: Grid) -> None:
    current = copy.deepcopy(puzzle)
    solution = copy.deepcopy(puzzle)
    global steps_counter
    steps_counter = 0
    solve_backtrack(solution)

    cheats = 0
    errors = 0
    t_start = time.perf_counter()

    help_text = """
Spielmodus. Befehle:
  set r c v  -> setze Wert v (1-9) in Zeile r, Spalte c (1-9)
  set r c ?  -> CHEAT: setze korrekten Wert für (r,c)
  del r c    -> löscht Eingabe in Zeile r, Spalte c (falls nicht gegeben)
  check      -> prüft Konflikte (Zeilen/Spalten/Blöcke)
  show       -> Brett anzeigen
  solve      -> Lösung anzeigen und Statistik ausgeben
  quit       -> beenden
""".strip()
    typer.echo(help_text)

    def is_given(r: int, c: int) -> bool:
        return puzzle[r][c] != 0

    def finish(summary_reason: str):
        elapsed = time.perf_counter() - t_start
        typer.echo("\n== Lösung ==")
        print_grid(solution, pretty=True)
        typer.echo("\n== Statistik ==")
        typer.echo(f" - Grund: {summary_reason}")
        typer.echo(f" - Zeit: {elapsed:.2f}s")
        typer.echo(f" - Fehler (falsche Versuche): {errors}")
        typer.echo(f" - Cheats (Auto-Einträge): {cheats}")

    while True:
        print_grid(current, pretty=True)
        cmd = typer.prompt("Eingabe").strip().split()
        if not cmd:
            continue
        op = cmd[0].lower()
        if op == "quit":
            finish("abgebrochen")
            break
        if op == "show":
            continue
        if op == "solve":
            finish("Cheat: vollständige Lösung angezeigt")
            break
        if op == "check":
            conflicts = []
            for r in range(9):
                for c in range(9):
                    v = current[r][c]
                    if v == 0:
                        continue
                    current[r][c] = 0
                    if not is_valid(current, r, c, v):
                        conflicts.append((r+1, c+1))
                    current[r][c] = v
            if conflicts:
                typer.echo("Konflikte bei: " + ", ".join(f"(Z{r},S{c})" for r, c in conflicts))
            else:
                typer.echo("Keine Konflikte gefunden.")
            continue
        if op == "set" and (len(cmd) == 4):
            rc, cc, vv = cmd[1], cmd[2], cmd[3]
            try:
                r, c = int(rc) - 1, int(cc) - 1
                if not (0 <= r < 9 and 0 <= c < 9):
                    raise ValueError
            except ValueError:
                typer.echo("Format: set r c v  (r,c:1-9, v:1-9 oder '?')")
                continue
            if is_given(r, c):
                typer.echo("Das ist ein gegebenes Feld – nicht änderbar.")
                continue
            if vv == "?":
                current[r][c] = solution[r][c]
                cheats += 1
                typer.echo(f"Cheat gesetzt an (Z{r+1},S{c+1}) → {solution[r][c]}")
            else:
                try:
                    v = int(vv)
                    if not (1 <= v <= 9):
                        raise ValueError
                except ValueError:
                    typer.echo("v muss 1-9 oder '?' sein")
                    continue
                if not is_valid(current, r, c, v):
                    typer.echo("Ungültiger Zug (Konflikt mit Zeile/Spalte/Block).")
                    errors += 1
                    continue
                if v != solution[r][c]:
                    errors += 1
                    typer.echo(f"Falsch. Tipp: probier 'set {r+1} {c+1} ?' für einen Cheat.")
                    continue
                current[r][c] = v

            if is_complete(current):
                if current == solution:
                    finish("korrekt gelöst")
                else:
                    finish("Brett voll aber nicht korrekt")
                break
            continue
        if op == "del" and len(cmd) == 3:
            try:
                r, c = int(cmd[1]) - 1, int(cmd[2]) - 1
                if not (0 <= r < 9 and 0 <= c < 9):
                    raise ValueError
            except ValueError:
                typer.echo("Format: del r c  (r,c:1-9)")
                continue
            if is_given(r, c):
                typer.echo("Gegebenes Feld kann nicht gelöscht werden.")
                continue
            current[r][c] = 0
            continue

        typer.echo("Unbekannter Befehl. Nutze: set/del/check/show/solve/quit")

#############################################
# Typer Commands
#############################################

@app.command()
def solve(
    rows: str = typer.Argument(..., help="9 Zeilen, mit '|' getrennt; '.' oder '0' für Leerfelder"),
    pretty: bool = typer.Option(True, "--pretty/--no-pretty", help="Schöne ASCII-Ausgabe statt einer einzigen Zeile"),
) -> None:
    """Löst das Sudoku und gibt die Lösung aus."""
    global steps_counter
    steps_counter = 0
    try:
        grid = parse_grid(rows)
    except typer.BadParameter as e:
        raise typer.BadParameter(str(e))

    start = time.time()
    solved = solve_backtrack(grid)
    duration = time.time() - start

    if solved:
        print_grid(grid, pretty=pretty)
        typer.echo(f"\nStatistik: {steps_counter} Backtracking-Schritte, {duration:.4f} Sekunden")
    else:
        typer.echo("Keine Lösung gefunden.")


@app.command("solve-file")
def solve_file(
    file: Path = typer.Argument(..., exists=True, readable=True, help="TXT oder JSON mit Puzzle"),
    pretty: bool = typer.Option(True, "--pretty/--no-pretty", help="Schöne ASCII-Ausgabe"),
) -> None:
    grid = load_puzzle_from_file(file)
    global steps_counter
    steps_counter = 0
    start = time.time()
    solved = solve_backtrack(grid)
    duration = time.time() - start
    if solved:
        print_grid(grid, pretty=pretty)
        typer.echo(f"\nStatistik: {steps_counter} Backtracking-Schritte, {duration:.4f} Sekunden")
    else:
        typer.echo("Keine Lösung gefunden.")


@app.command()
def play(
    puzzle: Optional[str] = typer.Option(None, "--puzzle", help="Puzzle als Pipe-String"),
    file: Optional[Path] = typer.Option(None, "--file", exists=True, readable=True, help="Puzzle aus Datei laden (TXT/JSON)"),
) -> None:
    if file is not None:
        grid = load_puzzle_from_file(file)
    elif puzzle is not None:
        grid = parse_grid(puzzle)
    else:
        # Interaktiv: 9 Zeilen abfragen
        typer.echo("Bitte 9 Zeilen eingeben (jeweils 9 Zeichen, '.' oder '0' für leer).")
        rows = []
        for i in range(1, 10):
            row = typer.prompt(f"Zeile {i}")
            rows.append(row)
        grid = parse_grid("|".join(rows))
    play_cli(grid)


@app.command()
def generate(
    difficulty: str = typer.Option("medium", "--difficulty", "-d", help="easy | medium | hard"),
    pretty: bool = typer.Option(True, "--pretty/--no-pretty", help="Ausgabe hübsch formatiert"),
    play: bool = typer.Option(False, "--play", help="Nach dem Generieren direkt im Terminal spielen"),
    seed: Optional[int] = typer.Option(None, "--seed", help="RNG Seed für reproduzierbare Puzzles"),
    export_fmt: Optional[str] = typer.Option(None, "--export", "-e", help="Exportformat: json oder txt"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Ausgabedatei (Default: auto)"),
) -> None:
    """Generiert ein Sudoku (eindeutig) und gibt es aus oder startet den Spielmodus."""
    rng_state = random.getstate()
    try:
        actual_seed = seed if seed is not None else random.SystemRandom().randrange(0, 2**32)
        random.seed(actual_seed)
        puzzle = generate_puzzle(difficulty)
    finally:
        random.setstate(rng_state)

    # Lösung für Export/Play berechnen
    solution = copy.deepcopy(puzzle)
    solve_backtrack(solution)

    # Seed anzeigen
    typer.echo(f"Seed: {actual_seed}")

    if export_fmt:
        path = export_puzzle(puzzle, solution, difficulty, actual_seed, out, export_fmt)
        typer.echo(f"Export gespeichert: {path}")

    if play:
        typer.echo("Generiertes Sudoku:")
        print_grid(puzzle, pretty=True)
        play_cli(puzzle)
    else:
        print_grid(puzzle, pretty=pretty)
        typer.echo("\nAls Pipe-String:")
        typer.echo(grid_to_pipe(puzzle))


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        while True:
            typer.echo("Sudoku Menü:")
            typer.echo("1) Sudoku eingeben und lösen")
            typer.echo("2) Sudoku generieren")
            typer.echo("3) Sudoku generieren & spielen")
            typer.echo("4) Spielen: aus Datei oder Seed")
            typer.echo("5) Beenden")
            choice = typer.prompt("Bitte Auswahl eingeben (1-5)")
            if choice == "1":
                typer.echo("Bitte 9 Zeilen eingeben (jeweils 9 Zeichen, '.' oder '0' für leer).")
                rows = []
                for i in range(1, 10):
                    row = typer.prompt(f"Zeile {i}")
                    rows.append(row)
                row_str = "|".join(rows)
                try:
                    grid = parse_grid(row_str)
                except typer.BadParameter as e:
                    typer.echo(f"Fehler: {e}")
                    continue
                global steps_counter
                steps_counter = 0
                start = time.time()
                solved = solve_backtrack(grid)
                duration = time.time() - start
                if solved:
                    typer.echo("Lösung:")
                    print_grid(grid, pretty=True)
                    typer.echo(f"Statistik: {steps_counter} Backtracking-Schritte, {duration:.4f} Sekunden")
                else:
                    typer.echo("Keine Lösung gefunden.")
            elif choice == "2":
                diff = typer.prompt("Schwierigkeit (easy/medium/hard)", default="medium")
                seed_in = typer.prompt("Seed (leer für zufällig)", default="")
                seed_val = int(seed_in) if seed_in.strip() != "" else None
                export = typer.prompt("Export (json/txt/leer)", default="")
                out = None
                if export.strip() != "":
                    out_path = typer.prompt("Dateiname (leer = automatisch)", default="")
                    out = Path(out_path) if out_path.strip() else None
                rng_state = random.getstate()
                try:
                    actual_seed = seed_val if seed_val is not None else random.SystemRandom().randrange(0, 2**32)
                    random.seed(actual_seed)
                    puzzle = generate_puzzle(diff)
                finally:
                    random.setstate(rng_state)
                solution = copy.deepcopy(puzzle)
                solve_backtrack(solution)
                if export.strip() != "":
                    try:
                        pth = export_puzzle(puzzle, solution, diff, actual_seed, out, export)
                        typer.echo(f"Export gespeichert: {pth}")
                    except Exception as e:
                        typer.echo(f"Export fehlgeschlagen: {e}")
                typer.echo("Generiertes Sudoku:")
                typer.echo(f"Seed: {actual_seed}")
                print_grid(puzzle, pretty=True)
                typer.echo("Als Pipe-String:")
                typer.echo(grid_to_pipe(puzzle))
            elif choice == "3":
                diff = typer.prompt("Schwierigkeit (easy/medium/hard)", default="medium")
                rng_state = random.getstate()
                try:
                    actual_seed = random.SystemRandom().randrange(0, 2**32)
                    random.seed(actual_seed)
                    puzzle = generate_puzzle(diff)
                finally:
                    random.setstate(rng_state)
                typer.echo(f"Seed: {actual_seed}")
                play_cli(puzzle)
            elif choice == "4":
                typer.echo("Quelle wählen:")
                typer.echo("1) Aus Datei (TXT/JSON)")
                typer.echo("2) Aus Seed (generieren)")
                sub = typer.prompt("Bitte Auswahl eingeben (1-2)")
                if sub == "1":
                    pth = typer.prompt("Pfad zur Datei (TXT/JSON)")
                    try:
                        grid = load_puzzle_from_file(Path(pth))
                    except Exception as e:
                        typer.echo(f"Fehler beim Laden: {e}")
                        continue
                    play_cli(grid)
                elif sub == "2":
                    diff = typer.prompt("Schwierigkeit (easy/medium/hard)", default="medium")
                    seed_in = typer.prompt("Seed (leer für zufällig)", default="")
                    seed_val = int(seed_in) if seed_in.strip() != "" else None
                    rng_state = random.getstate()
                    try:
                        actual_seed = seed_val if seed_val is not None else random.SystemRandom().randrange(0, 2**32)
                        random.seed(actual_seed)
                        puzzle = generate_puzzle(diff)
                    finally:
                        random.setstate(rng_state)
                    typer.echo(f"Seed: {actual_seed}")
                    play_cli(puzzle)
                else:
                    typer.echo("Ungültige Auswahl. Bitte 1-2 eingeben.")
                    continue
            elif choice == "5":
                typer.echo("Programm beendet.")
                raise typer.Exit()
            else:
                typer.echo("Ungültige Auswahl. Bitte 1-5 eingeben.")


if __name__ == "__main__":
    app()