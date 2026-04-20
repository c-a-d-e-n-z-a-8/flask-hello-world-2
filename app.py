# -*- coding: utf-8 -*-
"""
Flask web UI — YfinanceQuery (standalone / git-friendly)

All required functions from main.py and report.py are embedded directly;
no local imports are needed. Safe to share or run without companion files.

Usage:
  pip install flask curl_cffi pandas numpy scipy talib pyecharts lxml
  python app.py               # listens on http://127.0.0.1:5000
  python app.py --port 8080
  python app.py --host 0.0.0.0 --port 8080
"""

import argparse
import datetime
import gc
import html as _html
import os
import sys
import tempfile
import traceback
from io import StringIO
from random import randint
from time import sleep, time

import numpy as np
np.seterr(all='ignore')

import pandas as pd

from curl_cffi import requests
from lxml import etree
from scipy.signal import argrelextrema
import talib

from pyecharts import options as opts
from pyecharts.charts import Kline, Line, Bar, Grid
from pyecharts.globals import CurrentConfig

from flask import Flask, redirect, request, send_file

# ── CDN for pyecharts assets ─────────────────────────────────────────────────
CurrentConfig.ONLINE_HOST = "https://cdn.jsdelivr.net/gh/c-a-d-e-n-z-a/misc@refs/heads/main/"

# ── URL constants ─────────────────────────────────────────────────────────────
cm_url = os.environ.get('CM_URL')
cm_url2 = os.environ.get('CM_URL2')
si_url = os.environ.get('SI_URL')
tw_sf_url = os.environ.get('TW_SF_URL')


# ═══════════════════════════════════════════════════════════════════════════════
# Functions from main.py
# ═══════════════════════════════════════════════════════════════════════════════

MA_TYPE           = 0     # 0=SMA, 1=EMA, 2=WMA … (talib MA_Type)

# ── Global state ─────────────────────────────────────────────────────────────
error_ticker = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ═══════════════════════════════════════════════════════════════════════════════

def print_exception(estring):
  print(f'[EXCEPTION] {error_ticker}\n{estring}\n{traceback.format_exc()}\n')


# ═══════════════════════════════════════════════════════════════════════════════
# Ticker helpers
# ═══════════════════════════════════════════════════════════════════════════════

def stock_is_tw_otc(ticker):
  """
  輸入格式 '00631L.' 或 '0050.' → 輸出 '00631L.TWO' 或 '0050.TW'
  若不含 '.' 則直接回傳（視為美股）。
  """
  if ticker.find('.') == -1:
    return ticker

  t_digit = ticker[:ticker.find('.')]
  t = t_digit + ".TW"

  if stock_is_tw_otc.ticker_exist == False:
    headers = {
      'referer': 'https://www.wantgoo.com/',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
      'x-requested-with': 'XMLHttpRequest',
    }
    try:
      r = requests.get('https://www.wantgoo.com/investrue/all-alive', headers=headers)
      if r.status_code != 404:
        r.encoding = 'utf-8'
        stock_is_tw_otc.df_ticker = pd.read_json(StringIO(r.text), orient='records')
        stock_is_tw_otc.ticker_exist = True
    except Exception:
      pass

  if stock_is_tw_otc.ticker_exist == True:
    try:
      exchange_query = stock_is_tw_otc.df_ticker.iloc[
        stock_is_tw_otc.df_ticker.loc[stock_is_tw_otc.df_ticker['id'] == t_digit].index
      ]['market'].iloc[0]
      if exchange_query == "OTC":
        t = t_digit + ".TWO"
      else:
        t = t_digit + ".TW"
    except Exception:
      pass

  return t

stock_is_tw_otc.ticker_exist = False


# ═══════════════════════════════════════════════════════════════════════════════
# Data readers
# ═══════════════════════════════════════════════════════════════════════════════

