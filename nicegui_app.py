from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nicegui import app, events, run as nicegui_run, ui
from typer import BadParameter

from sudoku import (
    Grid,
    count_givens,
    export_puzzle,
    generate_puzzle,
    grid_to_pipe,
    is_complete,
    is_valid,
    load_puzzle_from_file,
    parse_grid,
    solve_backtrack,
)


Cell = Tuple[int, int]

PUZZLE_DIR = Path("puzzles")


def allow_sandboxed_nicegui_startup() -> None:
    original_setup = nicegui_run.setup

    def setup() -> None:
        try:
            original_setup()
        except PermissionError:
            # NiceGUI's CPU-bound helper uses a ProcessPoolExecutor. The Sudoku UI
            # does not need it, and some sandboxed Windows terminals block it.
            nicegui_run.process_pool = None

    nicegui_run.setup = setup


allow_sandboxed_nicegui_startup()


class SudokuGame:
    def __init__(self) -> None:
        self.difficulty = "medium"
        self.seed: Optional[int] = 42
        self.puzzle: Grid = [[0] * 9 for _ in range(9)]
        self.current: Grid = [[0] * 9 for _ in range(9)]
        self.solution: Grid = [[0] * 9 for _ in range(9)]
        self.givens: set[Cell] = set()
        self.selected: Optional[Cell] = None
        self.errors = 0
        self.hints = 0
        self.started_at = time.perf_counter()
        self.finished = False

    def load(self, puzzle: Grid, difficulty: str = "custom", seed: Optional[int] = None) -> None:
        self.difficulty = difficulty
        self.seed = seed
        self.puzzle = copy.deepcopy(puzzle)
        self.current = copy.deepcopy(puzzle)
        self.solution = copy.deepcopy(puzzle)
        solve_backtrack(self.solution)
        self.givens = {(r, c) for r in range(9) for c in range(9) if puzzle[r][c] != 0}
        self.selected = None
        self.errors = 0
        self.hints = 0
        self.started_at = time.perf_counter()
        self.finished = False

    def generate(self, difficulty: str, seed: Optional[int]) -> None:
        rng_state = random.getstate()
        try:
            actual_seed = seed if seed is not None else random.SystemRandom().randrange(0, 2**32)
            random.seed(actual_seed)
            puzzle = generate_puzzle(difficulty)
        finally:
            random.setstate(rng_state)
        self.load(puzzle, difficulty, actual_seed)

    def reset(self) -> None:
        self.current = copy.deepcopy(self.puzzle)
        self.errors = 0
        self.hints = 0
        self.started_at = time.perf_counter()
        self.finished = False

    def set_value(self, r: int, c: int, value: int) -> None:
        if (r, c) in self.givens or self.finished:
            return
        self.current[r][c] = value

    def conflicts(self) -> set[Cell]:
        bad: set[Cell] = set()
        for r in range(9):
            for c in range(9):
                value = self.current[r][c]
                if value == 0:
                    continue
                self.current[r][c] = 0
                if not is_valid(self.current, r, c, value):
                    bad.add((r, c))
                self.current[r][c] = value
        return bad

    def wrong_cells(self) -> set[Cell]:
        return {
            (r, c)
            for r in range(9)
            for c in range(9)
            if self.current[r][c] != 0 and self.current[r][c] != self.solution[r][c]
        }

    def empty_cells(self) -> List[Cell]:
        return [(r, c) for r in range(9) for c in range(9) if self.current[r][c] == 0]


game = SudokuGame()
cells: Dict[Cell, ui.input] = {}
number_buttons: Dict[int, ui.button] = {}
status_label: ui.label
meta_label: ui.label
timer_label: ui.label
pipe_textarea: ui.textarea
difficulty_select: ui.select
seed_input: ui.input


def parse_seed(value: Optional[str]) -> Optional[int]:
    if value is None or value.strip() == "":
        return None
    return int(value.strip())


def format_elapsed() -> str:
    elapsed = int(time.perf_counter() - game.started_at)
    minutes, seconds = divmod(elapsed, 60)
    return f"{minutes:02d}:{seconds:02d}"


