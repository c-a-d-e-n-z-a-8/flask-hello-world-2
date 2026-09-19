from flask import Flask, request, render_template, Response, jsonify, render_template_string
import yfinance as yf
import pandas as pd
import talib
#import requests
import json
import gc
import os
from itertools import dropwhile
from io import StringIO
import re

from urllib.parse import urljoin
import random

from pyecharts.charts import Bar, Tab
from pyecharts import options as opts
from pyecharts.commons.utils import JsCode

from datetime import date, datetime, timedelta
from curl_cffi import requests
import numpy as np
from pyecharts.charts import Line

import time
import traceback
from bs4 import BeautifulSoup as BS
from zoneinfo import ZoneInfo


# Initialization
api_key = os.environ.get('API_KEY')
cm_url = os.environ.get('CM_URL')
cm_url2 = os.environ.get('CM_URL2')
si_url = os.environ.get('SI_URL')
tw_sf_url = os.environ.get('TW_SF_URL')
portfolio_url = os.environ.get('PORTFOLIO_URL')
yahoo_url = os.environ.get('YAHOO_URL')

use_ollama = False
ollama_model = "deepseek-r1:8b"

BARS = 200


app = Flask(__name__)




################################################################################################################################################################
@app.route('/link/')
def link():
  links = []
  for rule in app.url_map.iter_rules():
    if "GET" in rule.methods and not rule.rule.startswith('/static'):
        links.append((rule.endpoint, rule.rule))
  html = '''
  <!DOCTYPE html>
  <html lang="zh">
  <head>
    <meta charset="UTF-8">
    <title>所有路由</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body>
    <div class="container mt-5">
        <h1 class="mb-4">Links</h1>
        <ul class="list-group">
        {% for endpoint, url in links %}
            <li class="list-group-item">
                <a href="{{ url }}" class="link-primary">{{ url }}</a>
                <span class="badge bg-secondary ms-2">{{ endpoint }}</span>
            </li>
        {% endfor %}
        </ul>
    </div>
  </body>
  </html>
  '''
  return render_template_string(html, links=links)




################################################################################################################################################################
################################################################################################################################################################
def fetch_tw_whale(ticker):
  
  return_value = {}
  
  if ".TW" in ticker:

    # Get CMoney CK key first
    headers = {
      'Accept': 'application/json, text/javascript, */*; q=0.01',
      'Accept-Language': 'en-US,en;q=0.9',
      'Connection': 'keep-alive',
      'Referer': f'{cm_url}?action=mf&id={ticker}',
      'Sec-Fetch-Dest': 'empty',
      'Sec-Fetch-Mode': 'cors',
      'Sec-Fetch-Site': 'same-origin',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
      'X-Requested-With': 'XMLHttpRequest',
      'sec-ch-ua': '"Microsoft Edge";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"Windows"',
    }
    
    params = {
      'action': 'mf',
      'count': str(BARS),
      'id': '2330',
      'ck': 'ML7EuNTM4B87LWAfCN94XIUVRMUVIHmjrEY^DHVQHBWwCRQrCXC3jMk$5OErz',
    }

    ck = ''
    r = requests.get(f'{cm_url}?action=mf&id=2330', headers=headers, verify=False)
    if r.status_code == 200:
      idx_b = r.text.index('var ck = "') + 10
      if idx_b > 0:
        idx_e = r.text.index('";', idx_b)
        ck = r.text[idx_b:idx_e]
        params['ck'] = ck
        print(f'CK: {ck}')
    
    if ck != '':
      params['id'] = ticker[:ticker.index('.')]
      r = requests.get(cm_url2, params=params, headers=headers, verify=False)
      if r.status_code == 200:
        cm_data = r.json()
        if cm_data != None:
          records = [
            {
              "date": pd.to_datetime(c[0], unit='ms'),
              "mf": c[8]["MfOvrBuy"] if c[8] else 0,
              "mf_acc": c[8]["MfOvrBuySm"] if c[8] else 0,
              "b_s": c[8]["BuyerSm"] if c[8] else 0,
            }
            for c in cm_data.get("DataLine", [])
          ]
  
          df_mf = pd.DataFrame.from_records(records).set_index("date")
  
          df_mf_reset = df_mf.tail(BARS).reset_index()
          df_mf_reset['date'] = df_mf_reset['date'].dt.strftime('%Y-%m-%d')
          return_value = df_mf_reset.to_dict(orient='records')

  return return_value




################################################################################################################################################################
def fetch_short_stats(ticker):
  
  return_value = {}
  
  if ".TW" not in ticker:
    headers_si = {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
      'Accept-Language': 'zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
      'Cache-Control': 'max-age=0',
      'Connection': 'keep-alive',
      'Referer': 'https://www.google.com/',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'same-origin',
      'Sec-Fetch-User': '?1',
      'Upgrade-Insecure-Requests': '1',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"Windows"',
    }
      
    r = requests.get(f'{si_url}/quote/{ticker}/short-interest', headers=headers_si, verify=False)
    if r.status_code == 200:
      html = r.text
      idx_b = html.find('"shortInterest":[{')
      if idx_b > -1:
        idx_e = html.find('],', idx_b)
        if idx_e > -1:
          json_txt = '[' + html[idx_b+17:idx_e+1]
          df = pd.read_json(StringIO(json_txt), orient='records')
          df['recordDate'] = pd.to_datetime(df['recordDate']).dt.strftime('%Y-%m-%d')
          if 'shortPercentOfFloat' in df.columns:
            rename_cols = {'recordDate': 'date', 'daysToCover': 'SR', 'shortPercentOfFloat': 'SF'}
          else:
            rename_cols = {'recordDate': 'date', 'daysToCover': 'SR'}
            
          df = df.rename(columns=rename_cols)[rename_cols.values()].tail(20)

          return_value = df.to_dict(orient='records')

  return return_value




################################################################################################################################################################
def fetch_tw_financing_stats(ticker):
  
  return_value = {}
  
  if ".TW" in ticker:

    url = f"{tw_sf_url}?no={ticker[:ticker.index('.')]}&m=mg"

    r = requests.get(url, timeout=10, verify=False)
    
    if r.status_code == 200:
      r.encoding = 'utf-8'
      html = r.text

      col_list = ["'融資餘額(張)'", "'融券餘額(張)'", "'借券賣出餘額(張)'"]
      data_list = []

      for c in col_list:
        idx_b = html.find(f"{c},\r\n") + len(c) + 1
        if idx_b > (len(c) + 21):
          idx_e = html.find(',\r\n', idx_b)
          data = html[idx_b:idx_e].strip()
          json_data = json.loads(data[6:])    # Remove 'data: ' and string to json list
          data_list.append(json_data)

      dfs = [pd.DataFrame(l, columns=['date', col_list[i]]).set_index('date') for i, l in enumerate(data_list)]
      if len(dfs) == 3:
        df = pd.concat(dfs, axis=1)
        df.index = pd.to_datetime(df.index, unit='ms').strftime('%Y-%m-%d')
        df.rename(columns={"'融資餘額(張)'": "BB", "'融券餘額(張)'": "SB", "'借券賣出餘額(張)'": "LSB"}, inplace=True)
  
        df_reset = df.tail(BARS).reset_index()
        return_value = df_reset.to_dict(orient='records')

  return return_value




################################################################################################################################################################
def fetch_symbol_name(ticker):
  
  return_value = ""
  
  headers = {
    'authority': 'query1.finance.yahoo.com',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
    'cache-control': 'max-age=0',
    'sec-ch-ua': '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
  }
  
  url = 'https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.stockList;symbols=' + ticker
  r = requests.get(url, headers=headers, timeout=5)

  if r.status_code == 200:
    yahoo_tw = r.json()
    return_value = yahoo_tw[0]['symbolName']

  return return_value



################################################################################################################################################################
def simplified_options(stock):
  result = []
  for date in stock.options:
    opt = stock.option_chain(date)
    for opt_type, label in zip(['calls', 'puts'], ['call', 'put']):
      df = getattr(opt, opt_type)
      df = df.copy()
      df['premium_est'] = df['lastPrice'] * df['volume'] * 100
      filtered = df[df['premium_est'] > 200_000]
      for _, row in filtered.iterrows():
        result.append({
          'date': date,
          'type': label,
          'strike': round(row['strike'], 4),
          'lastPrice': round(row['lastPrice'], 4),
          'volume': round(row['volume'], 4),
          'openInterest': round(row['openInterest'], 4),
          'premiumEstimated': round(row['premium_est'], 4),
          'inTheMoney': bool(row['inTheMoney'])
        })
  return result




################################################################################################################################################################
def fetch_stock_data(ticker):
  close = 'Close'
  MA_TYPE = 0
  
  stock = yf.Ticker(ticker)
  hist = stock.history(period="2y", auto_adjust=True)        
  hist['ATR'] = talib.ATR(hist['High'], hist['Low'], hist['Close'], timeperiod=5)
  
  hist.drop(['Open', 'High', 'Low', 'Stock Splits'], axis=1, inplace=True, errors='ignore')
  gc.collect()

  hist['10MA'] = talib.SMA(hist[close], timeperiod=10)
  hist['20MA'] = talib.SMA(hist[close], timeperiod=20)
  #hist['60MA'] = talib.SMA(hist[close], timeperiod=60)
  hist['200MA'] = talib.SMA(hist[close], timeperiod=200)  
  hist['BBU'], hist['60MA'], hist['BBD'] = talib.BBANDS(hist[close].values, timeperiod=60, nbdevup=2, nbdevdn=2, matype=MA_TYPE)    
  hist['RSI'] = talib.RSI(hist[close], timeperiod=14)
  hist['MACD'], hist['MACD Signal'], hist['MACDH'] = talib.MACD(hist[close], fastperiod=50, slowperiod=120, signalperiod=30)
  
  hist.drop(['MACD', 'MACD Signal'], axis=1, inplace=True)
  gc.collect()
  
  # Calculate the difference between closing price and 200MA
  hist['200MA Diff'] = (hist[close]-hist['200MA'])/hist['200MA']*100

  # Calculate the mean and standard deviation of the differences
  mean_diff = hist['200MA Diff'].mean()
  std_diff = hist['200MA Diff'].std()

  # Calculate the z-score
  hist['200MADZ'] = (hist['200MA Diff'] - mean_diff) / std_diff
  
  hist.drop(['200MA Diff'], axis=1, inplace=True)
  gc.collect()
  
  hist = hist.round(2)
  hist = hist.reset_index().tail(BARS)
  hist['Date'] = pd.to_datetime(hist['Date']).dt.strftime('%Y-%m-%d')
  
  #print(hist)
  
  hist_dict = hist.to_dict(orient="records")
  
  financials = stock.financials.to_dict()
  quarterly_financials = stock.quarterly_financials.to_dict()
  cash_flow = stock.cash_flow.to_dict()
  quarterly_cashflow = stock.quarterly_cashflow.to_dict()
  #info = stock.info
  info = dict(dropwhile(lambda item: item[0] != 'previousClose', stock.info.items()))
  print(info)
  
  upgrades_downgrades = stock.upgrades_downgrades[:10].to_dict()
  eps_trend = stock.eps_trend.to_dict()
  revenue_estimate = stock.revenue_estimate.to_dict()
  
  """
  options = stock.options[:8]
  options_data = {}
  for date in options:
    opt = stock.option_chain(date)
    options_data[date] = {
      "calls": opt.calls.round(4).to_dict(orient="records"),
      "puts": opt.puts.round(4).to_dict(orient="records")
    }
  """
  options_data = simplified_options(stock)
  
  gc.collect()
  
  return {
    "symbol_name": fetch_symbol_name(ticker),
    "history": hist_dict,
    "financials": financials,
    "quarterly_financials": quarterly_financials,
    "cash_flow": cash_flow,
    "quarterly_cashflow": quarterly_cashflow,
    "info": info,
    "upgrades_downgrades": upgrades_downgrades,
    "eps_trend": eps_trend,
    "revenue_estimate": revenue_estimate,
    "options": options_data,
    "mainforce_tw": fetch_tw_whale(ticker),
    "short_stats": fetch_short_stats(ticker),
    "securities_financing_tw": fetch_tw_financing_stats(ticker)
  }




################################################################################################################################################################
def ollama_generate(prompt, model='llama3'):
  print(f"Use Ollama: {model}")
  
  headers = {
    "Content-Type": "application/json"
  }

  data = {
    "model": model,  # 請確認這個模型已經在本地 ollama 中存在
    "messages": [
      {
        "role": "user",
        "content": prompt
      }
    ],
    "stream": False  # 若設為 True，會變成 stream 回傳
  }
 
  url = "http://localhost:11434/api/chat"
  response = requests.post(url, headers=headers, data=json.dumps(data), timeout=600)
  
  if response.status_code == 200:
    result = response.json()
    return(result["message"]["content"])
  else:
    print(f"❌ Ollama error：{response.status_code}")
    print(response.text)




################################################################################################################################################################
def gemini_generate_content(prompt, model_name, api_key, use_search=True):
  url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
  headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": api_key
  }
  
  data = {
    "contents": [
       {
         "parts": [
           {"text": prompt}
         ]
       }
    ]
  }

  if use_search:
    data["tools"] = [
       {
         "google_search": {}
       }
    ]

  response = requests.post(url, headers=headers, json=data, timeout=600)
  if response.status_code == 200:
    result = response.json()
    # 取出回應內容
    #return result['candidates'][0]['content']['parts'][0]['text']
    
    # ★ 修正 2：整合所有 parts 的文字
    try:
      if 'candidates' in result and result['candidates']:
          content = result['candidates'][0].get('content', {})
          parts = content.get('parts', [])
          
          # 使用 join 將所有 part 的 text 串接起來
          full_text = "".join([part.get('text', '') for part in parts])
          
          return full_text
      else:
          return "No candidates returned."
            
    except (KeyError, IndexError) as e:
      return f"Error parsing response: {e}"
  
  else:
    raise Exception(f"❌ Gemini API error: {response.status_code} {response.text}")




################################################################################################################################################################
def dict_to_table(data: list[dict], limit=200, csv=True) -> str:
  if not data:
    return "無資料"
  df = pd.DataFrame(data).tail(limit)
  if csv:
    return df.to_csv(index=False)
  else:
    return df.to_string(index=False)




################################################################################################################################################################
def dict_to_table_finance(data: list[dict], csv=True) -> str:
  if not data:
    return "無資料"
  df = pd.DataFrame(data)
  
  if csv:
    return df.to_csv(index=True)
  else:
    return df.to_string(index=True)




################################################################################################################################################################
@app.route('/aia/', methods=['GET', 'POST'])
def gemini_analysis():
  gc.collect()
  
  analysis = None
  error = None
  ticker = ''
  model_name = 'gemini-2.5-flash'  # 預設值

  if request.method == 'POST':
    ticker = request.form.get('ticker', '').strip()
    additional_prompt = request.form.get('additional_prompt', '').strip()
    model_name = request.form.get('model', 'gemini-2.5-flash')
    
    if not ticker:
      error = "請輸入股票代碼"
    else:
      try:
        stock_data = fetch_stock_data(ticker)
        symbol_name = stock_data['symbol_name']
        history_table = dict_to_table(stock_data['history'])
        mf_tw_table = dict_to_table(stock_data['mainforce_tw'])
        short_table = dict_to_table(stock_data['short_stats'])
        sf_tw_table = dict_to_table(stock_data['securities_financing_tw'])
        financials_table = dict_to_table_finance(stock_data['financials'])
        financials_q_table = dict_to_table_finance(stock_data['quarterly_financials'])
        cashflow_table = dict_to_table_finance(stock_data['cash_flow'])
        cashflow_q_table = dict_to_table_finance(stock_data['quarterly_cashflow'])
        #info_table = dict_to_table_finance(stock_data['info'])
        updown_table = dict_to_table_finance(stock_data['upgrades_downgrades'])
        eps_trend_table = dict_to_table_finance(stock_data['eps_trend'])
        revenue_estimate_table = dict_to_table_finance(stock_data['revenue_estimate'])
        option_table = dict_to_table_finance(stock_data['options'])

        gc.collect()
       
        print('----------------------------------------')
        prompt = f"""
你是一個資深的華爾街分析師，擅長從基本面技術面籌碼面產生股票分析報告。請根據 {symbol_name} ({ticker}) 的下列資料進行分析並產生一份繁體中文個股分析報告，首先用簡單的語言解釋這家公司的業務：它解決什麼問題，誰為此付費，為什麼客戶選擇它而不是替代品。
分解這家公司的收入流：哪些部門在增長，哪些在放緩，公司對頂級產品或客戶的依賴程度如何？解釋這家公司所在的行業：市場是在增長、穩定還是萎縮？什麼長期趨勢有利或不利於該業務？列出主要競爭對手：比較他們的定價權、產品實力、規模和競爭壁壘，突出這家公司明顯勝出或落後的地方。
然後從網路上搜尋近半年公司相關新聞並以表格方式總結其對股價與經營業務的影響，然後列出目前價格與關鍵支持價位，以及根據財報預測數據所推算的未來股價，內容包含基本面 (數字要有YoY加減速的分析，重點關注收入增長一致性、利潤率、債務水平、自由現金流強度和資本配置。並且根據年度財報預估與當季累積財報數字，預估後面一兩季的營收獲利起伏與對應的PE/PS/PB ratio，並且以表格列出每季EPS與營收增減的速度與加速度)、技術面 (配合成交量分析，例如是否有價量背離或技術指標與股價背離，或是型態上有破底翻、假突破、杯柄型態、上升旗型、下降旗型，或是 Mark Minervini 所提出的 Volatility Contraction Pattern 等典型股價走勢型態) 與期權市場的觀察與建議。 若mf_tw_table資料中有台灣股市主力當日買賣超 (mf)，主力買賣超累積 (mf_acc)，買賣家差數 (b_s)，順便分析主力吃或出貨狀況。若資料中short_table有值，根據SF (short floating) 與SR (short ratio) 分析市場空單狀況及嘎空可能性。若資料中有台灣股市 (sf_tw_table) 融資餘額 (BB)， 融券餘額 (SB)， 借券賣出餘額 (LSB)，分析市場空單狀況，嘎空可能性以及未來主力操作方向。
接下來，識別這家公司的最大風險。包括業務風險、財務風險、監管威脅和可能永久性傷害業務的因素，評估管理團隊的歷史表現。他們過去執行情況如何？他們的決策如何影響長期股東？
{additional_prompt}
最後，根據上述的所有分析，總結你的投資建議。

[技術面]
csv table 欄位縮寫: MACD Histogram (MACDH)， 60MA Bollinger Band (BBU， BBD)， 200MA Diff Z-Score (200MADZ)
{history_table}

[台股主力籌碼]
csv table 欄位縮寫: 主力當日買賣超 (mf)，主力買賣超累積 (mf_acc)，買賣家差數 (b_s)
{mf_tw_table}

[台股融資融券與借券賣出餘額]
csv table 欄位縮寫: 融資餘額 (BB)， 融券餘額 (SB)， 借券賣出餘額 (LSB)
{sf_tw_table}

[空單狀況]
csv table 欄位縮寫: SF (short floating)， SR (short ratio)
{short_table}

[財報資料]
###
公司概況:
{stock_data['info']}

###
年度財報: csv table 
{financials_table}

###
季度財報: csv table 
{financials_q_table}

###
年度現金流: csv table 
{cashflow_table}

###
季度現金流: csv table 
{cashflow_q_table}

###
EPS年度趨勢: csv table 
{eps_trend_table}

###
營收預估: csv table 
{revenue_estimate_table}

###
評等變化: csv table 
{updown_table}


[期權市場]
csv table
{option_table}
        """
        print(prompt)
        print('----------------------------------------')

        if use_ollama == True:
          analysis = ollama_generate(prompt, model=ollama_model)
        else:
          #import google.generativeai as genai
          #genai.configure(api_key=api_key)
          #model = genai.GenerativeModel(model_name)
          #response = model.generate_content(prompt)
          #analysis = response.text

          # Auto-detect if search should be used (disable for thinking/reasoning models)
          use_search = "thinking" not in model_name.lower() and "reasoning" not in model_name.lower()
          if model_name == 'gemini-2.5-flash':
            use_search = True
          else:
            use_search = False
          analysis = gemini_generate_content(prompt, model_name, api_key, use_search=use_search)
      except Exception as e:
        error = f"分析過程發生錯誤: {e}"

  return render_template('analysis.html', analysis=analysis, error=error, ticker=ticker, model=model_name)




