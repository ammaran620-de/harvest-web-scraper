# Verification evidence

Checks executed during development on 4 November 2026. These are observed results, not uptime guarantees.

| Check | Observed outcome | Scope |
|---|---|---|
| Python unittest suite | 26 tests passed | Executed locally with Python 3.12; network calls mocked in tests |
| Python live scrape | 40 valid products from two pages, no failed pages | Real HTTP requests to Books to Scrape |
| Hosted live scrape | 100 valid products from five pages | JavaScript Worker backend, not Python |
| Hosted title search | Sapiens query showed one of 40 records | Browser interaction |
| Filtered CSV download | One expected Sapiens record and expected column names | Downloaded file parsed and inspected |
| Python ZIP download | Download succeeded; archive integrity and required files checked | Published download |
| Hosted input validator | 20 validation, command and entity assertions passed | Node execution of the server validation function |
| GitHub Actions | Workflow supplied; run status not yet verified | Requires upload to the target repository |
| Docker | Dockerfile supplied; local build not verified | A Docker build is configured in CI |

## Automated Python cases

- Real HTML fixture yields 20 valid records with expected title, price, rating and product URL.
- A changed/empty template raises a clear extraction error.
- An invalid price is skipped with a warning.
- A product URL on another host is rejected.
- Duplicate product URLs across pages are removed.
- One failed page preserves successful records and records the failure.
- A transient 503 is retried once.
- Fully failed requests raise an extraction error.
- Health endpoint returns expected service state.
- Invalid page counts, types and extra URL fields are rejected.
- A successful API run is persisted and listed through SQLite.
- An upstream scrape error is mapped to HTTP 502.

## Runtime differences

| Capability | Python repository | Hosted demonstration |
|---|---|---|
| Server | FastAPI | JavaScript Cloudflare Worker |
| Extraction | HTTPX + HTMLParser | Fetch + HTMLRewriter |
| SQLite history | Yes | No |
| Automatic `/docs` | Yes | No |
| Cache | No | Warm-instance memory, up to 60 seconds |
| Source | Same fixed practice catalogue | Same fixed practice catalogue |
| Filtering/export UI | Included | Included |

The two runtimes have been smoke-tested separately. Exhaustive cross-runtime parity has not been established. Do not use the hosted UI alone as proof of Python deployment.

## Collection Builder revision

- Live Python category discovery returned 50 categories.
- A Mystery run with a five-page cap stopped after the category’s actual two pages: 32 unique products, no failed pages, one match at price ≤ £20 and rating ≥ 4 (`The Girl You Lost`).
- Additional fixture tests cover command defaults, complete plans, overlapping category names, rejected instructions, category pagination termination, inclusive filters, empty matches, category errors and API validation.
- Command planning does not use an LLM or paid API.

- Collection Builder browser checks against Python: a Travel command updated all four controls; the subsequent run returned 11 books. Filtering `Himalayas` downloaded a CSV parsed as one header row plus the expected product, with numeric price/rating and original URL. A zero-match title search showed its empty state.