def stock_datareader_yahoo(ticker, start, end, session=None, div_recovered=False):

  headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

  crumb = ""
  startDate_epoch = int(datetime.datetime.combine(start, datetime.datetime.now().time()).timestamp())
  endDate_epoch   = int(datetime.datetime.combine(end,   datetime.datetime.now().time()).timestamp())

  csv_url = (
    f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    f"?period1={startDate_epoch}&period2={endDate_epoch}"
    f"&interval=1d&events=history&includeAdjustedClose=true&events=div%2Csplits"
  )
  if crumb:
    csv_url += f"&crumb={crumb}"

  print('  url=' + csv_url)
  r = session.get(csv_url, headers=headers, timeout=5)
  r.encoding = 'utf-8'
  print(f'  status_code={r.status_code}')

  if r.status_code != 200:
    return pd.DataFrame()

  data = r.json()
  quote_data    = data["chart"]["result"][0]["indicators"]["quote"][0]
  adjclose_data = data["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]

  df = pd.DataFrame({
    "Date":      data["chart"]["result"][0]["timestamp"],
    "Open":      quote_data["open"],
    "High":      quote_data["high"],
    "Low":       quote_data["low"],
    "Close":     quote_data["close"],
    "Adj Close": adjclose_data,
    "Volume":    quote_data["volume"],
  })

  if div_recovered:
    ratio        = df['Adj Close'] / df['Close']
    df['Open']  *= ratio
    df['High']  *= ratio
    df['Low']   *= ratio
    df['Volume'] /= ratio
    df['Close']  = df['Adj Close']

  df['Date'] = pd.to_datetime(df['Date'], unit='s')
  df.set_index('Date', inplace=True, drop=True)
  return df


def stock_datareader_cnyes(ticker, start, end, session=None):

  startDate_epoch = datetime.datetime.combine(start, datetime.datetime.now().time()).timestamp()
  endDate_epoch   = datetime.datetime.combine(end,   datetime.datetime.now().time()).timestamp()

  if '.TWG' in ticker.upper():
    symbol = 'TWG:' + ticker[:ticker.index('.')]
  else:
    symbol = 'TWS:' + ticker[:ticker.index('.')]

  headers = {"User-Agent": 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36'}
  url = (
    f'https://ws.api.cnyes.com/ws/api/v1/charting/history'
    f'?resolution=D&symbol={symbol}:STOCK&from={endDate_epoch:.0f}&to={startDate_epoch:.0f}'
  )
  print("  url=" + url)

  r = session.get(url, headers=headers)
  retry_no = 0
  while r.status_code != 200 and retry_no < 10:
    sleep(randint(1, 3))
    print('  Retrying ' + ticker)
    r = session.get(url, headers=headers)
    retry_no += 1

  json_data = r.json()['data']
  for key in ['s', 'quote', 'session', 'nextTime']:
    json_data.pop(key, None)

  df = pd.DataFrame.from_dict(json_data)
  df.index = pd.to_datetime(df['t'], errors='ignore', unit='s')
  df.drop(['t'], axis=1, inplace=True)
  df = df.rename(columns={'h': 'High', 'l': 'Low', 'o': 'Open', 'c': 'Close', 'v': 'Volume'})
  df = df.reindex(['High', 'Low', 'Open', 'Close', 'Volume'], axis=1)
  df['PE'] = ''
  df.sort_index(inplace=True)
  df.index.name = 'Date'
  return df


def stock_datareader_cnyes_index(ticker, start, end, session=None):

  startDate_epoch = datetime.datetime.combine(start, datetime.datetime.now().time()).timestamp()
  endDate_epoch   = datetime.datetime.combine(end,   datetime.datetime.now().time()).timestamp()

  ticker_change = {'^TWII': 'TWS:TSE01:INDEX', '^TWOII': 'TWS:OTC01:INDEX'}

  headers = {"User-Agent": 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36'}
  url = (
    f"https://ws.api.cnyes.com/ws/api/v1/charting/history"
    f"?symbol={ticker_change[ticker]}&resolution=D&quote=1"
    f"&from={endDate_epoch:.0f}&to={startDate_epoch:.0f}"
  )

  r = session.get(url, headers=headers)
  retry_no = 0
  while r.status_code != 200 and retry_no < 10:
    sleep(randint(1, 3))
    print('  Retrying ' + ticker)
    r = session.get(url, headers=headers)
    retry_no += 1

  json_data = r.json()['data']
  for key in ['s', 'quote', 'session', 'nextTime']:
    json_data.pop(key, None)

  df = pd.DataFrame.from_dict(json_data)
  df.index = pd.to_datetime(df['t'], errors='ignore', unit='s')
  df.drop(['t'], axis=1, inplace=True)
  df = df.rename(columns={'h': 'High', 'l': 'Low', 'o': 'Open', 'c': 'Close', 'v': 'Volume'})
  df = df.reindex(['High', 'Low', 'Open', 'Close', 'Volume'], axis=1)
  df['Adj Close'] = df['Close']
  df.sort_index(inplace=True)
  df.index.name = 'Date'
  df['Volume'] = [(x / 10 if x > df['Volume'].mean() * 8 else x) for x in df['Volume']]
  return df


# ═══════════════════════════════════════════════════════════════════════════════
# talib statistics
# ═══════════════════════════════════════════════════════════════════════════════

def talib_stats_calculation_stock(dataframe):
  dataframe['Slow K'], dataframe['Slow D'] = talib.STOCH(
    dataframe['High'].values, dataframe['Low'].values, dataframe['Close'].values,
    fastk_period=9, slowk_period=3, slowk_matype=MA_TYPE,
    slowd_period=3, slowd_matype=MA_TYPE,
  )
  dataframe['Slow J']   = 3 * dataframe['Slow K'] - 2 * dataframe['Slow D']
  dataframe['CCI']      = talib.CCI(dataframe['High'].values, dataframe['Low'].values, dataframe['Close'].values)
  dataframe['RSI 14']   = talib.RSI(dataframe['Close'], timeperiod=14)
  dataframe['MACD'], dataframe['MACD Signal'], dataframe['MACD Hist'] = talib.MACD(
    dataframe['Close'], fastperiod=12, slowperiod=26, signalperiod=9
  )


def talib_stats_calculation_stock_week(dataframe):
  talib_stats_calculation_stock(dataframe)
  dataframe['Vel']  = np.gradient((dataframe['High'] + dataframe['Low'] + dataframe['Close']) / 3)
  dataframe['Mom']  = dataframe['Vel'] * dataframe['Volume']
  dataframe['Work'] = dataframe['Mom'] * dataframe['Vel'] * np.sign(dataframe['Vel'])
  dataframe['Work'] = (dataframe['Work'] - dataframe['Work'].mean()) / dataframe['Work'].std()


def talib_stats_calculation_stock_day(dataframe, coin=False):
  talib_stats_calculation_stock(dataframe)

  if coin:
    dataframe['MA 10']  = talib.MA(dataframe['Close'], 14,  matype=MA_TYPE)
    dataframe['MA 20']  = talib.MA(dataframe['Close'], 30,  matype=MA_TYPE)
    dataframe['MA 60']  = talib.MA(dataframe['Close'], 89,  matype=MA_TYPE)
    dataframe['MA 150'] = talib.MA(dataframe['Close'], 222, matype=MA_TYPE)
    dataframe['MA 200'] = talib.MA(dataframe['Close'], 296, matype=MA_TYPE)
  else:
    dataframe['MA 10']  = talib.MA(dataframe['Close'], 10,  matype=MA_TYPE)
    dataframe['MA 20']  = talib.MA(dataframe['Close'], 20,  matype=MA_TYPE)
    dataframe['MA 60']  = talib.MA(dataframe['Close'], 60,  matype=MA_TYPE)
    dataframe['MA 150'] = talib.MA(dataframe['Close'], 150, matype=MA_TYPE)
    dataframe['MA 200'] = talib.MA(dataframe['Close'], 200, matype=MA_TYPE)

  dataframe['Vol MA 20'] = talib.MA(dataframe['Volume'], 20, matype=MA_TYPE)

  dataframe['ATR']   = talib.ATR(dataframe['High'], dataframe['Low'], dataframe['Close'], timeperiod=20)
  dataframe['ATR 5'] = talib.ATR(dataframe['High'], dataframe['Low'], dataframe['Close'], timeperiod=5)

  dataframe['Chandelier Exit'] = dataframe['High'].rolling(window=20).max() - 3 * dataframe['ATR']
  dataframe['Chandelier Stop'] = dataframe['Low'].rolling(window=20).min()  + 3 * dataframe['ATR']

  dataframe['Vel']    = np.gradient((dataframe['High'] + dataframe['Low'] + dataframe['Close']) / 3)
  dataframe['Vel (5)'] = talib.MA(dataframe['Vel'], 5, matype=MA_TYPE)
  dataframe['Vel (5)'] = (dataframe['Vel (5)'] - dataframe['Vel (5)'].mean()) / dataframe['Vel (5)'].std()

  dataframe['Mom']      = dataframe['Vel'] * dataframe['Volume']
  dataframe['Work']     = dataframe['Mom'] * dataframe['Vel'] * np.sign(dataframe['Vel'])
  dataframe['Work (5)'] = talib.MA(dataframe['Work'], 5, matype=MA_TYPE)
  dataframe['Work (5)'] = (dataframe['Work (5)'] - dataframe['Work (5)'].mean()) / dataframe['Work (5)'].std()

  dataframe['MACD (R)'], dataframe['MACD Signal (R)'], dataframe['MACD Hist (R)'] = talib.MACD(
    dataframe['Close'], fastperiod=50, slowperiod=120, signalperiod=30
  )

  dataframe['MA 200 Diff'] = (dataframe['Close'] - dataframe['MA 200']) / dataframe['MA 200'] * 100

  bb_period = 89 if coin else 60
  dataframe['BB Upper'], dataframe['BB Middle'], dataframe['BB Lower'] = talib.BBANDS(
    dataframe['Close'].values, timeperiod=bb_period, nbdevup=2, nbdevdn=2, matype=MA_TYPE
  )


# ═══════════════════════════════════════════════════════════════════════════════
# Volume Profile helpers
# ═══════════════════════════════════════════════════════════════════════════════

def vp_get_vp_and_poc(dataframe, bars=200, segs=150, fmt_str='{:.2f}'):
  """
  計算 Volume Profile 與 Point of Control (POC)。

  Returns
  -------
  (vp, poc_idx) : (pd.Series, str) or (None, -1)
      vp 為各價位區間的成交量，poc_idx 為最大成交量價位的索引。
  """
  if (dataframe['Volume'].iloc[-1] != 0) and (len(dataframe) > bars):
    vp_raw = dataframe.tail(bars)
    vp_high = vp_raw['High'].max()
    vp_low  = vp_raw['Low'].min()
    vp_levels     = []
    vp_levels_sum = []

    for s in range(segs + 1):
      vp_levels.append(vp_low + (s * (vp_high - vp_low) / segs))

    for i in range(len(vp_levels) - 1):
      vol_sum = 0
      for k in range(len(vp_raw)):
        if (vp_raw['High'].iloc[k] > vp_levels[i]) and (vp_raw['Low'].iloc[k] < vp_levels[i + 1]):
          vol_sum += vp_raw['Volume'].iloc[k]
      vp_levels_sum.append(vol_sum)

    vp = pd.Series(vp_levels_sum, index=vp_levels[:-1])  # segs vs. segs+1
    vp.index = vp.index.map(fmt_str.format)

    return vp, vp.idxmax()    # Return VP series and POC index
  else:
    return None, -1


# ═══════════════════════════════════════════════════════════════════════════════
# Critical points helpers (ported from report.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _math_strictly_increasing(L):
  return all(x < y for x, y in zip(L, L[1:]))

def _math_strictly_decreasing(L):
  return all(x > y for x, y in zip(L, L[1:]))


def _critical_points_before(stock_df, stock_df_w, stock_df_m, stock):
  """Port of stock_check_critical_points_before_resample.
  Returns list of note strings ([BUY]/[SELL]/[OTHER]).
  stock_df_w / stock_df_m are the original (non-resampled) weekly/monthly frames.
  """
  buy   = []
  sell  = []
  other = []

  c_l6ds      = stock_df['Close'].values[-6:]
  c_l3ds      = stock_df['Close'].values[-3:]
  c_l2d       = stock_df['Close'].values[-2]
  c_l1d       = stock_df['Close'].values[-1]
  c_l1d_60ma  = stock_df['MA 60'].values[-1]
  c_l2d_60ma  = stock_df['MA 60'].values[-2]
  c_l1d_200ma = stock_df['MA 200'].values[-1]
  c_l2d_200ma = stock_df['MA 200'].values[-2]

  v_l2d      = stock_df['Volume'].values[-2]
  v_l1d      = stock_df['Volume'].values[-1]
  v_l1d_ma20 = stock_df['Vol MA 20'].values[-1]

  o_l1d = stock_df['Open'].values[-1]

  k_l2d = stock_df['Slow K'].values[-2]
  k_l1d = stock_df['Slow K'].values[-1]
  d_l2d = stock_df['Slow D'].values[-2]
  d_l1d = stock_df['Slow D'].values[-1]

  k_l2w = stock_df_w['Slow K'].values[-2]
  k_l1w = stock_df_w['Slow K'].values[-1]
  d_l2w = stock_df_w['Slow D'].values[-2]
  d_l1w = stock_df_w['Slow D'].values[-1]

  k_l3ms = stock_df_m['Slow K'].values[-3:]
  k_l2m  = stock_df_m['Slow K'].values[-2]
  k_l1m  = stock_df_m['Slow K'].values[-1]
  d_l2m  = stock_df_m['Slow D'].values[-2]
  d_l1m  = stock_df_m['Slow D'].values[-1]

  r_l2d = stock_df['RSI 14'].values[-2]
  r_l1d = stock_df['RSI 14'].values[-1]
  r_l2w = stock_df_w['RSI 14'].values[-2]
  r_l1w = stock_df_w['RSI 14'].values[-1]

  # Buy
  if c_l1d < stock['priceFloor']:              buy.append('低於買點')
  if (k_l2d <= d_l2d) and (k_l1d > d_l1d):   buy.append('日KD黃金交叉')
  if (k_l2w <= d_l2w) and (k_l1w > d_l1w):   buy.append('週KD黃金交叉')
  if (k_l2m <= d_l2m) and (k_l1m > d_l1m):   buy.append('月KD黃金交叉')
  if (k_l2d <= k_l1w) and (k_l1d > k_l1w):   buy.append('日K大於週K')
  if (k_l2w <= k_l1m) and (k_l1w > k_l1m):   buy.append('週K大於月K')
  if (k_l1d < 20) and (k_l2d >= 20):          buy.append('日KD小於20')
  if (k_l1w < 20) and (k_l2w >= 20):          buy.append('週KD小於20')
  if (k_l1d < 20) and (k_l1w < 20):           buy.append('日週K小於20')
  if (r_l1d < 30) and (r_l2d >= 30):          buy.append('日RSI小於30')
  if (r_l1w < 30) and (r_l2w >= 30):          buy.append('週RSI小於30')
  if (v_l1d > 1.5*v_l2d) and (c_l1d > o_l1d):          buy.append('量大收紅')
  if _math_strictly_increasing(c_l3ds):                  buy.append('三日均價由下往上')
  if (v_l1d < 0.5*v_l2d) and (c_l1d > c_l2d):          buy.append('量縮價不跌')
  if c_l3ds.mean() > c_l6ds.mean():                      buy.append('三日均價大於六日均價')
  if (c_l1d > c_l1d_60ma)  and (c_l2d <= c_l2d_60ma):  buy.append('漲破季線')
  if (c_l1d > c_l1d_200ma) and (c_l2d <= c_l2d_200ma): buy.append('漲破200MA')

  # Sell
  if c_l1d > stock['priceCeiling']:             sell.append('高於賣點')
  if (k_l2d >= d_l2d) and (k_l1d < d_l1d):    sell.append('日KD死亡交叉')
  if (k_l2w >= d_l2w) and (k_l1w < d_l1w):    sell.append('週KD死亡交叉')
  if (k_l2m >= d_l2m) and (k_l1m < d_l1m):    sell.append('月KD死亡交叉')
  if (k_l2d >= k_l1w) and (k_l1d < k_l1w):    buy.append('日K小於週K')
  if (k_l2w >= k_l1m) and (k_l1w < k_l1m):    buy.append('週K小於月K')
  if (k_l1d > 80) and (k_l2d <= 80):           buy.append('日KD大於80')
  if (k_l1w > 80) and (k_l2w <= 80):           buy.append('週KD大於80')
  if (k_l1d > 80) and (k_l1w > 80):            buy.append('日週K大於80')
  if (r_l1d > 70) and (r_l2d <= 70):           sell.append('日RSI大於70')
  if (r_l1w > 70) and (r_l2w <= 70):           sell.append('週RSI大於70')
  if (v_l1d > 1.5*v_l2d) and (c_l1d <= o_l1d):         sell.append('量大收黑')
  if _math_strictly_decreasing(c_l3ds):                  sell.append('三日均價由上往下')
  if (v_l1d > 1.5*v_l2d) and (c_l1d < c_l2d):          sell.append('量漲價跌')
  if c_l3ds.mean() < c_l6ds.mean():                      sell.append('三日均價小於六日均價')
  if (c_l1d < c_l1d_60ma)  and (c_l2d >= c_l2d_60ma):  sell.append('跌破季線')
  if (c_l1d < c_l1d_200ma) and (c_l2d >= c_l2d_200ma): sell.append('跌破200MA')

  # Other
  if v_l1d > v_l1d_ma20 * 1.5:             other.append('日線爆大量')
  if v_l1d < v_l1d_ma20 * 0.5:             other.append('日線縮小量')
  if _math_strictly_increasing(k_l3ms):    other.append('三月KD由下往上')
  if _math_strictly_decreasing(k_l3ms):    other.append('三月KD由上往下')

  lines = []
  if buy:   lines.append('[BUY]  : ' + ' | '.join(buy))
  if sell:  lines.append('[SELL] : ' + ' | '.join(sell))
  if other: lines.append('[OTHER]: ' + ' | '.join(other))
  return lines


def _critical_points_after(stock_df, stock_df_w):
  """Port of stock_check_critical_points_after_resample.
  stock_df_w / stock_df_m must be resampled to daily (same integer index as stock_df).
  Returns (dates_list, notes):
    dates_list: list of [i, tag] — i is integer index into stock_df / dates[]
      Tags: UL=KD-buy  DL=KD-sell  UM=MACD-buy  DM=MACD-sell
            UP=general-buy  DP=general-sell  OP=BB-squeeze
    notes: list of critical note strings for today
  """
  notes     = []
  dates_list = []
  today_idx  = len(stock_df.index) - 1

  for i in range(20, len(stock_df['Slow K'])):
    # KD buy: weekly KD golden cross at oversold
    if (stock_df_w['Slow K'][i] >= stock_df_w['Slow D'][i]) and (stock_df_w['Slow K'][i-1] < stock_df_w['Slow D'][i-1]) \
      and (stock_df_w['Slow K'][i] < 20) and (stock_df_w['Slow D'][i] < 20):
      dates_list.append([i, 'UL'])
      if i == today_idx: notes.append('[KD-CRS]: 買點-週K上穿週D')

    # KD buy: combined KD golden cross at oversold
    if (stock_df['Combined K'][i] >= stock_df['Combined D'][i]) and (stock_df['Combined K'][i-1] < stock_df['Combined D'][i-1]) \
      and (stock_df['Combined K'][i] < 20) and (stock_df['Combined D'][i] < 20):
      dates_list.append([i, 'UL'])
      if i == today_idx: notes.append('[KD-CRS]: 買點-合K上穿合D')

    # KD sell: weekly KD death cross at overbought
    if (stock_df_w['Slow K'][i] <= stock_df_w['Slow D'][i]) and (stock_df_w['Slow K'][i-1] > stock_df_w['Slow D'][i-1]) \
      and (stock_df_w['Slow K'][i] > 80) and (stock_df_w['Slow D'][i] > 80):
      dates_list.append([i, 'DL'])
      if i == today_idx: notes.append('[KD-CRS]: 賣點-週K下穿週D')

    # KD sell: combined KD death cross at overbought
    if (stock_df['Combined K'][i] <= stock_df['Combined D'][i]) and (stock_df['Combined K'][i-1] > stock_df['Combined D'][i-1]) \
      and (stock_df['Combined K'][i] > 80) and (stock_df['Combined D'][i] > 80):
      dates_list.append([i, 'DL'])
      if i == today_idx: notes.append('[KD-CRS]: 賣點-合K下穿合D')

    # MACD week zero-crossing up
    if (stock_df_w['MACD Hist'][i] >= 0) and (stock_df_w['MACD Hist'][i-1] < 0) \
      and (stock_df_w['MACD Hist'][i-1] > stock_df_w['MACD Hist'][i-5]):
      dates_list.append([i, 'UM'])
      if i == today_idx: notes.append('[MACD-CRS]: 週上穿')

    # MACD week zero-crossing down
    if (stock_df_w['MACD Hist'][i] < 0) and (stock_df_w['MACD Hist'][i-1] >= 0) \
      and (stock_df_w['MACD Hist'][i-1] < stock_df_w['MACD Hist'][i-5]):
      dates_list.append([i, 'DM'])
      if i == today_idx: notes.append('[MACD-CRS]: 週下穿')

  # MACD week local extrema
  macd_l = argrelextrema(stock_df_w['MACD Hist'].values, np.less,    order=20)[0]
  for i in macd_l:
    dates_list.append([int(i), 'UM'])
    if i == today_idx: notes.append('[MACD-W]: 買點-週低點')

  macd_h = argrelextrema(stock_df_w['MACD Hist'].values, np.greater, order=20)[0]
  for i in macd_h:
    dates_list.append([int(i), 'DM'])
    if i == today_idx: notes.append('[MACD-W]: 賣點-週高點')

  # MA 200 Diff local extrema
  ma200_std = stock_df['MA 200 Diff'].std()
  for i in argrelextrema(stock_df['MA 200 Diff'].values, np.less,    order=20)[0]:
    if stock_df['MA 200 Diff'][i] < ma200_std * (-1):
      dates_list.append([int(i), 'UP'])
  for i in argrelextrema(stock_df['MA 200 Diff'].values, np.greater, order=20)[0]:
    if stock_df['MA 200 Diff'][i] > ma200_std:
      dates_list.append([int(i), 'DP'])

  # BB contraction
  idx_bb = argrelextrema((stock_df['BB Upper'] - stock_df['BB Lower']).values, np.less, order=20)[0]
  for i in idx_bb:
    dates_list.append([int(i), 'BB'])
  if (len(idx_bb) > 0) and (idx_bb[-1] > today_idx - 3):
    notes.append('[BB]: ' + ('賣點-收縮向下' if stock_df['MA 60'][idx_bb[-1]] >= stock_df['MA 60'][today_idx] else '買點-收縮向上'))

  # All long MAs turn direction together
  if (stock_df['MA 60'][today_idx] > stock_df['MA 60'][today_idx-1]) \
    and (stock_df['MA 150'][today_idx] > stock_df['MA 150'][today_idx-1]) \
    and (stock_df['MA 200'][today_idx] > stock_df['MA 200'][today_idx-1]) \
    and ((stock_df['MA 60'][today_idx-1]  < stock_df['MA 60'][today_idx-2])
      or (stock_df['MA 150'][today_idx-1] < stock_df['MA 150'][today_idx-2])
      or (stock_df['MA 200'][today_idx-1] < stock_df['MA 200'][today_idx-2])):
    dates_list.append([today_idx, 'UP'])
    notes.append('[MA-ALL]: 買點-長均線全上彎')

  if (stock_df['MA 60'][today_idx] < stock_df['MA 60'][today_idx-1]) \
    and (stock_df['MA 150'][today_idx] < stock_df['MA 150'][today_idx-1]) \
    and (stock_df['MA 200'][today_idx] < stock_df['MA 200'][today_idx-1]) \
    and ((stock_df['MA 60'][today_idx-1]  > stock_df['MA 60'][today_idx-2])
      or (stock_df['MA 150'][today_idx-1] > stock_df['MA 150'][today_idx-2])
      or (stock_df['MA 200'][today_idx-1] > stock_df['MA 200'][today_idx-2])):
    dates_list.append([today_idx, 'DP'])
    notes.append('[MA-ALL]: 賣點-長均線全下彎')

  # MA crossings (today only)
  _ma_cross = [
    ('Close', 'MA 60',  '買點 Close > MA 60',  '賣點 Close < MA 60'),
    ('Close', 'MA 150', '買點 Close > MA 150', '賣點 Close < MA 150'),
    ('Close', 'MA 200', '買點 Close > MA 200', '賣點 Close < MA 200'),
    ('MA 60',  'MA 150', '買點 MA 60 > MA 150', '賣點 MA 60 < MA 150'),
    ('MA 60',  'MA 200', '買點 MA 60 > MA 200', '賣點 MA 60 < MA 200'),
    ('MA 150', 'MA 200', '買點 MA 150 > MA 200','賣點 MA 150 < MA 200'),
  ]
  for col_a, col_b, lbl_buy, lbl_sell in _ma_cross:
    if stock_df[col_a].iloc[today_idx] > stock_df[col_b].iloc[today_idx] \
      and stock_df[col_a].iloc[today_idx-1] < stock_df[col_b].iloc[today_idx-1]:
      notes.append(f'[MA-CRS]: {lbl_buy}')
    if stock_df[col_a].iloc[today_idx] < stock_df[col_b].iloc[today_idx] \
      and stock_df[col_a].iloc[today_idx-1] > stock_df[col_b].iloc[today_idx-1]:
      notes.append(f'[MA-CRS]: {lbl_sell}')

  # Volume
  if   stock_df['Volume'].iloc[-1] > stock_df['Vol MA 20'].iloc[-1] + 2*stock_df['Vol MA 20'].std():
    notes.append('[VOL]: 極大量')
  elif stock_df['Volume'].iloc[-1] < stock_df['Vol MA 20'].iloc[-1] * 0.382:
    notes.append('[VOL]: 極小量')

  # Candlestick patterns (last 20 bars)
  _o, _h, _l, _c = stock_df['Open'][-20:], stock_df['High'][-20:], stock_df['Low'][-20:], stock_df['Close'][-20:]
  if talib.CDL3WHITESOLDIERS(_o, _h, _l, _c).iloc[-1] != 0: notes.append('[K-TYPE]: 買點 三紅K')
  if talib.CDL3BLACKCROWS(_o, _h, _l, _c).iloc[-1]    != 0: notes.append('[K-TYPE]: 賣點 三綠K')
  _cdl = talib.CDLTRISTAR(_o, _h, _l, _c).iloc[-1]
  if _cdl != 0: notes.append('[K-TYPE]: ' + ('買點 三星' if _cdl > 0 else '賣點 三星'))
  if talib.CDLMORNINGSTAR(_o, _h, _l, _c).iloc[-1] != 0: notes.append('[K-TYPE]: 買點 晨星')
  if talib.CDLEVENINGSTAR(_o, _h, _l, _c).iloc[-1] != 0: notes.append('[K-TYPE]: 賣點 暮星')

  return dates_list, notes


# ═══════════════════════════════════════════════════════════════════════════════
# Main combined chart function
# ═══════════════════════════════════════════════════════════════════════════════

def stock_one_chart(ticker_input, dir='.', display_days=365, finlab_token=''):
  """
  整合圖表：將技術指標圖與持倉圖（美股: FINRA/Benzinga short interest,
  台股: FinLab 三大法人）結合在同一個時間 X 軸上，輸出一個合併的 HTML 圖表。

  Parameters
  ----------
  ticker_input : str
      Yahoo Finance ticker symbol，例如 'AAPL'、'0050.'（台股自動補 .TW/.TWO）。
  dir : str
      輸出目錄，預設為目前目錄 '.'。
  display_days : int
      顯示天數，預設 365 天。
  finlab_token : str
      FinLab API token。提供時用 FinLab 抓台股三大法人/借券/融資券資料；
      留空（預設）則改用 histock 爬蟲。
  """

  print(f'[ONE CHART] ------------------------------------------------')

  # ── 0. 準備 ticker ────────────────────────────────────────────────
  ticker = stock_is_tw_otc(ticker_input).upper()
  global error_ticker
  error_ticker = ticker
  is_tw  = ('.TW' in ticker) or ('^TW' in ticker)
  is_us  = not is_tw and ('.' not in ticker) and ('^' not in ticker) and ('=' not in ticker)

  stock = {'ticker': ticker, 'description': ticker}

  read_days = display_days + 450
  today     = datetime.date.today()
  startDate = today - datetime.timedelta(days=read_days)
  endDate   = today

  s = requests.Session(impersonate="chrome")

  # ── 1. 取日 K 資料 ────────────────────────────────────────────────
  print(f'  Fetching OHLCV: {ticker}')
  try:
    if is_tw:
      if datetime.datetime.now().time().hour < 9:
        stock_df = stock_datareader_cnyes(ticker, startDate, endDate, session=s)
      else:
        stock_df = stock_datareader_yahoo(ticker, startDate, endDate, session=s, div_recovered=False)
    elif '^TW' in ticker:
      stock_df = stock_datareader_cnyes_index(ticker, startDate, endDate, session=s)
    else:
      stock_df = stock_datareader_yahoo(ticker, startDate, endDate, session=s, div_recovered=False)
  except Exception as e:
    print_exception(e)
    return

  if stock_df.empty:
    print('  ERROR: empty dataframe')
    return

  # ── 2. 資料清理與 Resample ─────────────────────────────────────────
  stock_df.dropna(inplace=True)
  stock_df = stock_df[~stock_df.index.duplicated(keep='first')]
  stock_df.index = stock_df.index.normalize()

  agg_tw   = {'High': 'max', 'Low': 'min', 'Open': 'first', 'Close': 'last', 'Volume': 'sum'}
  agg_else = {'High': 'max', 'Low': 'min', 'Open': 'first', 'Close': 'last', 'Volume': 'sum', 'Adj Close': 'last'}

  if is_tw and datetime.datetime.now().time().hour < 9:
    agg_tw['PE'] = 'last'
    stock_df_w = stock_df.resample('W-Fri').agg(agg_tw)
    stock_df_m = stock_df.resample('BME').agg(agg_tw)
  elif is_tw:
    agg_tw['Adj Close'] = 'last'
    stock_df_w = stock_df.resample('W-Fri').agg(agg_tw)
    stock_df_m = stock_df.resample('BME').agg(agg_tw)
  else:
    stock_df_w = stock_df.resample('W-Fri').agg(agg_else)
    stock_df_m = stock_df.resample('BME').agg(agg_else)

  stock_df_w.dropna(inplace=True)
  stock_df_m.dropna(inplace=True)

  stock_df.index.names   = ['Date']
  stock_df_w.index.names = ['Date']
  stock_df_m.index.names = ['Date']

  # ── 3. talib 計算 ─────────────────────────────────────────────────
  is_coin = '-USD' in ticker.upper()
  try:
    talib_stats_calculation_stock_day(stock_df, is_coin)
    talib_stats_calculation_stock_week(stock_df_w)
    talib_stats_calculation_stock(stock_df_m)
  except Exception as e:
    print_exception(e)
    return

  # ── 4. Resample 對齊日頻（供 pyecharts panels 使用） ───────────────
  if 'priceFloor'   not in stock: stock['priceFloor']   = stock_df['Close'].min()
  if 'priceCeiling' not in stock: stock['priceCeiling'] = stock_df['Close'].max()

  stock_df_w_resample = stock_df_w[['Slow K', 'Slow D', 'CCI', 'RSI 14', 'MACD Hist', 'Mom', 'Work']].reindex(stock_df.index)
  if stock_df_w_resample.index[-1] < stock_df_w.index[-1]:
    stock_df_w_resample.iloc[-1] = stock_df_w.iloc[-1][['Slow K', 'Slow D', 'CCI', 'RSI 14', 'MACD Hist', 'Mom', 'Work']]
  stock_df_w_resample.interpolate(method='linear', limit_direction='backward', inplace=True)

  stock_df_m_resample = stock_df_m[['Slow K', 'Slow D', 'CCI', 'RSI 14']].reindex(stock_df.index)
  if stock_df_m_resample.index[-1] < stock_df_m.index[-1]:
    stock_df_m_resample.iloc[-1] = stock_df_m.iloc[-1][['Slow K', 'Slow D', 'CCI', 'RSI 14']]
  stock_df_m_resample.interpolate(method='linear', limit_direction='backward', inplace=True)

  stock_df.reset_index(inplace=True)
  stock_df_w_r = stock_df_w_resample.reset_index()
  stock_df_m_r = stock_df_m_resample.reset_index()

  factor_w = 7 if '-' in ticker else 5
  factor_m = 30 if '-' in ticker else 20
  stock_df['Combined K'] = (stock_df['Slow K'] + stock_df_w_r['Slow K']*factor_w + stock_df_m_r['Slow K']*factor_m) / (1+factor_w+factor_m)
  stock_df['Combined D'] = (stock_df['Slow D'] + stock_df_w_r['Slow D']*factor_w + stock_df_m_r['Slow D']*factor_m) / (1+factor_w+factor_m)
  #stock_df['RS Score'] = 0

  # ── 4b. Critical points analysis ──────────────────────────────────
  sig_notes     = []
  sig_dates_list = []
  # UL = red triangle below Low (KD buy)
  # DL = green triangle above High (KD sell)
  # UM/DM = red/green arrow (MACD signals)
  # UP/DP = red/green diamond (MA/price signals)
  # BB = purple circle at midpoint (BB squeeze)
  try:
    sig_notes      = _critical_points_before(stock_df, stock_df_w, stock_df_m, stock)
    dl, sig_after  = _critical_points_after(stock_df, stock_df_w_r)
    sig_dates_list = dl
    sig_notes     += sig_after
    for note in sig_notes:
      print(f'  {note}')
  except Exception as e:
    print(f'  WARNING: critical points analysis failed: {e}')

  dates = [
    d.strftime('%Y%m%d') if hasattr(d, 'strftime') else str(d)[:10].replace('-', '')
    for d in stock_df['Date']
  ]

  # ── 5. 取持倉資料並對齊 stock_df 的日期索引 ───────────────────────
  df_pos = None

  if is_us:
    print(f'  Fetching US short interest (Benzinga): {ticker}')
    try:
      headers_benzinga = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
      }
      r = requests.get(f'{si_url}/quote/{ticker}/short-interest',
                       headers=headers_benzinga, verify=False)
      if r.status_code == 200:
        html  = r.text
        json_txt = None

        # Try old format: "shortInterest":[{...}]
        idx_b = html.find('"shortInterest":[{')
        if idx_b > -1:
          idx_e = html.find('],', idx_b)
          if idx_e > -1:
            json_txt = '[' + html[idx_b+17:idx_e+1]

        # Try new format (Next.js RSC): \\\"shortInterest\\\":[...{...}]
        if json_txt is None:
          esc_pattern = '\\"shortInterest\\":'
          idx_b = html.find(esc_pattern)
          if idx_b > -1:
            # Find the closing bracket, accounting for escaped quotes
            search_start = idx_b + len(esc_pattern)
            # Skip the opening '[' and possible RSC reference string like \"$62:...\"
            bracket_start = html.find('[', search_start)
            if bracket_start > -1:
              # Find matching ']' — scan for '],\\"' or '],' or ']}' pattern
              depth = 0
              idx_e = bracket_start
              for ci in range(bracket_start, min(bracket_start + 50000, len(html))):
                if html[ci] == '[':
                  depth += 1
                elif html[ci] == ']':
                  depth -= 1
                  if depth == 0:
                    idx_e = ci
                    break
              if idx_e > bracket_start:
                raw = html[bracket_start:idx_e+1]
                # Un-escape: \\\" → " and \\\\ → backslash
                raw = raw.replace('\\"', '"')
                # Remove RSC reference strings like "$62:props:children:..." at start of array
                import re
                raw = re.sub(r'^\[\s*"[^"]*"\s*,', '[', raw)
                json_txt = raw

        if json_txt is not None:
          df_benz  = pd.read_json(StringIO(json_txt), orient='records')
          # Some fields may be strings instead of numbers
          for col in ['totalShortInterest', 'averageDailyVolume', 'shortPriorMo',
                      'sharesFloat', 'sharesOutstanding']:
            if col in df_benz.columns:
              df_benz[col] = pd.to_numeric(df_benz[col], errors='coerce')
          df_benz['Date'] = pd.to_datetime(df_benz['recordDate'], format='%Y-%m-%d')
          df_benz.set_index('Date', inplace=True, drop=True)
          df_benz = df_benz.rename(columns={
            'totalShortInterest': 'currentShortPositionQuantity',
            'averageDailyVolume':  'averageDailyVolumeQuantity',
            'daysToCover':         'shortRatio',
            'shortPercentOfFloat': 'shortFloat',
          })
          df_benz['shortRatio'] = df_benz['currentShortPositionQuantity'] / df_benz['averageDailyVolumeQuantity']
          stock_dt_idx = pd.to_datetime(stock_df['Date'])
          df_pos = df_benz[['currentShortPositionQuantity', 'averageDailyVolumeQuantity',
                             'shortRatio', 'shortFloat']].reindex(stock_dt_idx, method='pad')
          df_pos.index = range(len(df_pos))
          print(f'  Short interest: {len(df_benz)} records loaded')
        else:
          print(f'  WARNING: Could not find shortInterest data in Benzinga page')
    except Exception as e:
      print(f'  WARNING: Failed to fetch short interest: {e}')

  elif is_tw:
    try:
      BARS  = len(stock_df)
      token = ticker[:ticker.index('.')] if '.' in ticker else ticker

      if finlab_token:
        # ── FinLab path ───────────────────────────────────────────────
        print(f'  Fetching TW institutional investors (FinLab): {ticker}')
        import finlab as _finlab
        from finlab import data as _finlab_data
        _finlab.login(finlab_token)

        volume_fl = _finlab_data.get('price:成交股數').tail(BARS).div(1000).round(0)
        foreign_agency_fl = (
          _finlab_data.get('institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)') +
          _finlab_data.get('institutional_investors_trading_summary:外資自營商買賣超股數')
        ).tail(BARS).div(1000)
        trust_fl  = _finlab_data.get('institutional_investors_trading_summary:投信買賣超股數').tail(BARS).div(1000)
        dealer_fl = (
          _finlab_data.get('institutional_investors_trading_summary:自營商買賣超股數(自行買賣)') +
          _finlab_data.get('institutional_investors_trading_summary:自營商買賣超股數(避險)')
        ).tail(BARS).div(1000)
        lending_sell_fl = _finlab_data.get('security_lending_sell:借券賣出餘額').tail(BARS).div(1000).round(0)
        margin_buy_fl   = _finlab_data.get('margin_transactions:融資今日餘額').tail(BARS)
        margin_sell_fl  = _finlab_data.get('margin_transactions:融券今日餘額').tail(BARS)

        col_check = lambda df, col: df[col] if col in df.columns else pd.Series(np.nan, index=df.index)
        df_all = pd.concat([
          col_check(volume_fl,         token),
          col_check(foreign_agency_fl, token),
          col_check(trust_fl,          token),
          col_check(dealer_fl,         token),
          col_check(lending_sell_fl,   token),
          col_check(margin_buy_fl,     token),
          col_check(margin_sell_fl,    token),
        ], axis=1)
        df_all.columns = ['volume', 'foreign', 'trust', 'dealer', 'foreignShortBalance', 'lendingBalance', 'borrowingBalance']

      else:
        # ── histock path ──────────────────────────────────────────────
        print(f'  Fetching TW institutional investors (histock): {ticker}')
        histock_url = tw_sf_url

        # Volume from OHLCV already fetched via Yahoo Finance
        vol_series = stock_df[['Date', 'Volume']].copy()
        vol_series = vol_series.set_index(pd.to_datetime(vol_series['Date']))['Volume'].div(1000).round(0)

        # Financing stats (融資/融券/借券賣出) from histock (?m=mg)
        df_fin = None
        try:
          import json as _json
          r_fin = s.get(f'{histock_url}?no={token}&m=mg', timeout=10, verify=False)
          if r_fin.status_code == 200:
            r_fin.encoding = 'utf-8'
            html_fin = r_fin.text
            fin_col_list = ["'融資餘額(張)'", "'融券餘額(張)'", "'借券賣出餘額(張)'"]
            fin_data_list = []
            for c in fin_col_list:
              idx_b = html_fin.find(f"{c},\r\n") + len(c) + 1
              if idx_b <= len(c) + 21:
                continue
              idx_e = html_fin.find(",\r\n", idx_b)
              raw = html_fin[idx_b:idx_e].strip()
              fin_data_list.append(_json.loads(raw[6:]))
            if len(fin_data_list) == 3:
              dfs_fin = [
                pd.DataFrame(l, columns=['date', fin_col_list[i]]).set_index('date')
                for i, l in enumerate(fin_data_list)
              ]
              df_fin = pd.concat(dfs_fin, axis=1)
              df_fin.index = pd.to_datetime(df_fin.index, unit='ms')
              df_fin.rename(columns={
                "'融資餘額(張)'": 'BB', "'融券餘額(張)'": 'SB', "'借券賣出餘額(張)'": 'LSB'
              }, inplace=True)
        except Exception as e_fin:
          print(f'  WARNING: histock financing fetch failed: {e_fin}')

        # Institutional investors (三大法人) from histock (?m=si)
        df_inst = None
        try:
          import re as _re, json as _json
          r_inst = s.get(f'{histock_url}?no={token}&m=si', timeout=10, verify=False)
          if r_inst.status_code == 200:
            r_inst.encoding = 'utf-8'
            html_inst = r_inst.text
            type_alias = [('foreign', 'FI'), ('ing', 'IT'), ('dealer', 'DL')]
            data_frames_inst = []
            for type_key, alias in type_alias:
              m_inst = _re.search(
                rf"type\s*==\s*'{type_key}'.*?threeData\s*=\s*'(\[\[.*?\]\])'",
                html_inst, _re.DOTALL,
              )
              if not m_inst:
                continue
              parsed = _json.loads(m_inst.group(1))
              df_i = pd.DataFrame(parsed, columns=['date', alias]).set_index('date')
              data_frames_inst.append(df_i)
            if data_frames_inst:
              df_inst = pd.concat(data_frames_inst, axis=1)
              df_inst.index = pd.to_datetime(df_inst.index, unit='ms')
        except Exception as e_inst:
          print(f'  WARNING: histock institutional fetch failed: {e_inst}')

        # Combine: volume + institutional (FI/IT/DL) + financing (LSB/SB/BB)
        nan_inst = pd.DataFrame(np.nan, index=vol_series.index, columns=['FI', 'IT', 'DL'])
        nan_fin  = pd.DataFrame(np.nan, index=vol_series.index, columns=['LSB', 'SB', 'BB'])
        df_all = pd.concat([
          vol_series,
          df_inst[['FI', 'IT', 'DL']] if df_inst is not None else nan_inst,
          df_fin[['LSB', 'SB', 'BB']] if df_fin is not None else nan_fin,
        ], axis=1)
        df_all.columns = ['volume', 'foreign', 'trust', 'dealer', 'foreignShortBalance', 'lendingBalance', 'borrowingBalance']

      # Get main force data from CMoney
      print(f'  Fetching CMoney MainForce: {token}')
      cm_headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': f'{cm_url}?action=mf&id={token}',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
        'X-Requested-With': 'XMLHttpRequest',
        'sec-ch-ua': '"Microsoft Edge";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
      }
      cm_params = {
        'action': 'mf',
        'count': str(BARS),
        'id': token,
        'ck': 'ML7EuNTM4B87LWAfCN94XIUVRMUVIHmjrEY^DHVQHBWwCRQrCXC3jMk$5OErz',
      }
      ck = ''
      try:
        r_ck = s.get(f'{cm_url}?action=mf&id={token}', headers=cm_headers)
        if r_ck.status_code == 200:
          idx_b = r_ck.text.index('var ck = "') + 10
          if idx_b > 0:
            idx_e = r_ck.text.index('";', idx_b)
            ck = r_ck.text[idx_b:idx_e]
            cm_params['ck'] = ck
      except Exception:
        pass

      mf_list = []
      mf_acc_list = []
      buy_sum_list = []
      epoch_list = []
      if ck != '':
        try:
          r_mf = s.get(cm_url2, params=cm_params, headers=cm_headers)
          if r_mf.status_code == 200:
            cm_data = r_mf.json()
            if cm_data is not None and "DataLine" in cm_data:
              for c in cm_data["DataLine"]:
                epoch_list.append(c[0])
                if c[8] is not None:
                  mf_list.append(c[8]["MfOvrBuy"])
                  mf_acc_list.append(c[8]["MfOvrBuySm"])
                  buy_sum_list.append(c[8]["BuyerSm"])
                else:
                  mf_list.append(0)
                  mf_acc_list.append(0)
                  buy_sum_list.append(0)
        except Exception as e_mf:
          print(f'  WARNING: CMoney MainForce failed: {e_mf}')

      if len(mf_list) > 0:
        df_mf = pd.DataFrame(
          {'mf': mf_list, 'mf_acc': mf_acc_list, 'buy_sum': buy_sum_list},
          index=pd.to_datetime(epoch_list, unit='ms').rename('date')
        )
        df_all = pd.concat([df_all, df_mf], axis=1, join="outer")
      else:
        df_all['mf'] = np.nan
        df_all['mf_acc'] = np.nan
        df_all['buy_sum'] = np.nan

      df_all['foreign_acc'] = df_all['foreign'].cumsum()
      df_all['trust_acc']   = df_all['trust'].cumsum()
      df_all['dealer_acc']  = df_all['dealer'].cumsum()

      df_all.fillna(value=np.nan, inplace=True)

      stock_dt_idx = pd.to_datetime(stock_df['Date'])
      df_pos       = df_all.reindex(stock_dt_idx, method='pad')
      df_pos.index = range(len(df_pos))

      gc.collect()
    except Exception as e:
      print(f'  WARNING: Failed to fetch FinLab data: {e}')

  # ── 6. 顏色與共用設定 ─────────────────────────────────────────────
  c_red    = "#ff0000"
  c_green  = "#008000"
  c_blue   = "#0000ff"
  c_black  = "#000000"
  c_orange = "#ffa500"
  c_white  = "#ffffff"
  c_gray   = "#cbcbcb"
  c_purple = "#e040fb"
  c_d      = c_blue
  c_w      = c_green
  c_m      = c_orange
  c_y      = c_red
  c_bkg    = "#ffffff"
  c_up     = "#ec0000"
  c_down   = "#00da3c"
  c_up_l   = "#8A0000"
  d_down_l = "#008F28"
  c_axis_p = "#777777"

  f_str = '{:.4f}' if stock_df['Close'].values[-1] < 1 else '{:.2f}'

  # ── 7. 計算輔助統計 ───────────────────────────────────────────────
  ma_200_diff_std = stock_df['MA 200 Diff'].std()
  atr_mean = stock_df['ATR'].fillna(0).mean()
  vol_mean = stock_df['Volume'].tail(200).mean()
  vol_std2 = 2 * stock_df['Volume'].tail(200).std()

  price_chg = pd.DataFrame()
  price_chg['diff'] = stock_df['Close'].diff()
  price_chg['up']   = stock_df.where(price_chg['diff'] > 0, 0)['Volume']
  price_chg['down'] = stock_df.where(price_chg['diff'] <= 0, 0)['Volume']

  data_ohlc = stock_df[['Open', 'Close', 'Low', 'High']].map(f_str.format).values.tolist()

  order_value = 20
  data_points = []
  floor_val   = float(stock['priceFloor'])
  ceiling_val = float(stock['priceCeiling'])

  idx_max = argrelextrema(stock_df['High'].values, np.greater, order=order_value)[0]
  if len(idx_max) > 0:
    for i in range(len(idx_max)):
      data_points.append(opts.MarkPointItem(
        name='L_MAX',
        coord=[dates[idx_max[i]], stock_df['High'][idx_max[i]] * 1.03],
        value=f'{stock_df["High"][idx_max[i]]:.2f}',
        symbol='circle', symbol_size=3,
        itemstyle_opts=opts.ItemStyleOpts(color=c_black),
      ))

  idx_min = argrelextrema(stock_df['Low'].values, np.less, order=order_value)[0]
  if len(idx_min) > 0:
    for i in range(len(idx_min)):
      data_points.append(opts.MarkPointItem(
        name='L_MIN',
        coord=[dates[idx_min[i]], stock_df['Low'][idx_min[i]] * 0.97],
        value=f'{stock_df["Low"][idx_min[i]]:.2f}',
        symbol='circle', symbol_size=3,
        itemstyle_opts=opts.ItemStyleOpts(color=c_black),
      ))

  close_offset  = f'{float(data_ohlc[-1][3])*1.03:.2f}'
  close_comment = (
    f'{data_ohlc[-1][1]}\n'
    f'{((float(data_ohlc[-1][1])-float(data_ohlc[-2][1]))/float(data_ohlc[-2][1]))*100:.2f}%'
  )
  data_points.append(opts.MarkPointItem(
    name='close', coord=[dates[-1], close_offset],
    value=close_comment, symbol_size=6, symbol='diamond',
    itemstyle_opts=opts.ItemStyleOpts(color=c_black),
  ))

  # ── 7b. Critical point markers ────────────────────────────────────
  # 標記說明（buy 紅色置於 Low×0.95，sell 綠色置於 High×1.05，BB 紫色置於中點）：
  #   UL  ▲ 紅色三角  Low×0.95  KD 買點：週KD 或 合成KD 在低檔（K<20）出現黃金交叉
  #   DL  ▲ 綠色三角  High×1.05 KD 賣點：週KD 或 合成KD 在高檔（K>80）出現死亡交叉
  #   UM  ↑ 紅色箭頭  Low×0.95  MACD 多訊號：週MACD Hist 零軸上穿，或週MACD Hist 局部低點反轉向上
  #   DM  ↓ 綠色箭頭  High×1.05 MACD 空訊號：週MACD Hist 零軸下穿，或週MACD Hist 局部高點反轉向下
  #   UP  ◆ 紅色菱形  Low×0.95  多方訊號：MA200 Diff 局部低點反轉，或三條長均線（60/150/200）同步由下轉上彎
  #   DP  ◆ 綠色菱形  High×1.05 空方訊號：MA200 Diff 局部高點反轉，或三條長均線（60/150/200）同步由上轉下彎
  #   BB  ● 紫色圓形  中點       布林收縮：BB 上下軌間距局部極小值，波動率壓縮、即將方向性突破（方向待確認）
  # tag → (symbol, size, color, price_factor, use_high)
  # use_high=True → High×factor, False → Low×factor, None → (High+Low)/2
  _c_buy  = '#ec0000'
  _c_sell = '#00da3c'
  _tag_cfg = {
    'UL': ('triangle', 8, _c_buy,  0.95, False),  # KD buy
    'DL': ('triangle', 8, _c_sell, 1.05, True ),  # KD sell
    'UM': ('arrow',    6, _c_buy,  0.95, False),  # MACD buy
    'DM': ('arrow',    6, _c_sell, 1.05, True ),  # MACD sell
    'UP': ('diamond',  6, _c_buy,  0.95, False),  # general buy
    'DP': ('diamond',  6, _c_sell, 1.05, True ),  # general sell
    'BB': ('circle',   5, '#e040fb', 1.00, None),  # BB squeeze
  }
  for idx_sig, tag in sig_dates_list:
    if idx_sig >= len(dates):
      continue
    cfg = _tag_cfg.get(tag)
    if cfg is None:
      continue
    sym, sz, col, factor, use_high = cfg
    if use_high is None:
      price = (stock_df['High'][idx_sig] + stock_df['Low'][idx_sig]) / 2
    elif use_high:
      price = stock_df['High'][idx_sig] * factor
    else:
      price = stock_df['Low'][idx_sig] * factor
    data_points.append(opts.MarkPointItem(
      name=tag, coord=[dates[idx_sig], price],
      value=tag, symbol=sym, symbol_size=sz,
      itemstyle_opts=opts.ItemStyleOpts(color=col),
    ))

  # ── 7c. Volume Profile / POC markline ──────────────────────────────
  VP_SEGS = 150
  VP_BARS = 200
  VP_SPAN = 50

  vp_marklines = []
  vp, poc_idx = vp_get_vp_and_poc(stock_df, bars=VP_BARS, segs=VP_SEGS, fmt_str=f_str)
  if poc_idx != -1:
    round_factor_v = vp.max() / VP_SPAN
    vp_hist = vp.apply(lambda x: round(x / round_factor_v))
    for price_level, bar_len in vp_hist.items():
      # Volume profile horizontal bar
      vp_marklines.append([
        opts.MarkLineItem(coord=[dates[-VP_BARS], price_level]),
        opts.MarkLineItem(coord=[dates[-VP_BARS + bar_len], price_level]),
      ])
      # POC line extending to the right edge
      if price_level == poc_idx:
        vp_marklines.append([
          opts.MarkLineItem(coord=[dates[-VP_BARS + bar_len + 5], price_level]),
          opts.MarkLineItem(coord=[dates[-1], price_level]),
        ])

  # ── 8. Grid index 配置 + 自動佈局計算 ───────────────────────────────
  # pyecharts panels: 0=kline, 1=ATR, 2=Vol, 3=Mom, 4=MACD, 5=KD, 6=RSI, 7=CCI
  # position panels (US): 8=short bar, 9=short ratio line
  # position panels (TW): 8=inst bar, 9=buysum, 10=acc line, 11=finance line
  GRID_PY_COUNT = 8

  # ═══ 佈局比例設定 (只需調整這裡的數字即可) ════════════════════════════
  kline_px       = 500                        # K線固定像素高度
  bottom_reserve = 3                          # 底部保留 (datazoom slider 空間)
  layout_start   = 2                          # 上邊界 (%)
  layout_gap     = 1                          # 圖表間距 (%)
  tech_ratios  = [20, 4, 4, 4, 4, 8, 8, 8]  # kline, ATR, Vol, Mom, MACD, KD, RSI, CCI
  if is_us and df_pos is not None:
    pos_ratios = [8, 8]                   # short_bar, short_ratio_line
  elif is_tw and df_pos is not None:
    pos_ratios = [8, 4, 8, 8]             # inst_bar, buysum_line, acc_line, finance_line
  else:
    pos_ratios = []
  # ═════════════════════════════════════════════════════════════════════

  all_ratios  = tech_ratios + pos_ratios
  n_charts    = len(all_ratios)
  total_gaps  = layout_gap * (n_charts - 1)
  ratio_sum   = sum(all_ratios)
  bottom_pct  = bottom_reserve / (ratio_sum + bottom_reserve) * 100
  avail_pct   = 100 - layout_start - total_gaps - bottom_pct

  # grid_layout[i] = (pos_top_str, height_str)  e.g. ('2%', '15%')
  grid_layout = []
  cur = layout_start
  for r in all_ratios:
    h = r / ratio_sum * avail_pct
    grid_layout.append((f'{cur:.1f}%', f'{h:.1f}%'))
    cur += h + layout_gap

  total_grids = GRID_PY_COUNT + len(pos_ratios)
  dz_indices  = list(range(total_grids))

  # notes overlay: 10% up from the bottom of the kline chart area
  _kline_top_f = float(grid_layout[0][0].rstrip('%'))
  _kline_h_f   = float(grid_layout[0][1].rstrip('%'))
  notes_top    = f'{_kline_top_f + _kline_h_f * 0.85:.1f}%'
  total_h_px  = int((ratio_sum + bottom_reserve) / tech_ratios[0] * kline_px)
  total_h     = f'{total_h_px}px'
  dz_pos_top  = f'{100 - bottom_pct + layout_gap:.1f}%'

  # ── 9. 技術指標 sub-charts ────────────────────────────────────────
  kline_chart = (
    Kline(init_opts=opts.InitOpts(animation_opts=opts.AnimationOpts(animation=False)))
    .add_xaxis(xaxis_data=dates)
    .add_yaxis(
      'K-LINE', data_ohlc,
      itemstyle_opts=opts.ItemStyleOpts(color=c_up, color0=c_down, border_color=c_up_l, border_color0=d_down_l),
      markpoint_opts=opts.MarkPointOpts(data=data_points, symbol='pin', label_opts=opts.LabelOpts(font_size=10)),
      markline_opts=opts.MarkLineOpts(
        data=vp_marklines,
        symbol=['none', 'none'],
        label_opts=opts.LabelOpts(is_show=False),
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.4, color=c_gray),
      ) if vp_marklines else None,
    )
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(is_scale=True, axislabel_opts=opts.LabelOpts(font_size=8),
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               splitline_opts=opts.SplitLineOpts(is_show=False)),
      yaxis_opts=opts.AxisOpts(is_scale=True, axislabel_opts=opts.LabelOpts(font_size=8)),
      tooltip_opts=opts.TooltipOpts(trigger='axis', axis_pointer_type='cross',
                                    textstyle_opts=opts.TextStyleOpts(font_size=8)),
      legend_opts=opts.LegendOpts(textstyle_opts=opts.TextStyleOpts(font_size=8)),
      datazoom_opts=[
        opts.DataZoomOpts(is_show=False, type_='inside', xaxis_index=dz_indices,
                          range_start=50, range_end=100, is_realtime=False),
        opts.DataZoomOpts(is_show=True, xaxis_index=dz_indices, type_='slider',
                          pos_top=dz_pos_top, range_start=50, range_end=100, is_realtime=False),
      ],
      axispointer_opts=opts.AxisPointerOpts(is_show=True, link=[{'xAxisIndex': 'all'}],
                                             label=opts.LabelOpts(background_color=c_axis_p)),
      title_opts=opts.TitleOpts(title=f'{ticker} - {dates[-1]}', pos_left='5%'),
      toolbox_opts=opts.ToolboxOpts(
        is_show=True,
        feature={'dataZoom': {'yAxisIndex': 'none'}, 'restore': {}, 'saveAsImage': {}},
      ),
      graphic_opts=opts.GraphicGroup(
        graphic_item=opts.GraphicItem(left='75%', top=notes_top),
        children=[
          opts.GraphicText(
            graphic_item=opts.GraphicItem(left='center', top='middle', z=100),
            graphic_textstyle_opts=opts.GraphicTextStyleOpts(
              text='\n'.join(sig_notes),
            ),
          ),
        ],
      ),
    )
  )

  lines_chart = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('MA 10', stock_df['MA 10'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_black),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_black), z=6,
               markline_opts=opts.MarkLineOpts(
                 data=[{'name': 'floor',   'yAxis': floor_val,   'lineStyle': {'color': c_black, 'type': 'dotted'}},
                       {'name': 'ceiling', 'yAxis': ceiling_val, 'lineStyle': {'color': c_black, 'type': 'dotted'}}],
                 symbol=['none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .add_yaxis('MA 20',  stock_df['MA 20'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.7, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=5)
    .add_yaxis('MA 60',  stock_df['MA 60'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.5, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=4)
    .add_yaxis('MA 150', stock_df['MA 150'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.3, color=c_y),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_y), z=3)
    .add_yaxis('MA 200', stock_df['MA 200'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.3, color=c_purple),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_purple), z=2)
    .add_yaxis('BB H', stock_df['BB Upper'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m),
               areastyle_opts=opts.AreaStyleOpts(opacity=0.2, color=c_m), z=-2)
    .add_yaxis('BB L', stock_df['BB Lower'].map(f_str.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m),
               areastyle_opts=opts.AreaStyleOpts(opacity=1, color=c_white), z=-1)
    .set_global_opts(xaxis_opts=opts.AxisOpts(type_='category'))
  )
  overlap_kline_line = kline_chart.overlap(lines_chart)

  atr_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('ATR 5', stock_df['ATR 5'].map('{:.2f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_black),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_black), z=6)
    .add_yaxis('ATR 20', stock_df['ATR'].map('{:.2f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d),
               markline_opts=opts.MarkLineOpts(data=[{'yAxis': atr_mean}], symbol=['none'],
                 label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')), z=5)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=1, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=1, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[1][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  volume_bar = (
    Bar()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('up', price_chg['up'].tolist(), stack='stack1',
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_up),
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': vol_mean}, {'yAxis': vol_mean + vol_std2}],
                 symbol=['none', 'none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .add_yaxis('down', price_chg['down'].tolist(), stack='stack1',
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_down))
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=2, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=2, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(is_show=False),
    )
  )
  vol_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('Vol MA 20', stock_df['Vol MA 20'].map('{:.0f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=100)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category'),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[2][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )
  overlap_vol_line = volume_bar.overlap(vol_lines)

  mom_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('Work (5)', stock_df['Work (5)'].map('{:.2f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.5, color=c_blue),
               areastyle_opts=opts.AreaStyleOpts(opacity=0.5, color=c_blue),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_blue), z=5)
    .add_yaxis('Work (W)', stock_df_w_resample['Work'].map('{:.2f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_green),
               areastyle_opts=opts.AreaStyleOpts(opacity=1, color=c_green),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_green), z=4)
    .add_yaxis('Vel (5)', stock_df['Vel (5)'].map('{:.2f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_black),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_black), z=6,
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': 0}, {'yAxis': 2}, {'yAxis': -2}],
                 symbol=['none', 'none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=3, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=3, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[3][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  macd_bars = (
    Bar()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('MACD Hist',   stock_df['MACD Hist'].map('{:.2f}'.format).tolist(),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=6)
    .add_yaxis('MACD Hist (W)', stock_df_w_resample['MACD Hist'].map('{:.2f}'.format).tolist(),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_w), z=5)
    .add_yaxis('MACD Hist (R)', stock_df['MACD Hist (R)'].map('{:.2f}'.format).tolist(),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=7)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=4, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=4, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[4][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  kd_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('Slow K9 (C)', stock_df['Combined K'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_red),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_red), z=8)
    .add_yaxis('Slow D9 (C)', stock_df['Combined D'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_red, type_='dotted'),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_red), z=7)
    .add_yaxis('Slow K9',   stock_df['Slow K'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=6)
    .add_yaxis('Slow D9',   stock_df['Slow D'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d, type_='dotted'),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=5)
    .add_yaxis('Slow K9 (W)', stock_df_w_resample['Slow K'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.7, color=c_w),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_w), z=4)
    .add_yaxis('Slow D9 (W)', stock_df_w_resample['Slow D'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.7, color=c_w, type_='dotted'),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_w), z=3)
    .add_yaxis('Slow K9 (M)', stock_df_m_resample['Slow K'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.5, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=2,
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': 20}, {'yAxis': 50}, {'yAxis': 80}],
                 symbol=['none', 'none', 'none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .add_yaxis('Slow D9 (M)', stock_df_m_resample['Slow D'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.5, color=c_m, type_='dotted'),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=1)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=5, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=5, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[5][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  rsi_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    .add_yaxis('MA 200 DIFF', stock_df['MA 200 Diff'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_purple),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_purple), z=4,
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': 0}, {'yAxis': ma_200_diff_std}, {'yAxis': -ma_200_diff_std}],
                 symbol=['none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_purple, type_='dotted')))
    .add_yaxis('RSI 14', stock_df['RSI 14'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=3,
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': 30}, {'yAxis': 50}, {'yAxis': 70}],
                 symbol=['none', 'none', 'none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .add_yaxis('RSI 14 (W)', stock_df_w_resample['RSI 14'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.7, color=c_w),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_w), z=2)
    .add_yaxis('RSI 14 (M)', stock_df_m_resample['RSI 14'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.5, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=1)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=6, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=6, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[6][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  cci_lines = (
    Line()
    .add_xaxis(xaxis_data=dates)
    #.add_yaxis('RS Score', stock_df['RS Score'].map('{:.1f}'.format).tolist(),
    #           is_smooth=False, is_symbol_show=False, is_hover_animation=False,
    #           linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_purple),
    #           label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_purple), z=4)
    .add_yaxis('CCI', stock_df['CCI'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=3,
               markline_opts=opts.MarkLineOpts(
                 data=[{'yAxis': 100}, {'yAxis': -100}, {'yAxis': 0}],
                 symbol=['none', 'none', 'none'], label_opts=opts.LabelOpts(is_show=False),
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.3, color=c_black, type_='dotted')))
    .add_yaxis('CCI (W)', stock_df_w_resample['CCI'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.7, color=c_w),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_w), z=2)
    .add_yaxis('CCI (M)', stock_df_m_resample['CCI'].map('{:.1f}'.format).tolist(),
               is_smooth=False, is_symbol_show=False, is_hover_animation=False,
               linestyle_opts=opts.LineStyleOpts(width=2, opacity=0.5, color=c_m),
               label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_m), z=1)
    .set_global_opts(
      xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=7, boundary_gap=False,
                               axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                               axislabel_opts=opts.LabelOpts(font_size=8),
                               splitline_opts=opts.SplitLineOpts(is_show=False),
                               split_number=20, min_='dataMin', max_='dataMax'),
      yaxis_opts=opts.AxisOpts(grid_index=7, is_scale=True, split_number=5,
                               axislabel_opts=opts.LabelOpts(font_size=8)),
      legend_opts=opts.LegendOpts(pos_top=grid_layout[7][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
    )
  )

  # ── 10. 持倉 sub-charts ───────────────────────────────────────────
  pos_charts = []

  if is_us and df_pos is not None:
    short_bar = (
      Bar()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis('Avg Daily Vol', df_pos['averageDailyVolumeQuantity'].tolist(),
                 stack='pos_stack0', label_opts=opts.LabelOpts(is_show=False),
                 itemstyle_opts=opts.ItemStyleOpts(color=c_black), gap='0%')
      .add_yaxis('Short Interest', df_pos['currentShortPositionQuantity'].map('{:.0f}'.format).tolist(),
                 stack='pos_stack1', label_opts=opts.LabelOpts(is_show=False),
                 itemstyle_opts=opts.ItemStyleOpts(color=c_d), z=3, gap='0%')
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=GRID_PY_COUNT,
                                 boundary_gap=False,
                                 axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                                 splitline_opts=opts.SplitLineOpts(is_show=False),
                                 axislabel_opts=opts.LabelOpts(font_size=8),
                                 split_number=20, min_='dataMin', max_='dataMax'),
        yaxis_opts=opts.AxisOpts(grid_index=GRID_PY_COUNT, is_scale=True, split_number=5,
                                 axislabel_opts=opts.LabelOpts(font_size=8)),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )
    short_ratio_line = (
      Line()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis('Short Ratio', df_pos['shortRatio'].map('{:.2f}'.format).tolist(),
                 is_smooth=False, is_symbol_show=False, is_hover_animation=False,
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_black),
                 label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_black),
                 z=4, is_connect_nones=True)
      .add_yaxis('Short Float', df_pos['shortFloat'].map('{:.3f}'.format).tolist(),
                 is_smooth=False, is_symbol_show=False, is_hover_animation=False,
                 linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_green),
                 label_opts=opts.LabelOpts(is_show=False), itemstyle_opts=opts.ItemStyleOpts(color=c_green),
                 z=3, is_connect_nones=True)
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(type_='category', is_scale=True, grid_index=GRID_PY_COUNT+1,
                                 boundary_gap=False,
                                 axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                                 axislabel_opts=opts.LabelOpts(font_size=8),
                                 splitline_opts=opts.SplitLineOpts(is_show=False),
                                 split_number=20, min_='dataMin', max_='dataMax'),
        yaxis_opts=opts.AxisOpts(grid_index=GRID_PY_COUNT+1, is_scale=True, split_number=5,
                                 axislabel_opts=opts.LabelOpts(font_size=8),
                                 splitarea_opts=opts.SplitAreaOpts(
                                   is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1))),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT+1][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )
    pos_charts.append((short_bar,        opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT][0], height=grid_layout[GRID_PY_COUNT][1], pos_left='2%', pos_right='2%')))
    pos_charts.append((short_ratio_line, opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT+1][0], height=grid_layout[GRID_PY_COUNT+1][1], pos_left='2%', pos_right='2%')))

  elif is_tw and df_pos is not None:
    inst_bar = (
      Bar()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis(
        series_name="Volume",
        y_axis=df_pos["volume"].tolist(),
        stack="pos_stack0",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_gray),
        gap="0%",
      )
      .add_yaxis(
        series_name="Foreign",
        y_axis=df_pos["foreign"].map('{:.0f}'.format).tolist(),
        stack="pos_stack1",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_d),
        z=3,
        gap="0%",
      )
      .add_yaxis(
        series_name="Trust",
        y_axis=df_pos["trust"].map('{:.0f}'.format).tolist(),
        stack="pos_stack1",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_w),
        z=4,
        gap="0%",
      )
      .add_yaxis(
        series_name="Dealer",
        y_axis=df_pos["dealer"].map('{:.0f}'.format).tolist(),
        stack="pos_stack1",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_m),
        z=5,
        gap="0%",
      )
      .add_yaxis(
        series_name="MainForce",
        y_axis=df_pos["mf"].map('{:.0f}'.format).tolist(),
        stack="pos_stack2",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_red),
        z=6,
        gap="0%",
      )
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(
          type_="category",
          is_scale=True,
          grid_index=GRID_PY_COUNT,
          boundary_gap=False,
          axisline_opts=opts.AxisLineOpts(is_on_zero=False),
          splitline_opts=opts.SplitLineOpts(is_show=False),
          axislabel_opts=opts.LabelOpts(font_size=8),
          split_number=20,
          min_="dataMin",
          max_="dataMax",
        ),
        yaxis_opts=opts.AxisOpts(
          grid_index=GRID_PY_COUNT,
          is_scale=True,
          split_number=5,
          axislabel_opts=opts.LabelOpts(font_size=8),
        ),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )

    buysum_line = (
      Bar()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis(
        series_name="Buy Point Sum",
        y_axis=df_pos["buy_sum"].tolist(),
        stack="pos_stack3",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_gray),
        gap="0%",
      )
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(
          type_="category",
          is_scale=True,
          grid_index=GRID_PY_COUNT+1,
          boundary_gap=False,
          axisline_opts=opts.AxisLineOpts(is_on_zero=False),
          splitline_opts=opts.SplitLineOpts(is_show=False),
          axislabel_opts=opts.LabelOpts(font_size=8),
          split_number=20,
          min_="dataMin",
          max_="dataMax",
        ),
        yaxis_opts=opts.AxisOpts(
          grid_index=GRID_PY_COUNT+1,
          is_scale=True,
          split_number=5,
          axislabel_opts=opts.LabelOpts(font_size=8),
        ),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT+1][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )

    acc_line = (
      Line()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis(
        series_name="Sum Acc",
        y_axis=(df_pos["foreign_acc"]+df_pos["trust_acc"]+df_pos["dealer_acc"]).map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_black),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_black),
        z=4,
        is_connect_nones=True,
      )
      .add_yaxis(
        series_name="Foreign Acc",
        y_axis=df_pos["foreign_acc"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_d),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_d),
        z=3,
        is_connect_nones=True,
      )
      .add_yaxis(
        series_name="Trust Acc",
        y_axis=df_pos["trust_acc"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_w),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_w),
        z=2,
        is_connect_nones=True,
      )
      .add_yaxis(
        series_name="Dealer Acc",
        y_axis=df_pos["dealer_acc"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_m),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_m),
        z=1,
        is_connect_nones=True,
      )
      .add_yaxis(
        series_name="MainForce Acc",
        y_axis=df_pos["mf_acc"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_red, type_="dotted"),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_red),
        z=5,
        is_connect_nones=True,
      )
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(
          type_="category",
          is_scale=True,
          grid_index=GRID_PY_COUNT+2,
          boundary_gap=False,
          axisline_opts=opts.AxisLineOpts(is_on_zero=False),
          axislabel_opts=opts.LabelOpts(font_size=8),
          splitline_opts=opts.SplitLineOpts(is_show=False),
          split_number=20,
          min_="dataMin",
          max_="dataMax",
        ),
        yaxis_opts=opts.AxisOpts(
          grid_index=GRID_PY_COUNT+2,
          is_scale=True,
          split_number=5,
          axislabel_opts=opts.LabelOpts(font_size=8),
          splitarea_opts=opts.SplitAreaOpts(
            is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
          ),
        ),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT+2][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )

    finance_line = (
      Line()
      .add_xaxis(xaxis_data=dates)
      .add_yaxis(
        series_name="Foreign Short Selling",
        y_axis=df_pos["foreignShortBalance"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_green),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_green),
        z=3,
      )
      .add_yaxis(
        series_name="Margin Trading",
        y_axis=df_pos["borrowingBalance"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_red),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_red),
        z=2,
      )
      .add_yaxis(
        series_name="Short Selling",
        y_axis=df_pos["lendingBalance"].map('{:.0f}'.format).tolist(),
        is_smooth=False,
        is_symbol_show=False,
        is_hover_animation=False,
        linestyle_opts=opts.LineStyleOpts(width=1, opacity=1, color=c_green, type_="dotted"),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=c_green),
        z=1,
      )
      .set_global_opts(
        xaxis_opts=opts.AxisOpts(
          type_="category",
          is_scale=True,
          grid_index=GRID_PY_COUNT+3,
          boundary_gap=False,
          axisline_opts=opts.AxisLineOpts(is_on_zero=False),
          axislabel_opts=opts.LabelOpts(font_size=8),
          splitline_opts=opts.SplitLineOpts(is_show=False),
          split_number=20,
          min_="dataMin",
          max_="dataMax",
        ),
        yaxis_opts=opts.AxisOpts(
          grid_index=GRID_PY_COUNT+3,
          is_scale=True,
          split_number=5,
          axislabel_opts=opts.LabelOpts(font_size=8),
          splitarea_opts=opts.SplitAreaOpts(
            is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
          ),
        ),
        legend_opts=opts.LegendOpts(pos_top=grid_layout[GRID_PY_COUNT+3][0], textstyle_opts=opts.TextStyleOpts(font_size=8)),
      )
    )

    pos_charts.append((inst_bar,      opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT][0],   height=grid_layout[GRID_PY_COUNT][1],   pos_left='2%', pos_right='2%')))
    pos_charts.append((buysum_line,   opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT+1][0], height=grid_layout[GRID_PY_COUNT+1][1], pos_left='2%', pos_right='2%')))
    pos_charts.append((acc_line,      opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT+2][0], height=grid_layout[GRID_PY_COUNT+2][1], pos_left='2%', pos_right='2%')))
    pos_charts.append((finance_line,  opts.GridOpts(pos_top=grid_layout[GRID_PY_COUNT+3][0], height=grid_layout[GRID_PY_COUNT+3][1], pos_left='2%', pos_right='2%')))


  # ── 11. Grid 佈局（全部由 grid_layout 自動計算）──────────────────────
  has_pos = len(pos_charts) > 0

  py_grids = [
    opts.GridOpts(pos_top=grid_layout[i][0], height=grid_layout[i][1], pos_left='2%', pos_right='2%')
    for i in range(GRID_PY_COUNT)
  ]

  py_sub_charts = [
    (overlap_kline_line, py_grids[0]),
    (atr_lines,          py_grids[1]),
    (overlap_vol_line,   py_grids[2]),
    (mom_lines,          py_grids[3]),
    (macd_bars,          py_grids[4]),
    (kd_lines,           py_grids[5]),
    (rsi_lines,          py_grids[6]),
    (cci_lines,          py_grids[7]),
  ]

  # ── 12. 組合 Grid ─────────────────────────────────────────────────
  grid_chart = Grid(
    init_opts=opts.InitOpts(
      animation_opts=opts.AnimationOpts(animation=False),
      width='100%',
      height=total_h,
      page_title=f'{ticker} - One Chart',
      bg_color='#ffffff',
    )
  )

  for chart, grid_opt in py_sub_charts:
    grid_chart.add(chart, grid_opts=grid_opt)
  for chart, grid_opt in pos_charts:
    grid_chart.add(chart, grid_opts=grid_opt)

  # ── 13. 輸出 HTML ─────────────────────────────────────────────────
  save_html = dir + '/' + ticker + '_OC.html'
  grid_chart.render(save_html)
  print(f'  Saved: {save_html}')
  return save_html


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════════════════════════════
# Report helpers (from report.py)
# ═══════════════════════════════════════════════════════════════════════════════