################################################################################################################################################################
@app.route('/suityourself/', methods=['GET', 'POST'])
def gemini_analysis_user():
    gc.collect()
    analysis = None
    error = None
    ticker = ''
    model_name = 'gemini-2.5-pro'

    if request.method == 'POST':
        ticker = request.form.get('ticker', '').strip()
        additional_prompt = request.form.get('additional_prompt', '').strip()
        model_name = request.form.get('model', 'gemini-2.5-pro')
        gemini_key = request.form.get('gemini_key', '').strip()

        if not ticker:
            error = "請輸入股票代碼"
        elif not gemini_key:
            error = "請輸入有效的 Gemini API Key"
        else:
            try:
                # 假設 fetch_stock_data 和 gemini_generate_content 已定義
                stock_data = fetch_stock_data(ticker)
                symbol_name = stock_data['symbol_name']
                history_table = dict_to_table(stock_data['history'])
                mf_tw_table = dict_to_table(stock_data['mainforce_tw'])
                short_table = dict_to_table(stock_data['short_stats'])
                sf_tw_table = dict_to_table(stock_data['securities_financing_tw'])
                financials_table = dict_to_table_finance(stock_data['financials'])
                financials_q_table = dict_to_table_finance(stock_data['quarterly_financials'])
                cashflow_table = dict_to_table_finance(stock_data['cash_flow'])
                cashflow_q_table = dict_to_table_finance(stock_data['quarterly_cashflow'])
                #info_table = dict_to_table_finance(stock_data['info'])
                updown_table = dict_to_table_finance(stock_data['upgrades_downgrades'])
                eps_trend_table = dict_to_table_finance(stock_data['eps_trend'])
                revenue_estimate_table = dict_to_table_finance(stock_data['revenue_estimate'])
                option_table = dict_to_table_finance(stock_data['options'])

                gc.collect()
               
                print('----------------------------------------')
                prompt = f"""
你是一個資深的華爾街分析師，擅長從基本面技術面籌碼面產生股票分析報告。請根據 {symbol_name} ({ticker}) 的下列資料進行分析並產生一份繁體中文個股分析報告，首先用簡單的語言解釋這家公司的業務：它解決什麼問題，誰為此付費，為什麼客戶選擇它而不是替代品。
分解這家公司的收入流：哪些部門在增長，哪些在放緩，公司對頂級產品或客戶的依賴程度如何？解釋這家公司所在的行業：市場是在增長、穩定還是萎縮？什麼長期趨勢有利或不利於該業務？列出主要競爭對手：比較他們的定價權、產品實力、規模和競爭壁壘，突出這家公司明顯勝出或落後的地方。
然後從網路上搜尋近半年公司相關新聞並以表格方式總結其對股價與經營業務的影響，然後列出目前價格與關鍵支持價位，以及根據財報預測數據所推算的未來股價，內容包含基本面 (數字要有YoY加減速的分析，重點關注收入增長一致性、利潤率、債務水平、自由現金流強度和資本配置。並且根據年度財報預估與當季累積財報數字，預估後面一兩季的營收獲利起伏與對應的PE/PS/PB ratio，並且以表格列出每季EPS與營收增減的速度與加速度)、技術面 (配合成交量分析，例如是否有價量背離或技術指標與股價背離，或是型態上有破底翻、假突破、杯柄型態、上升旗型、下降旗型，或是 Mark Minervini 所提出的 Volatility Contraction Pattern 等典型股價走勢型態) 與期權市場的觀察與建議。 若mf_tw_table資料中有台灣股市主力當日買賣超 (mf)，主力買賣超累積 (mf_acc)，買賣家差數 (b_s)，順便分析主力吃或出貨狀況。若資料中short_table有值，根據SF (short floating) 與SR (short ratio) 分析市場空單狀況及嘎空可能性。若資料中有台灣股市 (sf_tw_table) 融資餘額 (BB)， 融券餘額 (SB)， 借券賣出餘額 (LSB)，分析市場空單狀況，嘎空可能性以及未來主力操作方向。
接下來，識別這家公司的最大風險。包括業務風險、財務風險、監管威脅和可能永久性傷害業務的因素，評估管理團隊的歷史表現。他們過去執行情況如何？他們的決策如何影響長期股東？
{additional_prompt}
最後，根據上述的所有分析，總結你的投資建議。

[技術面]
csv table 欄位縮寫: MACD Histogram (MACDH)， 60MA Bollinger Band (BBU， BBD)， 200MA Diff Z-Score (200MADZ)
{history_table}

[台股主力籌碼]
csv table 欄位縮寫: 主力當日買賣超 (mf)，主力買賣超累積 (mf_acc)，買賣家差數 (b_s)
{mf_tw_table}

[台股融資融券與借券賣出餘額]
csv table 欄位縮寫: 融資餘額 (BB)， 融券餘額 (SB)， 借券賣出餘額 (LSB)
{sf_tw_table}

[空單狀況]
csv table 欄位縮寫: SF (short floating)， SR (short ratio)
{short_table}

[財報資料]
###
公司概況:
{stock_data['info']}

###
年度財報: csv table 
{financials_table}

###
季度財報: csv table 
{financials_q_table}

###
年度現金流: csv table 
{cashflow_table}

###
季度現金流: csv table 
{cashflow_q_table}

###
EPS年度趨勢: csv table 
{eps_trend_table}

###
營收預估: csv table 
{revenue_estimate_table}

###
評等變化: csv table 
{updown_table}


[期權市場]
csv table
{option_table}
"""
                print(prompt)
                print('----------------------------------------')
                use_search = "thinking" not in model_name.lower() and "reasoning" not in model_name.lower()
                analysis = gemini_generate_content(prompt, model_name, gemini_key, use_search=use_search)
            except Exception as e:
                error = f"分析過程發生錯誤: {e}"

    return render_template('analysis_user.html', analysis=analysis, error=error, ticker=ticker, model=model_name)




################################################################################################################################################################
################################################################################################################################################################
def rewrite_html(html, base_url):
  # 將 src/href 內的絕對或相對路徑改寫成 proxy 路徑
  def repl(match):
    orig_url = match.group(2)
    # 處理相對路徑
    if not orig_url.startswith('http'):
      from urllib.parse import urljoin
      orig_url = urljoin(base_url, orig_url)
    return f'{match.group(1)}/proxy?url={orig_url}{match.group(3)}'

  # 只處理 src 和 href
  pattern = r'((?:src|href)=["\'])([^"\']+)(["\'])'
  return re.sub(pattern, repl, html, flags=re.IGNORECASE)




################################################################################################################################################################
@app.route('/proxy')
def proxy():
  target_url = request.args.get('url')
  if not target_url:
    return "請提供 ?url= 參數", 400

  try:
    resp = requests.get(target_url, headers={
      'User-Agent': request.headers.get('User-Agent', 'Mozilla/5.0')
    }, timeout=10)
    content_type = resp.headers.get('Content-Type', '')

    if 'text/html' in content_type:
      # 只重寫 HTML
      html = resp.text
      html = rewrite_html(html, target_url)
      return Response(html, status=resp.status_code, content_type=content_type)
    else:
      # 其他資源直接回傳
      return Response(resp.content, status=resp.status_code, content_type=content_type)

  except Exception as e:
      return f"Error: {e}", 500




################################################################################################################################################################
################################################################################################################################################################
no_list = list(range(1, 29660))
random.shuffle(no_list)
no_index = 0




################################################################################################################################################################
@app.route('/hokkien/')
def hokkien():
  return render_template('hokkien.html')




################################################################################################################################################################
def replace_button_with_audio(html):
  # 用 re 找出 button 的 data-src
  def repl(m):
    audio_url = m.group(1)
    # 你可以自訂 audio 樣式，這裡用 controls 會有原生播放icon
    return f'''
    <audio controls style="vertical-align: middle; height: 20px width: 20px;">
        <source src="{audio_url}" type="audio/mpeg">
        您的瀏覽器不支援音訊播放。
    </audio>
      '''
  # 把 button 換成 audio
  new_html = re.sub(
    r'<button[^>]*data-src="([^"]+)"[^>]*>.*?</button>',
    repl,
    html,
    flags=re.S
  )
  return new_html




################################################################################################################################################################
@app.route('/api/random')
def hokkien_random_word():
  global no_index, no_list
  max_retry = 10
  base_url = 'https://sutian.moe.edu.tw/'
  
  for _ in range(max_retry):
    # 取下一個不重複的 no
    if no_index >= len(no_list):
      random.shuffle(no_list)
      no_index = 0
    no = no_list[no_index]
    no_index += 1

    url = f'https://sutian.moe.edu.tw/zh-hant/su/{no}/'
    try:
      resp = requests.get(url,  timeout=5, verify=False)
    except Exception:
      continue
   
    if resp.status_code != 200:
      continue

    html = resp.text

    # 找到 div.row.justify-content-center
    match = re.search(r'<div class="row justify-content-center".*?</div>\s*</div>', html, re.S)
    if not match:
      continue
    div_html = match.group(0)

    # 補上 <a> 的完整網址
    #div_html = re.sub(
    #  r'href="(?!http)([^"]+)"',
    #  lambda m: f'href="{urljoin(base_url, m.group(1).lstrip("/"))}"',
    #  div_html
    #)
    
    div_html = re.sub(
      r'href="(?!http)([^"]+)"',
      lambda m: (
        f'href="{m.group(1)}"' if m.group(1).startswith('#')
        else f'href="{urljoin(base_url, m.group(1).lstrip("/"))}"'
      ),
      div_html
    )

    # 補上 <img> 的完整網址
    div_html = re.sub(
      r'src="(?!http)([^"]+)"',
      lambda m: f'src="{urljoin(base_url, m.group(1).lstrip("/"))}"',
      div_html
    )

    # 找出 button 的 data-src
    button_match = re.search(r'<button[^>]*data-src="([^"]+)"', div_html)
    audio_url = urljoin(base_url, button_match.group(1)) if button_match else ''

    # 補上 <button> 的完整 data-src
    div_html = re.sub(
      r'data-src="(?!http)([^"]+)"',
      lambda m: f'data-src="{urljoin(base_url, m.group(1).lstrip("/"))}"',
      div_html
    )

    div_html = replace_button_with_audio(div_html)

    return jsonify({'no': no, 'html': div_html, 'audio_url': audio_url})

  # 如果10次都沒找到
  return jsonify({'no': None, 'html': '<div>查無資料</div>', 'audio_url': ''})




################################################################################################################################################################
################################################################################################################################################################
def generate_option_tabs(ticker: str):
  stock = yf.Ticker(ticker)
  expirations = stock.options

  tab = Tab()
  all_options_list = []

  for expiry in expirations:
    try:
      opt_chain = stock.option_chain(expiry)
      calls = opt_chain.calls
      puts = opt_chain.puts
    except Exception:
      continue

    # 計算 premium
    calls["premium_est"] = calls["lastPrice"] * calls["volume"] * 100
    puts["premium_est"] = puts["lastPrice"] * puts["volume"] * 100

    options = pd.concat([calls.assign(type="Call"), puts.assign(type="Put")])
    options["expiry"] = expiry

    # 過濾條件
    options = options[(options["volume"] > 0) & (options["premium_est"] > 200_000)]
    if options.empty:
        continue

    options["premium_K"] = options["premium_est"] / 1000
    options = options.sort_values(by="premium_K", ascending=False)

    all_options_list.append(options)

    # 繪圖
    contracts = options["contractSymbol"].tolist()
    premiums = options["premium_K"].round(1).tolist()
    color_list = ["#FF4C4C" if t=="Call" else "#2ECC71" for t in options["type"]]

    bar = (
      Bar(init_opts=opts.InitOpts(width="1280px", height="720px"))
      .add_xaxis(contracts)
      .add_yaxis("Premium (K USD)", premiums,
                 #itemstyle_opts=opts.ItemStyleOpts(color="auto"),
                 itemstyle_opts=opts.ItemStyleOpts(color=JsCode("""
                    function(params) {
                      var colors = %s;
                      return colors[params.dataIndex];
                    }
                    """ % color_list)
                 ),
                 label_opts=opts.LabelOpts(is_show=True, position="top"))
      .set_global_opts(
        title_opts=opts.TitleOpts(title=f"{ticker.upper()} Options (Expiry {expiry})"),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, font_size=8)),
        yaxis_opts=opts.AxisOpts(name="Premium (K USD)"),
      )
    )

    tab.add(bar, expiry)

  # 總覽 tab
  if all_options_list:
    all_options = pd.concat(all_options_list)
    all_top10 = all_options.sort_values(by="premium_K", ascending=False).head(10)

    contracts = (all_top10["contractSymbol"] + " (" + all_top10["expiry"] + ")").tolist()
    premiums = all_top10["premium_K"].round(1).tolist()
    color_list = ["#FF4C4C" if t=="Call" else "#2ECC71" for t in all_top10["type"]]

    overview_bar = (
      Bar(init_opts=opts.InitOpts(width="1280px", height="720px"))
      .add_xaxis(contracts)
      .add_yaxis("Premium (K USD)", premiums,
                 #itemstyle_opts=opts.ItemStyleOpts(color="auto"),
                 itemstyle_opts=opts.ItemStyleOpts(color=JsCode("""
                    function(params) {
                      var colors = %s;
                      return colors[params.dataIndex];
                    }
                    """ % color_list)
                 ),
                 label_opts=opts.LabelOpts(is_show=True, position="top"))
      .set_global_opts(
        title_opts=opts.TitleOpts(title=f"{ticker.upper()} Options Overview (Top 10 Premium)"),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, font_size=8)),
        yaxis_opts=opts.AxisOpts(name="Premium (K USD)"),
      )
    )
    
    tab.add(overview_bar, "Overview")

  return tab.render_embed()




################################################################################################################################################################
@app.route("/optionpremium/", methods=["GET", "POST"])
def optionpremium():
  chart_html = None
  ticker = None
  if request.method == "POST":
    ticker = request.form.get("ticker")
    if ticker:
      chart_html = generate_option_tabs(ticker)

  return render_template("optionpremium.html", chart_html=chart_html, ticker=ticker)




################################################################################################################################################################
################################################################################################################################################################
def get_stock_data(ticker, start_date, end_date, session, crumb="F7GXvns0Eji"):

  start_epoch = int(datetime.combine(start_date, datetime.min.time()).timestamp())
  end_epoch = int(datetime.combine(end_date, datetime.min.time()).timestamp())
  url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_epoch}&period2={end_epoch}&interval=1d&events=history&includeAdjustedClose=true&events=div%2Csplits&crumb={crumb}"
  
  headers = {'user-agent': 'Mozilla/5.0'}
  r = session.get(url, headers=headers, timeout=5)
  r.raise_for_status()
  data = r.json()
  result = data["chart"]["result"][0]
  quote = result["indicators"]["quote"][0]
  adjclose = result["indicators"]["adjclose"][0]["adjclose"]
  df = pd.DataFrame({
    "Date": pd.to_datetime(result["timestamp"], unit='s'),
    "Open": quote["open"],
    "High": quote["high"],
    "Low": quote["low"],
    "Close": quote["close"],
    "Adj Close": adjclose,
    "Volume": quote["volume"]
  }).set_index("Date")
  df.name = ticker
  return df




################################################################################################################################################################
def calculate_variation(df):
  
  df['Adj Close Var'] = (df['Adj Close'] / df['Adj Close'].iloc[0]) * 100
  return df




################################################################################################################################################################
def align_dataframes(dfs):
  
  min_len = min(len(df) for df in dfs)
  base_index = min(range(len(dfs)), key=lambda i: len(dfs[i]))
  base_dates = dfs[base_index].index
  for i, df in enumerate(dfs):
    if len(df) != min_len:
      dfs[i] = df.reindex(base_dates, method='ffill')
      dfs[i].name = df.name
  return dfs, base_index




################################################################################################################################################################
def compute_beta(df1, df2):
  m = df1['Adj Close'].pct_change().dropna()
  t = df2['Adj Close'].pct_change().dropna()
  min_len = min(len(m), len(t))
  m, t = m[-min_len:], t[-min_len:]
  cov = np.cov(m, t)[0][1]
  var = np.var(m)
  return cov / var if var != 0 else np.nan




################################################################################################################################################################
@app.route('/compare', methods=['GET', 'POST'])
def compare():
  
  if request.method == 'POST':
    tickers = request.form.get('tickers')
    days = int(request.form.get('days', 1800))
  else:
    tickers = request.args.get('tickers')
    days = int(request.args.get('days', 1800))
    
  if not tickers:
    return "Please provide tickers parameter, e.g. ?tickers=AAPL,MSFT", 400
  tickers = [t.strip() for t in tickers.replace(' ', ',').split(',') if t.strip()]
  if len(tickers) < 1:
    return "Please provide at least one ticker.", 400

  today = date.today()
  start_date = today - timedelta(days=days)
  session = requests.Session(impersonate="chrome")
 
  stock_dfs = []
  errors = []
  for ticker in tickers:
    try:
      df = get_stock_data(ticker, start_date, today, session)
      df = calculate_variation(df)
      stock_dfs.append(df)
    except Exception as e:
      errors.append(f"{ticker}: {e}")

  if not stock_dfs:
    return "No data fetched.<br>" + "<br>".join(errors), 500

  stock_dfs, base_idx = align_dataframes(stock_dfs)

  # Calculate beta
  beta_dict = {}
  base_df = stock_dfs[0]
  for i in range(1, len(stock_dfs)):
    beta_value = compute_beta(base_df, stock_dfs[i])
    beta_dict[stock_dfs[i].name] = beta_value

  # Beta string
  beta_str = "\n".join([f"{name} / {base_df.name}: β={beta_value:.2f}" for name, beta_value in beta_dict.items()])

  # Stats string
  stats_string = ""
  for df in stock_dfs:
    stats_string += f'{df.name}: δ={df["Adj Close Var"].iloc[-1] - df["Adj Close Var"].iloc[0]:5.2f}%, σ={df["Adj Close Var"].std():5.2f}%\n'
  
  # Plot
  line = Line(init_opts=opts.InitOpts(page_title=" vs ".join(tickers), height='900px', width='1880px'))
  dates = stock_dfs[base_idx].index.strftime('%Y%m%d').tolist()
  line.add_xaxis(xaxis_data=dates)
  for df in stock_dfs:
    line.add_yaxis(
      series_name=df.name,
      y_axis=df["Adj Close Var"].map('{:.2f}'.format).tolist(),
      is_smooth=False,
      is_symbol_show=False,
      is_hover_animation=False,
      linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.9)
    )
  
  line.set_global_opts(
    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=10)),
    yaxis_opts=opts.AxisOpts(is_scale=False, splitarea_opts=opts.SplitAreaOpts(is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=0.5))),
    tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross", textstyle_opts=opts.TextStyleOpts(font_size=12)),
    legend_opts=opts.LegendOpts(textstyle_opts=opts.TextStyleOpts(font_size=12)),
    datazoom_opts=[
      opts.DataZoomOpts(is_show=False, type_="inside", xaxis_index=[0], range_start=0, range_end=100, is_realtime=False),
      opts.DataZoomOpts(is_show=True, xaxis_index=[0], type_="slider", pos_top="98%", range_start=0, range_end=100, is_realtime=False),
    ],
    title_opts=opts.TitleOpts(
      title=stats_string,
      subtitle=beta_str,  # beta in subtitle
      pos_left='10%',
      pos_top='10%',
      title_textstyle_opts=opts.TextStyleOpts(font_size=12),
      subtitle_textstyle_opts=opts.TextStyleOpts(font_size=12)
    ),
    toolbox_opts=opts.ToolboxOpts(is_show=True, feature={"dataZoom": {"yAxisIndex": "none"}, "restore": {}, "saveAsImage": {}}),
  )

  # Return HTML
  return line.render_embed()




################################################################################################################################################################
@app.route('/performance/', methods=['GET'])
def performance_diff():
  return '''
  <!DOCTYPE html>
  <html lang="en">
  <head>
      <meta charset="UTF-8">
      <title>Stock Compare</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
          body {
              background: #f8f9fa;
          }
          .container {
              max-width: 600px;
              margin-top: 80px;
              background: #fff;
              border-radius: 12px;
              box-shadow: 0 2px 16px rgba(0,0,0,0.08);
              padding: 32px 32px 24px 32px;
          }
          .form-label {
              font-weight: 500;
          }
          .btn-primary {
              width: 100%;
              font-size: 1.1rem;
              padding: 10px;
          }
          h2 {
              text-align: center;
              margin-bottom: 32px;
              font-weight: 700;
              color: #2c3e50;
          }
      </style>
  </head>
  <body>
      <div class="container">
          <h2>Stock Performance Comparison</h2>
          <form action="/compare" method="post">
              <div class="mb-3">
                  <label for="tickers" class="form-label">Tickers (comma separated):</label>
                  <input type="text" class="form-control" id="tickers" name="tickers" value="^GSPC,AAPL" required>
              </div>
              <div class="mb-3">
                  <label for="days" class="form-label">Days:</label>
                  <input type="number" class="form-control" id="days" name="days" value="1800" min="1" required>
              </div>
              <button type="submit" class="btn btn-primary">Compare</button>
          </form>
          <div class="text-center mt-4" style="color:#888;font-size:0.95em;">
              Example: <code>^GSPC,AAPL,MSFT,GOOG</code> &nbsp; | &nbsp; Days: <code>3650</code><br>
              Following tickers can be put as 1st position for beta calculation.<br>
              <code>^GSPC=S&P 500, ^IXIC=NASDAQ, ^DJI=Dow Jones, ^TWII=TAIEX</code>
              
          </div>
      </div>
  </body>
  </html>
  '''




################################################################################################################################################################
################################################################################################################################################################
def get_expirations(ticker):
  stock = yf.Ticker(ticker)
  return stock.options




################################################################################################################################################################
def get_option_chain(ticker, expiration):
  stock = yf.Ticker(ticker)
  chain = stock.option_chain(expiration)

  del stock
  gc.collect()

  return chain.calls, chain.puts




################################################################################################################################################################
def calculate_max_pain(calls, puts):
  # Data cleaning and type enforcement
  calls = calls.copy()
  puts = puts.copy()

  # Ensure openInterest column exists and handle missing values
  if 'openInterest' not in calls.columns:
      calls['openInterest'] = 0
  if 'openInterest' not in puts.columns:
      puts['openInterest'] = 0

  calls['openInterest'] = pd.to_numeric(calls['openInterest'], errors='coerce').fillna(0)
  puts['openInterest'] = pd.to_numeric(puts['openInterest'], errors='coerce').fillna(0)

  all_strikes = sorted(set(calls['strike']).union(set(puts['strike'])))
  
  if not all_strikes:
    return 0

  pain = {}

  for price in all_strikes:
    # Call Loss: sum(OI * (Price - Strike)) where Strike < Price (ITM Calls)
    itm_calls = calls[calls['strike'] < price]
    call_loss = (itm_calls['openInterest'] * (price - itm_calls['strike'])).sum()
    
    # Put Loss: sum(OI * (Strike - Price)) where Strike > Price (ITM Puts)
    itm_puts = puts[puts['strike'] > price]
    put_loss = (itm_puts['openInterest'] * (itm_puts['strike'] - price)).sum()
    
    pain[price] = call_loss + put_loss

  del all_strikes
  gc.collect()

  if not pain:
      return 0
      
  return min(pain, key=pain.get)




