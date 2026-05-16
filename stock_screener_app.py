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
st.title("🔥 終極股市實戰指南：產業熱區與動能篩選器")
st.markdown("""
結合「產業熱力圖」精準打擊市場熱點，並以「國防線 (20MA)」貫徹無條件停損紀律！
""")

# ==========================================
# 2. 資料獲取區 (加入菁英備援名單與翻譯)
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
        # 嘗試連線台灣證交所
        for suffix, url in urls.items():
            res = requests.get(url, headers=headers, timeout=8)
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
                        
        if not industry_map:
            raise Exception("抓取結果為空")
            
    except Exception:
        # 🚨 當雲端主機被證交所阻擋時，啟動內建的「台股菁英備援名單」
        st.warning("⚠️ 雲端主機遭證交所防火牆阻擋，已自動切換為【內建菁英權值股備援名單】。")
        return {
            "半導體業": [
                {"ticker": "2330.TW", "name": "台積電"}, {"ticker": "2454.TW", "name": "聯發科"},
                {"ticker": "2303.TW", "name": "聯電"}, {"ticker": "3711.TW", "name": "日月光投控"},
                {"ticker": "3231.TW", "name": "緯創"}, {"ticker": "3443.TW", "name": "創意"}
            ],
            "光電業": [
                {"ticker": "3008.TW", "name": "大立光"}, {"ticker": "2409.TW", "name": "友達"},
                {"ticker": "3481.TW", "name": "群創"}, {"ticker": "3046.TW", "name": "建碁"}
            ],
            "電腦及週邊設備業": [
                {"ticker": "2382.TW", "name": "廣達"}, {"ticker": "2356.TW", "name": "英業達"},
                {"ticker": "2324.TW", "name": "仁寶"}, {"ticker": "2376.TW", "name": "技嘉"},
                {"ticker": "2353.TW", "name": "宏碁"}, {"ticker": "2357.TW", "name": "華碩"}
            ],
            "電子零組件業": [
                {"ticker": "2308.TW", "name": "台達電"}, {"ticker": "3037.TW", "name": "欣興"},
                {"ticker": "2313.TW", "name": "華通"}, {"ticker": "2368.TW", "name": "金像電"}
            ],
            "航運業": [
                {"ticker": "2603.TW", "name": "長榮"}, {"ticker": "2609.TW", "name": "陽明"},
                {"ticker": "2615.TW", "name": "萬海"}, {"ticker": "2618.TW", "name": "長榮航"}
            ],
            "金融保險業": [
                {"ticker": "2881.TW", "name": "富邦金"}, {"ticker": "2882.TW", "name": "國泰金"},
                {"ticker": "2891.TW", "name": "中信金"}, {"ticker": "2886.TW", "name": "兆豐金"}
            ],
            "其他電子業": [
                {"ticker": "2317.TW", "name": "鴻海"}
            ]
        }
            
    return industry_map

industry_data = get_tw_stock_industry_map()
all_industries = sorted(list(industry_data.keys()))

ticker_lookup = {}
for ind, stocks in industry_data.items():
    for stock in stocks:
        ticker_lookup[stock['ticker']] = {'name': stock['name'], 'industry': ind}

# ==========================================
# 3. 核心指標運算 (加入 YFinance 自動翻譯機)
# ==========================================
def calculate_indicators(ticker_symbol, stock_name, industry, benchmark_df):
    try:
        stock = yf.Ticker(ticker_symbol)
        
        # 如果還是抓不到名字，從 YFinance 抓取並自動翻譯產業
        if stock_name == "搜尋中..." or not stock_name:
            info = stock.info
            stock_name = info.get('shortName', ticker_symbol)
            
            # YFinance 產業鏈中英自動翻譯字典
            sector_translations = {
                "Technology": "電子與科技業",
                "Financial Services": "金融保險業",
                "Healthcare": "生技醫療業",
                "Consumer Cyclical": "循環性消費",
                "Industrials": "傳統工業",
                "Basic Materials": "原物料業",
                "Real Estate": "營建與地產",
                "Communication Services": "通信網路業",
                "Utilities": "水電瓦斯業",
                "Energy": "能源業",
                "Consumer Defensive": "防禦性消費"
            }
            raw_sector = info.get('sector', '自訂標的')
            industry = sector_translations.get(raw_sector, raw_sector) # 找不到翻譯就保留原本的

        df = stock.history(period="1y")
        df = df.dropna(subset=['Close'])
        if len(df) < 240: return None
            
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['240MA'] = df['Close'].rolling(window=240).mean()
        df['20MA_Trend_Up'] = df['20MA'] > df['20MA'].shift(1)
        df['Above_240MA'] = df['Close'] > df['240MA']
        
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        
        obv = np.where(df['Close'] > df['Close'].shift(1), df['Volume'], np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
        df['OBV'] = pd.Series(obv, index=df.index).cumsum()
        
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
        txt = st.text_input("代號(逗號隔開):", "2330, 2603")
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
    
    # 讀取名單機制
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f: saved = f.read()
    else: saved = "2330.TW, 2317.TW, 2454.TW, 3008.TW"
    
    watchlist_txt = st.text_area("追蹤名單:", value=saved)
    if st.button("💾 儲存"):
        with open(WATCHLIST_FILE, "w") as f: f.write(watchlist_txt)
        st.success("儲存成功")
    btn_watchlist = st.button("🔬 體檢觀察池")

# ==========================================
# 5. 執行區
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
        
        st.subheader("📊 資金籌碼熱力圖")
        df['圖表名稱'] = df['股票代號'].str[:4] + " " + df['名稱']
        fig = px.treemap(df, path=[px.Constant("台股板塊"), '產業別', '圖表名稱'], values='Turnover', color='Daily_Return',
                         color_continuous_scale=['#008000', '#222222', '#ff0000'], color_continuous_midpoint=0)
        fig.update_traces(texttemplate="%{label}<br>%{color:.2f}%")
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("---")
        cols = ["股票代號", "名稱", "產業別", "最新收盤價", "國防線(20MA)", "高於年線", "月線向上", "MACD>0", "OBV創高", "RS強勢"]
        st.dataframe(df[cols], use_container_width=True)