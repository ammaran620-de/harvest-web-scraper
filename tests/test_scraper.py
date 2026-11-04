import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
import httpx
from fastapi.testclient import TestClient
from harvest.scraper import parse_catalogue,scrape_catalogue,fetch_page,ScrapeError
from harvest.api import app
HTML=(Path(__file__).parent/'fixtures'/'catalogue.html').read_text(encoding='utf-8')
URL='https://books.toscrape.com/catalogue/page-1.html'
class ParsingTests(unittest.TestCase):
    def test_real_fixture_extracts_twenty_records(self):
        rows,w=parse_catalogue(HTML,URL)
        self.assertEqual(len(rows),20);self.assertFalse(w)
        self.assertEqual(rows[0]['title'],'A Light in the Attic');self.assertEqual(rows[0]['price'],51.77);self.assertEqual(rows[0]['rating'],3)
        self.assertEqual(rows[0]['url'],'https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html')
    def test_changed_template_raises(self):
        with self.assertRaises(ScrapeError):parse_catalogue('<html>maintenance</html>',URL)
    def test_invalid_price_skipped(self):
        rows,w=parse_catalogue(HTML.replace('£51.77','invalid'),URL);self.assertEqual(len(rows),19);self.assertEqual(len(w),1)
    def test_external_link_skipped(self):
        rows,w=parse_catalogue(HTML.replace('href="a-light-in-the-attic_1000/index.html" title=','href="https://elsewhere.example/product" title='),URL)
        self.assertEqual(len(rows),19)
class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_removal(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=HTML,headers={'content-type':'text/html'}))) as c:
            r=await scrape_catalogue(2,c)
        self.assertEqual(r['count'],20);self.assertEqual(r['duplicates_removed'],20);self.assertEqual(r['pages_succeeded'],[1,2])
    async def test_partial_failure_retains_results(self):
        def handler(r):return httpx.Response(404) if 'page-2' in str(r.url) else httpx.Response(200,text=HTML,headers={'content-type':'text/html'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:r=await scrape_catalogue(2,c)
        self.assertEqual(r['failed_pages'],[2]);self.assertEqual(r['count'],20)
    async def test_retry_transient_error(self):
        calls=[]
        def handler(r):
            calls.append(1)
            return httpx.Response(503) if len(calls)==1 else httpx.Response(200,text=HTML,headers={'content-type':'text/html'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:r,_=await fetch_page(c,1)
        self.assertEqual(len(calls),2);self.assertEqual(len(r),20)
    async def test_upstream_failure(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(404))) as c:
            with self.assertRaises(ScrapeError):await scrape_catalogue(1,c)
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'HARVEST_DB':str(Path(self.temp.name)/'test.db')});self.env.start();self.client=TestClient(app)
    def tearDown(self):self.client.close();self.env.stop();self.temp.cleanup()
    def test_health(self):self.assertEqual(self.client.get('/api/health').json()['status'],'ok')
    def test_input_validation(self):
        for b in [{'pages':0},{'pages':6},{'pages':True},{'pages':1.5},{'pages':1,'url':'http://localhost'}]:self.assertEqual(self.client.post('/api/scrape',json=b).status_code,422)
    def test_run_persisted(self):
        with patch('harvest.api.scrape_catalogue',new=AsyncMock(return_value={'count':20,'scraped_at':'2026-11-04T00:00:00+00:00','items':[]})):
            self.assertEqual(self.client.post('/api/scrape',json={'pages':1}).status_code,200)
        self.assertEqual(self.client.get('/api/runs').json()['runs'][0]['record_count'],20)
    def test_source_error_maps_to_502(self):
        with patch('harvest.api.scrape_catalogue',new=AsyncMock(side_effect=ScrapeError('Unavailable'))):self.assertEqual(self.client.post('/api/scrape',json={'pages':1}).status_code,502)
if __name__=='__main__':unittest.main()