print_time_delta_start = time()
def print_time_delta(now, note):
  global print_time_delta_start
  print("  {:07.3f}: {}".format(now-print_time_delta_start, note))
  print_time_delta_start = now




def report_get_finviz_overview(token):

  print_time_delta_start = time()

  url = 'https://finviz.com/quote.ashx?t=' + token
  headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'}
  r = requests.get(url, headers=headers, verify=False, timeout=10)
  r.encoding = 'utf-8'

  # https://www.quotemedia.com/quotetools/symbolHelp/SymbolHelp_US_Version_Default.html?fbclid=IwAR0yadiPkg-Mp4X-guCwFYH7oJLnO2TvXgGy1a_sn-_idcAxNpycNiLsLOE
  chart_src = f'https://app.quotemedia.com/quotetools/getChart?webmasterId=91386&symbol={token}&chtype=FinancialLine&chcon=on&chdon=on&chfrmon=on&chscale=1d&chton=on&chwid=800&chhig=380&chln=ffa500&chfill=ffa500&chfnts=10&chbdr=000000&chbgch=ffffffff&chgrd=cccccc&svg=false&lang=en&locale=en'
  intraday_chart = f'<div align="center"><a href="https://www.marketwatch.com/investing/stock/{token}/analystestimates" target="_blank"><img style="max-height:100%; max-width:100%; object-fit:contain" src={chart_src}></a></div>'

  stats = rating = insider = news = ''

  if r.status_code == 200:
    selector = etree.HTML(r.text)

    result = selector.xpath("//table[@class='js-snapshot-table snapshot-table2 screener_snapshot-table-body']")
    if len(result) > 0:
      stats = etree.tostring(result[0], encoding='unicode', pretty_print=True).replace('href="', 'href="https://finviz.com/')

    result = selector.xpath("//table[@class='js-table-ratings styled-table-new is-rounded is-small']")                             
    if len(result) > 0:
      rating = etree.tostring(result[0], encoding='unicode', pretty_print=True)
  
    result = selector.xpath("//table[@class='body-table styled-table-new is-rounded p-0 mt-2']")
    if len(result) > 0:
      insider = etree.tostring(result[0], encoding='unicode', pretty_print=True)

    #result = selector.xpath("//table[@class='fullview-news-outer']")
    result = selector.xpath("//div[@class='body-table-news-wrapper news-table_wrapper']")
    if len(result) > 0:
      news = '<div align="center">' + etree.tostring(result[0], encoding='unicode', pretty_print=True) + '</div>'

    overview = '\n\n<hr color="#ff8000" align="center">\n'.join([intraday_chart, stats, rating, insider, news]).replace('width="100%"', 'align="center" width="70%"').replace('<table', '<table align="center" style="margin:0 auto"')
    print_time_delta(time(), "[FINVIZ] " + url)

    return overview

  else:
    print(f'Finviz response error code: {r.status_code}')
    return ''




