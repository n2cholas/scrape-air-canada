'''
Follow https://www.gregbrisebois.com/posts/chromedriver-in-wsl2/ to install ChromeDriver
(use v107 instead of 86)

Follow https://stackoverflow.com/a/61140905/7546401 to create cookies.json (Copy all as cURL (bash))
'''
# %%
import json
import re
import time
from collections import defaultdict

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from matplotlib import cm
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
    'dest0': 'NYC',
    'departureDate0': '2023-01-07',
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

center_date = '2023-01-07'
day_tol = 1

# %%
min_dep = str(pd.to_datetime(center_date) - pd.DateOffset(days=day_tol))[:10]
max_dep = str(pd.to_datetime(center_date) + pd.DateOffset(days=day_tol))[:10]
dates = pd.date_range(min_dep, max_dep).astype(str)

d = defaultdict(list)
row = None
N_RETRIES = 10
for dt in dates:
    for retry in range(1, N_RETRIES + 1):
        with webdriver.Chrome(executable_path=DRIVER_PATH, options=chrome_options) as driver:
            params['departureDate0'] = dt
            URL = 'https://www.aircanada.com/aeroplan/redeem/availability/outbound?' + '&'.join(
                f'{k}={v}' for k, v in params.items())
            driver.get(URL)
            time.sleep(3)  # is this sleep needed?
            for k, v in cookies.items():
                driver.add_cookie({'name': k, 'value': v})

            time.sleep(3)  # is this sleep needed?
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.find_all('kilo-upsell-row-cont')
            if not rows:
                print(f'No results for {dt}, retry {retry}...')
                continue

            for row in rows:
                stops, duration = row.find('kilo-flight-duration-pres').text.strip().split(' | ')
                departure = row.find('span', attrs={'class': re.compile('.*departure-time')}).text
                arrival = row.find('span', attrs={'class': re.compile('.*arrival-time')}).text
                operated_by = row.find('span', attrs={
                    'class': re.compile('.* operating-airline')
                }).text.removeprefix('Includes travel operated by ').removeprefix('Operated by ')
                dep_airport = row.find('span', attrs={
                    'class': re.compile('departure-name.*')
                }).text.strip()
                arr_airport = row.find('span', attrs={
                    'class': re.compile('arrival-name.*')
                }).text.strip()

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
                    d['operated_by'].append(operated_by)
                    d['stops'].append(stops)
                    d['duration'].append(duration)
                    d['departure'].append(departure)
                    d['arrival'].append(arrival)
                    d['departure_airport'].append(dep_airport)
                    d['arrival_airport'].append(arr_airport)
                    d['points'].append(points)
                    d['dollars'].append(dollars)

            print(f'Successfully pulled data for {dt}.')
            break
    else:
        print(f'Could not retrieve data for {dt}.')

raw_df = pd.DataFrame(d)
assert raw_df['date'].nunique() == len(dates), (raw_df['date'].unique(), dates)
# %%
cpp = 0.01
df = raw_df.copy()
df['points'] = (df['points'].str[:-1].astype(float) * 1000).astype(int)
df['dollars'] = df['dollars'].str.removeprefix('CA $').astype(int)
df['apx_points_only'] = (df['points'] + df['dollars'] / cpp).astype(int)
df.loc[df['operated_by'].str.len() == 0, 'operated_by'] = 'Air Canada'
dur_min = (df['duration']
    .str.extract('^(\d{1,2})hr(?:(\d{1,2})m)?').astype(float).fillna(0.0)  # noqa
    .apply(lambda row: row[0] * 60 + row[1], axis=1).astype(int)
)  # yapf: disable
df.insert(int(np.flatnonzero(df.columns == 'duration')[0] + 1), 'duration (min)', dur_min)


# %%
def rgb2hex(rgb):
    r, g, b, *_ = (rgb * 255).astype(int)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)


def text_color(rgb):
    r, g, b, *_ = (rgb * 255).astype(int)
    return '#000000' if r * 0.299 + g * 0.587 + b * 0.114 > 186 else '#ffffff'


def color_by(s1, s2, cmap='RdYlGn_r', vmax=None, vmin=None, cmap_min=0, cmap_max=1):
    vmin = vmin or s2.min()
    vmax = vmax or s2.max()
    inds = np.arange(cmap_min, cmap_max, (cmap_max - cmap_min) / (vmax - vmin))
    cmap_arr = cm.get_cmap(cmap)(inds)
    key2rgb = {d: cmap_arr[np.minimum(dm - vmin, vmax) - 1] for d, dm in zip(s1, s2)}
    return {
        k: f'background-color: {rgb2hex(rgb)}; color: {text_color(rgb)}'
        for k, rgb in key2rgb.items()
    }


strt, stop, cmap = 0.66, 1, cm.get_cmap('Purples')
date_colors = {
    d: 'background-color: ' + rgb2hex(c)
    for d, c in zip(dates, cmap(np.arange(strt, stop, (stop - strt) / len(dates))))
}

airports = df['arrival_airport'].unique()
airport_colors = {
    n: 'background-color: ' + rgb2hex(c)
    for n, c in zip(airports, cmap(np.arange(strt, stop, (stop - strt) / len(airports))))
}

non_stop = df.query('stops == "Non-stop"')
duration_colors = color_by(non_stop['duration'], non_stop['duration (min)'])

times_str = pd.concat([df['departure'], df['arrival']])
times = times_str.astype('datetime64[ns]')
time_colors = color_by(times_str,
                       times.dt.hour * 60 + times.dt.minute,
                       vmin=0,
                       vmax=24 * 60,
                       cmap='Purples',
                       cmap_min=0)

# %%
# yapf: disable
(df
    .query('stops == "Non-stop"')
    .drop(columns=['duration (min)'])
    .sort_values(by='apx_points_only', ignore_index=True)
    .style
    .format(thousands=',')
    .background_gradient(axis=0, subset='apx_points_only', cmap='RdYlGn_r', vmax=30_000)
    .applymap(lambda x: {
        **date_colors, **airport_colors, **duration_colors, **time_colors,
        'business': f'background-color: {rgb2hex(np.array(cmap(0.9)))}'
    }.get(x))
)
# yapf: enable
