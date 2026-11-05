<h1 align="center">Harvest</h1>

<p align="center"><strong>A web scraper that shows its work.</strong></p>

<p align="center">
  Turn a collection rule into a clean dataset, trace each record to its source, and see what happened on every page.
</p>

<p align="center">
  <a href="https://harvest-ammara-scraper.dazzlingadage1.chatgpt.site/"><strong>Try the live demo →</strong></a>
  · <a href="#run-the-python-backend">Run FastAPI locally</a>
  · <a href="docs/VERIFICATION.md">See verification results</a>
</p>

[![Harvest Collection Builder with a scraped Mystery record and its source receipt](docs/collection-builder.jpg)](https://harvest-ammara-scraper.dazzlingadage1.chatgpt.site/)

## One command. A dataset you can trace.

> Collect Mystery books under £20, rated 4+ stars, max 3 pages

Open **Edit command**, apply the suggested plan, and select **Start collection**. Harvest turns the command into editable category, price, rating, and page limits using a deterministic parser. Expand any result to see its product URL and the page it came from. Select the columns you want, then download the filtered records as CSV or JSON.

| 50 | 100 | 26 |
| :---: | :---: | :---: |
| Categories discovered from the source | Records collected in a five-page hosted run | Python tests passed locally |

The source is [Books to Scrape](https://books.toscrape.com/), a public practice catalogue. Harvest follows the catalogue's pagination and applies filters to the pages it collects. The price cap is inclusive.

## When page two fails

One regression test gives Harvest a valid first page and an HTTP 404 on page two. The scraper keeps all **20 valid records** and reports **page 2** in `failed_pages`. A separate test returns a 503 on the first attempt and confirms that a retry recovers the page.

| Backend decision | What you can inspect |
| --- | --- |
| Bound every collection | A one-to-five-page cap, request timeouts, and a run deadline |
| Validate records before returning them | Malformed entries are skipped with warnings. Duplicate product URLs collapse to one record per run. |
| Preserve the collection trail | Each record carries its source page. The response includes page outcomes, counts, and warnings. |
| Save the result | FastAPI gives each stored run a `run_id`. SQLite retains the latest 50 runs and the history endpoint lists the latest 10. |

[Scraper implementation](harvest/scraper.py) · [Failure and retry tests](tests/test_scraper.py) · [FastAPI and SQLite](harvest/api.py)

## Run the Python backend

Clone this repository and open its root directory. Requires **Python 3.11+**. The FastAPI app serves the Collection Builder and exposes Swagger at `/docs`.

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn harvest.api:app --reload
```

**macOS or Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn harvest.api:app --reload
```

Open [the local app](http://127.0.0.1:8000/) or [Swagger](http://127.0.0.1:8000/docs). The hosted demo runs on a JavaScript Cloudflare Worker. This repository contains the Python/FastAPI service with SQLite history.

## Try the API

In Swagger, send this body to `POST /api/scrape` and inspect `items`, `pages_succeeded`, `failed_pages`, and `run_id`.

```json
{
  "category": "mystery_3",
  "max_price": 20,
  "min_rating": 4,
  "pages": 3
}
```

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Check the runtime, source, and page limit |
| `GET /api/categories` | Discover available categories |
| `POST /api/plan` | Turn a supported command into an editable collection plan |
| `POST /api/scrape` | Run a collection and save the result |
| `GET /api/runs` | Inspect recent Python runs |

## Verify the behaviour

Run the test suite with the project's virtual environment active.

```bash
python -m unittest discover -s tests -v
```

The suite covers command parsing, category pagination, price and rating filters, invalid records, retries, partial results, and SQLite persistence. The [GitHub Actions workflow](.github/workflows/tests.yml) defines a Python 3.11 and 3.12 test matrix followed by a Docker build.

```bash
docker build -t harvest-api .
docker run --rm -p 8000:8000 -v harvest-data:/app/data harvest-api
```

The Docker volume preserves `data/harvest.db` between runs. Set `HARVEST_DB` to use a different path.

**Ammara Noor** · [GitHub](https://github.com/ammaran620-de)