def report_get_fbs_position_overview(token):

  user_agent = 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.170 Mobile Safari/537.36'
  headers = {"User-Agent":user_agent}

  if token.find('.TW') > 0:
    print_time_delta_start = time()
  
    url_overview = 'http://fubon-ebrokerdj.fbs.com.tw/Z/ZC/ZCX/ZCXFUBON_' + token[0:token.index('.TW')] + '.djhtm'
    url_major = 'http://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco_' + token[0:token.index('.TW')] + '.djhtm'
    url_inst = 'http://fubon-ebrokerdj.fbs.com.tw/z/zc/zcl/zcl.djhtm?a=' + token[0:token.index('.TW')] + '&b=3'
    #url_inst = 'http://fubon-ebrokerdj.fbs.com.tw/z/zc/zcl/zcl_' + token[0:token.index('.TW')] + '.djhtm'
    url_news = 'https://fubon-ebrokerdj.fbs.com.tw/z/zc/zcv/zcv_' + token[0:token.index('.TW')] + '_E_1.djhtm'  
    absolute_prefix = 'http://fubon-ebrokerdj.fbs.com.tw'
       
    stats = ''

    # Handle overview
    r = requests.get(url_overview, headers=headers, verify=False, timeout=5)
    r.encoding = 'big5'
    if r.status_code == 200:

      selector = etree.HTML(r.text)

      # Chart
      results = selector.xpath("//div[@class='midcontent_infomation02']")
      if len(results) > 0:
        result = results[0]

        for node in result.xpath('//img'):
          img_link = node.get('src').replace('169_133', '520_300')
          url_new = absolute_prefix + img_link
          node.set('src', url_new)

        for node in result.xpath('//*[@class or @id]'):
          node.attrib.pop('class', None)  # None is to not raise an exception if xyz does not exist
          node.attrib.pop('id', None)
          #node.attrib.clear()   # Clear all attributes

        tmp_html = etree.tostring(result, encoding='unicode', pretty_print=True).replace('&#13;\n', '\n') 
        stats = '  <div align="center">\n    ' + tmp_html + '\n  </div>'
        
        # Table for valuation
        result1 = result.getnext().getnext().getnext()
        for node in result1.xpath('//*[@class or @id]'):
          node.attrib.pop('class', None)  # None is to not raise an exception if xyz does not exist
          node.attrib.pop('id', None)
          #node.attrib.clear()   # Clear all attributes

        tmp_html = etree.tostring(result1, encoding='unicode', pretty_print=True).replace('&#13;\n', '\n')
        stats += '  <div align="center">\n    ' + tmp_html + '\n  </div>'
      
    
    # Handle major investors
    r = requests.get(url_major, headers=headers, verify=False, timeout=5)
    r.encoding = 'big5'
    if r.status_code == 200:

      selector = etree.HTML(r.text)

      results = selector.xpath("//table[@id='oMainTable']")
      if len(results) > 0:
        result = results[0]
        titles = result.xpath("//tr[@id='oScrollHead']")

        for idx, title in enumerate(titles):
          if idx != 2:
            result.remove(title)

        for node in result.xpath('//*[@href]'):
          href = node.get('href')
          url_new = absolute_prefix + href
          node.set('href', url_new)
          node.set('target', '_blank')

        for node in result.xpath('//*[@class or @id]'):
          node.attrib.pop('class', None)  # None is to not raise an exception if xyz does not exist
          node.attrib.pop('id', None)
          #node.attrib.clear()   # Clear all attributes

        # Workaround for eTree select script issue
        tmp_html = etree.tostring(result, encoding='unicode', pretty_print=True).replace('&#13;\n', '\n    ').replace('券商分點-進出明細', '<a href="' + url_major + '" target="_blank">券商分點-進出明細</a>', 1)
        tmp_html_end = tmp_html.index('</table>') + 8
        stats += '  <div align="center">\n    ' + tmp_html[0:tmp_html_end] + '\n  </div>'


    # Handle 3 institutes
    r = requests.get(url_inst, headers=headers, timeout=5)
    r.encoding = 'big5'
    if r.status_code == 200:
      selector = etree.HTML(r.text)

      results = selector.xpath("//table[@class='t01']")
      if len(results) > 0:
        result = results[0]
        titles = result.xpath("//tr[@id='oScrollHead']")

        for idx, title in enumerate(titles):
          if idx != 2:
            result.remove(title)

        # Workaround for eTree select script issue
        tmp_html = etree.tostring(result, encoding='unicode', pretty_print=True).replace('&#13;\n', '\n    ').replace('法人持股明細', '<a href="' + url_inst + '" target="_blank">法人持股明細</a>', 1)
        tmp_html_end = tmp_html.index('</table>') + 8
        stats += '\n  <br>\n  <div align="center">\n    ' + tmp_html[0:tmp_html_end] + '\n  <br>\n</div>'
      
      
    # Handle stock news
    r = requests.get(url_news, headers=headers, timeout=5, verify=False)
    r.encoding = 'big5'
    if r.status_code == 200:
      selector = etree.HTML(r.text)

      results = selector.xpath("//table[@class='t01']")
      if len(results) > 0:
        result = results[0]
        
        for node in result.xpath('//*[@href]'):
          href = node.get('href')
          url_new = absolute_prefix + href
          node.set('href', url_new)
          node.set('target', '_blank')

        for node in result.xpath('//*[@class or @id]'):
          node.attrib.pop('class', None)  # None is to not raise an exception if xyz does not exist
          node.attrib.pop('id', None)
          #node.attrib.clear()   # Clear all attributes

        # Workaround for eTree select script issue
        tmp_html = etree.tostring(result, encoding='unicode', pretty_print=True).replace('&#13;\n', '\n    ').replace('動態報導', '<a href="' + url_news + '" target="_blank">動態報導</a>', 1)
        stats += '\n  <br>\n  <div align="center">\n    ' + tmp_html.replace('width="100%"', 'width="50%"', 1) + '\n  <br>\n</div>'

    print_time_delta(time(), "[FBS] " + url_overview + " | " + url_major + " | " + url_inst + " | " + url_news)
           
    return stats      
    
  elif token.find('^TW') == 0:
    print_time_delta_start = time()
    index_iframe = '<div align="center">\n    <a href="https://fubon-ebrokerdj.fbs.com.tw/z/zb/zba/zba.djhtm" target="_blank">資金流向</a><br><br>\n<iframe src="https://jpc.moneydj.com/z/skv.djhtm?ASPID=sysjust&showAll=1&overlay=0&showTable=1&showLogo=0&w=600&h=600" width="600" height="600" frameborder="0" scrolling="no"></iframe>\n  </div>'
    print_time_delta(time(), "[FBS] Taiwan Index")
    
    return index_iframe
    
  else:
    return ''