def update_status(message: Optional[str] = None, tone: str = "info") -> None:
    colors = {
        "info": "text-slate-700",
        "good": "text-emerald-700",
        "warn": "text-amber-700",
        "bad": "text-rose-700",
    }
    status_label.text = message or "Bereit."
    status_label.classes(replace=f"text-sm font-semibold {colors[tone]}")
    meta_label.text = (
        f"{game.difficulty.title()} | Seed {game.seed if game.seed is not None else '-'} | "
        f"{count_givens(game.puzzle)} Vorgaben | Fehler {game.errors} | Tipps {game.hints}"
    )


def cell_classes(r: int, c: int, conflicts: set[Cell], wrong: set[Cell]) -> str:
    classes = [
        "sudoku-cell",
        "w-full",
        "h-full",
        "rounded-none",
        "text-center",
    ]
    if (r, c) in game.givens:
        classes.append("given-cell")
    elif game.current[r][c] != 0:
        classes.append("player-cell")
    if (r, c) == game.selected:
        classes.append("selected-cell")
    elif game.selected and (r == game.selected[0] or c == game.selected[1]):
        classes.append("peer-cell")
    if (r, c) in conflicts or (r, c) in wrong:
        classes.append("bad-cell")
    return " ".join(classes)


def refresh_board(message: Optional[str] = None, tone: str = "info") -> None:
    conflicts = game.conflicts()
    wrong = game.wrong_cells()
    for r in range(9):
        for c in range(9):
            cell = cells[(r, c)]
            value = game.current[r][c]
            cell.value = str(value) if value else ""
            cell.disable() if (r, c) in game.givens or game.finished else cell.enable()
            cell.classes(replace=cell_classes(r, c, conflicts, wrong))

    pipe_textarea.value = grid_to_pipe(game.current)
    update_status(message, tone)


def select_cell(r: int, c: int) -> None:
    game.selected = (r, c)
    refresh_board()


def normalize_cell_value(raw: object) -> int:
    value = str(raw or "").strip()
    if value == "":
        return 0
    return int(value[-1]) if value[-1] in "123456789" else 0


def on_cell_change(r: int, c: int, event: events.ValueChangeEventArguments) -> None:
    value = normalize_cell_value(event.value)
    if value and value != game.solution[r][c]:
        game.errors += 1
    game.set_value(r, c, value)
    if is_complete(game.current) and game.current == game.solution:
        game.finished = True
        refresh_board("Geloest. Sehr sauber gespielt.", "good")
        ui.notify("Sudoku geloest!", type="positive")
        return
    refresh_board()


def set_selected_value(value: int) -> None:
    if game.selected is None:
        update_status("Bitte zuerst ein Feld waehlen.", "warn")
        return
    r, c = game.selected
    if (r, c) in game.givens:
        update_status("Vorgegebene Felder bleiben fix.", "warn")
        return
    if value and value != game.solution[r][c]:
        game.errors += 1
    game.set_value(r, c, value)
    refresh_board()


def new_game() -> None:
    try:
        seed = parse_seed(seed_input.value)
    except ValueError:
        update_status("Seed muss eine ganze Zahl sein.", "bad")
        return
    game.generate(str(difficulty_select.value), seed)
    seed_input.value = str(game.seed)
    refresh_board("Neues Sudoku bereit.", "good")


def reset_game() -> None:
    game.reset()
    refresh_board("Board zurueckgesetzt.", "info")


def reveal_solution() -> None:
    game.current = copy.deepcopy(game.solution)
    game.finished = True
    refresh_board("Loesung eingeblendet.", "warn")


def check_game() -> None:
    conflicts = game.conflicts()
    wrong = game.wrong_cells()
    if conflicts:
        refresh_board(f"{len(conflicts)} Konfliktfelder gefunden.", "bad")
    elif wrong:
        refresh_board(f"{len(wrong)} falsche Eintraege gefunden.", "bad")
    else:
        refresh_board("Sieht gut aus.", "good")