################################################################################################################################################################
def build_chart_option(calls, puts, ticker, max_pain, underlying_price):

  df_calls = calls[['strike', 'openInterest']].dropna()
  df_puts = puts[['strike', 'openInterest']].dropna()

  # 計算選擇權賣方的總損失
  strikes = sorted(set(df_calls['strike']).union(set(df_puts['strike'])))
  # Normalize to consistent string format to ensure markLine xAxis matching
  def fmt_strike(s):
    return str(int(s)) if s == int(s) else str(s)
  strike_labels = [fmt_strike(s) for s in strikes]

  call_losses = []
  put_losses = []
  for expiry_price in strikes:
    # 看漲選擇權損失：價內 (strike < expiry_price)
    call_loss = df_calls[df_calls['strike'] < expiry_price].apply(
        lambda r: (expiry_price - r['strike']) * r['openInterest'], axis=1).sum()
    # 看跌選擇權損失：價內 (strike > expiry_price)
    put_loss = df_puts[df_puts['strike'] > expiry_price].apply(
        lambda r: (r['strike'] - expiry_price) * r['openInterest'], axis=1).sum()
    call_losses.append(float(call_loss))
    put_losses.append(float(put_loss))

  """
  mark_line = {
      "symbol": ["none", "none"],
      "label": {"formatter": "{b}: {c}", "position": "insideMiddle"},
      "lineStyle": {"type": "dashed"},
      "data": [
          {"xAxis": str(max_pain), "name": "Max Pain", "lineStyle": {"color": "blue"}},
          {"xAxis": str(round(underlying_price, 2)), "name": "Underlying", "lineStyle": {"color": "orange"}}
      ]
  }
  """
  mark_line = {
    "symbol": ["none", "none"],
    "label": {"formatter": "{b}: {c}", "position": "insideMiddle"},
    "lineStyle": {"type": "dashed"},
    "data": []
  }

  # 保證轉成字串，且格式與 strike_labels 一致
  if max_pain is not None:
    mark_line["data"].append({
      "xAxis": fmt_strike(max_pain),
      "name": "Max Pain",
      "lineStyle": {"color": "blue"}
    })

  if underlying_price is not None:
    # 找到離 underlying_price 最近的 strike（讓 x 軸可以對得上）
    closest_strike = min(strikes, key=lambda x: abs(x - underlying_price))
    mark_line["data"].append({
      "xAxis": fmt_strike(closest_strike),
      "name": "Underlying",
      "lineStyle": {"color": "orange"}
    })

  # chart1：選擇權賣方的總損失
  chart1 = {
    "tooltip": {"trigger": "axis"},
    "legend": {"data": ["Call Loss", "Put Loss"]},
    "xAxis": {
        "type": "category",
        "data": strike_labels,
        "name": "履約價",
        "axisLabel": {"rotate": 45}
    },
    "yAxis": {
        "type": "value",
        "name": "Total Loss ($)",
        "min": "dataMin",
        "max": "dataMax"
    },
    "series": [
        {"name": "Call Loss", "type": "bar", "data": call_losses, "itemStyle": {"color": "#d62728"}, "markLine": mark_line},
        {"name": "Put Loss", "type": "bar", "data": put_losses, "itemStyle": {"color": "#2ca02c"}},
    ]
  }

  # chart2：未平倉合約數
  # Use groupby to safely handle duplicate strikes (returns scalar, not Series)
  call_oi_map = df_calls.groupby('strike')['openInterest'].sum()
  put_oi_map  = df_puts.groupby('strike')['openInterest'].sum()
  call_oi = [int(call_oi_map.get(s, 0)) for s in strikes]
  put_oi  = [-int(put_oi_map.get(s, 0)) for s in strikes]

  chart2 = {
    "tooltip": {"trigger": "axis"},
    "legend": {"data": ["Call OI", "Put OI"]},
    "xAxis": {
      "type": "category",
      "data": strike_labels,
      "name": "履約價",
      "axisLabel": {"rotate": 45}
    },
    "yAxis": {
      "type": "value",
      "name": "Open Interest",
      "min": "dataMin",
      "max": "dataMax"
    },
    "series": [
      {"name": "Call OI", "type": "bar", "stack": "x", "data": call_oi, "itemStyle": {"color": "#d62728"}, "markLine": mark_line},
      {"name": "Put OI", "type": "bar", "stack": "x", "data": put_oi, "itemStyle": {"color": "#2ca02c"}},
    ]
  }

  del call_losses, put_losses, call_oi, put_oi
  gc.collect()

  return json.dumps({"chart1": chart1, "chart2": chart2})




################################################################################################################################################################
@app.route('/maxpain/', methods=['GET', 'POST'])
def maxpain():
  ticker = ""
  expirations = []
  selected_exp = ""
  max_pain = None
  chart = None
  error = None
  underlying_price = None

  if request.method == 'POST':
    action = request.form.get('action')
    ticker = request.form.get('ticker', '').upper()
    selected_exp = request.form.get('expiration')

    try:
      if action == 'get_expirations':
        expirations = get_expirations(ticker)

      elif action == 'get_chart':
        expirations = get_expirations(ticker)               
        if not selected_exp:
            raise ValueError("請選擇到期日")
        calls, puts = get_option_chain(ticker, selected_exp)
        max_pain = calculate_max_pain(calls, puts)
        
        hist = yf.Ticker(ticker).history(period="1d")
        if hist.empty:
            underlying_price = 0
        else:
            underlying_price = hist['Close'][-1]
          
        del hist
        gc.collect()
      
        chart = build_chart_option(calls, puts, ticker, max_pain, underlying_price)

    except Exception as e:
      error = str(e)

  print(f"max_pain_price = {max_pain}, underlying_price = {underlying_price}")

  return render_template(
    'maxpain.html',
    ticker=ticker,
    expirations=expirations,
    selected_exp=selected_exp,
    max_pain=max_pain,
    underlying_price=underlying_price,
    chart=chart,
    error=error
  )




################################################################################################################################################################
################################################################################################################################################################
@app.route('/tgs/')
def index():
  return render_template('tgs.html')




################################################################################################################################################################
@app.route('/tgs_analyze', methods=['POST'])
def analyze():
  data = request.form
  
  # 1. 獲取參數
  user_api_key = data.get('api_key')
  if user_api_key == "wwsspp":
    user_api_key = api_key
  selected_model = data.get('model_name')

  if not user_api_key:
    return jsonify({'success': False, 'error': '請輸入有效的 Gemini API Key'})
  
  # 3. 獲取策略參數
  company_name = data.get('company_name')
  context_structure = data.get('context_structure')
  context_drivers = data.get('context_drivers')
  context_uncertainty = data.get('context_uncertainty')
  boundary_conditions = data.get('boundary_conditions')

  # 4. Prompt (邏輯不變，維持 3C 架構)
  prompt = f"""
  你現在是精通李吉仁教授《轉型再成長》一書的首席策略顧問。
  你的任務是為 **「{company_name}」** 這家公司進行深度的策略規劃。
  請使用你的 Google Search 搜尋能力，先對該公司做深度研究，再依據 **Context (環境脈絡)、Change (策略改變)、Choice (策略選擇)** 的 3C 架構進行分析。
  
  *** 深度研究指令 (Deep Research Instructions) ***
  1.  **廣泛搜尋**：請不要只進行一次搜尋。請利用 Google Search 工具，針對該公司的「財務報表」、「競爭對手動態」、「產業分析報告」與「最新新聞」進行多角度的資料檢索。
  2.  **數據支撐**：分析時，請務必引用具體的數字（如營收成長率、毛利率變化、市佔率）來支持你的論點。
  3.  **交叉比對**：請結合搜尋到的外部客觀數據，與使用者提供的內部 Context 進行交叉比對。
  
  **使用者輸入 (Context)：**
  1. 目標公司：{company_name}
  2. 產業結構與改變脈絡: {context_structure}
  3. 未來成長驅動因子: {context_drivers}
  4. 不確定因素與可變性: {context_uncertainty}
  5. 邊界條件: {boundary_conditions}

  ---
  **任務執行步驟：**

  ### 第一部分：財務與成長動力掃描 (基於搜尋結果)
  請搜尋 **{company_name}** 過去五年的財務報表與新聞，簡要分析：
  * **營收與獲利趨勢：** (近五年是成長、持平還是衰退？)
  * **主要成長/衰退原因：** (市場因素或競爭因素？)
  * **現有核心動力：** (目前是靠什麼賺錢？)
  
  ### 第二部分：3C 策略架構分析
  基於上述財務背景與使用者的輸入，進行 Context, Change, Choice 分析：
  
  **Module 1: Context 情境洞察**
  * 根據使用者輸入，辨識成長機會與形成成長機會的結構性脈絡，同時理解未來可能的風險，作為後續成長方向與路徑選擇的依據。
  
  **Module 2: Change 變革核心**
  * 基於**改變以創造未來**的核心概念，建立想要改變的方向：建立事業新願景，提升價值定位，建構新競爭優勢。

  **Module 3: Choice 策略選擇**
  * 首先根據使用者輸入內容，分析**企業核心能力**
  * 根據**由內而外**與**由外而內**的兩種策略思維，結合**企業核心能力**，回答以下的關鍵問題 ：產品市場選擇，商業模式選擇，成長模式選擇 (外部併購、內部發展、策略性外包、切割獨立)。

  ### 第三部分：轉型再成長的策略擬定
  * 最後，根據第一部分的財務與成長動力掃描以及第二部分的3C策略架構分析，用**以終為始**的心智模式，分析企業領導人應該建立的企業願景。 
  * 接下來，透過願景建立新的期望目標，盤點現狀與期望目標間的差距，發展關鍵路徑，幫此公司擬訂**轉型再成長**的策略。
  * 策略的規劃需要按照書中的 **SPTSi** 架構：
    1. **Strategy Choice** 從 Gap Analysis 建立若干策略軸線。
    2. 在特定策略軸線下，**Key Path** 符合 MECE 原則拆解，確保所有路徑匯聚起來可以造成策略軸線想要改變的結果。
    3. **Tactical Action** 需對應所列出的 **Key Path**，專注於兩類戰術行動：一種是改變現狀的行動，另外一種是攸關重要資源投入的專案行動。
    4. **Success Indicator** 需對應所列出的 **Tactical Action**，可以有兩種不同面向的界定：一種是兼容過程與結果指標，另外一種是兼容品質與數量的成功指標。
  """

  """
  # 2. 設定 Gemini
  try:
    genai.configure(api_key=user_api_key)
    # 使用使用者選擇的模型
    model = genai.GenerativeModel(selected_model)
  except Exception as e:
    return jsonify({'success': False, 'error': f'模型設定失敗: {str(e)}'})

  try:
    response = model.generate_content(prompt)
    analysis_html = markdown.markdown(response.text, extensions=['fenced_code'])
    #return jsonify({'success': True, 'content': analysis_html, 'raw_markdown': response.text})
    return jsonify({'success': True, 'content': analysis_html})
  except Exception as e:
    return jsonify({'success': False, 'error': str(e)})
  """
  
  url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
  
  headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": user_api_key
  }

  # ★★★ 關鍵邏輯：根據模型版本切換工具名稱 ★★★
  # Gemini 2.0 使用 "google_search"
  tool_definition = {"google_search": {}}
  payload = {
    "contents": [{
      "parts": [{"text": prompt}]
    }],
    "tools": [
      tool_definition
    ]
  }

  try:
    # 5. 發送請求
    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=600)
    
    # 6. 錯誤處理
    if response.status_code != 200:
      error_msg = f"API Error ({response.status_code}): {response.text}"
      print(error_msg)
      return jsonify({'success': False, 'error': error_msg})

    # 7. 解析 JSON 回傳
    result_json = response.json()
    
    # 檢查是否有候選回應
    if 'candidates' not in result_json or not result_json['candidates']:
      return jsonify({'success': False, 'error': 'AI 未回傳任何內容 (可能被安全機制阻擋)'})
      
    candidate = result_json['candidates'][0]
    
    # 提取文字內容
    if 'content' in candidate and 'parts' in candidate['content']:
      parts = candidate['content']['parts']
        
      # 使用 List Comprehension 提取所有 part 的 text 並串接
      # part.get('text', '') 確保萬一某個 part 沒有 text 欄位也不會報錯
      raw_text = "".join([part.get('text', '') for part in parts])
      
      # 轉換 Markdown
      #analysis_html = markdown.markdown(raw_text, extensions=['fenced_code'])
      #print(analysis_html)
      
      return jsonify({
        'success': True, 
        'raw_markdown': raw_text
      })
    else:
       return jsonify({'success': False, 'error': '回傳格式異常，找不到 content parts'})

  except Exception as e:
    print(f"Server Error: {e}")
    return jsonify({'success': False, 'error': f"伺服器內部錯誤: {str(e)}"})




################################################################################################################################################################
################################################################################################################################################################
# ==========================================
# PART 1: Heatmap Logic
# ==========================================

TWSE_URL = "https://heatmap.fugle.tw/api/heatmaps/IX0001"
OTC_URL = "https://heatmap.fugle.tw/api/heatmaps/IX0043"

# S&P 500 相關設定
SP500_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
SP500_DATA_URL = "https://www.slickcharts.com/sp500"

# Nasdaq 100 相關設定
NDX_CSV_URL = "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/top_100.csv"
NDX_DATA_URL = "https://www.slickcharts.com/nasdaq100"

INDEX_LIST =  ["^TWII", "^TWOII", "00631L.TW", "^GSPC", "^RUT", "^N225", "^KS11", "VOO", "QQQ", "QLD", "000300.SS"]

HEADERS_FUGLE = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

INDUSTRY_MAP = {
  "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
  "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業",
  "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造",
  "15": "航運業", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨",
  "19": "綜合", "20": "其他", "21": "化學工業", "22": "生技醫療業",
  "23": "油電燃氣業", "24": "半導體業", "25": "電腦及週邊設備業",
  "26": "光電業", "27": "通信網路業", "28": "電子零組件業",
  "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
  "32": "文化創意業", "33": "農業科技業", "34": "電子商務",
  "35": "綠能環保", "36": "數位雲端", "37": "運動休閒",
  "38": "居家生活", "80": "管理股票",
}

# GICS Sector 快取 (只讀取一次)
GICS_SECTOR_CACHE = {}

# Nasdaq 100 ICB Subsector 快取
NDX_SUBSECTOR_CACHE = {}

PTT_AUTHORS = ["sky22485816", "a000000000", "waitrop", "zmcx16", "Robertshih", "Test520", "zesonpso", "MrChen", "phcebus", "f204137", "a0808996", "IBIZA", "leo15824", "tosay", "LDPC", "nina801105", "mrp", "minazukimaya", "liliumeow", "onekoni"]

DATA_CACHE = {"twse": None, "otc": None, "last_update": 0}
CACHE_DURATION = 300




def industry_label(code) -> str:
  if code is None: return "其他"
  s = str(code).strip().zfill(2)
  return INDUSTRY_MAP.get(s, "其他")



'''
def init_sp500_sectors():
  """初始化 S&P 500 的 GICS Sector 對應表 (只執行一次)"""
  global GICS_SECTOR_CACHE
  
  if GICS_SECTOR_CACHE:  # 如果已經載入過就直接返回
    print("[DEBUG] GICS Sector Cache already loaded.")
    return
  
  try:
    print("[DEBUG] Fetching S&P 500 GICS Sectors from Wikipedia...")
    
    # 使用 curl_cffi 的 impersonate 參數
    r = requests.get(
      SP500_WIKI_URL, 
      impersonate="chrome120",
      timeout=15
    )
    
    print(f"[DEBUG] Wikipedia Response: {r.status_code}")
    
    if r.status_code == 200:
      # 使用 pandas 讀取 HTML 表格
      df_list = pd.read_html(r.text)
      
      if df_list:
        df = df_list[0]  # 取第一個表格
        
        print(f"[DEBUG] Wikipedia Table Columns: {df.columns.tolist()}")
        
        # 建立 Symbol -> GICS Sector 的對應
        for _, row in df.iterrows():
          try:
            symbol = str(row.get('Symbol', '')).strip()
            sector = str(row.get('GICS Sector', 'Unknown')).strip()
            
            if symbol and symbol != 'nan':
              GICS_SECTOR_CACHE[symbol] = sector
          except Exception as e:
            continue
        
        print(f"[DEBUG] GICS Sectors loaded: {len(GICS_SECTOR_CACHE)} symbols")
        
         # 驗證前 5 個
        print("[DEBUG] First 5 entries:")
        for i, (k, v) in enumerate(list(GICS_SECTOR_CACHE.items())[:5]):
          print(f"  {k}: {v}")

      else:
        print("[WARN] No tables found in Wikipedia page")
    else:
      print(f"[WARN] Wikipedia fetch failed: {r.status_code}")
      
  except Exception as e:
    print(f"[ERROR] Failed to load GICS Sectors: {e}")
    traceback.print_exc()
'''
def init_sp500_sectors():
  """初始化 S&P 500 的 GICS Sector 對應表（從 GitHub CSV 抓取）"""
  global GICS_SECTOR_CACHE

  if GICS_SECTOR_CACHE:
    print("[DEBUG] GICS Sector Cache already loaded.")
    return

  try:
    print("[DEBUG] Fetching S&P 500 GICS Sectors from GitHub CSV...")
    r = requests.get(SP500_CSV_URL, timeout=15)
    print(f"[DEBUG] S&P 500 CSV Response: {r.status_code}")

    if r.status_code == 200:
      from io import StringIO as _SIO
      df = pd.read_csv(_SIO(r.text))
      for _, row in df.iterrows():
        symbol = str(row.get('Symbol', '')).strip()
        sector = str(row.get('GICS Sector', 'Unknown')).strip()
        if symbol and symbol != 'nan':
          GICS_SECTOR_CACHE[symbol] = sector

      print(f"[DEBUG] GICS Sectors loaded: {len(GICS_SECTOR_CACHE)} symbols")
      print("[DEBUG] First 5 entries:")
      for k, v in list(GICS_SECTOR_CACHE.items())[:5]:
        print(f"  {k}: {v}")
    else:
      print(f"[WARN] S&P 500 CSV fetch failed: {r.status_code}")

  except Exception as e:
    print(f"[ERROR] Failed to load GICS Sectors: {e}")
    traceback.print_exc()




def industry_label_us(symbol: str) -> str:
  """根據 Symbol 查詢對應的 GICS Sector (含容錯處理)"""
  
  # 1. 直接查找
  if symbol in GICS_SECTOR_CACHE:
    return GICS_SECTOR_CACHE[symbol]
  
  # 2. 嘗試將點號轉為破折號 (例如 BRK.B -> BRK-B)
  symbol_alt1 = symbol.replace('.', '-')
  if symbol_alt1 in GICS_SECTOR_CACHE:
    return GICS_SECTOR_CACHE[symbol_alt1]
  
  # 3. 嘗試將破折號轉為點號 (例如 BRK-B -> BRK.B)
  symbol_alt2 = symbol.replace('-', '.')
  if symbol_alt2 in GICS_SECTOR_CACHE:
    return GICS_SECTOR_CACHE[symbol_alt2]
  
  # 4. 嘗試移除所有符號 (例如 BRK.B -> BRKB)
  symbol_alt3 = symbol.replace('.', '').replace('-', '')
  if symbol_alt3 in GICS_SECTOR_CACHE:
    return GICS_SECTOR_CACHE[symbol_alt3]
  
  # 5. 找不到時打印警告
  print(f"[WARN] GICS Sector not found for symbol: {symbol} (tried: {symbol}, {symbol_alt1}, {symbol_alt2}, {symbol_alt3})")
  return "Unknown"
  



def init_ndx_subsectors():
  """初始化 Nasdaq 100 的 Subsector 對應表（從 GitHub CSV 抓取）"""
  global NDX_SUBSECTOR_CACHE

  if NDX_SUBSECTOR_CACHE:
    print("[DEBUG] Nasdaq 100 Subsector Cache already loaded.")
    return

  try:
    print("[DEBUG] Fetching Nasdaq 100 Subsectors from GitHub CSV...")
    r = requests.get(NDX_CSV_URL, timeout=15)
    print(f"[DEBUG] NDX CSV Response: {r.status_code}")

    if r.status_code == 200:
      from io import StringIO as _SIO
      df = pd.read_csv(_SIO(r.text))
      for _, row in df.iterrows():
        ticker = str(row.get('symbol', '')).strip()
        subsector = str(row.get('industry', 'Unknown')).strip()
        if ticker and ticker != 'nan':
          NDX_SUBSECTOR_CACHE[ticker] = subsector

      print(f"[DEBUG] Nasdaq 100 Subsectors loaded: {len(NDX_SUBSECTOR_CACHE)} symbols")
      print("[DEBUG] First 5 entries:")
      for k, v in list(NDX_SUBSECTOR_CACHE.items())[:5]:
        print(f"  {k}: {v}")
    else:
      print(f"[WARN] NDX CSV fetch failed: {r.status_code}")

  except Exception as e:
    print(f"[ERROR] Failed to load Nasdaq 100 Subsectors: {e}")
    traceback.print_exc()




def industry_label_ndx(symbol: str) -> str:
  """根據 Symbol 查詢對應的 ICB Subsector (含容錯處理)"""
  
  # 1. 直接查找
  if symbol in NDX_SUBSECTOR_CACHE:
    return NDX_SUBSECTOR_CACHE[symbol]
  
  # 2. 嘗試將點號轉為破折號 (例如 BRK.B -> BRK-B)
  symbol_alt1 = symbol.replace('.', '-')
  if symbol_alt1 in NDX_SUBSECTOR_CACHE:
    return NDX_SUBSECTOR_CACHE[symbol_alt1]
  
  # 3. 嘗試將破折號轉為點號 (例如 BRK-B -> BRK.B)
  symbol_alt2 = symbol.replace('-', '.')
  if symbol_alt2 in NDX_SUBSECTOR_CACHE:
    return NDX_SUBSECTOR_CACHE[symbol_alt2]
  
  # 4. 嘗試移除所有符號 (例如 BRK.B -> BRKB)
  symbol_alt3 = symbol.replace('.', '').replace('-', '')
  if symbol_alt3 in NDX_SUBSECTOR_CACHE:
    return NDX_SUBSECTOR_CACHE[symbol_alt3]
  
  # 5. 找不到時打印警告
  print(f"[WARN] ICB Subsector not found for symbol: {symbol} (tried: {symbol}, {symbol_alt1}, {symbol_alt2}, {symbol_alt3})")
  return "Unknown"