def report_get_position_pyramid(token):

  headers = {
    'authority': 'norway.twsthr.info',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
    'cache-control': 'max-age=0',
    'referer': 'https://norway.twsthr.info/StockHolders.aspx',
    'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
  }
  
  html = ''

  if token.find('.TW') > 0:
    print_time_delta_start = time()
    params = {'stock': token[0:token.index('.TW')]}

    r = requests.get('https://norway.twsthr.info/StockHolders.aspx', params=params, headers=headers, verify=False, timeout=5)
    #print(r.text)

    if r.status_code == 200:
      '''
      old_string = '<script type="c900c2a7c1e12d05ff5802d2-text/javascript">\nvar majorchartweek;\n$(document).ready(function() {\n	majorchartweek = new Highcharts.Chart({'
      new_string = '<script>\n	var chart = Highcharts.chart({'
      idx_b = r.text.find('<div id="C2" style="width: 715px;"')
      idx_e = r.text.find('</table>\n</div>', idx_b)
      week_chart = r.text[idx_b:idx_e+15]
      week_chart_list = week_chart.split('\n')
      tmp = '\n'.join(week_chart_list[0:4]) + '<div id="majorchartweek_container"></div>\n<script>\nvar chart = Highcharts.chart({\n' + '\n'.join(week_chart_list[8:])
      week_chart_modified = tmp.replace('display:none;', '').replace('715px', '1024px').replace('height: 285, width: 760', 'height: 400, width: 1000').replace('	});', '').replace('id="C2" style="width:1024px; position:;"', 'align="center"', 1)
      
      idx_b = r.text.find('<div id="D2"')
      idx_e = r.text.find('</div>', idx_b)
      diff_table = r.text[idx_b:idx_e+6].replace(' display:none', '').replace('715px', '1024px').replace('id="D2" style="width:1024px;"', 'align="center"', 1)

      html = '\n'.join(['\n', week_chart_modified, '<br>', diff_table, '\n'])
      '''
      r.encoding = 'utf-8'
      
      # Weekly chart
      idx_b = r.text.find('var majorchartweek;')
      if idx_b == -1:
        chart_html = ''
      else:
        idx_e = r.text.find('</script>', idx_b)
        week_chart = r.text[idx_b:idx_e+9]
        week_chart_modified = week_chart.replace('$(document).ready(function() {', '').replace('height: 285, width: 760', 'height: 400, width: 1000').replace('	});', '')
        chart_html = '<br>\n<div id="majorchartweek_container" align="center">\n<script type="text/javascript">' + week_chart_modified + '\n</div>\n<br>\n'
      
      # Comparison table
      idx_b = r.text.find("<div id ='D2'")
      if idx_b == -1:
        table_html = ''
      else:
        idx_e = r.text.find('</div>', idx_b)
        table_html = r.text[idx_b:idx_e+6].replace('style="width:715px; display:none"', 'align="center"').replace('715px', '1024px')
      
      html = chart_html + table_html + '\n<br>\n'
      
    print_time_delta(time(), "[PYRAMID]")
  
  return html