def hint() -> None:
    empties = game.empty_cells()
    if not empties:
        check_game()
        return
    r, c = random.choice(empties)
    game.current[r][c] = game.solution[r][c]
    game.hints += 1
    game.selected = (r, c)
    refresh_board(f"Tipp gesetzt: Zeile {r + 1}, Spalte {c + 1}.", "good")


def import_pipe() -> None:
    try:
        puzzle = parse_grid(str(pipe_textarea.value))
    except BadParameter as exc:
        update_status(str(exc), "bad")
        return
    game.load(puzzle)
    refresh_board("Puzzle importiert.", "good")


def export_json() -> None:
    filename = f"nicegui_{game.difficulty}_{game.seed if game.seed is not None else 'custom'}.json"
    path = export_puzzle(game.puzzle, game.solution, game.difficulty, game.seed, PUZZLE_DIR / filename, "json")
    ui.notify(f"Gespeichert: {path}", type="positive")
    update_status(f"Export gespeichert: {path}", "good")


def load_uploaded_file(event: events.UploadEventArguments) -> None:
    destination = PUZZLE_DIR / event.name
    PUZZLE_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(event.content.read())
    try:
        puzzle = load_puzzle_from_file(destination)
    except BadParameter as exc:
        update_status(str(exc), "bad")
        return
    game.load(puzzle, "custom")
    refresh_board(f"Geladen: {event.name}", "good")


def update_timer() -> None:
    timer_label.text = format_elapsed()


def build_board() -> None:
    with ui.element("div").classes("sudoku-board"):
        for r in range(9):
            for c in range(9):
                cell = (
                    ui.input()
                    .props("dense borderless maxlength=1 input-class=text-center")
                    .classes("sudoku-cell")
                    .on("focus", lambda _event, row=r, col=c: select_cell(row, col))
                    .on_value_change(lambda event, row=r, col=c: on_cell_change(row, col, event))
                )
                cells[(r, c)] = cell


def build_number_pad() -> None:
    with ui.element("div").classes("number-pad"):
        for value in range(1, 10):
            number_buttons[value] = ui.button(str(value), on_click=lambda v=value: set_selected_value(v)).props("flat")
        ui.button(icon="backspace", on_click=lambda: set_selected_value(0)).props("flat").tooltip("Feld leeren")