'''
def fetch_heatmap_data():
  now = time.time()
  if (DATA_CACHE["twse"] is None) or (now - DATA_CACHE["last_update"] > CACHE_DURATION):
    try:
      print(f"[{time.ctime()}] [DEBUG] Starting Heatmap Update...")

      # === 台股資料 (原有邏輯) ===
      r_twse = requests.get(TWSE_URL, headers=HEADERS_FUGLE, timeout=15)
      r_otc = requests.get(OTC_URL, headers=HEADERS_FUGLE, timeout=15)

      print(f"[DEBUG] Fugle Response - TWSE: {r_twse.status_code}, OTC: {r_otc.status_code}")

      if r_twse.status_code == 200:
        data_twse = r_twse.json().get("data", [])
        DATA_CACHE["twse"] = pd.DataFrame(data_twse)
        print(f"[DEBUG] TWSE Data loaded: {len(data_twse)} rows")

      if r_otc.status_code == 200:
        data_otc = r_otc.json().get("data", [])
        DATA_CACHE["otc"] = pd.DataFrame(data_otc)
        print(f"[DEBUG] OTC Data loaded: {len(data_otc)} rows")

      # === [新增] S&P 500 資料 ===
      print("[DEBUG] Fetching S&P 500 data from SlickCharts...")
      try:
        # 使用 curl_cffi 的 impersonate 參數
        r_sp500 = requests.get(
          SP500_DATA_URL,
          impersonate="chrome120",
          timeout=15
        )

        print(f"[DEBUG] SlickCharts Response: {r_sp500.status_code}")

        if r_sp500.status_code == 200:
          soup = BS(r_sp500.text, 'html.parser')

          # 找到 <div class="col-lg-7"> 內的表格
          target_div = soup.find('div', class_='col-lg-7')

          if target_div:
            table = target_div.find('table')

            if table:
              # 解析表格
              rows = []
              tbody = table.find('tbody')

              if tbody:
                for idx, tr in enumerate(tbody.find_all('tr')):
                  cols = tr.find_all('td')

                  if len(cols) >= 7:
                    try:
                      # SlickCharts 表格結構:
                      # 0: #(Rank), 1: Company, 2: Symbol, 3: Weight,
                      # 4: Price, 5: Chg, 6: % Chg

                      company = cols[1].text.strip()
                      symbol = cols[2].text.strip()
                      weight_raw = cols[3].text.strip()
                      price_raw = cols[4].text.strip()
                      change_raw = cols[5].text.strip()
                      pct_change_raw = cols[6].text.strip()

                      # === [關鍵修正] 正負號判斷邏輯 ===

                      # Weight 處理
                      weight_str = weight_raw.replace('%', '').strip()
                      weight = float(weight_str)

                      # Price 處理
                      price_str = price_raw.replace('$', '').replace(',', '').strip()
                      price = float(price_str)

                      # Change 處理：保留原始正負號
                      change_str = change_raw.replace('$', '').replace(',', '').strip()
                      change = float(change_str)  # 直接轉換，保留 +/- 號

                      # % Change 處理：移除括號和百分比符號，但保留原始正負號
                      # 從 Chg 欄位判斷正負（因為 % Chg 的括號不代表負數）
                      pct_change_str = pct_change_raw.replace('(', '').replace(')', '').replace('%', '').strip()
                      pct_change = float(pct_change_str)

                      # [重要] 根據 Chg 的正負來決定 % Chg 的正負
                      if change < 0:
                        pct_change = -abs(pct_change)
                      else:
                        pct_change = abs(pct_change)

                      # 取得 GICS Sector
                      sector = industry_label_us(symbol)

                      rows.append({
                        "symbol": symbol,
                        "name": company,
                        "closePrice": price,
                        "change": change,
                        "changePercent": pct_change,
                        "weight": weight,
                        "industry": sector,
                        "type": "EQUITY"
                      })

                      # 調試：打印前 3 筆
                      if idx < 3:
                        print(f"[DEBUG] {symbol}: Change={change}, %Chg={pct_change}, Weight={weight}")

                    except (ValueError, IndexError, AttributeError) as e:
                      print(f"[WARN] Parsing row {idx} error: {e}")
                      print(f"[WARN] Raw cols: {[c.text.strip() for c in cols[:7]]}")
                      continue

              if rows:
                DATA_CACHE["sp500"] = pd.DataFrame(rows)
                print(f"[DEBUG] S&P 500 Data loaded: {len(rows)} rows")
              else:
                print("[WARN] No valid rows parsed from SlickCharts table")
            else:
              print("[WARN] Table not found in target div")
          else:
            print("[WARN] <div class='col-lg-7'> not found")
        else:
          print(f"[WARN] SlickCharts fetch failed: {r_sp500.status_code}")

      except Exception as e:
        print(f"[ERROR] SlickCharts fetch error: {e}")
        traceback.print_exc()

      # === Nasdaq 100 資料 ===
      print("[DEBUG] Fetching Nasdaq 100 data from SlickCharts...")
      try:
        r_ndx = requests.get(NDX_DATA_URL, impersonate="chrome120", timeout=15)

        print(f"[DEBUG] SlickCharts Nasdaq 100 Response: {r_ndx.status_code}")

        if r_ndx.status_code == 200:
          soup = BS(r_ndx.text, 'html.parser')
          target_div = soup.find('div', class_='col-lg-7')

          if target_div:
            table = target_div.find('table')

            if table:
              rows = []
              tbody = table.find('tbody')

              if tbody:
                for idx, tr in enumerate(tbody.find_all('tr')):
                  cols = tr.find_all('td')

                  if len(cols) >= 7:
                    try:
                      # SlickCharts Nasdaq 100 表格結構與 S&P 500 相同
                      company = cols[1].text.strip()
                      symbol = cols[2].text.strip()
                      weight_raw = cols[3].text.strip()
                      price_raw = cols[4].text.strip()
                      change_raw = cols[5].text.strip()
                      pct_change_raw = cols[6].text.strip()

                      weight_str = weight_raw.replace('%', '').strip()
                      weight = float(weight_str)

                      price_str = price_raw.replace('$', '').replace(',', '').strip()
                      price = float(price_str)

                      change_str = change_raw.replace('$', '').replace(',', '').strip()
                      change = float(change_str)

                      pct_change_str = pct_change_raw.replace('(', '').replace(')', '').replace('%', '').strip()
                      pct_change = float(pct_change_str)

                      if change < 0:
                        pct_change = -abs(pct_change)
                      else:
                        pct_change = abs(pct_change)

                      # 使用 Nasdaq 100 專用的分類函數
                      subsector = industry_label_ndx(symbol)

                      rows.append({
                        "symbol": symbol,
                        "name": company,
                        "closePrice": price,
                        "change": change,
                        "changePercent": pct_change,
                        "weight": weight,
                        "industry": subsector,
                        "type": "EQUITY"
                      })

                      if idx < 3:
                        print(f"[DEBUG] NDX {symbol}: Change={change}, %Chg={pct_change}, Weight={weight}, Subsector={subsector}")

                    except (ValueError, IndexError, AttributeError) as e:
                      print(f"[WARN] Nasdaq 100 Parsing row {idx} error: {e}")
                      continue

              if rows:
                DATA_CACHE["ndx"] = pd.DataFrame(rows)
                print(f"[DEBUG] Nasdaq 100 Data loaded: {len(rows)} rows")
              else:
                print("[WARN] No valid rows parsed from Nasdaq 100 table")
            else:
              print("[WARN] Nasdaq 100 table not found")
          else:
            print("[WARN] Nasdaq 100 <div class='col-lg-7'> not found")
        else:
          print(f"[WARN] SlickCharts Nasdaq 100 fetch failed: {r_ndx.status_code}")

      except Exception as e:
        print(f"[ERROR] SlickCharts Nasdaq 100 fetch error: {e}")
        traceback.print_exc()


      DATA_CACHE["last_update"] = now
      print(f"[{time.ctime()}] [DEBUG] Heatmap Cache Updated.")
      
    except Exception as e:
      print(f"[ERROR] Fetching heatmap data failed: {e}")
      traceback.print_exc()
'''