def report_get_goodinfo_chart(token):

  if token.find('.TW') > 0:
    symbol = token[0:token.index('.TW')]
    chart = f'  <hr color="#ff8000" align="center">\n\
  <div align="center"><table><tbody><tr>\n\
  <td><iframe src="{cm_url}?action=v&id={symbol}" width="600" height="300" frameborder="0" scrolling="no"></iframe></td>\n\
  <td><iframe src="{cm_url}?action=f&id={symbol}" width="600" height="300" frameborder="0" scrolling="no"></iframe></td>\n\
  <td><iframe src="{cm_url}?action=e&id={symbol}" width="600" height="300" frameborder="0" scrolling="no"></iframe></td>\n\
  </tr><tr>\n\
  <td><iframe src="{cm_url}?action=p&id={symbol}" width="600" height="300" frameborder="0" scrolling="no"></iframe></td>\n\
  <td><a href="https://goodinfo.tw/tw/StockCashFlow.asp?RPT_CAT=M_YEAR&STOCK_ID={symbol}" target="_blank" style="display:block;width:600px;height:300px;line-height:300px;text-align:center;font-size:18px;text-decoration:none;color:#333;background:#f5f5f5;border:1px solid #ddd;">💰 現金流量 (GoodInfo)</a></td>\n\
  <td><a href="https://goodinfo.tw/tw/DayTrading.asp?STOCK_ID={symbol}" target="_blank" style="display:block;width:600px;height:300px;line-height:300px;text-align:center;font-size:18px;text-decoration:none;color:#333;background:#f5f5f5;border:1px solid #ddd;">📈 現股當沖 (GoodInfo)</a></td>\n\
  </tr></tbody></table></div>\n'

    return chart
  
  elif token.find('^TWII') == 0:
    chart = f'  <hr color="#ff8000" align="center">\n\
  <div align="center"><table><tbody><tr>\n\
  <td><a href="https://goodinfo.tw/tw/ShowBuySaleChart.asp?STOCK_ID=%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8&CHT_CAT=DATE" target="_blank"><img src="https://goodinfo.tw/tw/image/StockBuySale/BUY_SALE_DATE_%E5%8A%A0%E6%AC%8A%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  <td><a href="https://goodinfo.tw/tw/ShowMarginChart.asp?STOCK_ID=%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8&CHT_CAT=DATE" target="_blank"><img src="https://goodinfo.tw/tw/image/StockMargin/MARGIN_DATE_%E5%8A%A0%E6%AC%8A%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  <td><a href="https://goodinfo.tw/tw/DayTrading.asp?STOCK_ID=%E5%8A%A0%E6%AC%8A%E6%8C%87%E6%95%B8" target="_blank"><img src="https://goodinfo.tw/tw/image/StockDayTrading/DAY_TRADING_DATE_%E5%8A%A0%E6%AC%8A%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  </tr></tbody></table></div>\n'

    return chart

  elif token.find('^TWOII') == 0:
    chart = f'  <hr color="#ff8000" align="center">\n\
  <div align="center"><table><tbody><tr>\n\
  <td><a href="https://goodinfo.tw/tw/ShowBuySaleChart.asp?STOCK_ID=%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8&CHT_CAT=DATE" target="_blank"><img src="https://goodinfo.tw/tw/image/StockBuySale/BUY_SALE_DATE_%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  <td><a href="https://goodinfo.tw/tw/ShowMarginChart.asp?STOCK_ID=%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8&CHT_CAT=DATE" target="_blank"><img src="https://goodinfo.tw/tw/image/StockMargin/MARGIN_DATE_%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  <td><a href="https://goodinfo.tw/tw/DayTrading.asp?STOCK_ID=%E5%8A%A0%E6%AC%8A%E6%8C%87%E6%95%B8" target="_blank"><img src="https://goodinfo.tw/tw/image/StockDayTrading/DAY_TRADING_DATE_%E6%AB%83%E8%B2%B7%E6%8C%87%E6%95%B8.gif"></a></td>\n\
  </tr></tbody></table></div>\n'

    return chart
    
  else:
    return ''



