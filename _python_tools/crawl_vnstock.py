"""
=============================================================
  VNSTOCK DATA CRAWLER — Nguồn: Yahoo Finance + SSI iboard
  Chiến lược: Chia theo Năm (2026 -> 2022) + Incremental Save + Resume

  Dữ liệu thu thập:
    - Năm 2026: 2026-01-01 -> 2026-09-30 (đến tháng trước)
    - Năm 2025: 2025-01-01 -> 2025-12-31
    - Năm 2024: 2024-01-01 -> 2024-12-31
    - Năm 2023: 2023-01-01 -> 2023-12-31
    - Năm 2022: 2022-01-01 -> 2022-12-31

  Cấu trúc thư mục:
    - data/raw_by_year/{YEAR}/{TICKER}_{YEAR}.csv
    - data/eod_wide_all.csv (File gộp tổng hợp cuối cùng)
=============================================================
"""

import os
import time
import random
import json
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd

# ─────────────────────────────────────────────
#  CẤU HÌNH
# ─────────────────────────────────────────────
BASE_DIR  = Path("./data/raw_by_year")
COMBINED  = Path("./data/eod_wide_all.csv")
LOG_FILE  = Path("./data/crawl_log.txt")

# Danh sách các năm ưu tiên: 2026 trước, sau đó lùi dần về 2022
YEAR_CONFIGS = [
    {"year": 2026, "start": "2026-01-01", "end": "2026-09-30"},
    {"year": 2025, "start": "2025-01-01", "end": "2025-12-31"},
    {"year": 2024, "start": "2024-01-01", "end": "2024-12-31"},
    {"year": 2023, "start": "2023-01-01", "end": "2023-12-31"},
    {"year": 2022, "start": "2022-01-01", "end": "2022-12-31"},
]

DELAY_MIN   = 0.5
DELAY_MAX   = 1.2
MAX_RETRIES = 3

BASE_DIR.mkdir(parents=True, exist_ok=True)
COMBINED.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def log(msg: str):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def date_to_epoch(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())

# ─────────────────────────────────────────────
#  LẤY DANH SÁCH MÃ CỔ PHIẾU
# ─────────────────────────────────────────────
def get_symbols() -> list[str]:
    """Lấy danh sách mã HOSE + HNX + UPCOM từ SSI iboard hoặc fallback."""
    all_symbols = []
    H_ssi = {**HEADERS, "Referer": "https://iboard.ssi.com.vn/"}

    for exchange in ["HOSE", "HNX", "UPCOM"]:
        try:
            url = f"https://iboard-query.ssi.com.vn/v2/stock/group/{exchange}"
            r = requests.get(url, headers=H_ssi, timeout=15)
            items = r.json().get("data", [])
            if items:
                syms = [item.get("stock", item.get("c", "")).strip()
                        for item in items if item.get("stock") or item.get("c")]
                syms = [s for s in syms if s and len(s) <= 5 and s.isalnum()]
                all_symbols += syms
                log(f"  SSI {exchange}: {len(syms)} mã")
        except Exception as e:
            log(f"  ⚠️  SSI {exchange} thất bại: {e}")

    if all_symbols:
        return list(dict.fromkeys(all_symbols))

    log("  ⚠️  Dùng danh sách fallback 100 mã")
    return [
        "ACB","AGG","ANV","BCM","BID","BSI","BSR","BVH","BWE","CII",
        "CMG","CTD","CTG","CTS","DCM","DGC","DGW","DIG","DPM","DRC",
        "DXG","EIB","EVF","FPT","GAS","GEG","GMD","HAH","HBC","HCM",
        "HDC","HDG","HPG","HSG","HVN","IDC","KBC","KDH","KHG","LPB",
        "MBB","MBS","MSB","MSN","MWG","NKG","NLG","NT2","NVL","PDR",
        "PHR","PLX","PME","PNJ","POW","PPC","PTB","PVD","PVS","PVT",
        "QTP","REE","SAB","SBT","SHB","SHS","SJS","SKG","SSB","SSI",
        "STB","STK","TCB","TCH","TDH","TIG","TLG","TPB","TV2","TVH",
        "VCB","VCI","VGC","VHC","VHM","VIC","VIP","VJC","VNM","VPB",
        "VRE","VSC","VSH","VTP","VND","VOS","HPX","DBC","GEX"
    ]