def fetch_us_yahoo_quotes(symbols):
  """Batch fetch quotes from Yahoo Finance API. Uses session + crumb for auth."""
  if not symbols:
    return {}
  result = {}
  try:
    session = requests.Session(impersonate="chrome120")
    # Step 1: visit a Yahoo Finance stock page to get proper session cookies
    # (visiting just the homepage doesn't set the right auth cookies)
    session.get("https://finance.yahoo.com/quote/AAPL/", timeout=10)
    # Step 2: get crumb token
    crumb_r = session.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    crumb = crumb_r.text.strip()
    if not crumb or "<" in crumb or "Too Many" in crumb:
      print(f"[WARN] Yahoo Finance crumb fetch failed: {crumb_r.status_code} {crumb[:80]}")
      return {}
    print(f"[DEBUG] Yahoo Finance crumb: {crumb}")
  except Exception as e:
    print(f"[ERROR] fetch_us_yahoo_quotes session/crumb error: {e}")
    return {}

  BATCH = 200
  for i in range(0, len(symbols), BATCH):
    batch = symbols[i:i+BATCH]
    try:
      url = "https://query2.finance.yahoo.com/v7/finance/quote"
      params = {
        "symbols": ",".join(batch),
        "fields": "regularMarketPrice,regularMarketChangePercent,regularMarketChange,marketCap,shortName,regularMarketVolume,regularMarketOpen,regularMarketDayHigh,regularMarketDayLow",
        "crumb": crumb,
      }
      r = session.get(url, params=params, timeout=15)
      if r.status_code == 200:
        data = r.json()
        for quote in data.get("quoteResponse", {}).get("result", []):
          sym = quote.get("symbol")
          if sym:
            result[sym] = quote
      else:
        print(f"[WARN] Yahoo Finance quote batch {i//BATCH+1} failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
      print(f"[ERROR] fetch_us_yahoo_quotes batch {i//BATCH+1} error: {e}")
  print(f"[DEBUG] fetch_us_yahoo_quotes: got {len(result)} quotes for {len(symbols)} symbols")
  return result


def fetch_heatmap_data():
  now = time.time()
  if (DATA_CACHE["twse"] is None) or (now - DATA_CACHE["last_update"] > CACHE_DURATION):
    try:
      print(f"[{time.ctime()}] [DEBUG] Starting Heatmap Update...")

      # === 台股資料 (原有邏輯，不變) ===
      r_twse = requests.get(TWSE_URL, headers=HEADERS_FUGLE, timeout=15)
      r_otc = requests.get(OTC_URL, headers=HEADERS_FUGLE, timeout=15)

      print(f"[DEBUG] Fugle Response - TWSE: {r_twse.status_code}, OTC: {r_otc.status_code}")

      if r_twse.status_code == 200:
        data_twse = r_twse.json().get("data", [])
        DATA_CACHE["twse"] = pd.DataFrame(data_twse)
        print(f"[DEBUG] TWSE Data loaded: {len(data_twse)} rows")

      if r_otc.status_code == 200:
        data_otc = r_otc.json().get("data", [])
        DATA_CACHE["otc"] = pd.DataFrame(data_otc)
        print(f"[DEBUG] OTC Data loaded: {len(data_otc)} rows")

      # === S&P 500 資料 (via Yahoo Finance quote API) ===
      print("[DEBUG] Fetching S&P 500 data from Yahoo Finance...")
      try:
        if not GICS_SECTOR_CACHE:
          init_sp500_sectors()
        sp500_symbols = list(GICS_SECTOR_CACHE.keys())
        if sp500_symbols:
          quotes = fetch_us_yahoo_quotes(sp500_symbols)
          total_mc = sum((q.get("marketCap") or 0) for q in quotes.values())
          total_tv = sum(((q.get("regularMarketVolume") or 0) * (q.get("regularMarketPrice") or 0)) for q in quotes.values())
          rows = []
          for sym in sp500_symbols:
            q = quotes.get(sym)
            if not q:
              continue
            mc = q.get("marketCap") or 0
            price = q.get("regularMarketPrice") or 0
            vol = q.get("regularMarketVolume") or 0
            tv = price * vol
            rows.append({
              "symbol": sym,
              "name": q.get("shortName", sym),
              "closePrice": price,
              "openPrice": q.get("regularMarketOpen") or price,
              "highPrice": q.get("regularMarketDayHigh") or price,
              "lowPrice": q.get("regularMarketDayLow") or price,
              "tradeVolume": vol,
              "tradeValue": tv,
              "change": q.get("regularMarketChange") or 0,
              "changePercent": q.get("regularMarketChangePercent") or 0,
              "marketCapWeight": (mc / total_mc * 100) if total_mc > 0 else 0,
              "tradeValueWeight": (tv / total_tv * 100) if total_tv > 0 else 0,
              "industry": industry_label_us(sym),
              "type": "EQUITY"
            })
          if rows:
            DATA_CACHE["sp500"] = pd.DataFrame(rows)
            print(f"[DEBUG] S&P 500 Data loaded: {len(rows)} rows")
          else:
            print("[WARN] No S&P 500 data returned from Yahoo Finance")
        else:
          print("[WARN] GICS_SECTOR_CACHE empty, skipping S&P 500")
      except Exception as e:
        print(f"[ERROR] S&P 500 Yahoo Finance fetch error: {e}")
        traceback.print_exc()

      # === Nasdaq 100 資料 (via Yahoo Finance quote API) ===
      print("[DEBUG] Fetching Nasdaq 100 data from Yahoo Finance...")
      try:
        if not NDX_SUBSECTOR_CACHE:
          init_ndx_subsectors()
        ndx_symbols = list(NDX_SUBSECTOR_CACHE.keys())
        if ndx_symbols:
          quotes = fetch_us_yahoo_quotes(ndx_symbols)
          total_mc = sum((q.get("marketCap") or 0) for q in quotes.values())
          total_tv = sum(((q.get("regularMarketVolume") or 0) * (q.get("regularMarketPrice") or 0)) for q in quotes.values())
          rows = []
          for sym in ndx_symbols:
            q = quotes.get(sym)
            if not q:
              continue
            mc = q.get("marketCap") or 0
            price = q.get("regularMarketPrice") or 0
            vol = q.get("regularMarketVolume") or 0
            tv = price * vol
            rows.append({
              "symbol": sym,
              "name": q.get("shortName", sym),
              "closePrice": price,
              "openPrice": q.get("regularMarketOpen") or price,
              "highPrice": q.get("regularMarketDayHigh") or price,
              "lowPrice": q.get("regularMarketDayLow") or price,
              "tradeVolume": vol,
              "tradeValue": tv,
              "change": q.get("regularMarketChange") or 0,
              "changePercent": q.get("regularMarketChangePercent") or 0,
              "marketCapWeight": (mc / total_mc * 100) if total_mc > 0 else 0,
              "tradeValueWeight": (tv / total_tv * 100) if total_tv > 0 else 0,
              "industry": industry_label_ndx(sym),
              "type": "EQUITY"
            })
          if rows:
            DATA_CACHE["ndx"] = pd.DataFrame(rows)
            print(f"[DEBUG] Nasdaq 100 Data loaded: {len(rows)} rows")
          else:
            print("[WARN] No NDX data returned from Yahoo Finance")
        else:
          print("[WARN] NDX_SUBSECTOR_CACHE empty, skipping Nasdaq 100")
      except Exception as e:
        print(f"[ERROR] NDX Yahoo Finance fetch error: {e}")
        traceback.print_exc()

      DATA_CACHE["last_update"] = now
      print(f"[{time.ctime()}] [DEBUG] Heatmap Cache Updated.")

    except Exception as e:
      print(f"[ERROR] Fetching heatmap data failed: {e}")
      traceback.print_exc()


def get_clean_dataframe(market):
  fetch_heatmap_data()
  
  if market == "sp500":
    df = DATA_CACHE.get("sp500")
  elif market == "ndx":
    df = DATA_CACHE.get("ndx")
  elif market == "twse":
    df = DATA_CACHE.get("twse")
  else:
    df = DATA_CACHE.get("otc")
  
  if df is None or df.empty:
    print(f"[WARN] Dataframe for {market} is empty or None.")
    return pd.DataFrame()

  return df.copy()




def build_heatmap_data(df: pd.DataFrame, type_filter: str, area_metric: str):
  if df.empty: 
    return []

  data = df[df["type"] == type_filter].copy()
  
  if data.empty: 
    print(f"[DEBUG] No data found for type_filter: {type_filter}")
    return []

  # === 判斷是否為美股市場 (S&P 500 或 Nasdaq 100) ===
  is_us_market = "marketCapWeight" in data.columns

  if is_us_market:
    size_col = "marketCapWeight" if area_metric == "marketValueWeight" else "tradeValueWeight"
  else:
    # 台股邏輯 (維持不變)
    size_col = "tradeValue"
    if type_filter == "EQUITY":
      size_col = "marketValueWeight" if area_metric == "marketValueWeight" else "tradeValueWeight"

  # 數值轉換
  raw_size = data.get(size_col, pd.Series([0]*len(data)))
  if raw_size.dtype == 'object':
    raw_size = raw_size.astype(str).str.replace(',', '')
  
  data["size_val"] = pd.to_numeric(raw_size, errors="coerce").fillna(0)
  data["chg_pct"] = pd.to_numeric(data.get("changePercent"), errors="coerce").fillna(0)
  data["price"] = pd.to_numeric(data.get("closePrice"), errors="coerce").fillna(0)
  
  if is_us_market:
    data["open"] = pd.to_numeric(data.get("openPrice"), errors="coerce").fillna(data["price"])
    data["high"] = pd.to_numeric(data.get("highPrice"), errors="coerce").fillna(data["price"])
    data["low"] = pd.to_numeric(data.get("lowPrice"), errors="coerce").fillna(data["price"])
    data["vol"] = pd.to_numeric(data.get("tradeVolume"), errors="coerce").fillna(0)
    data["val"] = pd.to_numeric(data.get("tradeValue"), errors="coerce").fillna(0)
  else:
    data["open"] = pd.to_numeric(data.get("openPrice"), errors="coerce").fillna(0)
    data["high"] = pd.to_numeric(data.get("highPrice"), errors="coerce").fillna(0)
    data["low"] = pd.to_numeric(data.get("lowPrice"), errors="coerce").fillna(0)
    data["vol"] = pd.to_numeric(data.get("tradeVolume"), errors="coerce").fillna(0)
    data["val"] = pd.to_numeric(data.get("tradeValue"), errors="coerce").fillna(0)
  
  data["change_val"] = pd.to_numeric(data.get("change"), errors="coerce").fillna(0)
  data = data[data["size_val"] > 0]

  tree_data = []

  def get_value_array(row):
    return [
      row["size_val"], row["chg_pct"], row["price"], row["size_val"],
      row["open"], row["high"], row["low"], row["change_val"], row["vol"], row["val"]
    ]

  if type_filter == "INDEX":
    for _, row in data.iterrows():
      tree_data.append({"name": row["name"], "value": get_value_array(row)})
  else:
    # === [修改] 根據來源選擇分類函數 ===
    if is_us_market:
      data["industry_name"] = data["industry"]
    else:
      data["industry_name"] = data["industry"].apply(industry_label)
    
    grouped = data.groupby("industry_name")
    for industry, group in grouped:
      children = []
      for _, row in group.iterrows():
        children.append({
          "name": row['name'], 
          "value": get_value_array(row), 
          "id": row["symbol"]
        })
      tree_data.append({"name": industry, "children": children})

  return tree_data




# ==========================================
# PART 2: Yahoo Notify Logic
# ==========================================
class StockMonitor:
  def __init__(self):
    print("[DEBUG] Initializing StockMonitor...")
    self.session = requests.Session(impersonate="chrome")
    self.session.verify = False
    
    # Headers
    self.headers = {
      'authority': 'query1.finance.yahoo.com',
      'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
      'accept-language': 'zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    }
    
    # Initial Portfolio
    self.portfolio = [
      ["2454.TW", 820, 1200],
      ["2317.TW", 102, 130],
      ["3105.TWO", 195, 205],
      ["4927.TW", 100, 110],
      ["6706.TW", 157, 168]
    ]
    
    # Initial PTT author list
    self.author_list = []
    
    
    # Indices for portfolio list
    self.IDX_T = 0
    self.IDX_F = 1
    self.IDX_C = 2
    self.IDX_P = 3
    self.IDX_10MA = 4
    self.IDX_200MA = 7
    self.IDX_10MA_1 = 8
    self.IDX_200MA_1 = 11

    self.initialized = False
    self.url_git_json = portfolio_url
    
    # Constants
    self.DELTA_U = 0.01618
    self.DELTA_D = -0.01618
    self.DELTA_A = 0.00809  
    self.DELTA_I_U   = 0.00618   # delta up for index
    self.DELTA_I_D   = -0.00618  # delta down for index
    self.DELTA_I_A   = 0.00382   # delta abs for index

    
    # === 新增：計數器與新聞快取 ===
    self.run_count = 0
    self.news_cache = []

  def ma_calculation(self, ticker):
    # print(f"[DEBUG] Calculating MA for {ticker[0]}...") # Optional trace
    today = date.today()
    startDate = today - timedelta(days=365)
    endDate = today
    startDate_epoch = int(datetime.combine(startDate, datetime.now().time()).timestamp())
    endDate_epoch = int(datetime.combine(endDate, datetime.now().time()).timestamp())
    crumb = "dx7e5yMCafJ"
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker[0]}?period1={startDate_epoch}&period2={endDate_epoch}&interval=1d&events=history&includeAdjustedClose=true&events=div%2Csplits&crumb={crumb}"
    
    try:
      r = self.session.get(url, headers=self.headers, timeout=10)
      if r.status_code == 200:
        data = r.json()
        close = data["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]
        if None in close: return [None]*9
        
        precision = 4 if close[-1] < 1 else 2
        def safe_avg(lst): return round(sum(lst)/len(lst), precision) if lst else None

        ma10 = safe_avg(close[-10:])
        ma20 = safe_avg(close[-20:])
        ma60 = safe_avg(close[-60:])
        ma200 = safe_avg(close[-200:])
        ma10_1 = safe_avg(close[-11:-1])
        ma20_1 = safe_avg(close[-21:-1])
        ma60_1 = safe_avg(close[-61:-1])
        ma200_1 = safe_avg(close[-201:-1])
        
        return [None, ma10, ma20, ma60, ma200, ma10_1, ma20_1, ma60_1, ma200_1]
      else:
        print(f"[WARN] MA Fetch failed for {ticker[0]}, Status: {r.status_code}")
    except Exception as e:
      print(f"[ERROR] MA Calc Error {ticker[0]}: {e}")
    return [None]*9

  def init_portfolio(self):
    print("[DEBUG] Fetching Portfolio JSON from GitHub...")
    try:
      r = self.session.get(self.url_git_json, headers=self.headers, timeout=5)
      if r.status_code == 200:
        json_git = r.json()
        self.portfolio = json_git["portfolio"]
        print(f"[DEBUG] Portfolio loaded from GitHub. Total items: {len(self.portfolio)}")
        self.author_list = json_git["author"]
        print(f"[DEBUG] Author List loaded from GitHub. Total items: {len(self.author_list)}")
      else:
        print(f"[WARN] GitHub Portfolio fetch failed: {r.status_code}")
    except Exception as e:
      print(f"[ERROR] Init Portfolio failed: {e}")
      pass

    print("[DEBUG] Calculating missing MA data for portfolio...")
    for p in self.portfolio:
      # 當長度不足時計算，或者在 Reset 強制重算時也會補上
      if len(p) < 12:
        ma = self.ma_calculation(p)
        p.extend(ma)
      else:
        # 如果欄位已存在 (Reset 情況)，則更新後面的 MA
        ma = self.ma_calculation(p)
        if len(ma) >= 9:
            p[4:12] = ma[1:]

    self.initialized = True
    print("[DEBUG] Portfolio Initialization Complete.")


  def _fetch_ptt_rss(self, board='Stock'):
    """Fetch PTT articles via Atom RSS feed (works globally, no IP restriction)."""
    import xml.etree.ElementTree as ET
    entries = []
    try:
      r = requests.get(f'https://www.ptt.cc/atom/{board}.xml', impersonate="chrome120", timeout=10, verify=False)
      if r.status_code == 200:
        root = ET.fromstring(r.text)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in root.findall('atom:entry', ns):
          title = entry.find('atom:title', ns).text or ''
          link = entry.find('atom:link', ns).get('href', '')
          updated = entry.find('atom:updated', ns).text or ''
          author_el = entry.find('atom:author/atom:name', ns)
          author = author_el.text if author_el is not None else ''
          # Extract short date from ISO timestamp (e.g. "2026-09-19T10:53:16+08:00" -> " 9/19")
          date_short = updated
          try:
            dt = datetime.fromisoformat(updated)
            date_short = f'{dt.month}/{dt.day:02d}'
          except Exception:
            pass
          entries.append({'title': title, 'link': link, 'author': author, 'date': date_short})
        print(f"[DEBUG] PTT RSS fetched {len(entries)} entries for {board}")
    except Exception as e:
      print(f"[ERROR] PTT RSS Error: {e}")
    return entries


  def get_ptt_news(self, keywords):
    news_list = []
    url = 'https://www.ptt.cc/bbs/Stock/index.html'
    try:
      for i in range(5):
        r = requests.get(url, impersonate="chrome120", verify=False, cookies={'over18': '1'}, timeout=10)
        if r.status_code == 200:
          soup = BS(r.text, 'html.parser')
          articles = soup.select('div.r-ent')
          if not articles:
            print("[WARN] PTT News: 200 but no articles (Cloudflare soft-block), falling back to RSS")
            break
          paging = soup.select('div.btn-group-paging a')
          if not paging or len(paging) < 2:
            break
          url = 'https://www.ptt.cc' + paging[1]['href']

          for a in articles:
            element = a.contents[3]
            if len(element.contents) < 2: continue
            title = element.text.strip('\n')
            
            matched = False
            for k in keywords:
              if k in title:
                matched = True
                break
            
            nrec = a.contents[1].text
            is_hot = (nrec == '爆') or (nrec.isdigit() and int(nrec) > 20)

            if matched or is_hot:
              link = 'https://www.ptt.cc' + element.contents[1]['href']
              date = a.contents[5].contents[5].text
              tag = f"🔥({nrec})" if is_hot else "👀"
              news_list.append({"date": date, "title": title, "link": link, "tag": tag})
              
          time.sleep(0.5)
        else:
          print(f"[WARN] PTT News scrape failed (status={r.status_code}), falling back to RSS")
          break
          
    except Exception as e:
      print(f"[ERROR] PTT News scrape error: {e}")

    # Fallback: RSS when scraping returned nothing
    if not news_list:
      print("[DEBUG] PTT News: using RSS fallback")
      for entry in self._fetch_ptt_rss('Stock'):
        matched = any(k in entry['title'] for k in keywords)
        if matched:
          news_list.append({"date": entry['date'], "title": entry['title'], "link": entry['link'], "tag": "👀"})

    return news_list




  def get_ptt_tickers(self, portfolio):
    news_list = []
    url = 'https://www.ptt.cc/bbs/Stock/index.html'
    scrape_ok = False

    try:
      for _ in range(5):
        r = requests.get(url, impersonate="chrome120", verify=False, cookies={'over18': '1'}, timeout=10)
        if r.status_code == 200:
          r.encoding = 'utf-8'

          soup = BS(r.text, 'html.parser')
          articles = soup.select('div.r-ent')
          if not articles:
            print("[WARN] PTT Tickers: 200 but no articles (Cloudflare soft-block), falling back to RSS")
            break
          scrape_ok = True
          paging = soup.select('div.btn-group-paging a')
          if not paging or len(paging) < 2:
            break

          url = 'https://www.ptt.cc' + paging[1]['href']

          for a in articles:
            element = a.contents[3]

            if len(element.contents) < 2:
              continue

            title = element.text.strip('\n')

            for p in portfolio:

              symbol = p['symbol']
              symbol_des = (p['symbolName'].split(' '))[0]

              idx = symbol.find('.')
              if idx != -1:
                ticker = symbol[:idx]
              else:
                ticker = symbol

              if (ticker in title) or (symbol_des in title):
                link = 'https://www.ptt.cc' + element.contents[1]['href']
                date = a.contents[5].contents[5].text
              
                tag = f'💲(<a href="https://www.pttweb.cc/ptt-search#gsc.tab=0&gsc.q={ticker}&gsc.sort=date" target="_blank" style="color:inherit;">{ticker}</a>)'
                news_list.append({"date": date, "title": title, "link": link, "tag": tag})
                
          time.sleep(0.5)
        else:
          print(f"[WARN] PTT Ticker scrape failed (status={r.status_code}), falling back to RSS")
          break
          
    except Exception as e:
      print(f"[ERROR] PTT Ticker scrape error: {e}")

    # Fallback: RSS when scraping returned nothing
    if not news_list and not scrape_ok:
      print("[DEBUG] PTT Tickers: using RSS fallback")
      for entry in self._fetch_ptt_rss('Stock'):
        title = entry['title']
        for p in portfolio:
          symbol = p['symbol']
          symbol_des = (p['symbolName'].split(' '))[0]
          idx = symbol.find('.')
          ticker = symbol[:idx] if idx != -1 else symbol
          if (ticker in title) or (symbol_des in title):
            tag = f'💲(<a href="https://www.pttweb.cc/ptt-search#gsc.tab=0&gsc.q={ticker}&gsc.sort=date" target="_blank" style="color:inherit;">{ticker}</a>)'
            news_list.append({"date": entry['date'], "title": title, "link": entry['link'], "tag": tag})

    return news_list



  
  def get_ptt_authors(self, board, names):
    news_list = []
    url = f'https://www.ptt.cc/bbs/{board}/index.html'
    scrape_ok = False
    
    try:
      for _ in range(10):
        r = requests.get(url, impersonate="chrome120", verify=False, cookies={'over18': '1'}, timeout=10)
        if r.status_code == 200:
          r.encoding = 'utf-8'
          
          soup = BS(r.text, 'html.parser')
          articles = soup.select('div.r-ent')
          if not articles:
            print("[WARN] PTT Authors: 200 but no articles (Cloudflare soft-block), falling back to RSS")
            break
          scrape_ok = True
          paging = soup.select('div.btn-group-paging a')
          if not paging or len(paging) < 2:
            break

          url = 'https://www.ptt.cc' + paging[1]['href']

          for a in articles:
            element = a.contents[3]

            if len(element.contents) < 2:
              continue

            title = element.text.strip('\n')     
            meta = a.contents[5]
            name = meta.contents[1].text

            for n in names:

              if n == name:
                link = 'https://www.ptt.cc' + element.contents[1]['href']
                date = a.contents[5].contents[5].text
                tag = f'👤(<a href="https://www.pttweb.cc/user/{n}" target="_blank" style="color:inherit;">{n}</a>)'
                news_list.append({"date": date, "title": title, "link": link, "tag": tag})

          time.sleep(0.5)
        else:
          print(f"[WARN] PTT Author scrape failed (status={r.status_code}), falling back to RSS")
          break

    except Exception as e:
      print(f"[ERROR] PTT Author scrape error: {e}")

    # Fallback: RSS when scraping returned nothing
    if not news_list and not scrape_ok:
      print("[DEBUG] PTT Authors: using RSS fallback")
      for entry in self._fetch_ptt_rss(board):
        if entry['author'] in names:
          n = entry['author']
          tag = f'👤(<a href="https://www.pttweb.cc/user/{n}" target="_blank" style="color:inherit;">{n}</a>)'
          news_list.append({"date": entry['date'], "title": entry['title'], "link": entry['link'], "tag": tag})

    return news_list




  def check_signals(self, p_idx, price, price_1):
    # (Logic unchanged, omitted for brevity)
    p = self.portfolio[p_idx]

    # 取用欄位
    ma10 = p[4]
    ma20 = p[5]
    ma60 = p[6]
    ma200 = p[7]
    ma10_1 = p[8]
    ma20_1 = p[9]
    ma60_1 = p[10]
    ma200_1 = p[11]
    price_low = p[1]
    price_high = p[2]

    symbol = p[0]
    msgs = []

    # 輔助函數:根據箭頭自動添加顏色 class
    def styled_msg(text):
      if '↗' in text:
        return f'<span class="up">{text}</span>'
      elif '↘' in text:
        return f'<span class="down">{text}</span>'
      elif '-Fall' in text:
        return f'<span class="down">{text}</span>'
      else:
        return f'<span>{text}</span>'

    # --------------------------
    # 1. FLOOR / CEILING cross
    # --------------------------
    if price_low is not None:
      if (price > price_low) and (price_1 <= price_low):
        msgs.append(styled_msg(f"↗L({price_low})"))
      if (price < price_low) and (price_1 >= price_low):
        msgs.append(styled_msg(f"↘L({price_low})"))

    if price_high is not None:
      if (price > price_high) and (price_1 <= price_high):
        msgs.append(styled_msg(f"↗H({price_high})"))
      if (price < price_high) and (price_1 >= price_high):
        msgs.append(styled_msg(f"↘H({price_high})"))

    # --------------------------
    # 2. SMA10 / SMA20 / SMA60 / SMA200 Trend Cross
    # --------------------------
    if ma10_1 is not None:
      if (price > ma10) and (price_1 <= ma10_1):
        msgs.append(styled_msg(f"↗MA10({ma10})"))
      if (price < ma10) and (price_1 >= ma10_1):
        text = f"↘MA10({ma10})"
        if hasattr(self, "macd_w_is_fall"):
          if symbol in self.macd_w_is_fall and self.macd_w_is_fall[symbol] is True:
            text += " MACD-Fall"
        msgs.append(styled_msg(text))

    if ma20_1 is not None:
      if (price > ma20) and (price_1 <= ma20_1):
        msgs.append(styled_msg(f"↗MA20({ma20})"))
      if (price < ma20) and (price_1 >= ma20_1):
        text = f"↘MA20({ma20})"
        if ma10 is not None and ma10 > ma20:
          text += " JUMP-Fall"
        msgs.append(styled_msg(text))

    if ma60_1 is not None:
      if (price > ma60) and (price_1 <= ma60_1):
        msgs.append(styled_msg(f"↗MA60({ma60})"))
      if (price < ma60) and (price_1 >= ma60_1):
        msgs.append(styled_msg(f"↘MA60({ma60})"))

    if ma200_1 is not None:
      if (price > ma200) and (price_1 <= ma200_1):
        msgs.append(styled_msg(f"↗MA200({ma200})"))
      if (price < ma200) and (price_1 >= ma200_1):
        msgs.append(styled_msg(f"↘MA200({ma200})"))

    # --------------------------
    # 3. SMA Crossing (MA10-20, MA20-60, MA10-60)
    # --------------------------
    if ma10_1 is not None and ma60_1 is not None:
      if (ma10 > ma60) and (ma10_1 <= ma60_1):
        msgs.append(styled_msg(f"MA10↗60({ma10},{ma60})"))
      if (ma10 < ma60) and (ma10_1 >= ma60_1):
        msgs.append(styled_msg(f"MA10↘60({ma10},{ma60})"))

    if ma10_1 is not None and ma20_1 is not None:
      if (ma10 > ma20) and (ma10_1 <= ma20_1):
        msgs.append(styled_msg(f"MA10↗20({ma10},{ma20})"))
      if (ma10 < ma20) and (ma10_1 >= ma20_1):
        msgs.append(styled_msg(f"MA10↘20({ma10},{ma20})"))

    if ma20_1 is not None and ma60_1 is not None:
      if (ma20 > ma60) and (ma20_1 <= ma60_1):
        msgs.append(styled_msg(f"MA20↗60({ma20},{ma60})"))
      if (ma20 < ma60) and (ma20_1 >= ma60_1):
        msgs.append(styled_msg(f"MA20↘60({ma20},{ma60})"))

    # --------------------------
    # 4. 回傳結果
    # --------------------------
    return " | ".join(msgs)

  


  def get_fitx_data(self):
    try:
      url = "https://histock.tw/stock/module/function.aspx?m=stocktop2017&no=FITX"
      r = self.session.get(url, headers=self.headers, timeout=5)
      
      if r.status_code == 200:
        raw_html = r.text.split('~')[0]
        soup = BS(raw_html, 'html.parser')
        values = soup.select('div.ci_value')
        
        if len(values) >= 3:
          price = float(values[0].text.strip().replace(',', ''))
          change_val_str = values[1].text.strip().replace('▼', '-').replace('▲', '')
          change_pct_str = values[2].text.strip()

          try:
            change_val = float(change_val_str)
          except:
            change_val = 0.0
          
          try:
            delta = float(change_pct_str.replace('%', '')) / 100
          except:
            delta = 0.0

          return {
            "symbol": "FITX",
            "name": "台指期",
            "price": price,
            "change": change_pct_str,
            "change_val": change_val, # [新增]
            "alert": "",
            "delta": delta,
            "delta_val": 0.0 # [新增] 台指期可能沒有 "監控起始價" 的概念，暫設為 0
          }
    except Exception as e:
      print(f"[ERROR] FITX Fetch Error: {e}")
    
    return None  




  def run_check(self):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Starting Monitor run_check (Count: {self.run_count})")
    if not self.initialized:
      self.init_portfolio()
      
    # ==========================================
    # [新增] 每 30 次迴圈，更新一次所有股票的 MA
    # ==========================================
    if self.run_count > 0 and self.run_count % 30 == 0:
      print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Updating Portfolio Moving Averages...")
      for p in self.portfolio:
        # p[0] 是 symbol (e.g., "2330.TW")
        # 重新計算 MA
        new_ma = self.ma_calculation(p)
        
        # ma_calculation 回傳格式: [None, ma10, ma20, ma60, ma200, ma10_1, ma20_1, ma60_1, ma200_1]
        # self.portfolio (p) 的結構: 
        # idx 0:Symbol, 1:Low, 2:High, 3:Price, 
        # idx 4:MA10, 5:MA20, 6:MA60, 7:MA200, 8:MA10_1, ... 11:MA200_1
        
        # 確保有抓到資料才更新
        if len(new_ma) >= 9:
          # 使用 List Slicing 直接替換掉舊的 MA 數值 (從 index 4 到 11)
          p[4:12] = new_ma[1:]
          # print(f"[DEBUG] Updated MA for {p[0]}")
      print("[DEBUG] MA Update Complete.")

    rows = []
    ticker_news = []
    
    chunk_len = 20
    for c in range(0, len(self.portfolio), chunk_len):
      chunk = self.portfolio[c:c+chunk_len]
      tickers = [p[0] for p in chunk]
      tickers_url = ','.join(tickers)
      url = yahoo_url + tickers_url
      
      # print(f"[DEBUG] Fetching chunk {c//chunk_len + 1} from Yahoo...") # Trace chunk
      
      try:
        r = self.session.get(url, headers=self.headers, timeout=5)
        if r.status_code == 200:
          data = r.json()
          
          if self.run_count % 30 == 0:
            print("[DEBUG] Fetching PTT Ticker News...")
            ticker_news += self.get_ptt_tickers(data) 
          
          for item in data:
            symbol = item['symbol']
            if 'price' not in item or 'raw' not in item['price']: continue
            
            try:
              price = float(item['price']['raw'])
              price_1 = float(item.get('regularMarketPreviousClose', {}).get('raw', price))
            except:
              continue
              
            for i, p in enumerate(self.portfolio):
              if p[0] == symbol:
                name = item.get('symbolName', '').split(' ')[0]
                
                change_percent_str = item.get('changePercent', '0%')                
                # 嘗試提取 change 數值，若失敗則設為 0
                try:
                  change_val = float(item.get('change', {}).get('raw', 0))
                except (TypeError, ValueError):
                  change_val = 0.0
                
                p_last = p[self.IDX_P]
                if p_last is None: p[self.IDX_P] = price
                
                delta = 0
                delta_val = 0 # 新增 delta_val
                if p[self.IDX_P]:
                  delta = (price - p[self.IDX_P]) / p[self.IDX_P]
                  delta_val = price - p[self.IDX_P] # 計算相對於監控起始價的變動值
                  p[self.IDX_P] = price

                # 1. 收集所有警示訊息到一個 List
                alert_msgs = []

                # A. 急劇變動
                if symbol in INDEX_LIST: delta_a_judge = self.DELTA_I_A
                else: delta_a_judge = self.DELTA_A
                  
                if abs(delta) > delta_a_judge:
                  print(f"[ALERT] {symbol} {name} Delta: {delta:.4f}") # ALERT Debug
                  if delta > 0: 
                    alert_msgs.append(f'<span class="up">▲急拉 {delta*100:.2f}%</span>')
                  else: 
                    alert_msgs.append(f'<span class="down">▼急殺 {delta*100:.2f}%</span>')
                    
                # B. 支撐壓力
                if p[self.IDX_F] and price < p[self.IDX_F]:
                  alert_msgs.append(f'<span class="down">跌破 {p[self.IDX_F]}</span>')
                if p[self.IDX_C] and price > p[self.IDX_C]:
                  alert_msgs.append(f'<span class="up">突破 {p[self.IDX_C]}</span>')
                
                # C. 均線交叉
                # cross_msg = self.check_signals(i, price, price_1)
                # if cross_msg: alert_msgs.append(cross_msg)

                # 2. 合併為字串 (移除隱藏邏輯，直接顯示)
                display_alert = " ".join(alert_msgs)
                additional_alert = self.check_signals(i, price, price_1)
                
                # 3. 組合最終 alert (用 <br> 分隔,不需要 alert_style 了)
                final_alert = ""
                if display_alert:
                  final_alert = display_alert
                if additional_alert:
                  if final_alert:
                    final_alert += "<br>" + additional_alert
                  else:
                    final_alert = additional_alert
                
                rows.append({
                  "symbol": symbol,
                  "name": name,
                  "price": price,
                  "change": change_percent_str, # 這裡維持百分比字串
                  "change_val": change_val,     # [新增] 傳遞變動數值
                  "alert": final_alert,
                  "delta": delta,
                  "delta_val": delta_val        # [新增] 傳遞 Delta 數值
                })
        else:
           print(f"[WARN] Yahoo API Non-200 Status: {r.status_code}")
      except Exception as e:
        print(f"[ERROR] Yahoo Update error: {e}")
        traceback.print_exc()
    
    # ==========================================
    # [新增] 抓取台指期 (使用獨立 Function)
    # ==========================================
    fitx_data = self.get_fitx_data()
    if fitx_data:
      rows.append(fitx_data)
    
    #=== 定義輔助函數 ==
    def safe_parse_change(change_str):
      # 安全解析 change 百分比字串，返回絕對值
      try:
        return abs(float(str(change_str).rstrip('%')))
      except (ValueError, AttributeError, TypeError):
        return 0.0
    
    rows.sort(key=lambda x: (
      -abs(x.get('delta', 0)),                   # Level 1:delta絕對值（大到小）
      -safe_parse_change(x.get('change', '0%'))  # Level 2:change絕對值（大到小）
    ))
    
    # 排序但保留 delta
    #rows.sort(key=lambda x: abs(x.get('delta', 0)), reverse=True)
    
    
    keywords = [p[0].split('.')[0] for p in self.portfolio]

    # 只有當計數器是 0 或 30 的倍數時，才真正去爬蟲
    if self.run_count % 30 == 0:
      print(f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] Updating PTT News (Keywords/Authors)...")
      #self.news_cache = ticker_news + self.get_ptt_news(keywords) +  self.get_ptt_authors("Stock", PTT_AUTHORS)
      self.news_cache = ticker_news + self.get_ptt_news(keywords) +  self.get_ptt_authors("Stock", self.author_list)
      print(f"[DEBUG] Total News Found: {len(self.news_cache)}")
    
    self.run_count += 1
    # === 修改結束 ===

    return {
      "timestamp": datetime.now(ZoneInfo('Asia/Taipei')).strftime('%H:%M:%S'),
      "rows": rows,
      "news": self.news_cache  # 這裡改成回傳 cache
    }




monitor = StockMonitor()

# ==========================================
# PART 3: Web Application
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🚀Stock Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
  :root {
    --o-brand:#0f6cbd; --o-brand-dark:#0c5aa0; --o-bar:#0f6cbd;
    --o-ribbon:#faf9f8; --o-bg:#f3f2f1; --o-card:#ffffff; --o-border:#edebe9;
    --o-text:#201f1e; --o-text-sub:#605e5c; --o-hover:#f3f2f1;
    --o-shadow:0 1.6px 3.6px rgba(0,0,0,.10),0 .3px .9px rgba(0,0,0,.07);
  }
  body {
    background-color: var(--o-bg); margin: 0; padding: 0; overflow: hidden;
    font-family:'Segoe UI','Segoe UI Web (West European)',-apple-system,system-ui,'Microsoft JhengHei','微軟正黑體',sans-serif;
    color: var(--o-text);
  }
  .container-fluid { padding: 0 !important; margin: 0 !important; }
  .row { margin: 0 !important; }
  .col-lg-8 { padding: 0 !important; } 
  .card { border:1px solid var(--o-border) !important; border-radius:8px !important; margin:0; background:var(--o-card); box-shadow:var(--o-shadow); overflow:hidden; }
  .card-header { background:#fbfafa !important; color:var(--o-text) !important; border-bottom:1px solid var(--o-border); font-weight:600; }
  .card-body { padding: 0 !important; }

  .interval-bar {
    margin-left: auto;
    font-size: 12px;
    color: #555;
    white-space: nowrap;
  }
  .interval-bar select {
    font-size: 11px;
    padding: 1px 3px;
    border: 1px solid #ccc;
    border-radius: 3px;
    cursor: pointer;
  }
  .interval-bar label { margin-right: 4px; }
  #chart-container {
    width: 100%;
    height: calc(100vh - 112px);
    background: var(--o-card); border:1px solid var(--o-border); border-radius:8px; box-shadow: var(--o-shadow);
  }

  .notify-panel { height: calc(100vh - 112px); overflow: hidden; background: var(--o-card); border:1px solid var(--o-border); border-radius:8px; box-shadow: var(--o-shadow); display:flex; flex-direction:column; }
  
  /* 表格樣式 */
  .table-custom { font-size: 13px; width: 100%; margin-bottom: 0; }
  .table-custom th { background:#fbfafa; color: var(--o-text-sub); padding: 8px 12px; font-weight: 600; font-size:12px; border-bottom:1px solid var(--o-border); }
  .table-custom td { padding: 9px 12px; vertical-align: middle; border-bottom: 1px solid var(--o-border); }
  .table-custom tr:hover { background-color: var(--o-hover); }
  
  .news-item { padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 0.85rem; line-height: 1.4; }
  .news-link {
    color: #212529; /* 未點擊時：深黑色 (原本 text-dark 的顏色) */
    text-decoration: none;
  }
  .news-link:visited {
    color: #adb5bd; /* 已點擊時：淺灰色 */
  }
  .news-link:hover {
    color: #000;    /* 滑鼠移過去變全黑 */
    text-decoration: underline; /* 增加底線提示 */
  }
  
  .up { color: #d13438; font-weight: bold; }
  .down { color: #107c10; font-weight: bold; }
  .neutral { color: #6c757d; font-weight: normal; }  /* 灰色,較淡 */
  
  /* 警示標籤 */
  .alert-tag { font-size: 0.8rem; font-weight: bold; }
  
  /* Popup 容器 */
  .stock-popup {
    position: fixed;
    display: none;
    z-index: 9999;
    background: white;
    border: 2px solid #333;
    border-radius: 8px;
    padding: 10px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    pointer-events: none; /* 避免圖片擋住滑鼠事件 */
  }

  .stock-popup img {
    display: block;
    max-width: 800px;
    max-height: 600px;
    width: auto;
    height: auto;
  }

  .stock-popup .loading {
    padding: 20px;
    text-align: center;
    color: #666;
  }

  /* 股票代碼 hover 效果 */
  .stock-symbol-hover {
    cursor: pointer;
    position: relative;
  }

  .stock-symbol-hover:hover {
    background-color: #e3f2fd;
  }
  
  /* [新增] Tooltip 圖片預設樣式 (電腦版) */
  .chart-tooltip-img {
    width: 800px;
    height: auto;
    display: block;
  }

  /* ========================================= */
  /* [核心修正] Mobile Mode 強制滿版樣式 */
  /* ========================================= */
  
  /* 1. Body 開放滾動 */
  body.mobile-mode { 
    overflow: auto !important; 
  }

  /* 2. Monitor 區塊：固定高度、移除左邊框、增加下分隔線 */
  body.mobile-mode .notify-panel { 
    height: 500px;      
    overflow-y: auto; 
    border-left: none; 
    border-bottom: 5px solid #ddd;
  }

  /* 3. Heatmap 區塊：固定高度 */
  body.mobile-mode #chart-container {
    height: 600px;
  }
  body.mobile-mode .interval-bar {
    margin-left: 0;
    width: 100%;
    border-top: 1px solid #eee;
    padding-top: 4px;
  }

  /* Tooltip 兩欄佈局 */
  .tooltip-two-columns {
    display: flex;
    gap: 20px;
  }

  .tooltip-left-column {
    flex: 1;
    min-width: 200px;
  }

  .tooltip-right-column {
    flex: 1;
    min-width: 180px;
    border-left: 1px solid #ddd;
    padding-left: 15px;
  }

  /* [新增] Mobile Mode: 改為垂直堆疊 */
  body.mobile-mode .tooltip-two-columns {
    flex-direction: column;  /* 垂直排列 */
    gap: 10px;
  }

  body.mobile-mode .tooltip-right-column {
    border-left: none;           /* 移除左邊框 */
    border-top: 1px solid #ddd;  /* 改為上邊框 */
    padding-left: 0;
    padding-top: 10px;
  }

  /* 4. Tooltip 圖片縮小 */
  body.mobile-mode .chart-tooltip-img {
    width: 200px !important;
  }

  /* 5. [關鍵修正] 強制改變排列與寬度 */
  body.mobile-mode .main-row {
    flex-direction: column !important; /* Monitor(左欄) 在手機上置頂 */
  }

  /* 這裡就是解決無法滿版的核心代碼 */
  body.mobile-mode .main-row > div {
    width: 100% !important;     /* 無視 col-lg-* 的寬度限制 */
    max-width: 100% !important; /* 確保不被限制 */
    flex: 0 0 100% !important;  /* 強制 Flex 佔滿整行 */
    padding: 0 !important;      /* 移除欄位預設間距，達成邊對邊滿版 */
  }

  /* === Portfolio Sparkline Grid === */
  #portfolio-grid {
    display: none;
    width: 100%;
    height: calc(100vh - 60px);
    overflow-y: auto;
    padding: 8px;
  }
  body.mobile-mode #portfolio-grid {
    height: auto;
    max-height: 600px;
  }
  .pf-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(285px, 1fr));
    gap: 8px;
  }
  .pf-card {
    border: 1px solid #ccc;
    border-radius: 6px;
    padding: 7px 9px 6px;
    background: #fff;
  }
  .pf-card-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .pf-symbol { font-weight: bold; font-size: 13px; color: #222; }
  .pf-name { font-size: 10px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; margin-bottom: 2px; }
  .pf-price { font-size: 13px; font-weight: bold; }
  .pf-chart-title { font-size: 10px; color: #666; margin-bottom: 2px; }
  .pf-chart-area {
    width: 100%;
    height: 90px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f9f9f9;
    border-radius: 3px;
  }

  /* ===== Outlook chrome: top command bar + ribbon ===== */
  .col-lg-8 { padding: 8px !important; }
  .col-lg-4 { padding: 8px !important; }
  /* ===== Inbox tabs (Monitor / PTT News) ===== */
  .o-tabstrip { flex:none; display:flex; align-items:center; justify-content:space-between; padding:4px 8px 0 8px; border-bottom:1px solid var(--o-border); }
  .o-tabs { display:flex; gap:2px; }
  .o-tab { border:none; background:transparent; padding:8px 14px; font-size:14px; font-weight:600; color:var(--o-text-sub); cursor:pointer; border-bottom:2px solid transparent; }
  .o-tab:hover { color:var(--o-text); }
  .o-tab.active { color:var(--o-brand-dark); border-bottom-color:var(--o-brand); }
  .o-tab-tools { display:flex; align-items:center; gap:6px; padding-bottom:4px; }
  .o-tabpane { flex:1 1 auto; overflow-y:auto; min-height:0; }
  .iframe-view { display:none; width:100%; height:calc(100vh - 112px); background:var(--o-card); border:1px solid var(--o-border); border-radius:8px; box-shadow:var(--o-shadow); overflow:hidden; }
  .iframe-view iframe { width:100%; height:100%; border:none; }
  body.mobile-mode .iframe-view { height:600px; }
  body.mobile-mode .iframe-view iframe { width:100%; margin-left:0; }
  .o-tabpane .table-custom thead th { position:sticky; top:0; z-index:2; }
  /* ===== Stealth mode: fake email list ===== */
  #fake-mail { height:calc(100vh - 112px); overflow-y:auto; background:var(--o-card); border:1px solid var(--o-border); border-radius:8px; box-shadow:var(--o-shadow); }
  body.mobile-mode #fake-mail { height:600px; }
  .mail-toolbar { padding:12px 16px; font-size:15px; font-weight:600; border-bottom:1px solid var(--o-border); display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; background:var(--o-card); z-index:2; }
  .mail-item { display:flex; gap:10px; padding:10px 14px; border-bottom:1px solid var(--o-border); cursor:pointer; align-items:flex-start; }
  .mail-item:hover { background:var(--o-hover); }
  .mail-dot { width:8px; height:8px; border-radius:50%; background:var(--o-brand); margin-top:7px; flex:none; visibility:hidden; }
  .mail-item.unread .mail-dot { visibility:visible; }
  .mail-item.unread .mail-from, .mail-item.unread .mail-subj { font-weight:700; }
  .mail-avatar { width:34px; height:34px; border-radius:50%; font-weight:600; font-size:13px; display:grid; place-items:center; flex:none; }
  .mail-main { min-width:0; flex:1; }
  .mail-row1 { display:flex; justify-content:space-between; }
  .mail-from { font-size:14px; color:var(--o-text); }
  .mail-time { font-size:12px; color:var(--o-text-sub); flex:none; margin-left:8px; }
  .mail-subj { font-size:13px; color:var(--o-text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .mail-prev { font-size:12px; color:var(--o-text-sub); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .o-topbar { height:48px; background:var(--o-bar); display:flex; align-items:center; color:#fff; gap:4px; padding-right:4px; }
  .o-waffle { width:48px; height:48px; display:grid; place-items:center; cursor:pointer; border:none; background:transparent; color:#fff; }
  .o-waffle:hover { background:rgba(255,255,255,.12); }
  .o-appname { font-size:18px; font-weight:600; letter-spacing:.2px; padding:0 12px 0 4px; white-space:nowrap; }
  .o-search { flex:1; max-width:640px; margin:0 auto; height:32px; background:#fff; border-radius:4px; display:flex; align-items:center; padding:0 10px; color:var(--o-text-sub); font-size:14px; }
  .o-search svg { margin-right:8px; flex:none; }
  .o-search input { flex:1; min-width:0; border:none; outline:none; background:transparent; font-size:14px; color:var(--o-text); font-family:inherit; }
  .o-search input::placeholder { color:var(--o-text-sub); }
  .o-topbar-right { display:flex; align-items:center; gap:2px; margin-left:auto; flex:none; }
  .o-iconbtn { width:40px; height:48px; border:none; background:transparent; color:#fff; cursor:pointer; font-size:16px; display:grid; place-items:center; }
  .o-iconbtn:hover { background:rgba(255,255,255,.12); }
  .o-ribbon { height:48px; background:var(--o-ribbon); border-bottom:1px solid var(--o-border); display:flex; align-items:center; padding:0 12px; gap:8px; overflow-x:auto; }
  .o-ribbon .btn-group { display:flex; gap:2px; }
  .o-ribbon .btn { border:none !important; background:transparent !important; color:var(--o-text) !important; border-radius:4px !important; padding:6px 12px !important; font-size:14px !important; box-shadow:none !important; white-space:nowrap; }
  .o-ribbon .btn:hover { background:var(--o-hover) !important; }
  .o-ribbon .btn.active { background:#e1eefb !important; color:var(--o-brand-dark) !important; font-weight:600; }
  .o-ribbon-sep { width:1px; height:24px; background:var(--o-border); margin:0 4px; flex:none; }
  body.mobile-mode .o-ribbon { height:auto; flex-wrap:wrap; padding:6px 12px; }
  /* 手機頂部列：縮小各元件、讓搜尋框吸收剩餘寬度，確保 ⚙❔ET 與鈴鐺同排不溢出 */
  body.mobile-mode .o-topbar { gap:0; padding-right:2px; }
  body.mobile-mode .o-waffle { width:40px; }
  body.mobile-mode .o-appname { font-size:14px; padding:0 4px; max-width:34vw; overflow:hidden; text-overflow:ellipsis; display:inline-block; vertical-align:middle; }
  body.mobile-mode .o-search { max-width:none; }
  body.mobile-mode .o-iconbtn { width:34px; font-size:15px; }
  </style>
</head>
<body>

<div class="o-topbar">
  <button class="o-waffle" title="App launcher">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="#fff">
      <rect x="1" y="1" width="4" height="4" rx="1"/><rect x="8" y="1" width="4" height="4" rx="1"/><rect x="15" y="1" width="4" height="4" rx="1"/>
      <rect x="1" y="8" width="4" height="4" rx="1"/><rect x="8" y="8" width="4" height="4" rx="1"/><rect x="15" y="8" width="4" height="4" rx="1"/>
      <rect x="1" y="15" width="4" height="4" rx="1"/><rect x="8" y="15" width="4" height="4" rx="1"/><rect x="15" y="15" width="4" height="4" rx="1"/>
    </svg>
  </button>
  <span class="o-appname">Stock Dashboard</span>
  <div class="o-search">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#605e5c" stroke-width="1.5">
      <circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="15" y2="15"/>
    </svg>
    <input id="inbox-search" type="text" placeholder="搜尋股票代碼 / 名稱 / 新聞" oninput="applyInboxFilter()" autocomplete="off">
  </div>
  <div class="o-topbar-right">
    <button class="o-iconbtn" title="通知">🔔</button>
    <button class="o-iconbtn" title="設定">⚙</button>
    <button class="o-iconbtn" title="說明" onclick="toggleStealth()">❔</button>
  </div>
</div>

<div class="o-ribbon">
  <div class="btn-group btn-group-sm">
    <button class="btn btn-outline-dark active" onclick="setMarket(this, 'twse', 'INDEX')">上市指數</button>
    <button class="btn btn-outline-dark" onclick="setMarket(this, 'twse', 'EQUITY')">上市個股</button>
    <button class="btn btn-outline-dark" onclick="setMarket(this, 'otc', 'INDEX')">上櫃指數</button>
    <button class="btn btn-outline-dark" onclick="setMarket(this, 'otc', 'EQUITY')">上櫃個股</button>
    <button class="btn btn-outline-dark" onclick="setMarket(this, 'sp500', 'EQUITY')">S&P 500</button>
    <button class="btn btn-outline-dark" onclick="setMarket(this, 'ndx', 'EQUITY')">NASDAQ 100</button>
    <button class="btn btn-outline-secondary" onclick="showPortfolioView(this)">Portfolio</button>
    <button class="btn btn-outline-secondary" onclick="showIframeView(this, 'iframe-tw-trend')">TW-Trend</button>
    <button class="btn btn-outline-secondary" onclick="showIframeView(this, 'iframe-tw-ratio')">TW-Ratio</button>
    <button class="btn btn-outline-secondary" onclick="showIframeView(this, 'iframe-tw-breath')">TW-Breath</button>
    <button class="btn btn-outline-secondary" onclick="showIframeView(this, 'iframe-tw-today')">TW-Today</button>
    <button class="btn btn-outline-secondary" onclick="showIframeView(this, 'iframe-tw-market')">TW-Market</button>
  </div>
  <div class="o-ribbon-sep"></div>
  <div id="area-metric-selector" style="font-size:14px;">
    <label style="cursor:pointer"><input type="radio" name="area_metric" value="tradeValueWeight" checked onchange="updateHeatmap()"> 成交值</label>
    <label class="ms-2" style="cursor:pointer"><input type="radio" name="area_metric" value="marketValueWeight" onchange="updateHeatmap()"> 市值</label>
  </div>
  <div class="interval-bar">
    <span>更新間隔：</span>
    <label>Heatmap
      <select id="interval-heatmap" onchange="restartHeatmapInterval()">
        <option value="30000">30s</option>
        <option value="60000">1m</option>
        <option value="120000">2m</option>
        <option value="300000" selected>5m</option>
        <option value="600000">10m</option>
      </select>
    </label>
    <label>Portfolio
      <select id="interval-portfolio" onchange="restartPortfolioInterval()">
        <option value="30000">30s</option>
        <option value="60000">1m</option>
        <option value="120000">2m</option>
        <option value="300000" selected>5m</option>
        <option value="600000">10m</option>
      </select>
    </label>
    <label>Monitor
      <select id="interval-monitor" onchange="restartMonitorInterval()">
        <option value="30000">30s</option>
        <option value="60000">1m</option>
        <option value="120000" selected>2m</option>
        <option value="300000">5m</option>
        <option value="600000">10m</option>
      </select>
    </label>
  </div>
</div>

<div class="container-fluid">
  <div class="row main-row">
  <div class="col-lg-4">
    <div class="notify-panel">
      <div class="o-tabstrip">
        <div class="o-tabs">
          <button class="o-tab active" data-tab="monitor" onclick="switchInboxTab('monitor')">Monitor</button>
          <button class="o-tab" data-tab="news" onclick="switchInboxTab('news')">PTT / News</button>
        </div>
        <div class="o-tab-tools">
          <span class="badge bg-secondary" id="nt-time">--:--</span>
          <span id="audio-btn" style="cursor:pointer; font-size:1.1rem;" onclick="toggleSound(event)" title="點擊以啟用音效">🔇</span>
          <button class="btn btn-sm btn-outline-secondary" style="padding: 0px 6px; font-size: 0.8rem;" onclick="resetMonitor()">Reset</button>
        </div>
      </div>

      <div id="tab-monitor" class="o-tabpane">
        <table class="table-custom">
          <thead>
            <tr>
              <th style="width: 20%">股票</th>
              <th style="width: 20%">價/幅</th>
              <th style="width: 15%">變動率</th>
              <th style="width: 45%">警示</th>
            </tr>
          </thead>
          <tbody id="stock-table-body">
            <tr><td colspan="4" class="text-center text-muted">載入中...</td></tr>
          </tbody>
        </table>
      </div>

      <div id="tab-news" class="o-tabpane" style="display:none;">
        <div id="news-container">
          <div class="text-center p-3 text-muted">載入中...</div>
        </div>
      </div>

    </div>
  </div>

  <div class="col-lg-8">
    <div id="chart-container"></div>
    <div id="portfolio-grid"></div>

    <div id="iframe-tw-trend" class="iframe-view">
      <iframe data-src="https://c-a-d-e-n-z-a.github.io/webpage/group_trend.html" loading="lazy"></iframe>
    </div>
    <div id="iframe-tw-ratio" class="iframe-view">
      <iframe data-src="https://c-a-d-e-n-z-a.github.io/webpage/margin_ratio.html" loading="lazy"></iframe>
    </div>
    <div id="iframe-tw-breath" class="iframe-view">
      <iframe data-src="https://c-a-d-e-n-z-a.github.io/webpage/breadth_high_low.html" loading="lazy"></iframe>
    </div>
    <div id="iframe-tw-today" class="iframe-view">
      <iframe data-src="https://finlab.finance/stocks/today" loading="lazy"></iframe>
    </div>
    <div id="iframe-tw-market" class="iframe-view">
      <iframe data-src="https://ai.finlab.tw/tw_market/" loading="lazy"></iframe>
    </div>

    <div id="fake-mail" style="display:none;">
      <div class="mail-toolbar">
        <span>通知</span>
        <span style="font-weight:400; color:var(--o-text-sub); font-size:12px;">依日期排序 ↓ · 3 未讀</span>
      </div>
      <div class="mail-list">
        <div class="mail-item unread"><span class="mail-dot"></span><div class="mail-avatar" style="background:#dff6dd;">📈</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Price Alert</span><span class="mail-time">09:12</span></div><div class="mail-subj">觸及目標價 $184.00</div><div class="mail-prev">已達到你在觀察清單設定的價格提醒。</div></div></div>
        <div class="mail-item unread"><span class="mail-dot"></span><div class="mail-avatar" style="background:#e1eefb;">🔔</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Market News</span><span class="mail-time">09:01</span></div><div class="mail-subj">台股開盤上漲 0.8%，半導體領漲</div><div class="mail-prev">加權指數站上季線，權值股表現強勢。</div></div></div>
        <div class="mail-item unread"><span class="mail-dot"></span><div class="mail-avatar" style="background:#d4eefb;">🌐</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Global Markets</span><span class="mail-time">08:45</span></div><div class="mail-subj">Fed keeps rates steady; futures edge higher</div><div class="mail-prev">US index futures rose modestly after the decision.</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#dce8f7;">📊</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Watchlist Update</span><span class="mail-time">08:20</span></div><div class="mail-subj">觀察清單今日異動摘要</div><div class="mail-prev">12 檔上漲、5 檔下跌，整體成交量放大。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#efdbff;">📅</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Earnings Reminder</span><span class="mail-time">07:55</span></div><div class="mail-subj">本週財報行事曆：3 檔持股公布</div><div class="mail-prev">留意季度營收與 EPS 年增率的變化。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#e1eefb;">💹</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Tech News</span><span class="mail-time">07:40</span></div><div class="mail-subj">AI 晶片需求帶動供應鏈拉貨動能</div><div class="mail-prev">分析師上修下半年出貨預估。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#fff4ce;">💰</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Dividend Notice</span><span class="mail-time">07:15</span></div><div class="mail-subj">除息提醒：2 檔持股即將除息</div><div class="mail-prev">本週除息日與填息機率一覽。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#d4eefb;">📰</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Market Recap</span><span class="mail-time">昨天</span></div><div class="mail-subj">昨日收盤回顧與盤後重點</div><div class="mail-prev">三大指數收紅，資金流向科技類股。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#fde7e9;">⚠️</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Risk Alert</span><span class="mail-time">昨天</span></div><div class="mail-subj">VIX 波動度指數上升至 18.5</div><div class="mail-prev">市場情緒轉趨謹慎，注意部位控管。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#fff4ce;">🛢️</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Commodities</span><span class="mail-time">昨天</span></div><div class="mail-subj">油價走穩，黃金小幅回落</div><div class="mail-prev">市場評估供給前景與美元走勢。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#dff6dd;">🧾</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">Portfolio Digest</span><span class="mail-time">週一</span></div><div class="mail-subj">每週投資組合摘要已產生</div><div class="mail-prev">本週報酬 +1.4%，波動度較上週下降。</div></div></div>
        <div class="mail-item"><span class="mail-dot"></span><div class="mail-avatar" style="background:#e2e2e2;">⚙</div><div class="mail-main"><div class="mail-row1"><span class="mail-from">System</span><span class="mail-time">週一</span></div><div class="mail-subj">行情與籌碼資料同步完成</div><div class="mail-prev">已更新至最新交易日。</div></div></div>
      </div>
    </div>
  </div>
  </div>
</div>

<script>
let chartInstance = null;
let currentMarket = 'twse';
let currentType = 'INDEX';
let heatmapInterval = null;
let monitorInterval = null;

function fmtNum(n) { if(n === undefined) return '0'; return n.toLocaleString('en-US'); }
function fmtFloat(n, d=2) { if(n === undefined) return '0.00'; return n.toFixed(d); }

// Inbox 分頁切換 (Monitor / PTT News)
function switchInboxTab(tab) {
  document.querySelectorAll('.o-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('tab-monitor').style.display = (tab === 'monitor') ? '' : 'none';
  document.getElementById('tab-news').style.display = (tab === 'news') ? '' : 'none';
}

// 頂部搜尋：即時過濾 Monitor 清單與 PTT/新聞 (雙欄同步)
function applyInboxFilter() {
  const input = document.getElementById('inbox-search');
  const q = (input ? input.value : '').trim().toLowerCase();
  document.querySelectorAll('#stock-table-body > tr').forEach(tr => {
    tr.style.display = (!q || tr.textContent.toLowerCase().includes(q)) ? '' : 'none';
  });
  document.querySelectorAll('#news-container > .news-item').forEach(item => {
    item.style.display = (!q || item.textContent.toLowerCase().includes(q)) ? '' : 'none';
  });
}

// 隱藏看盤 (boss key)：右側切換成模擬 email 清單，再按一次還原
let stealthMode = false;
let stealthPrev = null;
function toggleStealth() {
  const chart = document.getElementById('chart-container');
  const pf = document.getElementById('portfolio-grid');
  const mail = document.getElementById('fake-mail');
  stealthMode = !stealthMode;
  const iframes = document.querySelectorAll('.iframe-view');
  if (stealthMode) {
    stealthPrev = { chart: chart.style.display, pf: pf.style.display, iframes: Array.from(iframes).map(el => el.style.display) };
    chart.style.display = 'none';
    pf.style.display = 'none';
    iframes.forEach(el => el.style.display = 'none');
    mail.style.display = 'block';
  } else {
    if (stealthPrev) {
      chart.style.display = stealthPrev.chart;
      pf.style.display = stealthPrev.pf;
      if (stealthPrev.iframes) {
        Array.from(iframes).forEach((el, i) => el.style.display = stealthPrev.iframes[i] || 'none');
      }
    }
    mail.style.display = 'none';
  }
}




function setMarket(btn, market, type) {
  hidePortfolioView();
  hideIframeViews();
  document.querySelectorAll('.btn-group button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentMarket = market;
  currentType = type;
  updateHeatmap();
}

let portfolioInterval = null;

function restartHeatmapInterval() {
  clearInterval(heatmapInterval);
  const ms = parseInt(document.getElementById('interval-heatmap').value);
  heatmapInterval = setInterval(conditionalUpdateHeatmap, ms);
}

function restartPortfolioInterval() {
  clearInterval(portfolioInterval);
  if (document.getElementById('portfolio-grid').style.display !== 'none' &&
      document.getElementById('portfolio-grid').style.display !== '') {
    const ms = parseInt(document.getElementById('interval-portfolio').value);
    portfolioInterval = setInterval(loadPortfolioSparklines, ms);
  }
}

function restartMonitorInterval() {
  clearInterval(monitorInterval);
  const ms = parseInt(document.getElementById('interval-monitor').value);
  monitorInterval = setInterval(updateNotify, ms);
}

function showPortfolioView(btn) {
  hideIframeViews();
  document.querySelectorAll('.btn-group button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('chart-container').style.display = 'none';
  document.getElementById('area-metric-selector').style.display = 'none';
  document.getElementById('portfolio-grid').style.display = 'block';
  loadPortfolioSparklines();
  clearInterval(portfolioInterval);
  const ms = parseInt(document.getElementById('interval-portfolio').value);
  portfolioInterval = setInterval(loadPortfolioSparklines, ms);
}

function hidePortfolioView() {
  clearInterval(portfolioInterval);
  portfolioInterval = null;
  document.getElementById('chart-container').style.display = '';
  document.getElementById('area-metric-selector').style.display = '';
  document.getElementById('portfolio-grid').style.display = 'none';
}

function hideIframeViews() {
  document.querySelectorAll('.iframe-view').forEach(el => el.style.display = 'none');
}

function showIframeView(btn, id) {
  hidePortfolioView();
  hideIframeViews();
  document.querySelectorAll('.btn-group button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('chart-container').style.display = 'none';
  document.getElementById('area-metric-selector').style.display = 'none';
  const container = document.getElementById(id);
  container.style.display = 'block';
  // Lazy-load iframe src on first activation
  const iframe = container.querySelector('iframe[data-src]');
  if (iframe && !iframe.src) {
    iframe.src = iframe.getAttribute('data-src');
  }
}

async function loadPortfolioSparklines() {
  const grid = document.getElementById('portfolio-grid');
  grid.innerHTML = '<div class="text-center text-muted p-3">Loading...</div>';

  try {
    // 1. 取得 monitor 資料 (含 symbol/name/price/change)
    const monitorRes = await fetch('/api/monitor');
    const monitorData = await monitorRes.json();
    const rows = (monitorData.rows || []).sort((a, b) => a.symbol.localeCompare(b.symbol));

    if (rows.length === 0) {
      grid.innerHTML = '<div class="text-center text-muted p-3">No portfolio data</div>';
      return;
    }

    // 2. 分批抓 sparkline (每批最多 15 個)
    const symbols = rows.map(r => r.symbol);
    const BATCH_SIZE = 15;
    const chunks = [];
    for (let i = 0; i < symbols.length; i += BATCH_SIZE) {
      chunks.push(symbols.slice(i, i + BATCH_SIZE));
    }

    const chartMap = {};
    for (const chunk of chunks) {
      const res = await fetch(`/api/sparkline_multi?symbols=${chunk.join(',')}`);
      const json = await res.json();
      const list = Array.isArray(json) ? json : (json.data || []);
      list.forEach(item => {
        const chart = item.chart;
        if (chart && chart.meta && chart.meta.symbol) {
          chartMap[chart.meta.symbol] = chart;
        }
      });
    }

    // 3. 渲染卡片
    let html = '<div class="pf-grid">';
    rows.forEach(row => {
      const safeId = 'pf_' + row.symbol.replace(/[^a-zA-Z0-9]/g, '_');
      let changeVal = parseFloat(row.change.replace('%', ''));
      const colorStyle = changeVal >= 0 ? 'color:#ff3333;' : 'color:#00cc44;';
      html += `
        <div class="pf-card">
          <div class="pf-card-header">
            <span class="pf-symbol">${row.symbol.split('.')[0]}</span>
            <span class="pf-price" style="${colorStyle}">${row.price}</span>
          </div>
          <div class="pf-name">${row.name}</div>
          <div id="${safeId}_title" class="pf-chart-title">即時走勢</div>
          <div id="${safeId}" class="pf-chart-area"><span style="color:#999;font-size:11px;">Loading...</span></div>
        </div>`;
    });
    html += '</div>';
    grid.innerHTML = html;

    // 4. 逐一繪製 SVG
    rows.forEach(row => {
      const safeId = 'pf_' + row.symbol.replace(/[^a-zA-Z0-9]/g, '_');
      const chartData = chartMap[row.symbol];
      if (chartData) {
        _drawSparklineSVG(safeId, chartData);
      } else {
        const el = document.getElementById(safeId);
        if (el) el.innerHTML = '<span style="color:#999;font-size:11px;">N/A</span>';
      }
    });

  } catch (err) {
    console.error('Portfolio sparklines error:', err);
    grid.innerHTML = `<div class="text-center text-danger p-3">Error: ${err.message}</div>`;
  }
}




// === 1. 畫圖函式 (修正灰色昨收線樣式) ===

// Inner renderer: takes pre-fetched chartData object
function _drawSparklineSVG(containerId, chartData) {
  const container = document.getElementById(containerId);
  if (!container) return;

  try {
    const timestamps = chartData.timestamp;
    const closes = chartData.indicators.quote[0].close;
    const meta = chartData.meta;

    const prevClose = meta.chartPreviousClose || meta.previousClose;
    const limitUp = meta.limitUpPrice;
    const limitDown = meta.limitDownPrice;

    let minT, maxT;
    const period = meta.tradingPeriods?.[0]?.[0];
    if (period && period.start && period.end) {
      minT = period.start;
      maxT = period.end;
    } else {
      if (timestamps && timestamps.length > 0) {
        minT = timestamps[0];
        maxT = timestamps[timestamps.length - 1];
      } else {
        minT = 0; maxT = 1;
      }
    }

    const points = [];
    for (let i = 0; i < timestamps.length; i++) {
      const t = timestamps[i];
      const p = closes[i];
      if (p !== null && p !== undefined && t >= minT && t <= maxT) {
        points.push({ t: t, p: p });
      }
    }

    if (points.length === 0) {
      container.innerHTML = '<span style="color:#ccc;font-size:12px;">等待開盤</span>';
      return;
    }

    let minP, maxP;
    const hasLimitPrice = (limitUp && limitUp !== '-' && limitDown && limitDown !== '-');
    if (hasLimitPrice) {
      maxP = parseFloat(limitUp);
      minP = parseFloat(limitDown);
    } else {
      minP = points[0].p; maxP = points[0].p;
      points.forEach(pt => {
        if (pt.p < minP) minP = pt.p;
        if (pt.p > maxP) maxP = pt.p;
      });
      if (prevClose) {
        if (prevClose < minP) minP = prevClose;
        if (prevClose > maxP) maxP = prevClose;
      }
      if (maxP === minP) { maxP *= 1.01; minP *= 0.99; }
    }

    const width = 300;
    const height = 110;
    const padding = 5;
    const getX = (t) => ((t - minT) / (maxT - minT)) * width;
    const getY = (p) => height - padding - ((p - minP) / (maxP - minP)) * (height - 2 * padding);

    const svgPoints = points.map(pt => `${getX(pt.t).toFixed(1)},${getY(pt.p).toFixed(1)}`).join(" ");

    let prevCloseLine = "";
    if (prevClose && prevClose >= minP && prevClose <= maxP) {
      const yPrev = getY(prevClose).toFixed(1);
      prevCloseLine = `<line x1="0" y1="${yPrev}" x2="${width}" y2="${yPrev}" stroke="#999" stroke-width="0.8" opacity="0.6" />`;
    }

    const lastPrice = points[points.length - 1].p;
    const refPrice = prevClose || points[0].p;
    const color = lastPrice >= refPrice ? "#ff3333" : "#00cc44";

    const precision = lastPrice < 1 ? 4 : 2;
    const chgPct = refPrice ? ((lastPrice - refPrice) / refPrice * 100) : 0;
    const chgSign = chgPct >= 0 ? '+' : '';
    const prevCloseStr = prevClose ? prevClose.toFixed(precision) : 'N/A';
    const titleEl = document.getElementById(containerId + '_title');
    if (titleEl) {
      const infoSpan = `<span style="font-weight:normal; color:${color};">&nbsp;(現 ${lastPrice.toFixed(precision)} / 昨 ${prevCloseStr} / ${chgSign}${chgPct.toFixed(2)}%)</span>`;
      titleEl.innerHTML = titleEl.textContent.trim() + infoSpan;
    }

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%; height:100%; background:transparent;">
        ${prevCloseLine}
        <polyline points="${svgPoints}"
              fill="none"
              stroke="${color}"
              stroke-width="2"
              stroke-linejoin="round"
              vector-effect="non-scaling-stroke" />
      </svg>
    `;
    container.setAttribute('data-loaded', 'true');
    container.style.background = 'transparent';
    container.style.border = 'none';

  } catch (err) {
    console.error("Chart Error:", err);
    container.innerHTML = '<span style="color:#ccc;font-size:12px;">N/A</span>';
  }
}

async function renderSparklineSVG(containerId, symbol) {
  const container = document.getElementById(containerId);
  if (!container || container.getAttribute('data-loaded')) return;

  const proxyUrl = `/api/sparkline/${encodeURIComponent(symbol)}`;

  try {
    const response = await fetch(proxyUrl);
    const json = await response.json();
    const chartData = Array.isArray(json) ? json[0].chart : json.data?.[0]?.chart;

    if (!chartData) throw new Error("無圖表資料");
    _drawSparklineSVG(containerId, chartData);

  } catch (err) {
    console.error("Chart Error:", err);
    if (container) container.innerHTML = '<span style="color:#ccc;font-size:12px;">N/A</span>';
  }
}




// === 2. Tooltip 格式化 (修改佈局以填滿) ===
function tooltipFormatter(info) {
  var val = info.data.value;
  if (!val) { val = info.value; }

  var styleTitle = 'font-weight:bold; border-bottom:1px solid #ccc; margin-bottom:8px; padding-bottom:5px; color:#000; font-size:16px;';
  // 稍微增加左側的最小寬度
  var styleRow = 'display:flex; justify-content:space-between; font-size:13px; color:#000; line-height:1.5; min-width:140px;';

  if (Array.isArray(val)) {
    var name = info.name;
    var symbol = info.data.id || '';

    var chgPct = fmtFloat(val[1]);
    var close = fmtFloat(val[2]);
    var open = fmtFloat(val[4]);
    var high = fmtFloat(val[5]);
    var low = fmtFloat(val[6]);
    var change = fmtFloat(val[7]);
    var vol = fmtNum(val[8]);
    var valMoney = fmtNum(val[9]);

    var chgColor = val[1] >= 0 ? '#ff3333' : '#00cc44';
    
    var safeSymbol = symbol.replace(/[^a-zA-Z0-9]/g, '');
    var chartId = 'spark_' + safeSymbol + '_' + Date.now();

    // 1. 左側資訊區 (固定最小寬度)
    var leftContent = `
      <div style="margin-right: 15px;">
        <div style="${styleRow}"><span>收盤：</span><b>${close}</b></div>
        <div style="${styleRow}"><span>漲跌：</span><span style="color:${chgColor};">${change} (${chgPct}%)</span></div>
        <div style="${styleRow}"><span>開盤：</span><span>${open}</span></div>
        <div style="${styleRow}"><span>最高：</span><span>${high}</span></div>
        <div style="${styleRow}"><span>最低：</span><span>${low}</span></div>
    `;
    if (currentType === 'EQUITY') {
      leftContent += `
        <div style="border-top:1px dashed #ddd; margin:4px 0;"></div>
        <div style="${styleRow}"><span>量：</span><span>${vol}</span></div>
        <div style="${styleRow}"><span>額：</span><span>${valMoney}</span></div>
      `;
    }
    leftContent += `</div>`;

    // 2. 右側圖表區 (【關鍵修改】Flex 填滿)
    var rightContent = '';
    if (symbol) {
      rightContent = `
        <div style="flex: 1; display: flex; flex-direction: column;">
           <div id="${chartId}_title" style="font-size:12px; color:#666; margin-bottom:4px; font-weight:bold;">即時走勢</div>
           <div id="${chartId}" style="width:100%; height:110px; display:flex; align-items:center; justify-content:center; background:#f9f9f9; border:1px solid #eee; border-radius:4px;">
            <span style="color:#999;font-size:12px;">Loading...</span>
           </div>
        </div>
      `;
      setTimeout(() => renderSparklineSVG(chartId, symbol), 100);
    }

    // 3. 下方大圖區
    var bottomImage = '';
    if (currentType === 'EQUITY' && symbol) {
      var imgUrl = '';
      if (currentMarket === 'sp500' || currentMarket === 'ndx') {
        imgUrl = `https://charts2.finviz.com/chart.ashx?t=${symbol.replace(/\./g, '-')}&ta=1&ty=c&p=d&s=l`;
      } else {
        imgUrl = `https://stock.wearn.com/finance_chart.asp?stockid=${symbol.split('.')[0]}&timeblock=270&sma1=10&sma2=20&sma3=60&volume=1`;
      }
      bottomImage = `
        <div style="margin-top:10px; padding-top:10px; border-top:1px solid #eee; text-align:center;">
          <img src="${imgUrl}" style="max-width:100%; height:auto; display:block; margin:auto;">
        </div>
      `;
    }

    // 主容器增加一點寬度，上半部使用 Flex 佈局
    return `
      <div style="padding:8px; min-width:320px; font-family:'Roboto', sans-serif;">
        <div style="${styleTitle}">${name} (${symbol})</div>
        <div style="display:flex; align-items: flex-start;">
          ${leftContent}
          ${rightContent}
        </div>
        ${bottomImage}
      </div>
    `;
  } 
  
  return `${info.name}: ${val}`;
}




function labelFormatterIndex(params) {
  if (Array.isArray(params.value)) {
  var price = params.value[2] ? params.value[2].toFixed(2) : '0.00';
  var chg = params.value[1] ? params.value[1].toFixed(2) + '%' : '0.00%';
  return params.name + '\\n' + price + ' | ' + chg;f
  }
  return params.name;
}




function labelFormatter(params) {
  if (Array.isArray(params.value)) {
  var symbol = params.data.id || ''; 
  var price = params.value[2] ? params.value[2].toFixed(2) : '0.00';
  var chg = params.value[1] ? params.value[1].toFixed(2) + '%' : '0.00%';
  return '{name|' + params.name + '(' + symbol + ')}\\n{val|' + price + ' | ' + chg + '}';
  }
  return params.name;
}




// 檢查是否在交易時間內(含週末判斷)
function isTwTradingHours() {
  const now = new Date();
  // 轉換為台北時間 (UTC+8)
  const taipeiTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Taipei' }));
      
  const day = taipeiTime.getDay(); // 0=週日, 6=週六
  if (day === 0 || day === 6) return false; // 週末不交易

  const hours = taipeiTime.getHours();
  const minutes = taipeiTime.getMinutes();
  const currentTime = hours * 60 + minutes; // 轉換為分鐘
  
  const startTime = 8 * 60 + 30;  // 08:30 = 510 分鐘
  const endTime = 14 * 60 + 30;   // 14:30 = 870 分鐘
  
  return currentTime >= startTime && currentTime <= endTime;
}





// 檢查是否在美股交易時間內
function isUsTradingHours() {
  const now = new Date();
  // 轉換為美東時間 (ET)
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  
  const day = etTime.getDay(); // 0=週日, 6=週六
  if (day === 0 || day === 6) return false; // 週末不交易
  
  const hours = etTime.getHours();
  const minutes = etTime.getMinutes();
  const currentTime = hours * 60 + minutes;
  
  const startTime = 9 * 60 + 30;   // 09:30
  const endTime = 16 * 60;          // 16:00
  
  return currentTime >= startTime && currentTime <= endTime;
}




// 條件式更新 Heatmap
function conditionalUpdateHeatmap() {
  if (currentMarket === 'sp500' || currentMarket === 'ndx') {
    if (isUsTradingHours()) {
      console.log('美股交易時間內，更新 Heatmap');
      updateHeatmap();
    } else {
      console.log('美股非交易時間，跳過更新');
    }
  } else if (currentMarket === 'twse' || currentMarket === 'otc') {
    if (isTwTradingHours()) {
      console.log('台股交易時間內，更新 Heatmap');
      updateHeatmap();
    } else {
      console.log('台股非交易時間，跳過更新');
    }
  } else {
    // 其他市場直接更新
    console.log(`${currentMarket} 市場，直接更新`);
    updateHeatmap();
  }
}




async function updateHeatmap() {
  // 檢查實例是否已存在
  if(!chartInstance) {
    console.log("[DEBUG] Initializing ECharts Instance...");
    chartInstance = echarts.init(document.getElementById('chart-container'));

    // 雙擊事件
    chartInstance.on('dblclick', function(params) {
      if (params.data && params.data.id) {
        const symbol = params.data.id;
        if (symbol) {
          if (currentMarket === 'sp500' || currentMarket === 'ndx') {
            // 美股：開啟 TradingView
            window.open(`https://www.tradingview.com/chart/?symbol=${symbol}`, '_blank');
          } else {
            // 台股：開啟 CMoney 論壇
            const stockCode = symbol.split('.')[0];
            window.open(`https://www.cmoney.tw/forum/stock/${stockCode}`, '_blank');
          }
        } 
      }
    });
  }

  chartInstance.showLoading();
  const areaVal = document.querySelector('input[name="area_metric"]:checked').value;
  
  // [新增] 判斷是否為手機模式
  const isMobile = document.body.classList.contains('mobile-mode');

  try {
    const res = await fetch(`/twheatmap/api/data?market=${currentMarket}&type=${currentType}&area=${areaVal}`);
    const treeData = await res.json();
    
    const option = {
      tooltip: { 
        formatter: tooltipFormatter,
        // [優化] 手機版 tooltip 限制在容器內，避免超出螢幕
        confine: true, 
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#ccc',
        borderWidth: 1,
        padding: 10
      },
      visualMap: {
        type: 'continuous', dimension: 1, min: -10, max: 10,
        inRange: { color: ['#31C950', '#FFF085', '#FB2C36'] }, 
        show: true, orient: 'vertical', left: 10, top: 'middle',
        itemHeight: 80, textStyle: { color: '#000'}
      },
      series: [{
        type: 'treemap', 
        data: treeData, 
        breadcrumb: { show: true }, 
        leafDepth: null, 
        
        // [關鍵修正] 如果是手機模式，關閉 roam (拖曳/縮放)，讓使用者可以滑動網頁
        roam: !isMobile, 
        width: '100%', height: '100%', top: 0, bottom: 0, left: 0, right: 0,
        levels: currentType === 'INDEX' ? [] : [
          { itemStyle: { borderColor: '#fff', borderWidth: 0, gapWidth: 0 } },
          { colorSaturation: [0, 1], itemStyle: { borderColor: '#555', borderWidth: 1, gapWidth: 2 }, upperLabel: { show: true, height: 30, color: '#000', fontWeight: 'bold' } },
          { colorSaturation: [0, 1], itemStyle: { borderColor: '#fff', borderWidth: 1, gapWidth: 1 }, label: { show: true, position: 'insideTopLeft', formatter: labelFormatter, rich: { name: { fontSize: 14, fontWeight: 'bold', color: '#000'}, val: { fontSize: 12, color: '#333'} } } }
        ],
        label: { show: true, formatter: labelFormatterIndex, fontSize: 14, color: '#000' }
      }]
    };
    chartInstance.setOption(option);
    chartInstance.hideLoading();
  } catch(e) { 
    console.error('[ERROR] Heatmap update failed:', e); 
    chartInstance.hideLoading();
  }
}




// [新增] 將 Yahoo 代碼轉換為 TradingView URL
function getYahooToTradingViewUrl(symbol) {
  let tvSymbol = symbol;

  // 1. 特殊指數與期貨對照表
  const indexMap = {
    '^TWII': 'TWSE:TAIEX',      // 加權指數
    '^TWOII': 'TPEX:TPEX',      // 櫃買指數
    'FITX': 'TAIFEX:TX1!',      // 台指期 (使用 TX1! 代表連續月)
    '^GSPC': 'SP:SPX',          // S&P 500
    '^NDX': 'TVC:NDX',          // Nasdaq 100
    '^IXIC': 'TVC:IXIC',        // Nasdaq Composite
    '^DJI': 'DJ:DJI',           // 道瓊
    '^N225': 'TVC:NI225',       // Nikkei 225
    '^KS11': 'KRX:KOSPI',       // KOSPI Composite Index
    '^VIX': 'VIX',
    '^VXN': 'VXN',
    'ES=F': 'CME_MINI:ES1!',    // S&P 500 期貨
    'NQ=F': 'CME_MINI:NQ1!',    // Nasdaq 期貨
    'YM=F': 'CBOT_MINI:YM1!',   // 道瓊期貨
    'TWD=X': 'USDTWD',
    'JPYTWD=X': 'JPYTWD',
    'BTC-USD': 'BTCUSD',
    'ETH-USD': 'ETHUSD',
    'SOL-USD': 'SOLUSD',
    'DOGE-USD': 'DOGEUSD'
  };

  if (indexMap[symbol]) {
    tvSymbol = indexMap[symbol];
  }
  
  // 2. 台股上市 (Yahoo: 2330.TW -> TV: TWSE:2330)
  else if (symbol.endsWith('.TW')) {
    tvSymbol = 'TWSE:' + symbol.replace('.TW', '');
  } 
  // 3. 台股上櫃 (Yahoo: 3105.TWO -> TV: TPEX:3105)
  else if (symbol.endsWith('.TWO')) {
    tvSymbol = 'TPEX:' + symbol.replace('.TWO', '');
  }
  // 4. 滬深 (Yahoo: 000300.SS -> TV: SSE:000300)
  else if (symbol.endsWith('.SS')) {
    tvSymbol = 'SSE:' + symbol.replace('.SS', '');
  }  
  // 5. 美股 (Yahoo: BRK-B -> TV: BRK.B, 其他通常通用)
  else {
    tvSymbol = symbol.replace('-', '.'); 
  }

  // 回傳 TradingView 超級圖表連結
  return `https://www.tradingview.com/chart/?symbol=${tvSymbol}`;
}




// [新增] 取得社群討論區連結 (CMoney / 富途)
function getCommunityLink(symbol) {

  // 1. 特殊指數與期貨對照表
  const communityMap = {
    '^TWII': 'https://www.cmoney.tw/forum/market',      // 加權指數
    '^TWOII': 'https://www.cmoney.tw/forum/stock/TWC00',      // 櫃買指數
    'FITX': 'https://www.cmoney.tw/forum/futures/TXF1?s=p',      // 台指期
    '^GSPC': 'https://www.futunn.com/hk/index/.SPX-US/community',           // S&P 500
    '^IXIC': 'https://www.futunn.com/hk/index/.IXIC-US',        // Nasdaq Composite
    '^DJI': 'https://www.futunn.com/hk/index/.DJI-US',            // 道瓊
  };

  // 修正點：如果對照表有資料，直接回傳該網址
  if (communityMap[symbol]) {
    return communityMap[symbol];
  } 
  
  // 2. 判斷是否包含 .TW (涵蓋 .TW 與 .TWO)
  else if (symbol.includes('.TW')) {
    // 移除 .TW 或 .TWO，只保留代碼 (e.g., 2330.TW -> 2330)
    const code = symbol.split('.')[0];
    return `https://www.cmoney.tw/forum/stock/${code}`;
  } 
  
  // 3. 美股或其他：使用富途牛牛 (需加上 -US)
  else {
    return `https://www.futunn.com/hk/stock/${symbol}-US/community`;
  }
}




// [新增] 音效狀態旗標
let soundOn = false;
const alertAudio = new Audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg");

// 依 soundOn 更新喇叭圖示外觀
function refreshAudioBtn() {
  const btn = document.getElementById('audio-btn');
  if (!btn) return;
  btn.innerText = soundOn ? "🔊" : "🔇";
  btn.title = soundOn ? "音效已啟用 (點擊關閉)" : "點擊以啟用音效";
  btn.style.color = soundOn ? "#198754" : "";
}




// [新增] 嘗試啟用音效 (解鎖瀏覽器限制)
// 喇叭按鈕：切換音效開/關
// event.stopPropagation() 是關鍵 —— 阻止 click 冒泡到 document 的全域監聽器，
// 否則關閉後會立刻被全域監聽器重新啟用 (原本按鈕失效的主因)。
function toggleSound(event) {
  if (event) event.stopPropagation();
  if (soundOn) {
    soundOn = false;
    refreshAudioBtn();
    return;
  }
  // 在使用者手勢中先靜音播放一次，解鎖瀏覽器的自動播放限制
  alertAudio.volume = 0;
  alertAudio.play().then(() => {
    alertAudio.pause();
    alertAudio.currentTime = 0;
    soundOn = true;
    refreshAudioBtn();
    console.log("[System] Audio enabled.");
  }).catch(e => {
    console.warn("音效啟用失敗 (瀏覽器阻擋):", e);
  });
}




// [修改] 警示音效函式 (增強版)
// 警示音：僅在使用者已啟用時才播放 (關閉後不再作響)
function playAlertSound() {
  if (!soundOn) return;
  alertAudio.volume = 1.0;
  try { alertAudio.currentTime = 0; } catch (e) {}
  alertAudio.play().catch(e => {
    console.warn("警示音播放失敗:", e);
  });
}




let flashInterval = null;
const originalTitle = document.title; // 記住原本的標題 (🚀Stock Dashboard)

// [新增] 開始閃爍標題
function startTabFlashing() {
  if (flashInterval) return; // 如果已經在閃爍，就不用重複啟動

  let showWarning = true;
  flashInterval = setInterval(() => {
    // 在 "原本標題" 與 "警示文字" 之間切換
    document.title = showWarning ? "⚠️【急拉/急殺警示】" : originalTitle;
    showWarning = !showWarning;
  }, 800); // 每 0.8 秒切換一次
}




// [新增] 停止閃爍標題 (回復原狀)
function stopTabFlashing() {
  if (flashInterval) {
    clearInterval(flashInterval);
    flashInterval = null;
    document.title = originalTitle; // 強制還原標題
  }
}




async function updateNotify() {
  try {
    const res = await fetch('/api/monitor');
    const data = await res.json();
    document.getElementById('nt-time').innerText = data.timestamp;

    let tableHtml = "";
    
    // [新增] 用來標記是否需要發出警報聲
    let triggerAlertSound = false;
    
    data.rows.forEach(row => {
      // 數值判斷與格式化
      let changeValue = parseFloat(row.change.replace('%', ''));
      let colorClass = "neutral";
      if (changeValue < 0) colorClass = "down";
      else if (changeValue > 0) colorClass = "up";
      
      // 格式化 change_val (加上 + 號，並保留兩位小數)
      let changeValStr = (row.change_val > 0 ? "+" : "") + row.change_val.toFixed(2);
      
      // delta 顏色與數值格式化
      let deltaClass = "neutral";
      if (row.delta > 0) deltaClass = "up";
      else if (row.delta < 0) deltaClass = "down";

      let deltaValStr = (row.delta_val > 0 ? "+" : "") + row.delta_val.toFixed(2);
      
      // 1. 取得 TradingView 連結 (這是原本的)
      const tvLink = getYahooToTradingViewUrl(row.symbol);
      
      // 2. [新增] 取得社群連結
      const commLink = getCommunityLink(row.symbol);
      
      // ============================================================
      // [新增] 檢查警示訊息關鍵字
      // ============================================================
      if (row.alert && (row.alert.includes("急拉") || row.alert.includes("急殺"))) {
        triggerAlertSound = true;
      }
      // ============================================================
      
      tableHtml += `
      <tr>
        <td class="stock-symbol-hover" data-symbol="${row.symbol}" style="padding: 0; height: 1px;">
           <a href="${tvLink}" target="_blank" style="display: flex; flex-direction: column; justify-content: center; width: 100%; height: 100%; padding: 8px; text-decoration:none; color:inherit;">
             <div class="fw-bold">${row.symbol}</div>
             <div class="small text-muted">${row.name}</div>
           </a>
        </td>
        <td>
           <div class="fw-bold">${row.price}</div>
           <div class="${colorClass} small">${row.change} (${changeValStr})</div>
        </td>
        <td>
           <div class="${deltaClass}">${(row.delta * 100).toFixed(2)}%</div>
           <div class="${deltaClass} small">(${deltaValStr})</div>
        </td>
        <td style="padding: 0; height: 1px;">
           <a href="${commLink}" target="_blank" style="display: flex; align-items: center; width: 100%; height: 100%; padding: 8px; text-decoration:none; color:inherit;">
             <div style="width: 100%">${row.alert || ""}</div>
           </a>
        </td>
      </tr>`;
    });
    document.getElementById('stock-table-body').innerHTML = tableHtml || '<tr><td colspan="4" class="text-center text-muted">無資料</td></tr>';

    // [新增] 如果偵測到關鍵字，播放音效
    if (triggerAlertSound) {
      playAlertSound();
      startTabFlashing();
    }

    // 新聞部分
    let newsHtml = "";
    if (data.news && data.news.length > 0) {
      data.news.forEach(n => {
        newsHtml += `
        <div class="news-item">
            <span class="news-tag">${n.tag}</span>
            <small class="text-muted" style="margin-left: 5px; margin-right: 5px;">${n.date}</small>
            <a href="${n.link}" target="_blank" class="news-link">${n.title}</a>
        </div>`;
      });
    } else {
      newsHtml = '<div class="text-center p-3 text-muted">暫無新聞</div>';
    }
    document.getElementById('news-container').innerHTML = newsHtml;

    // ===== 新增：綁定 hover 事件 =====
    attachStockHoverEvents();

    // 重新套用搜尋過濾 (list 每次刷新都會重建 innerHTML)
    applyInboxFilter();

  } catch(e) { console.error("Notify Error:", e); }
}



// 新增：Reset 按鈕功能
async function resetMonitor() {
  if(!confirm("確定要重新載入設定與重算均線嗎？")) return;
  
  // 讓按鈕暫時失效顯示載入中
  const btn = document.querySelector("button[onclick='resetMonitor()']");
  const originalText = btn.innerText;
  btn.innerText = "Processing...";
  btn.disabled = true;

  try {
    const res = await fetch('/api/reset');
    const data = await res.json();
    alert(data.message);
    // 成功後立即刷新列表
    updateNotify();
  } catch(e) {
    console.error(e);
    alert("Reset Failed: " + e);
  } finally {
    btn.innerText = originalText;
    btn.disabled = false;
  }
}




// ===== 新增函數：處理股票代碼 hover 事件 =====
function attachStockHoverEvents() {
  const stockCells = document.querySelectorAll('.stock-symbol-hover');
  
  stockCells.forEach(cell => {
    cell.addEventListener('mouseenter', handleStockHover);
    cell.addEventListener('mouseleave', handleStockLeave);
  });
}




const CHART_URL_MAP = {
  // === 台股相關 ===
  '^TWII': 'https://stock.wearn.com/finance_chart.asp?stockid=IDXWT&timeblock=270&sma1=10&sma2=20&sma3=60&volume=1',
  '^TWOII': 'https://stock.wearn.com/finance_chart.asp?stockid=IDXOT&timekind=0&timeblock=270&sma1=10&sma2=20&sma3=60&volume=1',
  'FITX': 'https://stock.wearn.com/finance_chart.asp?stockid=WTX&timekind=0&timeblock=270&sma1=10&sma2=20&sma3=60&volume=1', // 台指期

  // === 美股期貨 (維持原本 Intraday 5分K) ===
  'ES=F': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@es&tf=i5&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // S&P 500 Futures
  'NQ=F': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@nq&tf=i5&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // Nasdaq 100 Futures
  'YM=F': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@ym&tf=i5&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // Dow Jones Futures

  // === 美股現貨指數 (使用日線 tf=d 看趨勢) ===
  '^GSPC': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=SPY&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // S&P 500 (用 SPY 代表)
  '^IXIC': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=QQQ&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // Nasdaq (用 QQQ 代表)
  '^DJI':  'https://charts2-node.finviz.com/chart.ashx?cs=m&t=DIA&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // Dow Jones (用 DIA 代表)
  '^VIX':  'https://charts2-node.finviz.com/chart.ashx?cs=m&t=VIX&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 恐慌指數

  // === 匯率 Forex (Finviz 代碼對應) ===
  'DX-Y.NYB': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=DX&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d',     // 美元指數 (DXY)
  'EURUSD=X': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=EURUSD&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 歐元/美元
  'JPY=X':    'https://charts2-node.finviz.com/chart.ashx?cs=m&t=USDJPY&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 美元/日幣
  'GBPUSD=X': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=GBPUSD&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 英鎊/美元

  // === 原物料 Commodities ===
  'GC=F': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@GC&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 黃金期貨
  'CL=F': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@CL&tf=d&s=linear&pm=0&am=0&ct=candle_stick&tm=d', // 原油期貨

  // === 加密貨幣 ===
  'BTC-USD': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@btcusd&tf=d&ct=candle_stick&tm=d',
  'ETH-USD': 'https://charts2-node.finviz.com/chart.ashx?cs=m&t=@ethusd&tf=d&ct=candle_stick&tm=d'
};




function handleStockHover(event) {
  const symbol = event.currentTarget.getAttribute('data-symbol');
  if (!symbol) return;

  // === 1. 取得圖片 URL ===
  let imageUrl = (typeof CHART_URL_MAP !== 'undefined') ? CHART_URL_MAP[symbol] : null;

  if (!imageUrl) {
    if (symbol.includes('.TW')) {
      const stockCode = symbol.split('.')[0];
      imageUrl = `https://stock.wearn.com/finance_chart.asp?stockid=${stockCode}&timeblock=270&sma1=10&sma2=20&sma3=60&volume=1`;
    } else {
      var finvizSymbol = symbol.replace(/\./g, '-'); 
      imageUrl = `https://charts2.finviz.com/chart.ashx?t=${finvizSymbol}&ta=1&ty=c&p=d&s=l`;
    }
  }
  
  // === 2. 建立 Popup ===
  let popup = document.getElementById('stock-chart-popup');
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'stock-chart-popup';
    popup.className = 'stock-popup';
    
    // 基礎樣式
    popup.style.background = '#fff';
    popup.style.padding = '10px';
    popup.style.border = '1px solid #ccc';
    popup.style.boxShadow = '0 4px 15px rgba(0,0,0,0.3)'; // 加深一點陰影
    popup.style.borderRadius = '8px';
    popup.style.zIndex = '9999';
    document.body.appendChild(popup);
  }
  
  // === 3. 設定位置與尺寸 (關鍵修改) ===
  popup.style.display = 'block';
  popup.style.position = 'fixed';
  popup.style.left = '5px';
  popup.style.top = '50%';
  popup.style.transform = 'translateY(-50%)';
  
  // 【關鍵修改】：不鎖死 width，改用 min-width
  // 這樣一開始有最小寬度，等圖片載入後，寬度會自動被圖片撐開
  popup.style.width = 'auto'; 
  popup.style.minWidth = '320px'; 
  popup.style.maxWidth = '95vw'; // 防止圖片太大超出螢幕
  
  // === 4. 建構 HTML ===
  const sparklineId = 'hover_spark_' + symbol.replace(/[^a-zA-Z0-9]/g, '') + '_' + Date.now();

  popup.innerHTML = `
    <div style="display: flex; flex-direction: column; align-items: center;">
      
      <div style="width: 100%; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-bottom: 5px;">
        <div id="${sparklineId}_title" style="font-weight: bold; margin-bottom: 5px; font-size: 14px; text-align: left;">${symbol} 即時走勢</div>
        <div id="${sparklineId}" style="width: 100%; height: 80px; display:flex; align-items:center; justify-content:center; background:#f9f9f9;">
          <span class="loading" style="font-size:12px; color:#999;">載入即時盤...</span>
        </div>
      </div>

      <div id="popup-img-container" style="min-height: 200px; display:flex; align-items:center; justify-content:center;">
        <div class="loading" style="font-size:12px; color:#666;">載入技術線圖...</div>
      </div>

    </div>
  `;

  // === 5. 繪製 SVG ===
  setTimeout(() => {
    if (typeof renderSparklineSVG === 'function') {
        renderSparklineSVG(sparklineId, symbol);
    }
  }, 100);

  // === 6. 載入圖片 (撐開寬度) ===
  const img = new Image();
  
  // 圖片樣式：讓它保持原始比例，但不要超過螢幕寬度
  img.style.display = 'block';
  img.style.maxWidth = '90vw'; // 限制最大寬度，避免手機版爆版
  img.style.height = 'auto';
  
  img.onload = () => {
    const imgContainer = popup.querySelector('#popup-img-container');
    if (imgContainer) {
      imgContainer.innerHTML = ''; 
      imgContainer.appendChild(img);
      // 圖片載入後，popup 寬度會自動變寬
      // 上方的 SVG 因為設了 width: 100% 也會跟著拉長
    }
  };
  
  img.onerror = () => {
    const imgContainer = popup.querySelector('#popup-img-container');
    if (imgContainer) {
      imgContainer.innerHTML = '<div style="color: red; padding: 20px;">圖表載入失敗</div>';
    }
  };
  
  img.src = imageUrl;
}




function handleStockLeave(event) {
  const popup = document.getElementById('stock-chart-popup');
  if (popup) {
    popup.style.display = 'none';
    
    // 移除滑鼠移動監聽
    if (popup._updatePosition) {
      event.currentTarget.removeEventListener('mousemove', popup._updatePosition);
      popup._updatePosition = null;
    }
  }
}




window.addEventListener('resize', () => { if(chartInstance) chartInstance.resize(); });




// [修改] 全域點擊監聽
document.addEventListener('click', function globalInteract() {
  // 使用者點擊頁面代表已看到警示 → 停止標題閃爍
  // (不再自動解鎖音效；音效改由喇叭按鈕全權控制，避免與按鈕互相打架)
  stopTabFlashing();
}, { once: false });




document.addEventListener('DOMContentLoaded', () => {
  
  // [新增] 裝置偵測邏輯
  function checkMobileMode() {
    const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    
    // 判斷是否為 Android, iOS (iPhone/iPad/iPod) 或其他行動裝置
    // 這裡我們把 iPad 也強制歸類為 Mobile Mode，以符合您的需求
    const isMobile = /android|ipad|iphone|ipod|blackberry|iemobile|opera mini/i.test(userAgent.toLowerCase());
    
    // 或者：如果螢幕寬度真的非常小 (例如 < 768px)，也強制切換
    const isSmallScreen = window.innerWidth < 768;

    if (isMobile || isSmallScreen) {
      document.body.classList.add('mobile-mode');
      console.log("[System] Mobile Mode Activated (Reason: Device or Screen Size)");
    } else {
      document.body.classList.remove('mobile-mode');
      console.log("[System] Desktop Mode Activated");
    }
  }

  // 初始化時執行一次
  checkMobileMode();
  
  // 當視窗縮放時也重新檢查 (選用，方便電腦測試)
  window.addEventListener('resize', checkMobileMode);

  // ... (原本的初始化代碼) ...
  updateHeatmap();
  updateNotify();
  heatmapInterval = setInterval(conditionalUpdateHeatmap, 300000);
  monitorInterval = setInterval(updateNotify, 120000);
});
</script>

<div id="stock-chart-popup" class="stock-popup"></div>
</body>
</html>
"""




#@app.route("/")
@app.route("/stockdashboard/")
def stockdashboard():
  return render_template_string(HTML_TEMPLATE)




@app.route("/twheatmap/api/debug")
def api_debug_cache():
  fetch_heatmap_data()
  return jsonify({
    "GICS_SECTOR_CACHE_size": len(GICS_SECTOR_CACHE),
    "GICS_sample": list(GICS_SECTOR_CACHE.items())[:3],
    "NDX_SUBSECTOR_CACHE_size": len(NDX_SUBSECTOR_CACHE),
    "NDX_sample": list(NDX_SUBSECTOR_CACHE.items())[:3],
    "DATA_CACHE_sp500": None if DATA_CACHE.get("sp500") is None else len(DATA_CACHE["sp500"]),
    "DATA_CACHE_ndx": None if DATA_CACHE.get("ndx") is None else len(DATA_CACHE["ndx"]),
    "DATA_CACHE_twse": None if DATA_CACHE.get("twse") is None else len(DATA_CACHE["twse"]),
    "last_update": DATA_CACHE.get("last_update"),
  })


@app.route("/twheatmap/api/data")
def api_heatmap_data():
  market = request.args.get("market", "twse")
  type_filter = request.args.get("type", "INDEX")
  area_metric = request.args.get("area", "tradeValueWeight")
  
  print(f"[DEBUG] API Request - Heatmap: Market={market}, Type={type_filter}") # Trace Request
  
  df = get_clean_dataframe(market)
  data_list = build_heatmap_data(df, type_filter, area_metric)
  
  print(f"[DEBUG] Heatmap data returned: {len(data_list)} items") # Trace Response
  
  return json.dumps(data_list)




@app.route("/api/monitor")
def api_monitor():
  print("[DEBUG] API Request - Monitor Check")
  result = monitor.run_check()
  return jsonify(result)




@app.route("/api/sparkline_multi")
def api_sparkline_multi():
  import json as _json
  symbols_str = request.args.get('symbols', '')
  if not symbols_str:
    return jsonify({'error': 'No symbols'}), 400
  symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
  symbols_json = _json.dumps(symbols)
  url = f'https://tw.stock.yahoo.com/_td-stock/api/resource/FinanceChartService.ApacLibraCharts;type=tick;symbols={symbols_json}'
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://tw.stock.yahoo.com/',
  }
  try:
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return Response(r.content, content_type='application/json')
  except Exception as e:
    return jsonify({'error': str(e)}), 502




@app.route("/api/sparkline/<path:symbol>")
def api_sparkline(symbol):
  url = f'https://tw.stock.yahoo.com/_td-stock/api/resource/FinanceChartService.ApacLibraCharts;type=tick;symbols=["{symbol}"]'
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://tw.stock.yahoo.com/',
  }
  try:
    r = requests.get(url, headers=headers, timeout=5)
    r.raise_for_status()
    return Response(r.content, content_type='application/json')
  except Exception as e:
    return jsonify({'error': str(e)}), 502




# 新增的 Reset API
@app.route("/api/reset")
def api_reset():
  print("[DEBUG] API Request - Reset Monitor")
  monitor.initialized = False
  # 立即重新執行初始化與 MA 計算
  monitor.init_portfolio()
  return jsonify({"status": "ok", "message": "Monitor System Reset Complete (JSON Reloaded, MA Recalculated)."})




# Initial S&P500 and Nas-100 sectors
init_sp500_sectors()
init_ndx_subsectors() 




################################################################################################################################################################
################################################################################################################################################################
if __name__ == '__main__':
    app.run(debug=True)