# ═══════════════════════════════════════════════════════════════════════════════
# Flask application
# ═══════════════════════════════════════════════════════════════════════════════
# ── Flask app ───────────────────────────────────────────────────────────────
app = Flask(__name__)

WORK_DIR = os.path.join(tempfile.gettempdir(), 'yfinance_flask')
os.makedirs(WORK_DIR, exist_ok=True)


# ── Static: serve generated chart HTML files ────────────────────────────────
@app.route('/charts/<path:filename>')
def serve_chart(filename):
    filepath = os.path.join(WORK_DIR, filename)
    if not os.path.exists(filepath):
        return 'Chart file not found', 404
    return send_file(filepath)


# ═══════════════════════════════════════════════════════════════════════════
# Form page
# ═══════════════════════════════════════════════════════════════════════════

_FORM_PAGE = '''\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Stock Analyzer</title>
  <style>
    :root {
      --accent: #ff8000;
      --bg:     #1a1a2e;
      --card:   #16213e;
      --input:  #0f3460;
      --text:   #e0e0e0;
      --muted:  #888;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: var(--card);
      border-radius: 12px;
      padding: 2.2rem 2.5rem;
      width: 100%;
      max-width: 460px;
      box-shadow: 0 8px 32px rgba(0,0,0,.45);
    }
    h1 { color: var(--accent); font-size: 1.4rem; margin-bottom: 1.5rem; text-align: center; }
    label { display: block; font-size: .78rem; color: var(--muted); margin-bottom: .25rem; }
    input[type="text"], input[type="number"], input[type="password"] {
      width: 100%;
      background: var(--input);
      border: 1px solid #3a4a6a;
      border-radius: 6px;
      color: #fff;
      padding: .55rem .8rem;
      font-size: .9rem;
      margin-bottom: 1rem;
      transition: border-color .2s;
    }
    input:focus { outline: none; border-color: var(--accent); }
    button[type="submit"] {
      width: 100%;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: .7rem;
      font-size: 1rem;
      cursor: pointer;
      transition: opacity .2s;
    }
    button:hover { opacity: .85; }
    .hint { font-size: .72rem; color: var(--muted); margin-top: .6rem; text-align: center; }
    .loading-overlay {
      display: none;
      text-align: center;
      padding: 2rem 0;
    }
    .spinner {
      width: 40px; height: 40px;
      border: 4px solid #334;
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin .8s linear infinite;
      margin: 0 auto 1rem;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <h1>Stock Analyzer</h1>
    <div id="form-area">
      <form method="POST" action="/analyze" onsubmit="showLoading()">
        <label>Ticker &mdash; 美股如 AAPL，台股如 2330.</label>
        <input type="text" name="ticker" placeholder="AAPL" required autofocus>

        <label>顯示天數 (Days)</label>
        <input type="number" name="days" value="365" min="30" max="1825">

        <label>FinLab Token（台股選填，留空改用 histock 爬蟲）</label>
        <input type="password" name="finlab_token" placeholder="（選填）">

        <button type="submit">開始分析</button>
        <p class="hint">分析含網路爬蟲，通常需要 30–90 秒，請耐心等候</p>
      </form>
    </div>
    <div class="loading-overlay" id="loading-area">
      <div class="spinner"></div>
      <p style="color:var(--accent)">資料抓取中，請稍候&hellip;</p>
      <p style="font-size:.75rem;color:var(--muted);margin-top:.5rem">
        正在下載歷史K線、法人籌碼與財報資料
      </p>
    </div>
  </div>
  <script>
    function showLoading() {
      document.getElementById('form-area').style.display = 'none';
      document.getElementById('loading-area').style.display = 'block';
    }
  </script>
</body>
</html>
'''


