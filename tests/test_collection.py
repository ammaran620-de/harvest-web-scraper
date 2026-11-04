import re
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient
from harvest.commands import plan_command
from harvest.scraper import SOURCE, ScrapeError, parse_categories, scrape_catalogue
from harvest.api import app
from test_scraper import HTML

HOME = '<a href="catalogue/category/books/mystery_3/index.html"> Mystery </a>'
CATS = parse_categories(HOME)
END = re.sub(r'<li class="next">.*?</li>', '', HTML, flags=re.S)

class CommandTests(unittest.TestCase):
    def test_complete_command(self):
        p = plan_command('Collect mystery books under £20, rated 4+ stars, max 3 pages', CATS)['plan']
        self.assertEqual(p, dict(category='mystery_3', pages=3, max_price=20., min_rating=4))
    def test_defaults(self):
        self.assertEqual(plan_command('Collect all books', CATS)['plan']['max_price'], None)
    def test_unknown_instructions_rejected(self):
        for text in ['scrape jobs', 'collect books 6 pages', 'collect books rated 8 stars', 'collect https://example.com', 'collect books under £10001']:
            with self.subTest(text=text), self.assertRaises(ValueError): plan_command(text,CATS)
    def test_longest_category(self):
        cats=CATS+[dict(id='fiction_10',name='Fiction'),dict(id='science-fiction_16',name='Science Fiction')]
        self.assertEqual(plan_command('Collect science fiction books',cats)['plan']['category'],'science-fiction_16')
    def test_multiple_categories_rejected(self):
        with self.assertRaises(ValueError):plan_command('collect mystery and fiction',CATS+[dict(id='fiction_10',name='Fiction')])
    def test_categories_deduplicated(self):
        self.assertEqual(len(parse_categories(HOME+HOME)),2)

class CategoryScrapeTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self,**kwargs):
        self.urls=[]
        def handler(r):
            self.urls.append(str(r.url))
            return httpx.Response(200,text=HOME if str(r.url)==SOURCE+'/' else END,headers={'content-type':'text/html'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await scrape_catalogue(5,client,category='mystery_3',**kwargs)
    async def test_stop_at_category_end(self):
        result=await self.collect()
        self.assertEqual(result['pages_succeeded'],[1]);self.assertEqual(result['stop_reason'],'end_of_catalogue')
        self.assertEqual(len(self.urls),2);self.assertEqual(result['count'],20)
        self.assertEqual(result['page_trace'][0]['http_status'],200)
    async def test_filters_applied_and_counted(self):
        result=await self.collect(max_price=51.77,min_rating=3)
        self.assertTrue(any(r['title']=='A Light in the Attic' for r in result['items']))
        self.assertTrue(all(r['price']<=51.77 and r['rating']>=3 for r in result['items']))
        self.assertEqual(result['scraped_count'],20);self.assertEqual(result['filtered_out'],20-result['count'])
    async def test_empty_match_is_success(self):
        result=await self.collect(max_price=0)
        self.assertEqual(result['items'],[]);self.assertEqual(result['count'],0)
        self.assertEqual(result['pages_succeeded'],[1])
    async def test_unknown_category(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=HOME,headers={'content-type':'text/html'}))) as client:
            with self.assertRaises(ValueError):await scrape_catalogue(1,client,category='unknown_999')

class CollectionApiTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def tearDown(self):self.client.close()
    def test_plan_endpoint(self):
        with patch('harvest.api.get_categories',new=AsyncMock(return_value=CATS)):
            r=self.client.post('/api/plan',json={'command':'collect mystery books under £20'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['plan']['category'],'mystery_3')
    def test_plan_error(self):
        with patch('harvest.api.get_categories',new=AsyncMock(return_value=CATS)):
            self.assertEqual(self.client.post('/api/plan',json={'command':'scrape jobs'}).status_code,422)
    def test_category_upstream_error(self):
        with patch('harvest.api.get_categories',new=AsyncMock(side_effect=ScrapeError('unavailable'))):
            self.assertEqual(self.client.get('/api/categories').status_code,502)
    def test_filter_validation(self):
        for body in [{'max_price':True},{'max_price':-1},{'min_rating':6},{'min_rating':True},{'category':'all','extra':1}]:
            with self.subTest(body=body):self.assertEqual(self.client.post('/api/scrape',json=body).status_code,422)
