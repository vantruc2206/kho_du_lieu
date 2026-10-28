import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import datetime

DATA_DIR = Path(r"c:\bài tập\môn học\kho_du_lieu\data")
DB_PATH = DATA_DIR / "stock_dwh.db"
SCHEMA_PATH = Path(r"c:\bài tập\môn học\kho_du_lieu\schema_dwh.sql")

def init_database():
    print("=== STEP 1: INITIALIZING DATABASE SCHEMA ===")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())
    conn.commit()
    conn.close()
    print("Database initialized successfully at:", DB_PATH)

def load_dim_sector_and_ticker():
    print("\n=== STEP 2: POPULATING DIM_SECTOR & DIM_TICKER ===")
    df_meta = pd.read_csv(DATA_DIR / "dim_ticker_metadata.csv")
    
    # 1. Dim_Sector
    sectors = df_meta[['sector_name_vn', 'sector_name_en', 'sector_group', 'risk_level']].drop_duplicates().reset_index(drop=True)
    sectors['sector_key'] = sectors.index + 1
    
    conn = sqlite3.connect(DB_PATH)
    sectors.to_sql('dim_sector', conn, if_exists='replace', index=False)
    
    # Map sector_key back to tickers
    df_meta = df_meta.merge(sectors[['sector_name_vn', 'sector_key']], on='sector_name_vn', how='left')
    
    df_ticker = pd.DataFrame({
        'ticker_key': df_meta['ticker_key'],
        'ticker': df_meta['ticker'],
        'company_name': df_meta['company_name'],
        'sector_key': df_meta['sector_key'],
        'sector_group': df_meta['sector_group']
    })
    
    df_ticker.to_sql('dim_ticker', conn, if_exists='replace', index=False)
    conn.commit()
    conn.close()
    print(f"Loaded {len(sectors)} sectors and {len(df_ticker)} tickers into DWH.")

def get_market_phase(dt):
    year = dt.year
    if year == 2008:
        return 'Khủng Hoảng Tài Chính 2008 (Global Crisis)'
    elif year in [2009, 2010]:
        return 'Hồi Phục Sau Khủng Hoảng (Post-Crisis)'
    elif year in [2011, 2012]:
        return 'Khủng Hoảng Nợ Xấu & Ngân Hàng'
    elif year in range(2013, 2018):
        return 'Tăng Trưởng Ổn Định'
    elif year in [2018, 2019]:
        return 'Thị Trường Tích Lũy'
    elif year in [2020, 2021]:
        return 'Sốc COVID-19 & Bùng Nổ Dòng Tiền'
    elif year == 2022:
        return 'Khủng Hoảng Lãi Suất & BĐS 2022'
    elif year in [2023, 2024]:
        return 'Phục Hồi & Tích Lũy'
    else:
        return 'Tăng Trưởng Mới 2025-2026'

def load_dim_date():
    print("\n=== STEP 3: POPULATING DIM_DATE ===")
    start_date = datetime.date(2008, 1, 1)
    end_date = datetime.date(2026, 12, 31)
    
    dates = []
    curr = start_date
    while curr <= end_date:
        date_key = int(curr.strftime("%Y%m%d"))
        dates.append({
            'date_key': date_key,
            'full_date': curr.strftime("%Y-%m-%d"),
            'year': curr.year,
            'quarter': (curr.month - 1) // 3 + 1,
            'month': curr.month,
            'day': curr.day,
            'day_of_week': curr.isoweekday(),
            'day_name': curr.strftime("%A"),
            'is_weekend': 1 if curr.isoweekday() in [6, 7] else 0,
            'market_phase': get_market_phase(curr)
        })
        curr += datetime.timedelta(days=1)
        
    df_date = pd.DataFrame(dates)
    conn = sqlite3.connect(DB_PATH)
    df_date.to_sql('dim_date', conn, if_exists='replace', index=False)
    conn.commit()
    conn.close()
    print(f"Loaded {len(df_date)} dates into Dim_Date.")

