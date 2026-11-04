"""FastAPI application and bounded local SQLite run history."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from harvest.commands import plan_command
from harvest.scraper import ScrapeError, get_categories, scrape_catalogue

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title='Harvest Collection API', version='2.0.0', description='Category-aware extraction from the Books to Scrape adapter. No arbitrary URL fetching.')


class ScrapeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    pages: int = Field(default=3, ge=1, le=5, strict=True)
    category: str = Field(default='all', min_length=1, max_length=100)
    max_price: float | None = Field(default=None, ge=0, le=10000, strict=True)
    min_rating: int = Field(default=0, ge=0, le=5, strict=True)

    @field_validator('max_price', mode='before')
    @classmethod
    def reject_boolean_price(cls, value):
        if isinstance(value, bool):
            raise ValueError('Price must be numeric, not boolean.')
        return value


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command: str = Field(min_length=3, max_length=500)


@contextmanager
def connection():
    path = Path(os.environ.get('HARVEST_DB', str(ROOT / 'data' / 'harvest.db')))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, record_count INTEGER NOT NULL, result_json TEXT NOT NULL)')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.get('/', response_class=HTMLResponse)
def home():
    html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    return html.replace('href="/download/source.zip"', 'href="https://harvest-ammara-scraper.dazzlingadage1.chatgpt.site/download/source.zip"')


@app.get('/api/health')
def health():
    return dict(status='ok', runtime='Python / FastAPI', source='https://books.toscrape.com', max_pages=5, storage='SQLite', command_parser='deterministic')


@app.get('/api/categories')
async def categories():
    try:
        return {'categories': await get_categories()}
    except ScrapeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post('/api/plan')
async def plan(request: CommandRequest):
    try:
        return plan_command(request.command, await get_categories())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ScrapeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post('/api/scrape')
async def scrape(request: ScrapeRequest):
    try:
        result = await scrape_catalogue(request.pages, category=request.category, max_price=request.max_price, min_rating=request.min_rating)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ScrapeError as exc:
        raise HTTPException(502, str(exc)) from exc
    run_id = str(uuid4())
    with connection() as conn:
        conn.execute('INSERT INTO runs VALUES (?, ?, ?, ?)', (run_id, result['scraped_at'], result['count'], json.dumps(result)))
        conn.execute('DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY created_at DESC LIMIT 50)')
    return {**result, 'run_id': run_id}


@app.get('/api/runs')
def runs():
    with connection() as conn:
        return {'runs': [dict(r) for r in conn.execute('SELECT id, created_at, record_count FROM runs ORDER BY created_at DESC LIMIT 10')]}


@app.get('/download/source.zip')
def source():
    path = ROOT / 'source.zip'
    if not path.exists():
        raise HTTPException(404, 'Download the project from the hosted demo.')
    return FileResponse(path, filename='harvest-web-scraper.zip')
