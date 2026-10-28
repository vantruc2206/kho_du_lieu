import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="DWH & BI — Phân Tích Chứng Khoán Trong Khủng Hoảng",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM GLASSMORPHISM CSS ---
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .css-1r6slb0, .css-12w0qpk {
        background: rgba(255, 255, 255, 0.03);
    }
    h1, h2, h3 {
        color: #00E5FF !important;
        font-family: 'Segoe UI', Roboto, sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
DB_PATH = Path(r"c:\bài tập\môn học\kho_du_lieu\data\stock_dwh.db")

@st.cache_data(ttl=3600)
def load_data(query):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# --- TITLE BANNER ---
st.title("📈 KHO DỮ LIỆU & BUSINESS INTELLIGENCE (DWH/BI)")
st.subheader("Hệ Thống Phân Tích Hiệu Suất Nhóm Ngành Chứng Khoán Việt Nam Trong Khủng Hoảng (2008 - 2026)")
st.markdown("---")

# --- SIDEBAR FILTERS ---
st.sidebar.header("🔍 Bộ Lọc Dữ Liệu (Filters)")

years = list(range(2008, 2027))
selected_year = st.sidebar.selectbox("Chọn Năm Phân Tích", ["Tất cả (2008-2026)"] + years, index=0)

sector_groups = ["Tất cả", "Defensive", "Cyclical", "Growth"]
selected_group = st.sidebar.selectbox("Nhóm Ngành (Sector Group)", sector_groups, index=0)

phases = [
    "Tất cả",
    "Khủng Hoảng Tài Chính 2008 (Global Crisis)",
    "Hồi Phục Sau Khủng Hoảng (Post-Crisis)",
    "Khủng Hoảng Nợ Xấu & Ngân Hàng",
    "Tăng Trưởng Ổn Định",
    "Thị Trường Tích Lũy",
    "Sốc COVID-19 & Bùng Nổ Dòng Tiền",
    "Khủng Hoảng Lãi Suất & BĐS 2022",
    "Phục Hồi & Tích Lũy",
    "Tăng Trưởng Mới 2025-2026"
]
selected_phase = st.sidebar.selectbox("Giai Đoạn Thị Trường", phases, index=0)

# Build Dynamic SQL Clause
where_clauses = ["1=1"]
if selected_year != "Tất cả (2008-2026)":
    where_clauses.append(f"d.year = {selected_year}")
if selected_group != "Tất cả":
    where_clauses.append(f"s.sector_group = '{selected_group}'")
if selected_phase != "Tất cả":
    where_clauses.append(f"d.market_phase = '{selected_phase}'")

where_str = " AND ".join(where_clauses)

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 1. Tổng Quan Thị Trường", 
    "🛡️ 2. Ngành Trong Khủng Hoảng", 
    "📈 3. Chi Tiết Mã Cổ Phiếu", 
    "🏛️ 4. Kiến Trúc Kho Dữ Liệu"
])

