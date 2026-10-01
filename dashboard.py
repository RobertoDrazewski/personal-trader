"""
dashboard.py
Panel visual de Puma-Code Trading Agent.
"""
import os
import base64
from datetime import datetime, timezone

import pandas as pd
import psycopg2
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from PIL import Image

from config import Config
from logger_db import init_db, get_state, set_state, delete_state, _dsn
from broker_alpaca import AlpacaBroker
from strategy import compute_signal

APP_TITLE = "Puma-Code Trading Agent"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

try:
    page_icon_img = Image.open(os.path.join(STATIC_DIR, "favicon.png"))
except Exception:
    page_icon_img = "🤖"

st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon_img)

# ---------- Metadatos para "Agregar a pantalla de inicio" (iOS/Android) ----------
st.markdown("""
<link rel="apple-touch-icon" href="/app/static/apple-touch-icon.png">
<link rel="icon" type="image/png" href="/app/static/favicon.png">
<link rel="manifest" href="/app/static/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="PC Trading">
<meta name="theme-color" content="#0B1220">
""", unsafe_allow_html=True)

# ---------- Estilo: marca Puma Code + mobile-friendly ----------
st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem; padding-left: 1rem; padding-right: 1rem;}
    [data-testid="stMetricValue"] {font-size: 1.3rem;}
    [data-testid="stMetricLabel"] {font-size: 0.78rem; opacity: 0.85;}
    h1 {font-size: 1.6rem !important;}
    .pc-header {
        display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
        margin-bottom: 1rem; padding: 18px 22px;
        background: linear-gradient(135deg, rgba(192,138,78,0.10), rgba(79,209,232,0.08));
        border: 1px solid rgba(255,255,255,0.08); border-radius: 14px;
    }
    .pc-header img {height: 64px; width: auto; object-fit: contain; flex-shrink: 0;}
    .pc-header-text {display: flex; flex-direction: column; gap: 2px;}
    .pc-header h1 {margin: 0; font-size: 1.7rem !important; line-height: 1.15;
                    background: linear-gradient(90deg, #D9A05B, #4FD1E8);
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
    .pc-header .pc-subtitle {margin: 0; font-size: 0.85rem; color: #9FB0C3; letter-spacing: 0.3px;}
    @media (max-width: 640px) {
        .pc-header {padding: 14px 16px; gap: 14px;}
        .pc-header img {height: 46px;}
        .pc-header h1 {font-size: 1.2rem !important;}
        .pc-header .pc-subtitle {font-size: 0.72rem;}
        [data-testid="stMetricValue"] {font-size: 1.1rem;}
    }
</style>
""", unsafe_allow_html=True)

init_db()

# --- Contraseña simple ---
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        try:
            st.image(os.path.join(STATIC_DIR, "header_logo.png"), width=90)
        except Exception:
            pass
        st.title(APP_TITLE)
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if pwd == APP_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()


def load_table(query: str) -> pd.DataFrame:
    conn = psycopg2.connect(_dsn())
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


@st.cache_resource
def get_broker():
    return AlpacaBroker()


def logo_b64():
    try:
        with open(os.path.join(STATIC_DIR, "header_logo.png"), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# =========================================================================
# ENCABEZADO
# =========================================================================
kill_active = get_state("kill_switch") == "active"
logo64 = logo_b64()
logo_html = f'<img src="data:image/png;base64,{logo64}">' if logo64 else "🤖"
st.markdown(
    f'<div class="pc-header">{logo_html}'
    f'<div class="pc-header-text"><h1>{APP_TITLE}</h1>'
    f'<p class="pc-subtitle">Panel en vivo — Paper Trading · Alpaca</p></div></div>',
    unsafe_allow_html=True,
)

if kill_active:
    st.error("🛑 DETENIDO (kill switch activo)")
else:
    st.success("🟢 Operando normalmente")

equity_df = load_table("SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT 500")

m1, m2, m3, m4 = st.columns(4)
if not equity_df.empty:
    last = equity_df.iloc[0]
    m1.metric("Equity", f"${last['equity']:,.2f}", f"{last['daily_pl_pct']*100:.2f}% hoy",
               help="El valor total de tu cuenta ahora: efectivo + lo que valen tus posiciones abiertas.")
    m2.metric("P&L del día", f"${(last['equity'] - equity_df.iloc[-1]['equity']):,.2f}" if len(equity_df) > 1 else "$0.00",
               help="Profit & Loss: cuánto ganaste o perdiste hoy, en dólares.")
    m3.metric("Drawdown", f"{last['drawdown_pct']*100:.2f}%",
               help="Caída desde el punto más alto que alcanzó tu cuenta.")
else:
    m1.metric("Equity", "sin datos")
m4.metric("Límite drawdown", f"{Config.MAX_DRAWDOWN_PCT*100:.0f}%", help="Kill switch automático si se supera este %.")

st.divider()

tab_resumen, tab_graficos, tab_ops, tab_news, tab_screener, tab_bt, tab_glosario, tab_control = st.tabs([
    "📊 Resumen", "🕯️ Gráficos", "💰 Operaciones", "📰 Noticias",
    "🧭 Screener", "🧪 Backtest", "📖 Glosario", "⚙️ Control"
])

with tab_resumen:
    left, right = st.columns([2, 1])
    with left:
        if not equity_df.empty:
            chart_df = equity_df.sort_values("id").copy()
            chart_df["ts_dt"] = pd.to_datetime(chart_df["ts"])

            range_label = st.radio(
                "Rango", ["1D", "1M", "1Y", "Todo"], horizontal=True, label_visibility="collapsed", index=0,
            )
            now = chart_df["ts_dt"].max()
            if range_label == "1D":
                cutoff = now - pd.Timedelta(days=1)
            elif range_label == "1M":
                cutoff = now - pd.Timedelta(days=30)
            elif range_label == "1Y":
                cutoff = now - pd.Timedelta(days=365)
            else:
                cutoff = chart_df["ts_dt"].min()
            view_df = chart_df[chart_df["ts_dt"] >= cutoff]
            if view_df.empty:
                view_df = chart_df

            current_val = view_df["equity"].iloc[-1]
            start_val = view_df["equity"].iloc[0]
            pct_change = ((current_val - start_val) / start_val * 100) if start_val else 0
            pct_color = "#22c55e" if pct_change >= 0 else "#ef4444"
            pct_sign = "+" if pct_change >= 0 else ""

            st.markdown(f"""
                <div style="display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;">
                    <span style="font-size:1.9rem; font-weight:700;">$ {current_val:,.2f}</span>
                    <span style="font-size:1.1rem; font-weight:600; color:{pct_color};">{pct_sign}{pct_change:.2f}%</span>
                </div>
                <div style="color:#9FB0C3; font-size:0.82rem; margin-bottom:6px;">
                    {view_df['ts_dt'].iloc[-1].strftime('%d %b %Y, %H:%M UTC')}
                </div>
            """, unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=view_df["ts_dt"], y=view_df["equity"], mode="lines", fill="tozeroy",
                line=dict(color="#E8A33D", width=2.2), fillcolor="rgba(232,163,61,0.14)",
                hovertemplate="$%{y:,.2f}<extra></extra>",
            ))
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=10),
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=10, color="#9FB0C3")),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)", griddash="dot",
                           tickprefix="$", tickformat="~s", tickfont=dict(size=10, color="#9FB0C3")),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Todavía no hay datos de equity.")
    with right:
        st.subheader("Cartera")
        try:
            positions = get_broker().get_open_positions()
        except Exception as e:
            positions = []
            st.caption(f"No se pudo consultar Alpaca: {e}")
        if positions:
            pie_df = pd.DataFrame([{"symbol": p.symbol, "value": float(p.market_value)} for p in positions])
            fig_pie = px.pie(pie_df, values="value", names="symbol", hole=0.45)
            fig_pie.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                                   legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sin posiciones abiertas (100% en efectivo).")

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔔 Última acción")
        last_order = load_table("SELECT * FROM orders ORDER BY id DESC LIMIT 1")
        if not last_order.empty:
            o = last_order.iloc[0]
            side_label = {"buy": "🟢 COMPRÓ", "sell": "🔴 VENDIÓ", "trailing_stop_sell": "🛡️ Protegió"}.get(o["side"], o["side"])
            st.markdown(f"**{side_label} {int(o['qty'])} de {o['symbol']}**")
            st.caption(f"Motivo: {o['reason']}")
            st.caption(f"Cuándo: {o['ts']}")
        else:
            st.info("Todavía no hizo ninguna operación.")
    with col_b:
        st.subheader("🔮 ¿Qué evalúa ahora?")
        try:
            broker = get_broker()
            rows = []
            for sym in Config.SYMBOLS[:8]:
                try:
                    df = broker.get_recent_bars(sym, Config.TIMEFRAME_MINUTES, Config.LOOKBACK_BARS)
                    res = compute_signal(df)
                    rows.append({"Símbolo": sym, "Señal": res["signal"], "Motivo": res.get("reason", "")})
                except Exception:
                    rows.append({"Símbolo": sym, "Señal": "error", "Motivo": "no se pudo evaluar"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(f"Primeros 8 de {len(Config.SYMBOLS)} símbolos.")
        except Exception as e:
            st.caption(f"No se pudo evaluar: {e}")

with tab_graficos:
    st.subheader("Elegí un símbolo")
    chosen = st.selectbox("Símbolo", Config.SYMBOLS, index=0)
    if chosen:
        try:
            broker = get_broker()
            df = broker.get_recent_bars(chosen, Config.TIMEFRAME_MINUTES, max(Config.LOOKBACK_BARS, 100))
            if df is not None and not df.empty:
                sma_fast = df["close"].rolling(10).mean()
                sma_slow = df["close"].rolling(30).mean()
                delta = df["close"].diff()
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                rsi = 100 - (100 / (1 + avg_gain / avg_loss.replace(0, 1e-10)))

                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                                              name=chosen, increasing_line_color="#22c55e", decreasing_line_color="#ef4444"))
                fig.add_trace(go.Scatter(x=df.index, y=sma_fast, line=dict(color="#60a5fa", width=1.3), name="SMA 10"))
                fig.add_trace(go.Scatter(x=df.index, y=sma_slow, line=dict(color="#f59e0b", width=1.3), name="SMA 30"))
                fig.update_layout(height=420, margin=dict(l=5, r=5, t=30, b=10), xaxis_rangeslider_visible=False,
                                   template="plotly_dark", title=f"{chosen} — {Config.TIMEFRAME_MINUTES}min",
                                   legend=dict(orientation="h", y=1.08))
                st.plotly_chart(fig, use_container_width=True)

                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=df.index, y=rsi, line=dict(color="#a78bfa", width=1.3), name="RSI"))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color="#ef4444")
                fig_rsi.add_hline(y=30, line_dash="dot", line_color="#22c55e")
                fig_rsi.update_layout(height=160, margin=dict(l=5, r=5, t=10, b=10), template="plotly_dark", yaxis_range=[0, 100])
                st.plotly_chart(fig_rsi, use_container_width=True)

                result = compute_signal(df)
                st.info(f"**Señal: {result['signal'].upper()}** — {result.get('reason', '')}")
            else:
                st.warning("No se pudieron traer datos.")
        except Exception as e:
            st.error(f"Error: {e}")

with tab_ops:
    st.subheader("Historial de órdenes")
    orders_df = load_table("SELECT ts, symbol, side, qty, status, reason FROM orders ORDER BY id DESC LIMIT 100")
    if not orders_df.empty:
        side_counts = orders_df["side"].value_counts().reset_index()
        side_counts.columns = ["tipo", "cantidad"]
        col1, col2 = st.columns([1, 2])
        with col1:
            fig_pie2 = px.pie(side_counts, values="cantidad", names="tipo", hole=0.45)
            fig_pie2.update_layout(height=260, template="plotly_dark", legend=dict(orientation="h", y=-0.15))
            st.plotly_chart(fig_pie2, use_container_width=True)
        with col2:
            st.caption("buy = compra | sell = venta | trailing_stop_sell = protección puesta")
            st.dataframe(orders_df, use_container_width=True, hide_index=True)
    else:
        st.caption("Todavía no se ejecutó ninguna orden.")

with tab_news:
    st.subheader("📰 Noticias evaluadas")
    news_events = load_table("SELECT ts, message FROM events WHERE message LIKE '%noticia%' ORDER BY id DESC LIMIT 30")
    if not news_events.empty:
        st.dataframe(news_events, use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no se registró ninguna noticia.")

with tab_screener:
    st.subheader("🧭 Screener")
    DEFAULT_UNIVERSE = (
        "AAPL,MSFT,GOOGL,NVDA,TSLA,AMZN,META,XOM,CVX,COP,SLB,OXY,"
        "CAT,DE,HON,GE,BA,ALB,SQM,LAC,RIO,YPF,GGAL,PAM,BMA,VIST,MELI,GLOB,SPY,QQQ,DIA"
    )
    universe_input = st.text_area("Símbolos candidatos", value=DEFAULT_UNIVERSE, height=80)
    if st.button("🔍 Escanear ahora"):
        candidate_symbols = [s.strip().upper() for s in universe_input.split(",") if s.strip()]
        progress = st.progress(0, text="Escaneando...")
        broker = get_broker()
        scan_results = []
        for i, sym in enumerate(candidate_symbols):
            try:
                df = broker.get_recent_bars(sym, Config.TIMEFRAME_MINUTES, Config.LOOKBACK_BARS)
                result = compute_signal(df)
                result["symbol"] = sym
            except Exception as e:
                result = {"symbol": sym, "signal": "error", "reason": str(e)}
            scan_results.append(result)
            progress.progress((i + 1) / len(candidate_symbols), text=f"Escaneando... {sym}")
        progress.empty()
        scan_df = pd.DataFrame(scan_results)
        order = {"buy": 0, "sell": 1, "hold": 2, "error": 3}
        scan_df["_order"] = scan_df["signal"].map(order).fillna(9)
        scan_df = scan_df.sort_values("_order").drop(columns="_order")
        buys = scan_df[scan_df["signal"] == "buy"]
        if not buys.empty:
            st.success(f"🟢 Señal de compra: {', '.join(buys['symbol'])}")
        else:
            st.info("Ningún símbolo da señal de compra ahora.")
        cols_to_show = [c for c in ["symbol", "signal", "reason", "sma_fast", "sma_slow", "rsi", "last_close"] if c in scan_df.columns]
        st.dataframe(scan_df[cols_to_show], use_container_width=True, hide_index=True)
        if not buys.empty:
            st.code(",".join(list(dict.fromkeys(Config.SYMBOLS + list(buys["symbol"])))), language=None)

with tab_bt:
    st.subheader("🧪 Backtesting")
    try:
        bt_results = load_table("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 20")
    except Exception:
        bt_results = pd.DataFrame()
    if not bt_results.empty:
        st.dataframe(bt_results, use_container_width=True, hide_index=True)
    else:
        st.caption("Todavía no corriste ningún backtest.")
    st.divider()
    st.subheader("🎛️ Optimización")
    try:
        opt_results = load_table(
            "SELECT symbol, sma_fast, sma_slow, rsi_buy_max, trailing_stop_pct, num_trades, "
            "win_rate, total_return_pct, max_drawdown_pct, score FROM optimize_results ORDER BY score DESC LIMIT 15"
        )
        if not opt_results.empty:
            st.dataframe(opt_results, use_container_width=True, hide_index=True)
        else:
            st.caption("Todavía no corriste el optimizador.")
    except Exception:
        st.caption("Todavía no corriste el optimizador.")

with tab_glosario:
    st.subheader("📖 Glosario")
    glossary = [
        ("Equity", "El valor total de tu cuenta: efectivo + lo que valen tus posiciones abiertas."),
        ("P&L (Profit & Loss)", "Ganancia o pérdida en dólares."),
        ("Drawdown", "Cuánto cayó tu cuenta desde su punto más alto."),
        ("SMA (Media Móvil Simple)", "Promedio del precio de cierre de los últimos N períodos."),
        ("Cruce alcista", "La media rápida cruza por encima de la lenta — señal de tendencia hacia arriba."),
        ("Cruce bajista", "La media rápida cruza por debajo de la lenta — señal de reversión a la baja."),
        ("RSI", "Mide 0-100 qué tan sobrecomprado/sobrevendido está un activo. >70 sobrecomprado, <30 sobrevendido."),
        ("Trailing Stop", "Orden de venta que sube con el precio y nunca baja — protege ganancias."),
        ("Kill switch", "Interruptor de emergencia que frena todas las operaciones nuevas."),
        ("Paper trading", "Operar con dinero simulado, precios reales."),
        ("Win rate", "% de operaciones cerradas en ganancia."),
        ("Timeframe", "Tamaño de cada vela de precio — no es el horario de mercado."),
        ("Buy & Hold", "Comprar y no vender nunca — referencia para medir si una estrategia activa vale la pena."),
        ("ADR", "Certificado de acción extranjera cotizando en dólares en EEUU."),
        ("ETF", "Fondo que agrupa muchos activos en un solo papel (ej. SPY = S&P 500)."),
    ]
    for term, definition in glossary:
        with st.expander(f"**{term}**"):
            st.write(definition)

with tab_control:
    st.subheader("Control manual")
    kcol1, kcol2 = st.columns(2)
    with kcol1:
        if not kill_active and st.button("🛑 Activar kill switch"):
            set_state("kill_switch", "active")
            st.rerun()
    with kcol2:
        if kill_active and st.button("▶️ Desactivar kill switch"):
            delete_state("kill_switch")
            st.rerun()
    st.divider()
    st.subheader("📋 Log de eventos")
    events_df = load_table("SELECT ts, level, message FROM events ORDER BY id DESC LIMIT 100")
    if not events_df.empty:
        st.dataframe(events_df, use_container_width=True, hide_index=True)
    else:
        st.caption("Sin eventos todavía.")

st.caption(f"Actualizado: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} — recargá para refrescar.")