def run_etl_fact():
    print("\n=== STEP 4: EXTRACTING, TRANSFORMING & LOADING FACT_DAILY_STOCK_PRICE ===")
    
    conn = sqlite3.connect(DB_PATH)
    df_ticker = pd.read_sql("SELECT ticker, ticker_key FROM dim_ticker", conn)
    ticker_map = dict(zip(df_ticker['ticker'], df_ticker['ticker_key']))
    
    f1 = DATA_DIR / "2008-2022.csv"
    f2 = DATA_DIR / "2022-2026.csv"
    
    print("Reading 2008-2022.csv...")
    df1 = pd.read_csv(f1, low_memory=False)
    if 'time' in df1.columns:
        df1.rename(columns={'time': 'date', 'symbol': 'ticker'}, inplace=True)
        
    print("Reading 2022-2026.csv...")
    df2 = pd.read_csv(f2, low_memory=False)
    
    # Combine datasets
    print("Combining datasets...")
    df_all = pd.concat([df1, df2], ignore_index=True)
    del df1, df2
    
    # Clean ticker column
    df_all['ticker'] = df_all['ticker'].astype(str).str.strip().str.upper()
    df_all['ticker_key'] = df_all['ticker'].map(ticker_map)
    df_all = df_all.dropna(subset=['ticker_key', 'date'])
    df_all['ticker_key'] = df_all['ticker_key'].astype(int)
    
    # Clean & Format date_key
    df_all['date_dt'] = pd.to_datetime(df_all['date'], errors='coerce')
    df_all = df_all.dropna(subset=['date_dt'])
    df_all['date_key'] = df_all['date_dt'].dt.strftime("%Y%m%d").astype(int)
    
    # Deduplicate on (date_key, ticker_key)
    df_all = df_all.drop_duplicates(subset=['date_key', 'ticker_key'])
    df_all = df_all.sort_values(by=['ticker_key', 'date_dt']).reset_index(drop=True)
    
    print("Calculating Technical Metrics (MA20, MA50, Drawdown)...")
    # Grouped rolling metrics
    df_all['ma20'] = df_all.groupby('ticker_key')['close'].transform(lambda x: x.rolling(20, min_periods=1).mean())
    df_all['ma50'] = df_all.groupby('ticker_key')['close'].transform(lambda x: x.rolling(50, min_periods=1).mean())
    
    # 20-day Max Drawdown
    df_all['roll_max20'] = df_all.groupby('ticker_key')['close'].transform(lambda x: x.rolling(20, min_periods=1).max())
    df_all['max_drawdown_20d'] = (df_all['close'] - df_all['roll_max20']) / df_all['roll_max20'] * 100
    
    # Fill defaults
    for col in ['open', 'high', 'low', 'close', 'adj_close', 'volume', 'turnover_est_bn', 'pct_change_calc', 'true_range', 'hlc3']:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce').fillna(0.0)
            
    df_all.rename(columns={'pct_change_calc': 'pct_change'}, inplace=True)
    
    fact_cols = [
        'date_key', 'ticker_key', 'open', 'high', 'low', 'close', 'adj_close',
        'volume', 'turnover_est_bn', 'pct_change', 'true_range', 'hlc3', 'ma20', 'ma50', 'max_drawdown_20d'
    ]
    
    df_fact = df_all[fact_cols]
    
    print(f"Loading {len(df_fact):,} rows into Fact_Daily_Stock_Price...")
    
    # Insert in chunks of 100,000 for fast SQLite loading
    chunk_size = 100000
    for i in range(0, len(df_fact), chunk_size):
        chunk = df_fact.iloc[i:i+chunk_size]
        chunk.to_sql('fact_daily_stock_price', conn, if_exists='append', index=False)
        print(f"  Processed {min(i+chunk_size, len(df_fact)):,} / {len(df_fact):,} rows...")
        
    conn.commit()
    conn.close()
    print("=== ETL PIPELINE COMPLETED SUCCESSFULLY! ===")

if __name__ == "__main__":
    init_database()
    load_dim_sector_and_ticker()
    load_dim_date()
    run_etl_fact()
