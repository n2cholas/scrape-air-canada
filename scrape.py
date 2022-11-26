# Follow https://www.gregbrisebois.com/posts/chromedriver-in-wsl2/ to install ChromeDriver (use v107 instead of 86)
# Follow https://stackoverflow.com/a/61140905/7546401 to create cookies.json (Copy all as cURL (bash))
# %%
import json
import re
import time
from collections import defaultdict

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

pd.set_option('display.max_rows', 500)

headers = {
    'authority':
        'www.aircanada.com',
    'accept':
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',  # noqa: E501
    'accept-language':
        'en-GB,en-US;q=0.9,en;q=0.8',
    'cache-control':
        'max-age=0',
    'dnt':
        '1',
    'referer':
        'https://www.aircanada.com/ca/en/aco/home.html',
    'sec-ch-ua':
        '"Google Chrome";v="107", "Chromium";v="107", "Not=A?Brand";v="24"',
    'sec-ch-ua-mobile':
        '?0',
    'sec-ch-ua-platform':
        '"Windows"',
    'sec-fetch-dest':
        'document',
    'sec-fetch-mode':
        'navigate',
    'sec-fetch-site':
        'same-origin',
    'sec-fetch-user':
        '?1',
    'upgrade-insecure-requests':
        '1',
    'user-agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',  # noqa: E501
}

params = {
    'org0': 'YYZ',
    'dest0': 'ORD',
    'departureDate0': '2022-12-10',
    'lang': 'en-CA',
    'tripType': 'O',
    'ADT': '1',
    'YTH': '0',
    'CHD': '0',
    'INF': '0',
    'INS': '0',
    'marketCode': 'TNB',
}

chrome_options = Options()
chrome_options.add_argument("--headless")
# chrome_options.headless = True  # also works
DRIVER_PATH = '/usr/bin/chromedriver'

# %%
with open('cookies.json', 'r') as f:
    cookies = json.load(f)
center_date = '2022-12-10'

# %%
min_dep = str(pd.to_datetime(center_date) - pd.DateOffset(days=2))[:10]
max_dep = str(pd.to_datetime(center_date) + pd.DateOffset(days=2))[:10]

d = defaultdict(list)
with webdriver.Chrome(executable_path=DRIVER_PATH, options=chrome_options) as driver:
    for dt in pd.date_range(min_dep, max_dep).astype(str):
        params['departureDate0'] = dt
        URL = 'https://www.aircanada.com/aeroplan/redeem/availability/outbound?' + '&'.join(
            f'{k}={v}' for k, v in params.items())
        driver.get(URL)
        for k, v in cookies.items():
            driver.add_cookie({'name': k, 'value': v})

        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        for row in soup.find_all('kilo-upsell-row-cont'):
            stops, duration = row.find('kilo-flight-duration-pres').text.strip().split(' | ')
            departure = row.find('span', attrs={'class': re.compile('.*departure-time')}).text
            arrival = row.find('span', attrs={'class': re.compile('.*arrival-time')}).text
            for i, cell in enumerate(row.find_all('kilo-cabin-cell-pres')):
                try:
                    points, dollars = cell.find('kilo-price-with-points').text.split('+')
                except Exception as e:
                    print('points, dollars ', e)
                    continue
                try:
                    cl = cell.get('data-analytics-val').split('>')[1].split(' ')[0]
                except Exception as e:
                    cl = ['economy', 'business'][i]  # is this robust?
                    print('class getter failed', e, 'set to', cl)

                d['date'].append(dt)
                d['class'].append(cl)
                d['stops'].append(stops)
                d['duration'].append(duration)
                d['points'].append(points)
                d['dollars'].append(dollars)
                d['departure'].append(departure)
                d['arrival'].append(arrival)

df = pd.DataFrame(d)
# %%
cpp = 0.01
pts = df['points'].str[:-1].astype(float) * 1000
pts_dlrs = df['dollars'].str.removeprefix('CA $').astype(float) / cpp
df['apx_total_points'] = pts + pts_dlrs

# %%
print(df.sort_values(by='apx_total_points'))
