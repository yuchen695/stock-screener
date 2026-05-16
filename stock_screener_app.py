import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import plotly.express as px
import os

# ==========================================
# 1. 介面設定
# ==========================================
st.set_page_config(page_title="大戶實戰選股系統", layout="wide")
st.title("🔥 終極股市實戰指南：雲端強化版")

# ==========================================
# 2. 資料獲取區 (加入強大的錯誤處理與備援機制)
# ==========================================
@st.cache_data(ttl=86400)
def get_tw_stock_industry_map():
    industry_map = {}
    urls = {
        ".TW": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        ".TWO": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        for suffix, url in urls.items():
            res = requests.get(url, headers=headers, timeout=10)
            df = pd.read_html(res.text)[0]
            for i in range(len(df)):
                row = df.iloc[i]
                col_name = str(row[0])
                industry = str(row[4])
                if '　' in col_name and industry != 'nan':
                    ticker = col_name.split('　')[0]
                    name = col_name.split('　')[1]
                    if ticker.isdigit() and len(ticker) == 4:
                        full_ticker = f"{ticker}{suffix}"
                        if industry not in industry_map: industry_map[industry] = []
                        industry_map[industry].append({'ticker': full_ticker, 'name': name})
    except Exception:
        # 如果證交所掛了，提供一個最基本的備援分類
        st.warning("⚠️ 證交所連線不穩，已啟動備援資料庫。")
        return {"基本權值股": [{"ticker": "2330.TW", "name": "台積電"}, {"ticker": "2317.TW", "name": "鴻海"}]}
            
    return industry_map

industry_data = get_tw_stock_industry_map()
all_industries = sorted(list(industry_data.keys()))

# 快速查詢字典
ticker_lookup = {}
for ind, stocks in industry_data.items():
    for stock in stocks:
        ticker_lookup[stock['ticker']] = {'name': stock['name'], 'industry': ind}

# ==========================================
# 3. 核心指標運算 (修正名稱缺失問題)
# ==========================================
def calculate_indicators(ticker_symbol, stock_name, industry, benchmark_df):
    try:
        stock = yf.Ticker(ticker_symbol)
        
        # 修正問題2：如果名稱是搜尋中，嘗試補抓
        if stock_name == "搜尋中..." or not stock_name:
            info = stock.info
            stock_name = info.get('shortName', ticker_symbol)
            industry = info.get('sector', '自訂標的')

        df = stock.history(period="1y")
        df = df.dropna(subset=['Close'])
        if len(df) < 240: return None
            
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['240MA'] = df['Close'].rolling(window=240).mean()
        df['20MA_Trend_Up'] = df['20MA'] > df['20MA'].shift(1)
        df['Above_240MA'] = df['Close'] > df['240MA']
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        
        # OBV
        obv = np.where(df['Close'] > df['Close'].shift(1), df['Volume'], np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
        df['OBV'] = pd.Series(obv, index=df.index).cumsum()
        
        # RS
        df['Stock_Return_10d'] = df['Close'].pct_change(periods=10)
        aligned_benchmark = benchmark_df['Close'].reindex(df.index).ffill()
        df['Benchmark_Return_10d'] = aligned_benchmark.pct_change(periods=10)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        daily_return = (latest['Close'] - prev['Close']) / prev['Close'] if prev['Close'] != 0 else 0
        turnover = latest['Close'] * latest['Volume']
        
        is_strong = (latest['Above_240MA'] and latest['20MA_Trend_Up'] and latest['MACD'] > 0 and 
                     latest['OBV'] >= df['OBV'].rolling(window=20).max().iloc[-1] and 
                     (latest['Stock_Return_10d'] - latest['Benchmark_Return_10d']) > 0)
        
        return {
            "股票代號": ticker_symbol, "名稱": stock_name, "產業別": industry,
            "最新收盤價": round(latest['Close'], 2),
            "國防線(20MA)": f"{round(latest['20MA'], 2)} (🚨賣出)" if latest['Close'] < latest['20MA'] else f"{round(latest['20MA'], 2)} (✅安全)",
            "高於年線": "✅" if latest['Above_240MA'] else "❌",
            "月線向上": "✅" if latest['20MA_Trend_Up'] else "❌",
            "MACD>0": "✅" if latest['MACD'] > 0 else "❌",
            "OBV創高": "✅" if latest['OBV'] >= df['OBV'].rolling(window=20).max().iloc[-1] else "❌",
            "RS強勢": "✅" if (latest['Stock_Return_10d'] - latest['Benchmark_Return_10d']) > 0 else "❌",
            "is_strong": is_strong, "Daily_Return": daily_return, "Turnover": turnover
        }
    except Exception: return None

# ==========================================
# 4. 側邊欄與邏輯
# ==========================================
WATCHLIST_FILE = "my_watchlist.txt"
with st.sidebar:
    st.header("🔍 1. 市場打獵區")
    scan_mode = st.radio("掃描範圍：", ("產業掃描", "個股快篩", "全市場掃描"))
    
    market_list = []
    if scan_mode == "產業掃描":
        selected = st.multiselect("產業：", options=all_industries, default=all_industries[:1])
        for s in selected:
            for item in industry_data.get(s, []): market_list.append({'ticker': item['ticker'], 'name': item['name'], 'industry': s})
    elif scan_mode == "個股快篩":
        txt = st.text_input("代號(逗號隔開):", "2330, 2317")
        for t in txt.split(','):
            t = t.strip() + ".TW" if t.strip().isdigit() else t.strip()
            info = ticker_lookup.get(t, {'name': '搜尋中...', 'industry': '臨時測試'})
            market_list.append({'ticker': t, 'name': info['name'], 'industry': info['industry']})
    else:
        for ind, stocks in industry_data.items():
            for s in stocks: market_list.append({'ticker': s['ticker'], 'name': s['name'], 'industry': ind})
            
    btn_market = st.button("🚀 啟動市場掃描")
    st.markdown("---")
    st.header("📁 2. 我的觀察池")
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f: saved = f.read()
    else: saved = "2330.TW"
    watchlist_txt = st.text_area("追蹤名單:", value=saved)
    if st.button("💾 儲存"):
        with open(WATCHLIST_FILE, "w") as f: f.write(watchlist_txt)
        st.success("儲存成功")
    btn_watchlist = st.button("🔬 體檢觀察池")

# ==========================================
# 5. 執行
# ==========================================
active_list = []
if btn_market: active_list = market_list
elif btn_watchlist:
    for t in watchlist_txt.split(','):
        t = t.strip() + ".TW" if t.strip().isdigit() else t.strip()
        info = ticker_lookup.get(t, {'name': '搜尋中...', 'industry': '觀察池'})
        active_list.append({'ticker': t, 'name': info['name'], 'industry': info['industry']})

if active_list:
    bench = yf.Ticker("0050.TW").history(period="1y")
    results = []
    bar = st.progress(0)
    for i, item in enumerate(active_list):
        res = calculate_indicators(item['ticker'], item['name'], item['industry'], bench)
        if res: results.append(res)
        bar.progress((i+1)/len(active_list))
    
    if results:
        df = pd.DataFrame(results)
        # 熱力圖
        df['圖表名稱'] = df['股票代號'].str[:4] + " " + df['名稱']
        fig = px.treemap(df, path=[px.Constant("台股"), '產業別', '圖表名稱'], values='Turnover', color='Daily_Return',
                         color_continuous_scale=['#008000', '#222222', '#ff0000'], color_continuous_midpoint=0)
        st.plotly_chart(fig, use_container_width=True)
        # 表格
        cols = ["股票代號", "名稱", "產業別", "最新收盤價", "國防線(20MA)", "高於年線", "月線向上", "MACD>0", "OBV創高", "RS強勢"]
        st.dataframe(df[cols], use_container_width=True)