def build_ui() -> None:
    global difficulty_select, meta_label, pipe_textarea, seed_input, status_label, timer_label

    ui.colors(primary="#176b5d", secondary="#d1512d", accent="#f4b400")
    ui.add_head_html(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@700&family=Nunito+Sans:wght@500;700;900&display=swap" rel="stylesheet">
        """
    )
    ui.add_css(
        """
        :root {
            --ink: #17211d;
            --paper: #f7f3e8;
            --mint: #d9f0df;
            --green: #176b5d;
            --red: #d1512d;
            --gold: #f4b400;
            --line: #1f332c;
        }

        body {
            background:
                linear-gradient(135deg, rgba(23, 107, 93, 0.16), transparent 34%),
                radial-gradient(circle at 80% 15%, rgba(244, 180, 0, 0.20), transparent 26%),
                repeating-linear-gradient(45deg, rgba(23, 33, 29, 0.035) 0 1px, transparent 1px 16px),
                var(--paper);
            color: var(--ink);
            font-family: "Nunito Sans", sans-serif;
        }

        .headline {
            font-family: "Fraunces", serif;
            letter-spacing: 0;
        }

        .tool-panel {
            background: rgba(255, 252, 242, 0.82);
            border: 2px solid rgba(31, 51, 44, 0.12);
            border-radius: 8px;
            box-shadow: 0 18px 48px rgba(31, 51, 44, 0.12);
            backdrop-filter: blur(9px);
        }

        .sudoku-board {
            aspect-ratio: 1 / 1;
            width: min(88vw, 620px);
            display: grid;
            grid-template-columns: repeat(9, minmax(0, 1fr));
            grid-template-rows: repeat(9, minmax(0, 1fr));
            border: 4px solid var(--line);
            background: var(--line);
            gap: 1px;
            box-shadow: 0 22px 60px rgba(31, 51, 44, 0.22);
        }

        .sudoku-cell {
            min-width: 0;
            min-height: 0;
            border-radius: 0;
            background: #fffdf6;
            color: var(--ink);
            font-weight: 900;
        }

        .sudoku-cell:nth-child(3n) {
            border-right: 3px solid var(--line);
        }

        .sudoku-cell:nth-child(n+19):nth-child(-n+27),
        .sudoku-cell:nth-child(n+46):nth-child(-n+54) {
            border-bottom: 3px solid var(--line);
        }

        .sudoku-cell input {
            height: 100%;
            font-size: clamp(1.35rem, 4.2vw, 2.4rem);
            font-weight: 900;
            padding: 0;
            caret-color: var(--red);
        }

        .given-cell {
            background: #d9f0df;
            color: #102e27;
        }

        .player-cell {
            color: #176b5d;
        }

        .peer-cell {
            background: #fff3cf;
        }

        .selected-cell {
            background: #f4b400;
            color: #17211d;
        }

        .bad-cell {
            background: #ffd7c9;
            color: #981b1b;
        }

        .number-pad {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.5rem;
        }

        .number-pad .q-btn {
            min-height: 3rem;
            border: 2px solid rgba(31, 51, 44, 0.16);
            background: rgba(255, 252, 242, 0.9);
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 900;
        }

        @media (max-width: 880px) {
            .game-shell {
                grid-template-columns: 1fr;
            }

            .sudoku-board {
                width: min(94vw, 560px);
            }
        }
        """
    )

    with ui.column().classes("w-full min-h-screen items-center px-4 py-8 gap-6"):
        with ui.row().classes("w-full max-w-7xl items-end justify-between gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Sudoku Studio").classes("headline text-5xl md:text-7xl text-slate-900")
                meta_label = ui.label().classes("text-sm font-bold text-slate-700")
            with ui.column().classes("items-end gap-1"):
                timer_label = ui.label("00:00").classes("headline text-4xl text-emerald-800")
                status_label = ui.label("Bereit.").classes("text-sm font-semibold text-slate-700")

        with ui.element("div").classes("game-shell grid grid-cols-[minmax(0,620px)_minmax(320px,420px)] gap-6 w-full max-w-7xl items-start"):
            build_board()

            with ui.column().classes("tool-panel w-full p-4 gap-4"):
                with ui.row().classes("w-full gap-3"):
                    difficulty_select = ui.select(["easy", "medium", "hard"], value="medium", label="Level").classes("grow")
                    seed_input = ui.input("Seed", value="42").classes("grow")
                with ui.row().classes("w-full gap-2"):
                    ui.button("Neu", icon="casino", on_click=new_game).classes("grow")
                    ui.button("Reset", icon="restart_alt", on_click=reset_game).props("outline").classes("grow")

                build_number_pad()

                with ui.row().classes("w-full gap-2"):
                    ui.button("Check", icon="fact_check", on_click=check_game).props("outline").classes("grow")
                    ui.button("Tipp", icon="lightbulb", on_click=hint).props("outline").classes("grow")
                    ui.button("Loesen", icon="visibility", on_click=reveal_solution).props("outline color=secondary").classes("grow")

                pipe_textarea = ui.textarea("Pipe-String", value="").props("autogrow").classes("w-full")
                with ui.row().classes("w-full gap-2"):
                    ui.button("Import", icon="input", on_click=import_pipe).props("outline").classes("grow")
                    ui.button("Export", icon="save", on_click=export_json).props("outline").classes("grow")
                ui.upload(on_upload=load_uploaded_file, label="JSON/TXT laden", auto_upload=True).props("accept=.json,.txt").classes("w-full")

    ui.timer(1.0, update_timer)


build_ui()
game.generate("medium", 42)
refresh_board("Seed 42 geladen.", "good")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Sudoku Studio", reload=False, port=8080)