@app.route('/')
def index():
    return _FORM_PAGE


# ═══════════════════════════════════════════════════════════════════════════
# Analyze route — synchronous; browser waits while we compute
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/analyze', methods=['POST'])
def analyze():
    ticker       = request.form.get('ticker', '').strip().upper()
    finlab_token = request.form.get('finlab_token', '').strip()
    try:
        days = int(request.form.get('days', '365'))
    except ValueError:
        days = 365

    if not ticker:
        return redirect('/')

    # Resolve short TW form: '2454.' → '2454.TW' or '2454.TWO'
    ticker = stock_is_tw_otc(ticker).upper()

    # 1. Generate pyecharts chart  ─────────────────────────────────────────
    chart_url = ''
    chart_err = ''
    try:
        path = stock_one_chart(ticker, dir=WORK_DIR, display_days=days, finlab_token=finlab_token)
        if path:
            chart_url = '/charts/' + os.path.basename(path)
    except Exception as exc:
        chart_err = _html.escape(str(exc))

    # 2. Build portfolio report HTML  ──────────────────────────────────────
    report_body = _build_report(ticker)

    return _render_result(ticker, days, chart_url, chart_err, report_body)


# ═══════════════════════════════════════════════════════════════════════════
# Report builder — calls report.py helper functions
# ═══════════════════════════════════════════════════════════════════════════

def _build_report(ticker: str) -> str:
    """
    Assembles the report-tab HTML by calling the individual report_get_*
    helpers from report.py (FinViz, FBS, GoodInfo, Pyramid).
    Returns a self-contained HTML fragment (no <html>/<body> wrapper).
    """

    is_tw = '.TW' in ticker

    # ── external links bar ────────────────────────────────────────────────
    tidx = next((i for i, c in enumerate(ticker) if c == '.'), len(ticker))
    sym  = ticker[:tidx]

    if is_tw:
        pe_href  = f'https://www.wantgoo.com/stock/{sym}/enterprise-value/price-to-earning-ratio'
        pb_href  = f'https://www.wantgoo.com/stock/{sym}/enterprise-value/price-book-ratio'
        ps_href  = ''
        fi_href  = f'https://www.wsj.com/market-data/quotes/TW/{sym}/financials/quarter/cash-flow'
        own_href = ''
        gex_href = ''
        ptt_href = f'https://www.ptt.cc/bbs/Stock/search?q={sym}'
        cm_href  = f'https://www.cmoney.tw/follow/channel/stock-{sym}?chart=d&type=Personal'
    else:
        pe_href  = f'https://www.macrotrends.net/assets/php/fundamental_iframe.php?t={ticker}&type=pe-ratio&statement=price-ratios&freq=Q'
        pb_href  = f'https://www.macrotrends.net/assets/php/fundamental_iframe.php?t={ticker}&type=price-book&statement=price-ratios&freq=Q'
        ps_href  = f'https://www.macrotrends.net/assets/php/fundamental_iframe.php?t={ticker}&type=price-sales&statement=price-ratios&freq=Q'
        fi_href  = f'https://www.wsj.com/market-data/quotes/{ticker}/financials/quarter/cash-flow'
        own_href = f'https://www.dataroma.com/m/stock.php?sym={ticker.replace("-",".")}'
        gex_href = f'https://unusualwhales.com/stock/{ticker}/greek-exposure'
        ptt_href = f'https://www.ptt.cc/bbs/Stock/search?q={ticker}'
        cm_href  = ''

    def alink(href, text):
        return f'<a href="{_html.escape(href)}" target="_blank">{text}</a>' if href else ''

    links_html = ' &emsp; '.join(filter(None, [
        alink(pe_href,  'PE Chart'),
        alink(pb_href,  'PB Chart'),
        alink(ps_href,  'PS Chart'),
        alink(fi_href,  'Finance'),
        alink(own_href, 'Ownership'),
        alink(gex_href, 'GEX'),
        alink(ptt_href, 'PTT'),
        alink(cm_href,  'CMoney'),
    ]))

    parts = [
        f'<p style="text-align:center;padding:10px 8px">{links_html}</p>',
        '<hr color="#ff8000">',
    ]

    # ── helper: call a report function, append result ─────────────────────
    def _try(fn, label):
        try:
            fragment = fn(ticker)
            if fragment:
                parts.append(fragment)
                parts.append('<hr color="#ff8000">')
        except Exception as exc:
            parts.append(
                f'<p style="color:#c66;padding:6px"><b>{label}:</b> '
                f'{_html.escape(str(exc))}</p><hr color="#ff8000">'
            )

    # ── All tickers (functions handle their own TW/US filtering internally) ──
    _try(report_get_fbs_position_overview, 'FBS Position')
    _try(report_get_position_pyramid,      'Pyramid')
    _try(report_get_goodinfo_chart,        'GoodInfo')

    # ── US-only: exclude TW / indices / FX / HK / CN ──────────────────────
    _EXCLUDE = ['.TW', '^', '.SZ', '.SS', '.HK', '-USD', '=X']
    if not any(e in ticker for e in _EXCLUDE):
        _try(report_get_finviz_overview, 'FinViz')

    return '\n'.join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Result page — two-tab layout, all inline HTML
# ═══════════════════════════════════════════════════════════════════════════

def _render_result(ticker: str, days: int, chart_url: str, chart_err: str, report_body: str) -> str:

    # Chart tab content
    if chart_url:
        chart_content = (
            f'<iframe src="{chart_url}" frameborder="0" '
            f'style="width:100%;height:100%;display:block;border:none"></iframe>'
        )
    else:
        msg = _html.escape(chart_err) if chart_err else '未知錯誤'
        chart_content = (
            f'<div style="padding:2rem;color:#c66">'
            f'<b>Chart 產生失敗：</b>{msg}</div>'
        )

    report_content = f'''\
<div id="report-inner" style="padding:12px;font-size:12px;font-family:Arial,Helvetica,sans-serif;transform-origin:top left;">
  {report_body}
</div>'''

    return f'''\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_html.escape(ticker)} &mdash; Stock Analyzer</title>
  <style>
    :root {{
      --accent:   #ff8000;
      --bg:       #1a1a2e;
      --bar-bg:   #16213e;
      --tab-act:  #0f3460;
      --text:     #e0e0e0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      overflow: hidden;
    }}
    /* Full-viewport flex column — dvh avoids iOS Safari address-bar overlap */
    .layout {{
      display: flex;
      flex-direction: column;
      height: 100vh;
      height: 100dvh;
    }}
    /* ── Top bar ── */
    .topbar {{
      flex-shrink: 0;
      background: var(--bar-bg);
      border-bottom: 2px solid var(--accent);
      display: flex;
      align-items: center;
      padding: .4rem 1rem;
      gap: 1rem;
    }}
    .topbar .title {{
      flex: 1;
      font-size: 1rem;
      font-weight: bold;
      color: #fff;
    }}
    .topbar a {{
      color: var(--accent);
      text-decoration: none;
      font-size: .82rem;
    }}
    .topbar a:hover {{ text-decoration: underline; }}
    /* ── Tab bar ── */
    .tab-bar {{
      flex-shrink: 0;
      display: flex;
      background: var(--bar-bg);
    }}
    .tab-btn {{
      padding: .5rem 1.6rem;
      min-width: 0;
      flex: 1 1 auto;
      cursor: pointer;
      border: none;
      background: transparent;
      color: #999;
      font-size: .88rem;
      border-bottom: 3px solid transparent;
      transition: all .15s;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .tab-btn:hover {{ color: #fff; }}
    .tab-btn.active {{
      color: #fff;
      border-bottom-color: var(--accent);
      background: var(--tab-act);
    }}
    /* ── Panels ── */
    .tab-panel {{
      flex: 1;
      overflow: hidden;
      display: none;
    }}
    .tab-panel.active {{
      display: flex;
      flex-direction: column;
    }}
    /* Chart panel: iframe fills everything */
    #panel-chart {{ overflow: hidden; }}
    /* Report panel: scrollable both axes for wide tables/iframes on mobile */
    #panel-report {{ overflow-x: auto; overflow-y: auto; background: #fff; color: #222; }}
    /* ── Report table styles (mirrors report.py HTML output) ── */
    #panel-report * {{
      font-size: 12px;
      font-family: Arial, Helvetica, sans-serif, "Microsoft JhengHei";
    }}
    #panel-report a {{ color: #0066cc; }}
    #panel-report table {{ border-collapse: collapse; }}
    #panel-report td, #panel-report th {{
      border: 1px solid #FDEBD2;
      text-align: left;
      padding: 5px;
    }}
    #panel-report .is-negative {{ color: #008000; }}
    #panel-report .is-positive {{ color: #ff0000; }}
    #panel-report .t3r1         {{ color: #ff0000; }}
    #panel-report .snapshot-td2 {{
      color: #000;
      text-decoration: none;
      border: 1px solid #d3d3d3;
      white-space: nowrap;
    }}
    #panel-report .snapshot-td2-cp {{
      color: #000;
      text-decoration: none;
      border: 1px solid #d3d3d3;
      cursor: pointer;
      white-space: nowrap;
    }}
    #panel-report .fullview-ratings-outer {{
      border: 1px solid #d3d3c3;
    }}
    #panel-report td.fullview-ratings-inner {{
      border: 1px solid #d3d3c3;
    }}
    #panel-report .body-table-rating-downgrade {{
      color: #dd3333;
      text-decoration: none;
      background: #fff0f0;
    }}
    #panel-report .body-table-rating-upgrade {{
      color: #009900;
      text-decoration: none;
      background: #f0fff0;
    }}
    #panel-report .body-table-rating-neutral {{
      color: #333;
      text-decoration: none;
      background: #f0f0f0;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highcharts/12.3.0/highcharts.min.js"></script>
</head>
<body>
<div class="layout">

  <div class="topbar">
    <span class="title">&#x1F4C8; {_html.escape(ticker)} &nbsp;&middot;&nbsp; {days}d</span>
    <a href="/">&#8592; 返回</a>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('chart',this)">
      &#x1F4CA; 圖表 Chart
    </button>
    <button class="tab-btn" onclick="switchTab('report',this)">
      &#x1F4CB; 報告 Report
    </button>
  </div>

  <div id="panel-chart"  class="tab-panel active">{chart_content}</div>
  <div id="panel-report" class="tab-panel">{report_content}</div>

</div>
<script>
  // ── Report scale: fit wide content to panel width ──────────────────────
  function adjustReportScale() {{
    var panel = document.getElementById('panel-report');
    var inner = document.getElementById('report-inner');
    if (!inner || !panel) return;
    inner.style.zoom = '';            // reset to measure natural width
    var naturalW = inner.scrollWidth;
    var panelW   = panel.clientWidth;
    if (naturalW > panelW && panelW > 0) {{
      inner.style.zoom = panelW / naturalW;
    }}
  }}
  window.addEventListener('resize', adjustReportScale);

  // ── Deferred iframe loading (avoid rendering in hidden/zero-size panel) ──
  document.addEventListener('DOMContentLoaded', function() {{
    document.querySelectorAll('.tab-panel:not(.active) iframe').forEach(function(f) {{
      if (f.src && f.src !== 'about:blank') {{
        f.setAttribute('data-deferred-src', f.src);
        f.src = 'about:blank';
      }}
    }});
  }});

  function switchTab(name, btn) {{
    document.querySelectorAll('.tab-panel').forEach(function(p) {{
      p.classList.remove('active');
    }});
    document.querySelectorAll('.tab-btn').forEach(function(b) {{
      b.classList.remove('active');
    }});
    var panel = document.getElementById('panel-' + name);
    panel.classList.add('active');
    btn.classList.add('active');
    // Restore deferred iframes on first visit to this panel
    panel.querySelectorAll('iframe[data-deferred-src]').forEach(function(f) {{
      f.src = f.getAttribute('data-deferred-src');
      f.removeAttribute('data-deferred-src');
    }});
    if (name === 'report') {{ adjustReportScale(); }}
  }}
</script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='YfinanceQuery Flask UI')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Port (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Enable Flask debug mode')
    args = parser.parse_args()

    print(f'Starting server at http://{args.host}:{args.port}')
    print(f'Chart files will be stored in: {WORK_DIR}')
    app.run(host=args.host, port=args.port, debug=args.debug)