# ==========================================
# TAB 1: TỔNG QUAN THỊ TRƯỜNG
# ==========================================
with tab1:
    st.markdown("### 📊 Tổng Quan Thanh Khoản & Biến Động Thị Trường")
    
    kpi_query = f"""
    SELECT 
        COUNT(f.fact_id) AS total_records,
        COUNT(DISTINCT f.ticker_key) AS active_tickers,
        SUM(f.turnover_est_bn) AS total_turnover,
        AVG(f.pct_change) AS avg_daily_change
    FROM fact_daily_stock_price f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_ticker t ON f.ticker_key = t.ticker_key
    JOIN dim_sector s ON t.sector_key = s.sector_key
    WHERE {where_str};
    """
    df_kpi = load_data(kpi_query)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tổng Số Bản Ghi Fact", f"{df_kpi['total_records'].iloc[0]:,}")
    with col2:
        st.metric("Số Mã Cổ Phiếu Giao Dịch", f"{df_kpi['active_tickers'].iloc[0]:,}")
    with col3:
        st.metric("Tổng Thanh Khoản (Tỷ VNĐ)", f"{df_kpi['total_turnover'].iloc[0]:,.1f}")
    with col4:
        st.metric("Biến Động Giá Tự Nhiên TB (%)", f"{df_kpi['avg_daily_change'].iloc[0]:.2f}%")
        
    st.markdown("---")
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### 🍩 Tỷ Trọng Thanh Khoản Theo Nhóm Ngành")
        pie_query = f"""
        SELECT 
            s.sector_group,
            SUM(f.turnover_est_bn) AS turnover
        FROM fact_daily_stock_price f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_ticker t ON f.ticker_key = t.ticker_key
        JOIN dim_sector s ON t.sector_key = s.sector_key
        WHERE {where_str}
        GROUP BY s.sector_group;
        """
        df_pie = load_data(pie_query)
        fig_pie = px.pie(
            df_pie, values='turnover', names='sector_group', 
            color='sector_group',
            color_discrete_map={'Defensive':'#00E676', 'Cyclical':'#FF1744', 'Growth':'#00E5FF'},
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col_chart2:
        st.markdown("#### 📈 Diễn Biến Thanh Khoản Hàng Năm (2008 - 2026)")
        bar_query = """
        SELECT 
            d.year,
            s.sector_group,
            SUM(f.turnover_est_bn) AS turnover
        FROM fact_daily_stock_price f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_ticker t ON f.ticker_key = t.ticker_key
        JOIN dim_sector s ON t.sector_key = s.sector_key
        GROUP BY d.year, s.sector_group
        ORDER BY d.year;
        """
        df_bar = load_data(bar_query)
        fig_bar = px.bar(
            df_bar, x='year', y='turnover', color='sector_group',
            barmode='stack',
            color_discrete_map={'Defensive':'#00E676', 'Cyclical':'#FF1744', 'Growth':'#00E5FF'},
            labels={'turnover': 'Thanh Khoản (Tỷ VNĐ)', 'year': 'Năm'}
        )
        st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# TAB 2: NGÀNH TRONG KHỦNG HOẢNG
# ==========================================
with tab2:
    st.markdown("### 🛡️ Phân Tích Hiệu Suất Nhóm Ngành Trong Các Đợt Khủng Hoảng")
    st.info("💡 **Quy Luật Đầu Tư**: Trong các đợt khủng hoảng (năm 2008, 2011, 2022), nhóm **Phòng Thủ (Defensive)** ít sụt giảm hơn nhóm **Chu Kỳ (Cyclical)**, đóng vai trò là 'Trú ẩn an toàn' nâng cao hiệu suất danh mục.")
    
    dd_query = """
    SELECT 
        d.market_phase,
        s.sector_group,
        s.sector_name_vn,
        ROUND(AVG(f.pct_change), 2) AS avg_return_pct,
        ROUND(AVG(f.max_drawdown_20d), 2) AS avg_max_drawdown
    FROM fact_daily_stock_price f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_ticker t ON f.ticker_key = t.ticker_key
    JOIN dim_sector s ON t.sector_key = s.sector_key
    WHERE d.market_phase IN ('Khủng Hoảng Tài Chính 2008 (Global Crisis)', 'Khủng Hoảng Lãi Suất & BĐS 2022', 'Sốc COVID-19 & Bùng Nổ Dòng Tiền')
    GROUP BY d.market_phase, s.sector_group, s.sector_name_vn
    ORDER BY avg_max_drawdown DESC;
    """
    df_dd = load_data(dd_query)
    
    st.markdown("#### 🔻 Mức Sụt Giảm Giá Tối Đa (Max Drawdown 20D) Theo Ngành")
    fig_dd = px.box(
        df_dd, x='sector_group', y='avg_max_drawdown', color='sector_group',
        points="all", hover_data=['sector_name_vn', 'market_phase'],
        color_discrete_map={'Defensive':'#00E676', 'Cyclical':'#FF1744', 'Growth':'#00E5FF'},
        labels={'avg_max_drawdown': 'Mức Sụt Giảm TB (%)', 'sector_group': 'Nhóm Ngành'}
    )
    st.plotly_chart(fig_dd, use_container_width=True)
    
    st.markdown("#### 🏆 Top 10 Cổ Phiếu Phòng Thủ Trú Ẩn Tốt Nhất Nổi Bật 2022")
    top_def_query = """
    SELECT 
        t.ticker,
        t.company_name,
        s.sector_name_vn,
        ROUND(AVG(f.close), 2) AS avg_close,
        ROUND(AVG(f.pct_change), 2) AS avg_daily_return,
        ROUND(AVG(f.max_drawdown_20d), 2) AS avg_max_drawdown
    FROM fact_daily_stock_price f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_ticker t ON f.ticker_key = t.ticker_key
    JOIN dim_sector s ON t.sector_key = s.sector_key
    WHERE d.year = 2022 AND s.sector_group = 'Defensive'
    GROUP BY t.ticker
    HAVING COUNT(f.fact_id) > 100
    ORDER BY avg_max_drawdown DESC
    LIMIT 10;
    """
    df_top_def = load_data(top_def_query)
    st.dataframe(df_top_def, use_container_width=True)

# ==========================================
# TAB 3: CHI TIẾT MÃ CỔ PHIẾU
# ==========================================
with tab3:
    st.markdown("### 📈 Phân Tích Kỹ Thuật & Biến Động Giá Mã Cổ Phiếu")
    
    tickers_query = "SELECT DISTINCT ticker FROM dim_ticker ORDER BY ticker;"
    df_tickers = load_data(tickers_query)
    
    selected_ticker = st.selectbox("Chọn Mã Cổ Phiếu", df_tickers['ticker'], index=df_tickers['ticker'].tolist().index('FPT') if 'FPT' in df_tickers['ticker'].tolist() else 0)
    
    stock_query = f"""
    SELECT 
        d.full_date,
        f.open, f.high, f.low, f.close, f.volume, f.ma20, f.ma50, f.max_drawdown_20d
    FROM fact_daily_stock_price f
    JOIN dim_date d ON f.date_key = d.date_key
    JOIN dim_ticker t ON f.ticker_key = t.ticker_key
    WHERE t.ticker = '{selected_ticker}'
    ORDER BY d.full_date ASC;
    """
    df_stock = load_data(stock_query)
    df_stock['full_date'] = pd.to_datetime(df_stock['full_date'])
    
    st.markdown(f"#### 📉 Biểu Đồ Giá Close & Đường Trung Bình Động (MA20 / MA50) của **{selected_ticker}**")
    
    fig_stock = go.Figure()
    fig_stock.add_trace(go.Scatter(x=df_stock['full_date'], y=df_stock['close'], mode='lines', name='Giá Đóng Cửa (Close)', line=dict(color='#00E5FF', width=1.5)))
    fig_stock.add_trace(go.Scatter(x=df_stock['full_date'], y=df_stock['ma20'], mode='lines', name='MA20', line=dict(color='#FFD600', width=1)))
    fig_stock.add_trace(go.Scatter(x=df_stock['full_date'], y=df_stock['ma50'], mode='lines', name='MA50', line=dict(color='#FF1744', width=1)))
    
    fig_stock.update_layout(template="plotly_dark", height=500, xaxis_title="Thời Gian", yaxis_title="Giá (VNĐ)")
    st.plotly_chart(fig_stock, use_container_width=True)

# ==========================================
# TAB 4: KIẾN TRÚC KHO DỮ LIỆU
# ==========================================
with tab4:
    st.markdown("### 🏛️ Sơ Đồ Star Schema & Từ Điển Dữ Liệu (Data Dictionary)")
    
    st.markdown("""
    ```mermaid
    erDiagram
        Fact_Daily_Stock_Price }|--|| Dim_Date : "date_key"
        Fact_Daily_Stock_Price }|--|| Dim_Ticker : "ticker_key"
        Dim_Ticker }|--|| Dim_Sector : "sector_key"
        
        Fact_Daily_Stock_Price {
            int fact_id PK
            int date_key FK
            int ticker_key FK
            real open
            real high
            real low
            real close
            real volume
            real turnover_est_bn
            real pct_change
            real ma20
            real ma50
            real max_drawdown_20d
        }
        
        Dim_Date {
            int date_key PK
            date full_date
            int year
            int quarter
            int month
            string market_phase
        }
        
        Dim_Ticker {
            int ticker_key PK
            string ticker
            string company_name
            int sector_key FK
            string sector_group
        }
        
        Dim_Sector {
            int sector_key PK
            string sector_name_vn
            string sector_group
            string risk_level
        }
    ```
    """)
    
    st.markdown("#### 📖 Từ Điển Dữ Liệu (Data Dictionary)")
    st.markdown("""
    | Bảng | Tên Trường | Kiểu Dữ Liệu | Loại Khóa | Mô Tả Ý Nghĩa |
    | :--- | :--- | :--- | :--- | :--- |
    | `Dim_Date` | `date_key` | INTEGER | Primary Key | Khóa ngày định dạng YYYYMMDD |
    | `Dim_Date` | `market_phase` | VARCHAR | Attributes | Phân loại giai đoạn thị trường (Khủng hoảng 2008, 2022, Phục hồi...) |
    | `Dim_Sector` | `sector_group` | VARCHAR | Attributes | Phân loại nhóm ngành (`Defensive`, `Cyclical`, `Growth`) |
    | `Dim_Ticker` | `ticker` | VARCHAR | Attributes | Mã chứng khoán (VNM, FPT, HPG...) |
    | `Fact_Daily_Stock_Price` | `close` | REAL | Measure | Giá đóng cửa phiên giao dịch |
    | `Fact_Daily_Stock_Price` | `max_drawdown_20d` | REAL | Measure | Mức sụt giảm tối đa 20 phiên (%) |
    """)
