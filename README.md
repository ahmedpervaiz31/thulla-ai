# Thulla

Arcade cardroom for **Thulla** (Getaway) — play human vs AI in the browser, or watch AI vs AI.

## Setup

```bash
pip install -r requirements.txt
# DMC bot (model_best) — optional but recommended for 4-player tables:
pip install -r requirements-dmc.txt
# Checkpoint: model_best.tar in thulla-ai/ or workspace root (or checkpoints/)
# Or: set THULLA_DMC_CHECKPOINT to an explicit path
python -m uvicorn web.app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

With a loaded checkpoint, **4-player** seats use the DMC net (`bot_kind: "dmc"`, names `DMC1`…). Other player counts still use the heuristic `ComputerPlayer`.

CLI (optional):

```bash
python main.py -p 4
```

## Layout

| Path | What |
|------|------|
| `thulla/` | Game engine, heuristic bot, public info, eval |
| `thulla_dmc/` | DouZero-style DMC train / eval / app bot |
| `checkpoints/` | Drop `model_best.tar` here for the web app |
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