# ─────────────────────────────────────────────
#  LẤY GIÁ LỊCH SỬ CHO 1 NĂM CỤ THỂ
# ─────────────────────────────────────────────
def get_ohlcv_by_year(ticker: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Lấy dữ liệu OHLCV của 1 mã cổ phiếu trong khoảng 1 năm từ Yahoo Finance."""
    symbol = f"{ticker}.VN"
    p1 = date_to_epoch(start_date)
    p2 = date_to_epoch(end_date)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d"
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
        
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        
        timestamps = result[0].get("timestamp", [])
        if not timestamps:
            return None
        
        indicators = result[0].get("indicators", {})
        quote = indicators.get("quote", [{}])[0]
        adjclose = indicators.get("adjclose", [{}])[0].get("adjclose", [])
        
        dates = [datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps]
        
        df = pd.DataFrame({
            "date": dates,
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "adj_close": adjclose if len(adjclose) == len(timestamps) else quote.get("close", []),
            "volume": quote.get("volume", []),
        })
        
        df = df.dropna(subset=["close"]).reset_index(drop=True)
        if df.empty:
            return None

        for c in ["open", "high", "low", "close", "adj_close"]:
            df[c] = df[c].round(2)
        
        df["true_range"] = (df["high"] - df["low"]).round(2)
        df["hlc3"] = ((df["high"] + df["low"] + df["close"]) / 3).round(2)
        df["pct_change_calc"] = (df["close"].pct_change().round(4) * 100).fillna(0)
        df["turnover_est_bn"] = ((df["close"] * df["volume"]) / 1e9).round(3)
        
        df["ticker"] = ticker
        df = df.sort_values("date").reset_index(drop=True)
        return df

    except Exception:
        return None

# ─────────────────────────────────────────────
#  CHƯƠNG TRÌNH CHÍNH CRAWL THEO NĂM
# ─────────────────────────────────────────────
def main():
    log("=" * 66)
    log("  BẮT ĐẦU CÀO DỮ LIỆU CHỨNG KHOÁN (ƯU TIÊN 2026 -> LÙI DẦN VỀ 2022)")
    log("=" * 66)

    symbols = get_symbols()
    log(f"✅ Tổng số mã thu thập: {len(symbols)}")

    # Duyệt qua từng năm theo thứ tự 2026 -> 2025 -> 2024 -> 2023 -> 2022
    for cfg in YEAR_CONFIGS:
        year = cfg["year"]
        start_date = cfg["start"]
        end_date = cfg["end"]

        year_dir = BASE_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        log("\n" + "─" * 66)
        log(f"🚀 [GIAI ĐOẠN NĂM {year}] Khoảng thời gian: {start_date} → {end_date}")
        log("─" * 66)

        skipped, success, failed = 0, 0, []

        for i, ticker in enumerate(symbols, 1):
            save_path = year_dir / f"{ticker}_{year}.csv"

            # Resume: Nếu đã có file năm này thì bỏ qua
            if save_path.exists():
                skipped += 1
                continue

            log(f" [{year}] [{i:>4}/{len(symbols)}] {ticker:<8} 🔄 Đang tải dữ liệu năm {year}...")

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    df_ticker = get_ohlcv_by_year(ticker, start_date, end_date)

                    if df_ticker is None or df_ticker.empty:
                        break

                    # Incremental Save: Lưu ngay từng file theo từng năm
                    df_ticker.to_csv(save_path, index=False, encoding="utf-8-sig")
                    success += 1
                    log(f" [{year}] [{i:>4}/{len(symbols)}] {ticker:<8} ✅ {len(df_ticker):>4} ngày phiên")
                    break

                except Exception as e:
                    if attempt == MAX_RETRIES:
                        failed.append(ticker)
                    else:
                        time.sleep(1)

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        log(f"📊 [NĂM {year} HOÀN THÀNH] ✅ Tải mới: {success} | ⏭ Bỏ qua (đã có): {skipped} | ❌ Thất bại: {len(failed)}")

    # ─────────────────────────────────────────────
    #  GỘP TẤT CẢ FILE THEO TỪNG NĂM THÀNH FILE TỔNG HỢP
    # ─────────────────────────────────────────────
    log("\n" + "=" * 66)
    log("  GỘP TẤT CẢ FILE CSV CÁC NĂM VÀO DATASET TỔNG HỢP")
    log("=" * 66)

    all_csv_files = sorted(BASE_DIR.glob("*/*.csv"))
    log(f"📂 Tìm thấy {len(all_csv_files)} file CSV từ tất cả các thư mục năm...")

    if all_csv_files:
        chunks = []
        for f in all_csv_files:
            try:
                chunks.append(pd.read_csv(f, encoding="utf-8-sig", low_memory=False))
            except Exception as e:
                log(f"⚠️  Lỗi đọc file {f.name}: {e}")

        if chunks:
            df_all = pd.concat(chunks, ignore_index=True)
            if "date" in df_all.columns:
                df_all = df_all.sort_values(["ticker", "date"]).reset_index(drop=True)
            df_all.to_csv(COMBINED, index=False, encoding="utf-8-sig")

            log(f"\n🎉 TỔNG HỢP HOÀN TẤT DỮ LIỆU TỪ 2022 ĐẾN 2026!")
            log(f"   Tổng số dòng dữ liệu : {len(df_all):>10,}")
            log(f"   Tổng số cột          : {len(df_all.columns):>10}")
            log(f"   Số mã cổ phiếu       : {df_all['ticker'].nunique():>10}")
            log(f"   Khoảng ngày          : {df_all['date'].min()} → {df_all['date'].max()}")
            log(f"   File xuất tổng hợp   : {COMBINED.resolve()}")

    log("=" * 66)

if __name__ == "__main__":
    main()
