import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import plotly.express as px
import os

# ==========================================
# 1. 介面設定與說明
# ==========================================
st.set_page_config(page_title="大戶實戰選股系統", layout="wide")
st.title("🔥 終極股市實戰指南：產業熱區與動能篩選器")
st.markdown("""
結合「產業熱力圖」精準打擊市場熱點，並以「國防線 (20MA)」貫徹無條件停損紀律！
* **🗺️ 資金熱力圖：** 區塊大小代表「成交值(資金量)」，紅色代表漲、綠色代表跌。
* **🛡️ 國防線警示：** 買進後請嚴格盯住「20MA防守價」，一旦跌破請克服心魔、無條件停損出場！
* **📈 終極強勢條件：** 股價大於年線、月線向上、MACD大於0、OBV創高、RS強勢。
""")

# ==========================================
# 2. 資料獲取區 (真實台股清單與產業分類)
# ==========================================
@st.cache_data(ttl=86400)
def get_tw_stock_industry_map():
    """從證交所獲取上市、上櫃、興櫃股票清單，並依據「產業別」進行分類"""
    industry_map = {}
    urls = {
        ".TW": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",       # 上市
        ".TWO": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",      # 上櫃
        ".TWO_EMG": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=5"   # 興櫃
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for suffix_key, url in urls.items():
        suffix = ".TWO" if suffix_key == ".TWO_EMG" else suffix_key
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            df = pd.read_html(res.text)[0]
            
            for i in range(len(df)):
                row = df.iloc[i]
                col_name = str(row[0])
                industry = str(row[4]) 
                
                if industry == 'nan' or industry.strip() == '':
                    industry = '未分類/興櫃'
                
                if '　' in col_name: 
                    ticker = col_name.split('　')[0]
                    name = col_name.split('　')[1]
                    
                    if ticker.isdigit() and len(ticker) == 4:
                        full_ticker = f"{ticker}{suffix}"
                        if industry not in industry_map:
                            industry_map[industry] = []
                        industry_map[industry].append({'ticker': full_ticker, 'name': name})
        except Exception:
            pass
            
    return industry_map

industry_data = get_tw_stock_industry_map()
all_industries = sorted(list(industry_data.keys()))

ticker_lookup = {}
for ind, stocks in industry_data.items():
    for stock in stocks:
        ticker_lookup[stock['ticker']] = {'name': stock['name'], 'industry': ind}

# ==========================================
# 3. 核心策略運算區
# ==========================================
def calculate_indicators(ticker_symbol, stock_name, industry, benchmark_df):
    """計算實戰指南所需的核心指標，並加入資料清洗防呆機制"""
    try:
        stock = yf.Ticker(ticker_symbol)
        
        if stock_name == "搜尋中...":
            try:
                info = stock.info
                stock_name = info.get('shortName', ticker_symbol)
                industry = info.get('sector', '臨時測試')
            except:
                stock_name = ticker_symbol 
        
        df = stock.history(period="1y")
        
        # 🛡️ 除錯機制 1：清除無效資料 (空值)
        df = df.dropna(subset=['Close', 'Volume'])
        
        if len(df) < 240: 
            return None
            
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['240MA'] = df['Close'].rolling(window=240).mean()
        df['20MA_Trend_Up'] = df['20MA'] > df['20MA'].shift(1)
        df['Above_240MA'] = df['Close'] > df['240MA']
        
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Above_Zero'] = df['MACD'] > 0
        
        obv = np.where(df['Close'] > df['Close'].shift(1), df['Volume'], 
              np.where(df['Close'] < df['Close'].shift(1), -df['Volume'], 0))
        df['OBV'] = pd.Series(obv, index=df.index).cumsum()
        df['OBV_High'] = df['OBV'] >= df['OBV'].rolling(window=20).max()
        
        df['Stock_Return_10d'] = df['Close'].pct_change(periods=10)
        aligned_benchmark = benchmark_df['Close'].reindex(df.index).ffill()
        df['Benchmark_Return_10d'] = aligned_benchmark.pct_change(periods=10)
        df['RS_10d'] = df['Stock_Return_10d'] - df['Benchmark_Return_10d']
        df['RS_Positive'] = df['RS_10d'] > 0
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 🛡️ 除錯機制 2：安全計算漲跌幅，避免 NaN
        try:
            if prev['Close'] == 0 or pd.isna(latest['Close']) or pd.isna(prev['Close']):
                daily_return = 0.0
            else:
                daily_return = (latest['Close'] - prev['Close']) / prev['Close']
        except:
            daily_return = 0.0

        # 安全計算成交值
        turnover = latest['Close'] * latest['Volume']
        if pd.isna(turnover):
            turnover = 0.0
        
        close_val = round(latest['Close'], 2)
        ma20_val = round(latest['20MA'], 2)
        defense_status = f"{ma20_val} (🚨無條件賣出!)" if close_val < ma20_val else f"{ma20_val} (✅安全)"
        
        is_strong = (latest['Above_240MA'] and latest['20MA_Trend_Up'] and 
                     latest['MACD_Above_Zero'] and latest['OBV_High'] and latest['RS_Positive'])
        
        return {
            "股票代號": ticker_symbol,
            "名稱": stock_name,
            "產業別": industry,
            "最新收盤價": close_val,
            "國防線(20MA)": defense_status,
            "高於年線": "✅" if latest['Above_240MA'] else "❌",
            "月線向上": "✅" if latest['20MA_Trend_Up'] else "❌",
            "MACD>0": "✅" if latest['MACD_Above_Zero'] else "❌",
            "OBV創高": "✅" if latest['OBV_High'] else "❌",
            "RS強勢": "✅" if latest['RS_Positive'] else "❌",
            "is_strong": is_strong,
            "Daily_Return": daily_return,
            "Turnover": turnover
        }
    except Exception:
        return None

# ==========================================
# 4. 側邊欄 UI 與雙軌執行邏輯
# ==========================================
WATCHLIST_FILE = "my_watchlist.txt"

with st.sidebar:
    st.header("🔍 1. 尋找市場新獵物")
    scan_mode = st.radio("選擇市場掃描範圍：", 
                         ("依產業類股掃描 (推薦)", "自訂個股掃描 (快篩)", "全市場掃描 (上市/上櫃/興櫃)"))
    
    market_tickers_to_scan = []
    
    if scan_mode == "依產業類股掃描 (推薦)":
        selected_industries = st.multiselect(
            "請選擇你想掃描的產業：",
            options=all_industries,
            default=["半導體業"] if "半導體業" in all_industries else []
        )
        for ind in selected_industries:
            for stock_info in industry_data.get(ind, []):
                market_tickers_to_scan.append({
                    'ticker': stock_info['ticker'], 'name': stock_info['name'], 'industry': ind
                })
                
    elif scan_mode == "自訂個股掃描 (快篩)":
        quick_tickers = st.text_input("輸入想快速測試的股票代號 (如: 2330, 2603)", value="2330, 2317")
        raw_list = [t.strip().upper() for t in quick_tickers.replace('\n', ',').split(",") if t.strip()]
        for t in raw_list:
            if t.isdigit() and len(t) == 4:
                t = f"{t}.TW"
            info = ticker_lookup.get(t)
            if info:
                market_tickers_to_scan.append({'ticker': t, 'name': info['name'], 'industry': info['industry']})
            else:
                market_tickers_to_scan.append({'ticker': t, 'name': '搜尋中...', 'industry': '臨時測試'})
                
    else:
        for ind, stocks in industry_data.items():
            for stock_info in stocks:
                market_tickers_to_scan.append({
                    'ticker': stock_info['ticker'], 'name': stock_info['name'], 'industry': ind
                })
                
    run_market_scan = st.button("🚀 啟動市場掃描", type="secondary")

    st.markdown("---")
    
    st.header("📁 2. 我的專屬觀察池")
    st.markdown("將平時關注的股票存在這，完全獨立運作，不受上方影響。")
    
    default_list = "2330.TW, 2317.TW, 2454.TW"
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            default_list = f.read()
            
    custom_tickers = st.text_area("輸入長期追蹤股票代號 (逗號分隔)", value=default_list, height=100)
    
    if st.button("💾 儲存名單"):
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            f.write(custom_tickers)
        st.success("✅ 名單已成功儲存在電腦中！")
        
    run_watchlist_scan = st.button("🔬 一鍵體檢觀察池", type="primary")

# ==========================================
# 5. 掃描觸發判斷與進度顯示
# ==========================================
tickers_to_scan = []
is_watchlist_mode = False

if run_watchlist_scan:
    is_watchlist_mode = True
    raw_list = [t.strip().upper() for t in custom_tickers.replace('\n', ',').split(",") if t.strip()]
    for t in raw_list:
        if t.isdigit() and len(t) == 4:
            t = f"{t}.TW"
        info = ticker_lookup.get(t)
        if info:
            tickers_to_scan.append({'ticker': t, 'name': info['name'], 'industry': info['industry']})
        else:
            tickers_to_scan.append({'ticker': t, 'name': '搜尋中...', 'industry': '自訂清單'})
            
elif run_market_scan:
    is_watchlist_mode = False
    tickers_to_scan = market_tickers_to_scan

if len(tickers_to_scan) > 0:
    st.write("---")
    st.info("正在獲取大盤基準資料 (0050.TW) 作為對比...")
    benchmark = yf.Ticker("0050.TW").history(period="1y")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    total = len(tickers_to_scan)
    
    for i, item in enumerate(tickers_to_scan):
        status_text.text(f"正在分析 ({i+1}/{total}): {item['ticker']}")
        res = calculate_indicators(item['ticker'], item['name'], item['industry'], benchmark)
        if res:
            results.append(res)
        progress_bar.progress((i + 1) / total)
        time.sleep(0.02)
        
    status_text.text("✅ 分析完成！")
    
    # ==========================================
    # 6. 結果呈現區 (熱力圖與表格)
    # ==========================================
    if results:
        df_results = pd.DataFrame(results)
        
        st.subheader("📊 資金籌碼熱力圖")
        
        # 🛡️ 除錯機制 3：將所有的 NaN 轉換為 0，確保圖表正常顯示
        df_results['Daily_Return'] = df_results['Daily_Return'].fillna(0)
        df_results['漲跌幅(%)'] = df_results['Daily_Return'] * 100
        df_results['Turnover'] = df_results['Turnover'].fillna(1).replace(0, 1)
        
        df_results['純代號'] = df_results['股票代號'].str.replace('.TW', '', regex=False).str.replace('.TWO', '', regex=False)
        df_results['圖表顯示名稱'] = df_results['純代號'] + " " + df_results['名稱']
        
        fig = px.treemap(
            df_results,
            path=[px.Constant("台股掃描板塊"), '產業別', '圖表顯示名稱'], 
            values='Turnover', 
            color='漲跌幅(%)',
            color_continuous_scale=['#008000', '#222222', '#ff0000'], 
            color_continuous_midpoint=0,
            hover_data=['最新收盤價', '國防線(20MA)']
        )
        fig.update_traces(texttemplate="%{label}<br>%{color:.2f}%")
        fig.update_layout(margin=dict(t=30, l=10, r=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("---")
        
        strong_stocks = df_results[df_results["is_strong"] == True]
        display_cols = ["股票代號", "名稱", "產業別", "最新收盤價", "國防線(20MA)", "高於年線", "月線向上", "MACD>0", "OBV創高", "RS強勢"]
        
        if is_watchlist_mode:
            st.subheader(f"📋 專屬觀察池：全標的體檢報告 (共 {len(df_results)} 檔)")
            st.dataframe(df_results[display_cols], use_container_width=True)
            
            if not strong_stocks.empty:
                st.success(f"💡 恭喜！您的觀察名單中有 {len(strong_stocks)} 檔符合「完美強勢條件」，可以準備伺機進場！")
            else:
                st.warning("⚠️ 目前您的觀察池中，暫無完美符合所有強勢條件的標的，建議繼續觀望或尋找新標的。")
        else:
            st.subheader(f"🎯 市場掃描：發現 {len(strong_stocks)} 檔強勢標的")
            if not strong_stocks.empty:
                st.dataframe(strong_stocks[display_cols], use_container_width=True)
                st.success("""
                **💡 顧問實戰叮嚀：** 1. 買進強勢股後，請死死盯住**「國防線(20MA)」**。
                2. 跌破防守價亮起警示，代表大戶成本已失守，請直接無條件賣出，絕不攤平！
                """)
            else:
                st.warning("此範圍內，目前暫無完美符合條件的標的，空手等待是最好的策略！")
            
            st.write("---")
            with st.expander("👀 查看本次掃描【所有標的】狀態 (含未過濾)"):
                st.dataframe(df_results[display_cols], use_container_width=True)