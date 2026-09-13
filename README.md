# Thulla

Arcade cardroom for **Thulla** (Getaway) — play human vs AI in the browser, or watch AI vs AI.

## Setup

```bash
pip install -r requirements.txt
python -m uvicorn web.app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

CLI (optional):

```bash
python main.py -p 4
```

## Layout

| Path | What |
|------|------|
| `thulla/` | Game engine, bots, public info, eval |
| `web/` | FastAPI + static arcade UI |
| `games/ongoing/` | Live checkpoints (resume after reload) |
| `games/completed/` | Finished games for bot review (JSON + `.md`) |
| `scripts/run_eval.py` | Bot strength / calibration vs random |
| `tests/` | Unit tests |

Completed human-vs-AI files include Ideal Move advice on each of your decisions, opening hands, and trick-by-trick plays — read the `.md` first.

## Modes

- **Human vs AI** — you at seat 0; scratch pad + ideal-move coach on the table
- **AI vs AI** — spectator stepping / autoplay

## Tests

```bash
python -m unittest discover -s tests -v
```
