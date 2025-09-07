# Sudoku CLI (Typer)

Ein schlankes Sudoku-Tool als **Typer-CLI**: Puzzles **lösen**, **generieren**, **spielen** – mit Seed-Unterstützung, Import/Export und hübscher Terminal-Ausgabe.

(von chat gpt nach meinen Vorgaben generiert)

![status](https://img.shields.io/badge/python-3.9%2B-blue) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features
- **Lösen**: Backtracking-Solver (9×9), robuste Eingabeprüfung
- **Generieren**: zufällige, **eindeutig** lösbare Puzzles (`easy/medium/hard`)
- **Spielen**: interaktiver Terminal-Mode inkl. **Cheat** (`set r c ?`), Fehlerzählung & Zeitmessung
- **Seed sichtbar**: reproduzierbare Puzzles via `--seed`; Seed wird ausgegeben
- **Import/Export**: Pipe-String / TXT / JSON (inkl. Lösung & Metadaten)
- **Hübsches Board**: Meta-Header ohne Rahmen, Spielfeld mit Pipes & Rahmen

> **Hinweis:** Eindeutige Lösung ≠ „ohne Raten“. Der Generator garantiert **eine** Lösung; nicht, dass jede Lösung ohne Trial&Error mit rein menschlichen Strategien erreichbar ist.

---

## Systemvoraussetzungen
- Python **3.9+**
- Terminal mit fester Breite (Monospace)
- Optional (Windows): [`colorama`](https://pypi.org/project/colorama/) für zuverlässige ANSI-Farben

---

## Installation

### 1) Repository klonen
```bash
git clone <dein-repo-url>
cd sudoku
```

### 2) Virtuelle Umgebung anlegen
**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```
**Windows (PowerShell):**
```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

### 3) Abhängigkeiten installieren
Variante A – minimal:
```bash
pip install typer
```

---

## Start

### Interaktives Menü
```bash
python sudoku.py
```
Menüoptionen:
1) **Sudoku eingeben und lösen** (9 Zeilen, `.`/`0` für leer)
2) **Sudoku generieren** (optional Seed & Export)
3) **Sudoku generieren & spielen**
4) **Spielen: aus Datei oder Seed** (Untermenü)
5) Beenden

---

## CLI-Kommandos

### Lösen
```bash
python sudoku.py solve "53..7....|6..195...|.98....6.|8...6...3|4..8.3..1|7...2...6|.6....28.|...419..5|....8..79"
```
Optionen: `--pretty/--no-pretty`

### Aus Datei lösen
```bash
python sudoku.py solve-file puzzles/example.json
```

### Generieren
```bash
python sudoku.py generate -d medium
python sudoku.py generate -d hard --seed 12345
```
Optionen:
- `-d/--difficulty {easy|medium|hard}`
- `--seed <int>` → Seed wird **ausgegeben** (und beim Export mitgeschrieben)
- `--play` → direkt im Terminal spielen
- `--export {json|txt}` und `--out <pfad>` → Export
- `--pretty/--no-pretty`

### Spielen
Aus Datei:
```bash
python sudoku.py play --file puzzles/medium_42.json
```
Aus Pipe-String:
```bash
python sudoku.py play --puzzle "..3.5....|.1..9..2.|...3.....|..7...1..|.4.....3.|..2...8..|.....7...|.6..1..4.|....8.3.."
```

#### Befehle im Spielmodus
```
set r c v   # setze Wert v (1-9) in Zeile r, Spalte c (1-9)
set r c ?   # CHEAT: setzt korrekten Wert aus der Lösung
del r c     # löscht Eingabe (falls nicht gegeben)
check       # zeigt Konflikte (Zeile/Spalte/Block)
show        # Brett anzeigen
solve       # komplette Lösung + Statistik anzeigen
quit        # beenden
```
Am Ende werden **Zeit**, **Fehler**, **Cheats** und die **Lösung** ausgegeben.

---

## Import/Export

### Pipe-String
Interne Darstellungsform, `|` trennt Zeilen, `.`/`0` = leer.
```text
53..7....|6..195...|.98....6.|8...6...3|4..8.3..1|7...2...6|.6....28.|...419..5|....8..79
```

### TXT
Datei mit Pipe-String **oder** 9 Zeilen à 9 Zeichen.

### JSON (Export)
Beispiel:
```json
{
  "format": 1,
  "difficulty": "medium",
  "seed": 42,
  "puzzle": "..3.5....|.1..9..2.|...3.....|..7...1..|.4.....3.|..2...8..|.....7...|.6..1..4.|....8.3..",
  "solution": "...",
  "clues": 30,
  "generated_at": "2025-09-08_16:12:03"
}
```

---

## Entwickler-Notizen
- **Eindeutigkeit**: Beim „Ausgraben“ wird nach jedem Entfernen via `solve_count` geprüft und bei `solutions>=2` rückgängig gemacht → genau **eine** Lösung.
- **Ratenfreiheit**: nicht garantiert (kann optional mit logikorientiertem Solver nachgerüstet werden).
- **Seed**: Wenn nicht angegeben, wird ein zufälliger 32‑bit Seed erzeugt und ausgegeben.

### Roadmap (Ideen)
- `--no-guess` + logische Techniken (Singles, Locked Candidates, Paare, X-Wing, …)
- `--color {auto|on|off}` und besseres Windows-ANSI (per `colorama`)
- `undo/redo`, Pencil Marks
- Packaging (`pyproject.toml`, `pipx install .`), Tests

---

## Lizenz
MIT – siehe `LICENSE`.

