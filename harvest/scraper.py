"""Public catalogue adapter with bounded pagination and traceable results."""
import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

SOURCE = 'https://books.toscrape.com'
RATINGS = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}
_category_cache = None


class ScrapeError(Exception):
    pass


def source_url_allowed(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.netloc == 'books.toscrape.com' and not p.query and not p.fragment


class CategoryParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.items = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            url = urljoin(self.base, a['href'])
            import re
            match = re.fullmatch(r'/catalogue/category/books/([a-z0-9-]+_\d+)/index.html', urlparse(url).path)
            if match and source_url_allowed(url):
                self.current = {'id': match.group(1), 'url': url, 'name': ''}

    def handle_data(self, data):
        if self.current is not None:
            self.current['name'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.current['name'] = ' '.join(self.current['name'].split())
            if self.current['name']:
                self.items.append(self.current)
            self.current = None


def parse_categories(html, base=SOURCE + '/'):
    parser = CategoryParser(base)
    parser.feed(html)
    found = list({c['id']: c for c in parser.items}.values())
    if not found:
        raise ScrapeError('Category list was not found; the source may have changed.')
    return [{'id': 'all', 'name': 'All categories', 'url': SOURCE + '/catalogue/page-1.html'}] + found


class CatalogueParser(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.rows, self.warnings = [], []
        self.current = None
        self.field = None
        self.buffer = []
        self.heading = False
        self.in_next = False
        self.next_url = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        if tag == 'li' and 'next' in classes:
            self.in_next = True
        if tag == 'a' and self.in_next:
            candidate = urljoin(self.url, a.get('href', ''))
            if source_url_allowed(candidate):
                self.next_url = candidate
        if tag == 'article' and 'product_pod' in classes:
            self.current = {'source_page': self.url}
        if self.current is None:
            return
        if tag == 'h3':
            self.heading = True
        if tag == 'a' and self.heading:
            self.current.update(title=a.get('title', '').strip(), url=urljoin(self.url, a.get('href', '')))
        if tag == 'p':
            if 'star-rating' in classes:
                self.current['rating'] = next((RATINGS[x] for x in classes if x in RATINGS), None)
            if 'price_color' in classes:
                self.field, self.buffer = 'price', []
            elif 'availability' in classes:
                self.field, self.buffer = 'availability', []

    def handle_data(self, data):
        if self.field:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'li':
            self.in_next = False
        if tag == 'h3':
            self.heading = False
        if self.current is not None and tag == 'p' and self.field:
            self.current[self.field] = ' '.join(''.join(self.buffer).split())
            self.field = None
        if tag == 'article' and self.current is not None:
            row = self.current
            try:
                price = Decimal(row.get('price', '').replace('£', '').strip())
                if not price.is_finite() or price < 0 or not row.get('title') or not row.get('availability') or row.get('rating') not in range(1, 6):
                    raise ValueError()
                if not source_url_allowed(row.get('url', '')):
                    raise ValueError()
                row.update(price=float(price), currency='GBP')
                self.rows.append(row)
            except (ValueError, InvalidOperation):
                self.warnings.append('Skipped malformed product on ' + self.url)
            self.current, self.field = None, None


def parse_page(html, url):
    parser = CatalogueParser(url)
    parser.feed(html)
    if not parser.rows:
        raise ScrapeError('No valid products found; source markup may have changed.')
    return parser


def parse_catalogue(html, url):
    p = parse_page(html, url)
    return p.rows, p.warnings


async def request_html(client, url):
    if not source_url_allowed(url):
        raise ScrapeError('Source URL is outside the supported adapter.')
    started = time.perf_counter()
    for attempt in range(2):
        try:
            response = await client.get(url)
            if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                await asyncio.sleep(.5)
                continue
            response.raise_for_status()
            if not 200 <= response.status_code < 300:
                raise ScrapeError('Unexpected redirect from source.')
            if 'text/html' not in response.headers.get('content-type', ''):
                raise ScrapeError('Source did not return HTML.')
            if len(response.content) > 2_000_000:
                raise ScrapeError('Source exceeded the page size limit.')
            return response.text, {'url': url, 'http_status': response.status_code, 'attempts': attempt + 1, 'duration_ms': round((time.perf_counter() - started) * 1000)}
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == 0:
                await asyncio.sleep(.5)
                continue
            raise ScrapeError('Source could not be reached after retry.') from exc
        except httpx.HTTPStatusError as exc:
            raise ScrapeError(f'Source returned HTTP {exc.response.status_code}.') from exc
    raise ScrapeError('Source unavailable.')


def make_client():
    return httpx.AsyncClient(timeout=8, follow_redirects=False, headers={'User-Agent': 'HarvestPortfolio/2.0 (bounded educational scraper)'})


async def get_categories(client=None):
    global _category_cache
    if client is None and _category_cache and time.monotonic() - _category_cache[0] < 600:
        return _category_cache[1]
    own = client is None
    if own:
        client = make_client()
    try:
        html, _ = await request_html(client, SOURCE + '/')
        categories = parse_categories(html)
        if own:
            _category_cache = (time.monotonic(), categories)
        return categories
    finally:
        if own:
            await client.aclose()


async def fetch_page(client, page):
    html, _ = await request_html(client, f'{SOURCE}/catalogue/page-{page}.html')
    return parse_catalogue(html, f'{SOURCE}/catalogue/page-{page}.html')


async def scrape_catalogue(pages=1, client=None, *, category='all', max_price=None, min_rating=0):
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 5:
        raise ValueError('pages must be an integer from 1 to 5')
    if isinstance(min_rating, bool) or not isinstance(min_rating, int) or not 0 <= min_rating <= 5:
        raise ValueError('min_rating must be from 0 to 5')
    if max_price is not None and (isinstance(max_price, bool) or not isinstance(max_price, (int, float)) or not 0 <= max_price <= 10000):
        raise ValueError('max_price must be a finite number from 0 to 10000')
    own = client is None
    if own:
        client = make_client()
    start = time.perf_counter()
    rows, warnings, failed, successful, trace = [], [], [], [], []
    name, url = 'All categories', SOURCE + '/catalogue/page-1.html'
    stop_reason = 'page_limit'
    try:
        async with asyncio.timeout(35):
            if category != 'all':
                cats = await get_categories(client)
                chosen = next((c for c in cats if c['id'] == category), None)
                if chosen is None:
                    raise ValueError('Unknown category. Refresh the category list.')
                name, url = chosen['name'], chosen['url']
            seen = set()
            for number in range(1, pages + 1):
                if url in seen:
                    warnings.append('Stopped a repeated pagination link.')
                    stop_reason = 'pagination_loop'
                    break
                seen.add(url)
                try:
                    html, event = await request_html(client, url)
                    parsed = parse_page(html, url)
                    rows.extend(parsed.rows)
                    warnings.extend(parsed.warnings)
                    successful.append(number)
                    trace.append({**event, 'page': number, 'status': 'collected', 'records': len(parsed.rows), 'skipped': len(parsed.warnings)})
                    if not parsed.next_url:
                        stop_reason = 'end_of_catalogue'
                        break
                    # Restrict next links to the current catalogue/category directory.
                    if urlparse(parsed.next_url).path.rsplit('/', 1)[0] != urlparse(url).path.rsplit('/', 1)[0]:
                        warnings.append('Stopped an unexpected pagination path.')
                        stop_reason = 'unexpected_next_link'
                        break
                    url = parsed.next_url
                except ScrapeError as exc:
                    failed.append(number)
                    warnings.append(str(exc))
                    trace.append({'page': number, 'url': url, 'status': 'failed', 'error': str(exc)})
                    # The fixed all-books adapter can identify the next page even after failure.
                    if category == 'all':
                        url = f'{SOURCE}/catalogue/page-{number + 1}.html'
                    else:
                        stop_reason = 'page_failure'
                        break
                if number < pages:
                    await asyncio.sleep(.25)
    except TimeoutError:
        stop_reason = 'deadline'
        warnings.append('Stopped at the 35-second run deadline.')
    finally:
        if own:
            await client.aclose()
    if not rows:
        raise ScrapeError('Unable to collect products. ' + '; '.join(warnings))
    unique = list({r['url']: r for r in rows}.values())
    for row in unique:
        row['category'] = name
    filtered = [r for r in unique if (max_price is None or r['price'] <= max_price) and r['rating'] >= min_rating]
    return dict(source=SOURCE, scraped_at=datetime.now(timezone.utc).isoformat(), duration_ms=round((time.perf_counter() - start) * 1000), pages_requested=pages, pages_succeeded=successful, failed_pages=failed, duplicates_removed=len(rows) - len(unique), scraped_count=len(unique), filtered_out=len(unique) - len(filtered), count=len(filtered), category=name, filters={'category': category, 'max_price': max_price, 'min_rating': min_rating}, stop_reason=stop_reason, page_trace=trace, warnings=warnings, runtime='Python / FastAPI', cache_hit=False, items=filtered)
