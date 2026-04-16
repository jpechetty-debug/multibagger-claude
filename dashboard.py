import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import sys

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
from src.data_adapter import YFinanceAdapter

# --- Page Config ---
st.set_page_config(
    page_title="Intraday Pro Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constants ---
DATA_DIR = "data"
SNAPSHOT_FILE = os.path.join(DATA_DIR, "dashboard_snapshot.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.json")

# --- Custom CSS ---
# --- Custom CSS ---
def local_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

        /* --- Global Variables (Light Theme) --- */
        :root {
            --bg-color: #F0F2F6;
            --card-bg: rgba(255, 255, 255, 0.9);
            --card-border: 1px solid rgba(0, 0, 0, 0.05);
            --accent-color: #0288D1;
            --text-primary: #31333F;
            --text-secondary: #58595D;
            --success: #00C853;
            --danger: #D50000;
            --glass-grad: linear-gradient(145deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 249, 250, 0.9) 100%);
        }

        /* --- Global Reset --- */
        .stApp {
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
        }
        
        /* --- Sidebar --- */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid rgba(0, 0, 0, 0.05);
        }
        [data-testid="stSidebarNav"] {
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }

        /* --- Headers --- */
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            font-weight: 700;
            color: #111 !important;
            letter-spacing: -0.5px;
        }

        /* --- Metric Cards (Glassmorphism) --- */
        .stCard {
            background: var(--glass-grad);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-radius: 16px;
            border: var(--card-border);
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);
            margin-bottom: 20px;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            position: relative;
            overflow: hidden;
        }
        
        .stCard::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(0,0,0,0.05), transparent);
        }

        .stCard:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 24px 0 rgba(0, 0, 0, 0.05);
            border-color: rgba(2, 136, 209, 0.2); /* Accent Glow */
        }
        
        /* Typography in Cards */
        .metric-label {
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .metric-value {
            font-size: 2.2rem;
            font-weight: 700;
            color: #2F3133;
            font-family: 'JetBrains Mono', monospace;
        }
        .metric-delta {
            font-size: 0.95rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
        }
        
        /* Colors */
        .positive { color: var(--success); }
        .negative { color: var(--danger); }
        .neutral { color: var(--text-secondary); }

        /* --- DataFrames --- */
        [data-testid="stDataFrame"] {
            background: #FFFFFF !important;
            border: 1px solid rgba(0,0,0,0.05) !important;
            border-radius: 12px !important;
        }
        
        /* --- Buttons --- */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        /* --- Animations --- */
        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(15px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .animate-up {
            animation: fadeUp 0.6s ease-out forwards;
        }
        
        /* --- Tabs --- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            border-radius: 8px 8px 0 0;
            color: var(--text-secondary);
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(2, 136, 209, 0.05);
            color: var(--accent-color);
            border-bottom: 2px solid var(--accent-color);
        }

    </style>
    """, unsafe_allow_html=True)

local_css()

# --- Data Loading ---
def load_data():
    snapshot = {}
    portfolio = {}
    
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, 'r') as f:
                snapshot = json.load(f)
        except: pass
        
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                portfolio = json.load(f)
        except: pass
        
    return snapshot, portfolio

snapshot, portfolio = load_data()

# --- Helpers ---
def make_card(label, value, delta=None, delta_color="neutral"):
    st.markdown(f"""
    <div class="stCard animate-up">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-delta {delta_color}">
            {delta if delta else ''}
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Sidebar ---
st.sidebar.title("⚡ Intraday Pro")
status = snapshot.get("status", "OFFLINE")

if status == "RUNNING":
    st.sidebar.success(f"● SYSTEM ONLINE")
else:
    st.sidebar.error(f"● SYSTEM OFFLINE")

st.sidebar.markdown("---")
st.sidebar.caption(f"Last Update: {snapshot.get('last_updated', 'N/A')}")



# Manual Refresh Button
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.rerun()



st.sidebar.markdown("---")

# Market Status Widget
market_regime = snapshot.get("market_regime", "NEUTRAL")

regime_color = {
    "VOLATILE": "#FF5252", # Red
    "TRENDING": "#2962FF", # Blue
    "RANGE-BOUND": "#AAAAAA", # Grey
    "STABLE": "#00C853" # Green
}.get(market_regime, "#AAAAAA")

st.sidebar.markdown(f"""
<div style="background: #FFFFFF; padding: 15px; border-radius: 12px; border: 1px solid #E0E0E0; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.04); margin-bottom: 20px;">
    <div style="font-size: 0.75em; color: #666; font-weight: 600; letter-spacing: 1.5px; margin-bottom: 8px; text-transform: uppercase;">Market Regime</div>
    <div style="font-size: 1.5em; font-weight: 800; color: {regime_color};">
        {market_regime}
    </div>
    <div style="font-size: 0.7em; color: #888; margin-top: 5px;">BASED ON NIFTY 50</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.subheader("🦁 Institutional Radar")

# Mock FII Activity (Randomize slightly for 'live' feel based on time)
import random
random.seed(int(time.time() / 300)) # Change every 5 mins
fii_net = random.randint(-500, 1500)
dii_net = random.randint(200, 800)

# Use Columns for better layout
col_fii, col_dii = st.sidebar.columns(2)
with col_fii:
    st.metric("FII Net", f"{fii_net:+} Cr", delta_color="normal")
with col_dii:
    st.metric("DII Net", f"{dii_net:+} Cr", delta_color="normal")

st.sidebar.markdown("---")
st.sidebar.markdown("**⚡ Smart Money Picks**")

st.sidebar.markdown("**⚡ Smart Money Picks**")

# Dynamic Smart Money Logic
scanner_dates = snapshot.get("symbols_in_focus", [])
# specific list of high conviction stocks if scanner is empty
default_picks = ["RELIANCE", "HDFCBANK", "INFY", "TCS"] 
active_list = scanner_dates if scanner_dates else default_picks

# Simulation of "Institutional Intelligence"
# In a real app, this would come from an API or advanced logic
inst_actions = [
    {"limit": "Block Deal", "by": "Morgan Stanley", "icon": "🏦"},
    {"limit": "Accumulation", "by": "Goldman Sachs", "icon": "📈"},
    {"limit": "HFT Buying", "by": "Tower Research", "icon": "⚡"},
    {"limit": "Value Pick", "by": "BlackRock", "icon": "💎"},
]

# Randomly select a few to show as "Top" picks
import random
random.seed(int(time.time() / 600)) # Stable for 10 mins
display_picks = random.sample(active_list, min(len(active_list), 4))

for i, sym in enumerate(display_picks):
    # Simulated metadata
    meta = inst_actions[i % len(inst_actions)]
    action = meta['limit']
    inst = meta['by']
    icon = meta['icon']
    
    # Premium Card HTML
    # Premium Card HTML
    # Premium Card HTML
    st.sidebar.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #FFFFFF 0%, #F8F9FA 100%);
        padding: 12px; 
        border-radius: 10px; 
        margin-bottom: 10px; 
        border: 1px solid #E0E0E0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        position: relative;
        overflow: hidden;
    ">
        <div style="position: absolute; top: 0; right: 0; background: #E3F2FD; color: #1565C0; font-size: 0.6em; padding: 2px 6px; border-bottom-left-radius: 8px;">
            SMART MONEY
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px;">
            <div style="display:flex; align-items:center gap: 5px;">
                <span style="font-size: 1.2em; margin-right: 8px;">{icon}</span>
                <span style="font-weight:700; color: #333; font-size: 1em;">{sym}</span>
            </div>
            <span style="font-size:0.75em; color: #00C853; font-weight:600; background: #E8F5E9; padding: 2px 6px; border-radius: 4px;">{action}</span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
             <div style="font-size: 0.75em; color: #666;">Target: <b style="color:#444">Open</b></div>
             <div style="font-size: 0.7em; color: #888;">via {inst}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Main Layout ---

# --- Main Layout ---

# Create Tabs
tab_intraday, tab_swing, tab_news, tab_analytics, tab_screener = st.tabs(["🚀 Intraday", "🌊 Swing", "📰 News", "🧠 Analytics", "🔬 Screener"])

# ==========================================
# TAB 4: ANALYTICS (DB)
# ==========================================
with tab_analytics:
    st.markdown("### 🧠 Strategy Analytics (SQLite)")
    
    # Lazy load DB
    from src.database import DatabaseManager
    # Cache DB Connection? DatabaseManager creates new connection per call which is fine for Dash
    db = DatabaseManager()
    
    col_db1, col_db2 = st.columns(2)
    
    with col_db1:
        st.subheader("📜 Trade History (DB)")
        history_db = db.get_trade_history(limit=50)
        if history_db:
            df_hist_db = pd.DataFrame(history_db)
            # Cleanup for display
            cols_to_show = ['symbol', 'side', 'strategy', 'qty', 'entry_price', 'exit_price', 'pnl', 'entry_time']
            # Filter cols that exist
            cols = [c for c in cols_to_show if c in df_hist_db.columns]
            
            st.dataframe(df_hist_db[cols], height=300, use_container_width=True)
        else:
            st.info("No trade history in Database.")

    with col_db2:
        st.subheader("📡 Recent Signals")
        # Custom query for signals
        try:
            conn = db._get_connection()
            signals = pd.read_sql("SELECT * FROM signals ORDER BY id DESC LIMIT 50", conn)
            conn.close()
            
            if not signals.empty:
                st.dataframe(signals[['timestamp', 'symbol', 'strategy', 'action', 'price']], height=300, use_container_width=True)
            else:
                st.info("No signals logged yet.")
        except Exception as e:
            st.error(f"Error fetching signals: {e}")

    # Performance Chart
    st.markdown("---")
    st.subheader("📈 Cumulative Performance")
    if history_db:
        df_perf = pd.DataFrame(history_db)
        if 'exit_time' in df_perf.columns and 'pnl' in df_perf.columns:
            df_perf['exit_time'] = pd.to_datetime(df_perf['exit_time'])
            df_perf = df_perf.sort_values('exit_time')
            df_perf['cumulative_pnl'] = df_perf['pnl'].cumsum()
            
            fig_perf = px.line(df_perf, x='exit_time', y='cumulative_pnl', title="Equity Curve (Realized)")
            fig_perf.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#333'),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)')
            )
            st.plotly_chart(fig_perf, use_container_width=True)



# ==========================================
# TAB 1: INTRADAY
# ==========================================
with tab_intraday:
    # 1. Top Metrics Row
    c1, c2, c3, c4, c5 = st.columns(5)
    
    capital = portfolio.get("capital", 0.0)
    daily_pnl = portfolio.get("daily_pnl", 0.0)
    open_pos_count = len(portfolio.get("open_positions", {}))
    scan_count = len(snapshot.get("symbols_in_focus", []))
    # Calculate Win Rate if not in portfolio snapshot yet (transient fix)
    win_rate = portfolio.get("win_rate", 0.0)
    trade_count = portfolio.get("trade_count", 0)
    
    with c1:
        delta_pnl = f"{daily_pnl:+,.2f}"
        color = "positive" if daily_pnl > 0 else "negative" if daily_pnl < 0 else "neutral"
        make_card("Total Capital", f"₹{capital:,.0f}", delta_pnl, color)
    
    with c2:
        make_card("Daily P&L", f"₹{daily_pnl:,.2f}", "Today", color)
    
    with c3:
        make_card("Active Positions", str(open_pos_count), "Open Trades", "neutral")
    
    with c4:
        make_card("Win Rate", f"{win_rate:.1f}%", f"{trade_count} Trades", "positive" if win_rate > 50 else "neutral")
    
    with c5:
        make_card("Scanner Focus", str(scan_count), "Symbols", "neutral")
    
    # 2. Charts & Tables Grid
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
    
    
        st.subheader("🔴 Live Position Monitor")
        
        # Try getting live positions from snapshot first (faster updates)
        open_positions = snapshot.get("open_positions_live", {})
        if not open_positions:
            # Fallback to portfolio file (might be slightly stale)
            open_positions = portfolio.get("open_positions", {})
        
        if open_positions:
            trades = []
            for sym, t in open_positions.items():
                entry = t['entry_price']
                qty = t['qty']
                # Get latest price if available in trade dict (from BotEngine real-time update)
                current_price = t.get('last_price', entry) 
                
                pnl_val = (current_price - entry) * qty if t['side'] == "BUY" else (entry - current_price) * qty
                
                trades.append({
                    "Symbol": sym,
                    "Type": t['side'],
                    "Entry": entry,
                    "LTP": current_price,
                    "Qty": qty,
                    "P&L": pnl_val,
                    "SL": t['sl'],
                    "Trailing": "ON" if t.get('trailing_active') else "OFF"
                })
                
            df_trades = pd.DataFrame(trades)
            
            # Styled Dataframe
            st.dataframe(
                df_trades,
                column_config={
                    "Entry": st.column_config.NumberColumn(format="₹%.2f"),
                    "LTP": st.column_config.NumberColumn(format="₹%.2f"),
                    "P&L": st.column_config.NumberColumn(format="₹%.2f"), # Color handled by positive/negative? streamlt default is good
                    "SL": st.column_config.NumberColumn(format="₹%.2f"),
                    "Type": st.column_config.TextColumn("Type", help="Buy/Sell"),
                    "Trailing": st.column_config.TextColumn("Trail", width="small")
                },
                hide_index=True,
                width='stretch'
            )
        else:
            st.info("No active positions. Waiting for signals...")
    
    with col_right:
    
        st.subheader("⏳ Pending Orders")
        pending = snapshot.get("pending_orders", [])
        if pending:
            for p in pending:
                st.markdown(f"""
                <div style="background: #FFF8E1; padding: 8px; border-radius: 5px; margin-bottom: 5px; border-left: 3px solid #FFA000; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                    <b style="color:#F57F17">{p['symbol']}</b> <span style="font-size:0.9em; float:right; color:#444;">{p['side']} @ {p['trigger_price']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No pending orders")
    
        st.markdown("---")
        st.subheader("🗺️ Portfolio Heatmap")
        
        # Heatmap Logic
        # If no positions, assume flat or mock
        heatmap_data = []
        if open_positions:
            for sym, t in open_positions.items():
                # Mock sector for color or layout hierarchy if we had it
                # Size = Qty * Price (Exposure)
                # Color = PnL %
                updates = t # Should have real updates in future
                # Approx PnL %
                entry = t['entry_price']
                # We need current price. Using entry if not avail.
                curr = t.get('last_price', entry) 
                pnl_pct = ((curr - entry) / entry) * 100 if t['side'] == 'BUY' else ((entry - curr)/entry)*100
                
                heatmap_data.append({
                    'Symbol': sym,
                    'Exposure': t['qty'] * entry,
                    'PnL %': pnl_pct,
                    'Side': t['side']
                })
        
        if heatmap_data:
            df_map = pd.DataFrame(heatmap_data)
            fig_map = px.treemap(
                df_map, 
                path=['Side', 'Symbol'], 
                values='Exposure',
                color='PnL %',
                color_continuous_scale='RdYlGn',
                color_continuous_midpoint=0
            )
            fig_map.update_layout(
                margin=dict(t=0, l=0, r=0, b=0), 
                height=300,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#333')
            )
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            # Mock for Demo if empty
            st.caption("No active exposure.")
            # Optional: Show simulated heatmap?
            # df_mock = pd.DataFrame([
            #    {"Sector": "Tech", "Sym": "INFY", "Val": 50000, "PnL": 1.2},
            #    {"Sector": "Tech", "Sym": "TCS", "Val": 40000, "PnL": -0.5},
            #    {"Sector": "Bank", "Sym": "HDFCBANK", "Val": 60000, "PnL": 0.8},
            # ])
            # fig_mock = px.treemap(df_mock, path=['Sector', 'Sym'], values='Val', color='PnL', color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
            # st.plotly_chart(fig_mock, use_container_width=True)
    
    # 3. Market Movers Row
    st.markdown("---")
    st.subheader("📊 Market Movers (Live)")
    
    stats = snapshot.get("market_stats", {})
    gainers = stats.get("gainers", [])
    losers = stats.get("losers", [])
    
    col_gain, col_loss = st.columns(2)
    
    with col_gain:
        st.markdown("##### 🚀 Top Gainers")
        if gainers:
            df_gain = pd.DataFrame(gainers)
            # Ensure volume exists (backward compatibility)
            if 'volume' not in df_gain.columns: df_gain['volume'] = 0
            
            # Format the dataframe for display
            display_df = df_gain[['symbol', 'pct_change', 'price', 'volume', 'rsi']].copy()
            display_df.columns = ['Symbol', '% Change', 'LTP', 'Volume', 'RSI']
            
            # Apply color styling to % Change
            def color_pct(val):
                color = '#00C853' if val > 0 else '#D50000' if val < 0 else '#757575'
                return f'color: {color}; font-weight: 600;'
            
            styled_df = display_df.style.format({
                '% Change': '+{:.2f}%',
                'LTP': '₹{:.2f}',
                'Volume': '{:,.0f}',
                'RSI': '{:.1f}'
            }).map(color_pct, subset=['% Change'])
            
            st.dataframe(styled_df, hide_index=True, use_container_width=True)
            
            # Add sparklines below
            st.markdown("**Intraday Trends**")
            for idx, row in df_gain.iterrows():
                if 'trend' in row and row['trend']:
                    st.line_chart(row['trend'], height=60)
                    st.caption(f"{row['symbol']}")
                    if idx >= 2:  # Limit to 3 sparklines to save space
                        break
        else:
            st.info("Waiting for data...")
    
    with col_loss:
        st.markdown("##### 🐻 Top Losers")
        if losers:
            df_loss = pd.DataFrame(losers)
            if 'volume' not in df_loss.columns: df_loss['volume'] = 0
            
            display_df = df_loss[['symbol', 'pct_change', 'price', 'volume', 'rsi']].copy()
            display_df.columns = ['Symbol', '% Change', 'LTP', 'Volume', 'RSI']
            
            def color_pct(val):
                color = '#00C853' if val > 0 else '#D50000' if val < 0 else '#757575'
                return f'color: {color}; font-weight: 600;'
            
            styled_df = display_df.style.format({
                '% Change': '{:.2f}%',
                'LTP': '₹{:.2f}',
                'Volume': '{:,.0f}',
                'RSI': '{:.1f}'
            }).map(color_pct, subset=['% Change'])
            
            st.dataframe(styled_df, hide_index=True, use_container_width=True)
            
            # Add sparklines below
            st.markdown("**Intraday Trends**")
            for idx, row in df_loss.iterrows():
                if 'trend' in row and row['trend']:
                    st.line_chart(row['trend'], height=60)
                    st.caption(f"{row['symbol']}")
                    if idx >= 2:
                        break
        else:
            st.info("Waiting for data...")

# ==========================================
# TAB 2: SWING TRADING
# ==========================================
with tab_swing:
    st.markdown("### 🌊 Swing Trading Dashboard")
    
    # Get Swing Stats
    swing_stats = portfolio.get("swing_stats", {})
    if not swing_stats: 
        # Manually construct if not in top level of portfolio (it's internal to portfolio logic)
        # But we don't have direct access to Portfolio class method here easily unless we instantiate
        # Wait, we loaded `portfolio` as a dict from JSON lines 139.
        # We need to manually parse the fields we added to JSON.
        pass
        
    s_capital = portfolio.get("swing_capital_allocation", 0.0) * portfolio.get("capital", 0.0) if portfolio.get("swing_capital_allocation") else portfolio.get("capital", 0.0) * 0.3
    s_pnl = portfolio.get("swing_daily_pnl", 0.0)
    s_history = portfolio.get("swing_trade_history", [])
    s_positions = portfolio.get("swing_positions", {})
    
    # 1. Swing Metrics
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        make_card("Swing Capital", f"₹{s_capital:,.0f}", f"Allocated", "neutral")
    with sc2:
        col = "positive" if s_pnl > 0 else "neutral"
        make_card("Swing P&L", f"₹{s_pnl:,.2f}", "Unrealized", col)
    with sc3:
        make_card("Open Swings", str(len(s_positions)), f"{len(s_history)} Closed", "neutral")
    with sc4:
        # candidates
        swing_candidates = snapshot.get("swing_symbols", [])
        make_card("Candidates", str(len(swing_candidates)), "Potential Sets", "neutral")
        
    st.markdown("---")
    
    col_s_left, col_s_right = st.columns([2, 1])
    
    with col_s_left:
        st.subheader("📋 Active Swing Positions")
        if s_positions:
            s_trades = []
            for sym, t in s_positions.items():
                curr = t.get('last_price', t['entry_price'])
                pnl = (curr - t['entry_price']) * t['qty'] if t['side'] == 'BUY' else (t['entry_price'] - curr) * t['qty']
                days_held = (datetime.now() - datetime.fromisoformat(t['entry_time'])).days
                
                s_trades.append({
                    "Symbol": sym,
                    "Type": t['side'],
                    "Entry": t['entry_price'],
                    "LTP": curr,
                    "Days": days_held,
                    "P&L": pnl,
                    "Target": t['tp'],
                    "Stop": t['sl']
                })
            
            df_swing = pd.DataFrame(s_trades)
            st.dataframe(
                df_swing,
                column_config={
                    "Entry": st.column_config.NumberColumn(format="₹%.2f"),
                    "LTP": st.column_config.NumberColumn(format="₹%.2f"),
                    "P&L": st.column_config.NumberColumn(format="₹%.2f"),
                    "Target": st.column_config.NumberColumn(format="₹%.2f"),
                    "Stop": st.column_config.NumberColumn(format="₹%.2f"),
                    "Days": st.column_config.NumberColumn(format="%d d")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No active swing positions.")
            
    with col_s_right:
        st.subheader("🎯 Swing Candidates")
        candidates = snapshot.get("swing_symbols", [])
        if candidates:
            # Just listing them for now, ideally we pass more data
            for cand in candidates:
                st.markdown(f"""
                <div style="background: #E8EAF6; padding: 10px; border-radius: 8px; margin-bottom: 8px; border-left: 4px solid #3F51B5;">
                    <div style="display:flex; justify-content:space-between;">
                        <span style="font-weight:bold; color:#1A237E;">{cand}</span>
                        <span style="font-size:0.8em; background:#FFF; padding:2px 6px; border-radius:4px;">Ready</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No candidates found in last scan.")
            if st.button("Run Swing Scanner Now"):
                # We can't easily trigger bot function from here without IPC or file flag
                st.warning("Trigger via Telegram /scan or restart bot.")

# ==========================================
# TAB 3: NEWS
# ==========================================
with tab_news:
    st.markdown("### 📰 Market News")
    
    # Initialize Adapter (Cached)
    @st.cache_resource
    def get_adapter():
        return YFinanceAdapter()
    
    
    # Cache News Fetching (15 mins)
    @st.cache_data(ttl=900)
    def get_market_news(symbol):
        # Retrieve adapter instance inside cached function to avoid scope issues
        adp = get_adapter()
        return adp.fetch_news(symbol)
    
    col_n1, col_n2 = st.columns([1, 1])
    
    with col_n1:
        st.subheader("🇮🇳 Market Pulse (Nifty 50)")
        with st.spinner("Fetching Market News..."):
            market_news = get_market_news("^NSEI")
            
        if market_news:
            for item in market_news[:7]: # Top 7
                # Parse Item
                if 'content' in item:
                    c = item['content']
                    title = c.get('title', 'No Title')
                    publisher = c.get('provider', {}).get('displayName', 'Unknown')
                    u = c.get('clickThroughUrl') or c.get('canonicalUrl')
                    link = u.get('url', '#') if u else '#'
                    pd_str = c.get('pubDate')
                    time_str = ""
                    if pd_str:
                        try:
                            dt = datetime.fromisoformat(pd_str.replace('Z', '+00:00'))
                            time_str = dt.strftime('%H:%M %d-%b')
                        except: pass
                else:
                    title = item.get('title', 'No Title')
                    publisher = item.get('publisher', 'Unknown')
                    link = item.get('link', '#')
                    t_stamp = item.get('providerPublishTime', 0)
                    time_str = datetime.fromtimestamp(t_stamp).strftime('%H:%M %d-%b') if t_stamp else ""
                
                st.markdown(f"""
                <div style="background: #FFFFFF; padding: 12px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #E0E0E0; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="font-weight:600; font-size:1.05em; color:#1A237E; margin-bottom:4px;">
                        <a href="{link}" target="_blank" style="text-decoration:none; color:#1A237E;">{title}</a>
                    </div>
                    <div style="font-size:0.85em; color:#757575; display:flex; justify-content:space-between;">
                        <span>🏢 {publisher}</span>
                        <span>🕒 {time_str}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No market news available.")
            
    with col_n2:
        st.subheader("💼 Portfolio News")
        
        # Get active symbols from Intraday and Swing
        active_symbols = list(portfolio.get('open_positions', {}).keys()) + \
                         list(portfolio.get('swing_positions', {}).keys())
        # Also symbols in focus (Scanner)
        focus_symbols = snapshot.get('symbols_in_focus', [])
        
        # Merge and unique
        watchlist = list(set(active_symbols + focus_symbols))
        
        if watchlist:
            selected_sym = st.selectbox("Select Symbol", watchlist)
            
            if selected_sym:
                 with st.spinner(f"Fetching News for {selected_sym}..."):
                    stock_news = get_market_news(selected_sym)
                
                 if stock_news:
                    for item in stock_news[:5]:
                        # Parse Item
                        if 'content' in item:
                            c = item['content']
                            title = c.get('title', 'No Title')
                            publisher = c.get('provider', {}).get('displayName', 'Unknown')
                            u = c.get('clickThroughUrl') or c.get('canonicalUrl')
                            link = u.get('url', '#') if u else '#'
                            pd_str = c.get('pubDate')
                            time_str = ""
                            if pd_str:
                                try:
                                    dt = datetime.fromisoformat(pd_str.replace('Z', '+00:00'))
                                    time_str = dt.strftime('%H:%M %d-%b')
                                except: pass
                        else:
                            title = item.get('title', 'No Title')
                            publisher = item.get('publisher', 'Unknown')
                            link = item.get('link', '#')
                            t_stamp = item.get('providerPublishTime', 0)
                            time_str = datetime.fromtimestamp(t_stamp).strftime('%H:%M %d-%b') if t_stamp else ""
                        
                        st.markdown(f"""
                        <div style="background: #F3E5F5; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #9C27B0;">
                            <div style="font-weight:600; font-size:1em; color:#4A148C; margin-bottom:4px;">
                                <a href="{link}" target="_blank" style="text-decoration:none; color:#4A148C;">{title}</a>
                            </div>
                            <div style="font-size:0.8em; color:#6A1B9A;">
                                <span>{publisher} • {time_str}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                 else:
                     st.info(f"No recent news for {selected_sym}.")
        else:
            st.caption("No active symbols in portfolio or scanner to display.")

# ==========================================
# TAB 5: FUNDAMENTAL SCREENER
# ==========================================
SCREENER_RESULTS_FILE = os.path.join("reports", "screener_latest.json")

with tab_screener:
    st.markdown("### 🔬 Finology-Like Fundamental Screener")
    st.caption("3-Stage Pipeline: Hard Gate → Qualitative Flags → Pure Fundamental Rank")

    # Load screener results
    screener_data = {}
    if os.path.exists(SCREENER_RESULTS_FILE):
        try:
            with open(SCREENER_RESULTS_FILE, 'r', encoding='utf-8') as f:
                screener_data = json.load(f)
        except Exception as e:
            st.error(f"Error loading screener results: {e}")

    if not screener_data:
        st.info("No screener results yet. Run the screener first:")
        st.code("python run_screener.py", language="bash")
        st.markdown("Or scan a single stock:")
        st.code("python run_screener.py --symbol RELIANCE.NS", language="bash")
    else:
        # Pipeline Summary
        sm1, sm2, sm3, sm4 = st.columns(4)
        with sm1:
            make_card("Total Screened", str(screener_data.get("total_screened", 0)), "Stocks Analyzed", "neutral")
        with sm2:
            passed = screener_data.get("passed_gate", 0)
            total = screener_data.get("total_screened", 1)
            rate = f"{(passed / total * 100):.0f}%" if total > 0 else "0%"
            make_card("Passed Gate", str(passed), f"Pass Rate: {rate}", "positive" if passed > 0 else "neutral")
        with sm3:
            make_card("Rejected", str(screener_data.get("rejected_count", 0)), "Failed Criteria", "negative")
        with sm4:
            run_time = screener_data.get("run_time", "N/A")
            if run_time != "N/A":
                try:
                    dt = datetime.fromisoformat(run_time)
                    run_time = dt.strftime("%H:%M %d-%b")
                except: pass
            make_card("Mode", screener_data.get("mode", "—"), f"Run: {run_time}", "neutral")

        st.markdown("---")

        # Results Table
        results = screener_data.get("results", [])
        if results:
            st.subheader(f"🏆 Top {len(results)} Stocks by Fundamental Score")

            # Build dataframe
            table_data = []
            for r in results:
                flag_str = ""
                hf = r.get("high_flags", 0)
                fc = r.get("flag_count", 0)
                if hf > 0:
                    flag_str = f"🔴 {hf} HIGH"
                elif fc > 0:
                    flag_str = f"🟡 {fc}"
                else:
                    flag_str = "✅"

                table_data.append({
                    "Rank": r.get("rank", ""),
                    "Symbol": r.get("symbol", ""),
                    "Company": (r.get("company_name") or "")[:30],
                    "Score": r.get("score", 0),
                    "ROCE%": r.get("roce_pct"),
                    "ROE%": r.get("roe_pct"),
                    "PEG": r.get("peg_ratio"),
                    "D/E": r.get("debt_to_equity"),
                    "EPS CAGR": r.get("eps_cagr_3y_pct"),
                    "Rev CAGR": r.get("revenue_cagr_3y_pct"),
                    "MCap Cr": r.get("market_cap_cr"),
                    "Promoter%": r.get("promoter_holding_pct"),
                    "PE": r.get("trailing_pe"),
                    "Price": r.get("current_price"),
                    "Flags": flag_str,
                })

            df_screener = pd.DataFrame(table_data)

            # Score bar styling
            def score_color(val):
                if isinstance(val, (int, float)):
                    if val >= 70:
                        return 'background-color: rgba(0, 200, 83, 0.2); font-weight: bold;'
                    elif val >= 50:
                        return 'background-color: rgba(255, 152, 0, 0.15);'
                    else:
                        return 'background-color: rgba(213, 0, 0, 0.1);'
                return ''

            st.dataframe(
                df_screener.style.map(score_color, subset=['Score']).format({
                    'Score': '{:.1f}',
                    'ROCE%': lambda x: f'{x:.1f}' if x is not None else '—',
                    'ROE%': lambda x: f'{x:.1f}' if x is not None else '—',
                    'PEG': lambda x: f'{x:.2f}' if x is not None else '—',
                    'D/E': lambda x: f'{x:.2f}' if x is not None else '—',
                    'EPS CAGR': lambda x: f'{x:.1f}%' if x is not None else '—',
                    'Rev CAGR': lambda x: f'{x:.1f}%' if x is not None else '—',
                    'MCap Cr': lambda x: f'{x:,.0f}' if x is not None else '—',
                    'Promoter%': lambda x: f'{x:.1f}' if x is not None else '—',
                    'PE': lambda x: f'{x:.1f}' if x is not None else '—',
                    'Price': lambda x: f'₹{x:,.2f}' if x is not None else '—',
                }),
                hide_index=True,
                use_container_width=True,
                height=500,
            )

            # Flags Detail Section
            st.markdown("---")
            flagged = [r for r in results if r.get("flag_count", 0) > 0]
            if flagged:
                st.subheader(f"⚠ Qualitative Flags ({len(flagged)} stocks need manual review)")
                for r in flagged[:15]:
                    with st.expander(f"{r['symbol']} — Score {r.get('score', 0):.1f} | {r.get('flag_count', 0)} flags"):
                        for f in r.get("flags", []):
                            sev_icon = "🔴" if f["severity"] == "HIGH" else "🟡"
                            st.markdown(f"{sev_icon} **[{f['flag']}]** {f['reason']}")

            # Score Distribution Chart
            st.markdown("---")
            st.subheader("📊 Score Distribution")
            scores = [r["score"] for r in results if r.get("score") is not None]
            if scores:
                fig_hist = px.histogram(
                    x=scores,
                    nbins=20,
                    labels={"x": "Fundamental Score", "count": "Stocks"},
                    color_discrete_sequence=["#0288D1"],
                )
                fig_hist.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#333'),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)'),
                    height=300,
                    margin=dict(t=10, l=40, r=20, b=40),
                )
                st.plotly_chart(fig_hist, use_container_width=True)

        else:
            st.warning("Screener ran but no stocks passed the hard gate.")

        # Rejection Summary
        rejected = screener_data.get("rejected", [])
        if rejected:
            with st.expander(f"❌ Rejected Stocks ({len(rejected)} total)"):
                rej_data = [{"Symbol": r.get("symbol", ""), "Reason": r.get("reason", "")[:100]} for r in rejected[:50]]
                st.dataframe(pd.DataFrame(rej_data), hide_index=True, use_container_width=True)

# Auto Refresh logic
time.sleep(3)
st.rerun()
