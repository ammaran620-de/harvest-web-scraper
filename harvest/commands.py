"""Deterministic command-to-filter planning. No model or API key required."""
import re


def plan_command(command, categories):
    if not isinstance(command, str) or not 3 <= len(command.strip()) <= 500:
        raise ValueError('Enter a command between 3 and 500 characters.')
    text = command.lower().strip()
    if re.search(r'https?://', text):
        raise ValueError('Use the supported source selector; arbitrary website URLs are not supported.')
    plan = {'category': 'all', 'pages': 3, 'max_price': None, 'min_rating': 0}
    remaining = text
    matches = []
    for cat in sorted(categories, key=lambda c: len(c['name']), reverse=True):
        if cat['id'] == 'all':
            continue
        pattern = r'(?<!\w)' + re.escape(cat['name'].lower()) + r'(?!\w)'
        if re.search(pattern, remaining):
            matches.append(cat)
            remaining = re.sub(pattern, ' ', remaining)
    if len(matches) > 1:
        raise ValueError('Choose one category per collection.')
    if matches:
        plan['category'] = matches[0]['id']
    price = re.search(r'(?:under|below|less than|at most|maximum price|max price|<=|≤)\s*(?:£|gbp\s*)?(\d+(?:\.\d{1,2})?)', remaining)
    if price:
        plan['max_price'] = float(price.group(1))
        if plan['max_price'] > 10000:
            raise ValueError('Maximum price must be between 0 and 10000 GBP.')
        remaining = remaining[:price.start()] + ' ' + remaining[price.end():]
    rating = re.search(r'(?:rated|rating|at least)\s*(\d)(?:\s*\+)?\s*(?:stars?)?|\b(\d)\s*\+?\s*stars?(?:\s+or\s+above)?', remaining)
    if rating:
        plan['min_rating'] = int(rating.group(1) or rating.group(2))
        if not 1 <= plan['min_rating'] <= 5:
            raise ValueError('Rating must be from 1 to 5.')
        remaining = remaining[:rating.start()] + ' ' + remaining[rating.end():]
    pages = re.search(r'(?:max(?:imum)?\s*)?(\d+)\s*pages?', remaining)
    if pages:
        plan['pages'] = int(pages.group(1))
        if not 1 <= plan['pages'] <= 5:
            raise ValueError('The collection limit is 1–5 pages.')
        remaining = remaining[:pages.start()] + ' ' + remaining[pages.end():]
    allowed = {'collect','scrape','find','get','show','list','book','books','all','categories','category','from','the','with','and','or','above','export','download','as','csv','json','to','of','please','a'}
    unknown = [w for w in re.findall(r'[a-z]+|\d+', remaining) if w not in allowed]
    if unknown:
        raise ValueError('Could not interpret: ' + ', '.join(dict.fromkeys(unknown)) + '. Use a category, price, rating and page limit, or edit the controls directly.')
    name = next((c['name'] for c in categories if c['id'] == plan['category']), 'All categories')
    return {'plan': plan, 'category_name': name, 'parser': 'deterministic', 'note': 'Review this plan before collection. Price limits are inclusive (≤). Filters apply within the collected pages, not the entire catalogue.'}
