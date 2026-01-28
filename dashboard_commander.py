import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import time
import os
import sys
import subprocess
import psutil
from datetime import datetime

# ==============================================================================
# 1. ESTÉTICA Y CONFIGURACIÓN "TECH"
# ==============================================================================
st.set_page_config(page_title="AETHER REAL-TIME", layout="wide", page_icon="📈")

st.markdown("""
<style>
    /* Fondo Azul Medianoche con profundidad */
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    
    /* Contenedores con efecto cristal */
    [data-testid="stMetric"] {
        background: rgba(22, 27, 34, 0.8);
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Números que "brillan" */
    [data-testid="stMetricValue"] { color: #58a6ff !important; font-family: 'JetBrains Mono', monospace; }
    
    /* Terminal de Logs Estilizada */
    .terminal-box {
        background-color: #010409;
        border: 1px solid #30363d;
        color: #8b949e;
        font-family: 'Consolas', monospace;
        padding: 15px;
        border-radius: 8px;
        height: 350px;
        overflow-y: auto;
    }
    
    /* Títulos Neón */
    h1, h2, h3 { color: #adbac7; letter-spacing: -1px; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "data/market_memory.db"
LOG_FILE = "bot_logs.txt"

# ==============================================================================
# 2. MOTOR DE DATOS EN VIVO (ULTRA-FAST)
# ==============================================================================
def get_live_data():
    if not os.path.exists(DB_PATH): return None, None, None, None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=0.1)
        # 1. Precios y Volatilidad (Últimas 50 velas)
        df_m = pd.read_sql("SELECT * FROM market_metrics ORDER BY timestamp DESC LIMIT 50", conn)
        # 2. IA y Confianza
        df_a = pd.read_sql("SELECT * FROM ai_predictions ORDER BY timestamp DESC LIMIT 1", conn)
        # 3. Datos de Cuenta (Capital/Equity)
        df_acc = pd.read_sql("SELECT * FROM account_metrics ORDER BY timestamp DESC LIMIT 1", conn)
        # 4. Trades
        df_t = pd.read_sql("SELECT * FROM trade_history ORDER BY close_time DESC LIMIT 10", conn)
        conn.close()
        return df_m, df_a, df_acc, df_t
    except:
        return None, None, None, None

# ==============================================================================
# 3. INTERFAZ DE COMANDO ACTIVA
# ==============================================================================

# Barra Superior (Ticker de Símbolos)
ticker_placeholder = st.empty()

# Bloque Principal de Métricas
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
p_cap = m_col1.empty() # Capital
p_pnl = m_col2.empty() # PnL
p_prc = m_col3.empty() # Precio
p_vol = m_col4.empty() # Volatilidad
p_cnf = m_col5.empty() # Confianza

st.divider()

# Gráfico y Logs
c_chart, c_logs = st.columns([2, 1])
chart_placeholder = c_chart.empty()
logs_placeholder = c_logs.empty()

# ==============================================================================
# 4. LOOP INFINITO DE ACTUALIZACIÓN (SIN PARPADEO)
# ==============================================================================
while True:
    df_m, df_a, df_acc, df_t = get_live_data()
    
    if df_m is not None and not df_m.empty:
        # --- 1. ACTUALIZAR MÉTRICAS ---
        last_m = df_m.iloc[0]
        
        equity = df_acc.iloc[0]['equity'] if df_acc is not None and not df_acc.empty else 10000.0
        pnl_session = df_t['profit'].sum() if df_t is not None and not df_t.empty else 0.0
        
        p_cap.metric("CAPITAL (EQUITY)", f"${equity:,.2f}")
        p_pnl.metric("PNL SESIÓN", f"${pnl_session:.2f}", delta=f"{pnl_session:.2f}")
        p_prc.metric("XAUUSD LIVE", f"{last_m['close']:.2f}")
        p_vol.metric("VOLATILIDAD", f"{last_m.get('volatility', 0):.5f}")
        
        conf = df_a.iloc[0]['confidence'] * 100 if df_a is not None and not df_a.empty else 0.0
        p_cnf.metric("CONFIANZA IA", f"{conf:.1f}%", delta="SINCRO" if conf > 50 else "DÉBIL")

        # --- 2. ACTUALIZAR GRÁFICO ---
        fig = go.Figure(data=[go.Candlestick(
            x=df_m['timestamp'], open=df_m['open'], high=df_m['high'], low=df_m['low'], close=df_m['close'],
            increasing_line_color='#3fb950', decreasing_line_color='#f85149'
        )])
        fig.update_layout(
            height=450, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis_rangeslider_visible=False, font=dict(color="#8b949e"),
            yaxis=dict(side="right", gridcolor="#21262d")
        )
        chart_placeholder.plotly_chart(fig, use_container_width=True)

    # --- 3. ACTUALIZAR LOGS ---
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-30:]
            log_content = "".join([f"<div>{line}</div>" for line in lines])
            logs_placeholder.markdown(f"<div class='terminal-box'>{log_content}</div>", unsafe_allow_html=True)

    time.sleep(1) # Frecuencia de 1Hz