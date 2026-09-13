"""FastAPI app for Thulla arcade UI."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from thulla.advise import advise_session
from thulla.persist import get_or_load_session, persist_and_return, ensure_games_layout
from thulla.session import create_session

# Windows / some hosts omit .js → module MIME; browsers reject text/plain modules.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

STATIC_DIR = Path(__file__).resolve().parent / "static"

ensure_games_layout()


class ModuleStaticFiles(StaticFiles):
    """Serve .js as text/javascript and avoid sticky wrong MIME via 304 cache."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if path.endswith(".js"):
            response.headers["content-type"] = "text/javascript; charset=utf-8"
            # Prevent browsers from keeping a prior text/plain cache entry.
            response.headers["cache-control"] = "no-cache"
        return response


app = FastAPI(title="Thulla")
app.mount("/static", ModuleStaticFiles(directory=STATIC_DIR), name="static")


class CreateGameBody(BaseModel):
    mode: str = Field(..., pattern="^(human|ai)$")
    players: int = Field(..., ge=3, le=8)


class PlayBody(BaseModel):
    card: str


class TakeBody(BaseModel):
    accept: bool


class GiveBody(BaseModel):
    accept: bool


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/games")
def api_create_game(body: CreateGameBody):
    try:
        session = create_session(body.mode, body.players)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return persist_and_return(session)


@app.get("/api/games/{game_id}")
def api_get_game(game_id: str):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    return session.to_dict()


@app.post("/api/games/{game_id}/play")
def api_play(game_id: str, body: PlayBody):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        session.play_card(body.card)
        return persist_and_return(session)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/games/{game_id}/take")
def api_take(game_id: str, body: TakeBody):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        session.answer_take(body.accept)
        return persist_and_return(session)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/games/{game_id}/give")
def api_give(game_id: str, body: GiveBody):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        session.answer_give(body.accept)
        return persist_and_return(session)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/games/{game_id}/advise")
def api_advise(game_id: str):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    advice = advise_session(session)
    if advice.get("available"):
        session.record_advice_request(advice)
        try:
            from thulla.persist import save_session

            save_session(session)
        except OSError:
            pass
    return advice


@app.post("/api/games/{game_id}/step")
def api_step(game_id: str):
    session = get_or_load_session(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        session.step()
        return persist_and_return(session)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
