"""
dashboard.py
Panel visual. En Railway, es el start command del servicio "dashboard":
streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0

Lee la misma base Postgres que usa el agente (DATABASE_URL compartida
entre ambos servicios vía Railway) y consulta Alpaca en vivo con tus keys.
"""
import os
from datetime import datetime, timezone

import pandas as pd
import psycopg2
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from config import Config
from logger_db import init_db, get_state, set_state, delete_state, _dsn
from broker_alpaca import AlpacaBroker
from strategy import compute_signal

st.set_page_config(page_title="Agente de Trading — Puma Code", layout="wide", page_icon="🤖")
st.markdown("""
<style>
    .block-container {padding-top: 1.2rem; padding-bottom: 1rem;}
    [data-testid="stMetricValue"] {font-size: 1.4rem;}
</style>
""", unsafe_allow_html=True)

init_db()

# --- Contraseña simple: el dashboard queda accesible por un link público en
# Railway, así que protegemos con una password antes de mostrar nada. ---
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔒 Panel del Agente de Trading")
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


kill_active = get_state("kill_switch") == "active"

col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("🤖 Agente de Trading — Panel en vivo")
with col_status:
    if kill_active:
        st.error("🛑 DETENIDO (kill switch activo)")
    else:
        st.success("🟢 Operando normalmente")

equity_df = load_table("SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT 500")

m1, m2, m3, m4 = st.columns(4)
if not equity_df.empty:
    last = equity_df.iloc[0]
    m1.metric(
        "Equity (el valor total de tu cuenta ahora: efectivo + lo que valen tus posiciones abiertas)",
        f"${last['equity']:,.2f}", f"{last['daily_pl_pct']*100:.2f}% hoy",
    )
    m2.metric(
        "P&L del día (Profit & Loss: cuánto ganaste o perdiste hoy, en dólares)",
        f"${(last['equity'] - equity_df.iloc[-1]['equity']):,.2f}" if len(equity_df) > 1 else "$0.00",
    )
    m3.metric(
        "Drawdown (caída desde el punto más alto que alcanzó tu cuenta)",
        f"{last['drawdown_pct']*100:.2f}%",
    )
else:
    m1.metric("Equity", "sin datos")
m4.metric("Límite de drawdown (kill switch automático)", f"{Config.MAX_DRAWDOWN_PCT*100:.0f}%")

st.divider()

tab_resumen, tab_graficos, tab_ops, tab_news, tab_screener, tab_bt, tab_glosario, tab_control = st.tabs([
    "📊 Resumen", "🕯️ Gráficos por símbolo", "💰 Operaciones", "📰 Noticias",
    "🧭 Screener", "🧪 Backtest / Optimización", "📖 Glosario", "⚙️ Control"
])

with tab_resumen:
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Evolución del equity")
        if not equity_df.empty:
            chart_df = equity_df.sort_values("id")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=chart_df["ts"], y=chart_df["equity"], mode="lines", fill="tozeroy",
                line=dict(color="#22c55e" if chart_df["equity"].iloc[-1] >= chart_df["equity"].iloc[0] else "#ef4444", width=2),
                fillcolor="rgba(34,197,94,0.12)",
            ))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="USD", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Todavía no hay datos de equity.")

    with right:
        st.subheader("Distribución de tu cartera")
        try:
            positions = get_broker().get_open_positions()
        except Exception as e:
            positions = []
            st.caption(f"No se pudo consultar Alpaca: {e}")
        if positions:
            pie_df = pd.DataFrame([{"symbol": p.symbol, "value": float(p.market_value)} for p in positions])
            fig_pie = px.pie(pie_df, values="value", names="symbol", hole=0.45)
            fig_pie.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sin posiciones abiertas (100% en efectivo).")

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔔 Última acción del agente")
        last_order = load_table("SELECT * FROM orders ORDER BY id DESC LIMIT 1")
        if not last_order.empty:
            o = last_order.iloc[0]
            side_label = {"buy": "🟢 COMPRÓ", "sell": "🔴 VENDIÓ", "trailing_stop_sell": "🛡️ Puso protección en"}.get(o["side"], o["side"])
            st.markdown(f"**{side_label} {int(o['qty'])} de {o['symbol']}**")
            st.caption(f"Motivo: {o['reason']}")
            st.caption(f"Cuándo: {o['ts']}")
        else:
            st.info("Todavía no hizo ninguna operación.")

    with col_b:
        st.subheader("🔮 ¿Qué está evaluando ahora?")
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
            status_df = pd.DataFrame(rows)
            st.dataframe(status_df, use_container_width=True, hide_index=True)
            st.caption(f"Mostrando los primeros 8 de {len(Config.SYMBOLS)} símbolos.")
        except Exception as e:
            st.caption(f"No se pudo evaluar: {e}")

with tab_graficos:
    st.subheader("Elegí un símbolo para ver su gráfico de velas")
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
                fig.add_trace(go.Scatter(x=df.index, y=sma_fast, line=dict(color="#60a5fa", width=1.3), name="SMA rápida (10)"))
                fig.add_trace(go.Scatter(x=df.index, y=sma_slow, line=dict(color="#f59e0b", width=1.3), name="SMA lenta (30)"))
                fig.update_layout(height=480, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False,
                                   template="plotly_dark", title=f"{chosen} — velas de {Config.TIMEFRAME_MINUTES} min")
                st.plotly_chart(fig, use_container_width=True)

                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=df.index, y=rsi, line=dict(color="#a78bfa", width=1.3), name="RSI"))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color="#ef4444", annotation_text="sobrecomprado (70)")
                fig_rsi.add_hline(y=30, line_dash="dot", line_color="#22c55e", annotation_text="sobrevendido (30)")
                fig_rsi.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark", yaxis_range=[0, 100])
                st.plotly_chart(fig_rsi, use_container_width=True)

                result = compute_signal(df)
                st.info(f"**Señal actual: {result['signal'].upper()}** — {result.get('reason', '')}")
            else:
                st.warning("No se pudieron traer datos para este símbolo.")
        except Exception as e:
            st.error(f"Error consultando Alpaca: {e}")

with tab_ops:
    st.subheader("Historial de órdenes")
    orders_df = load_table("SELECT ts, symbol, side, qty, status, reason FROM orders ORDER BY id DESC LIMIT 100")
    if not orders_df.empty:
        side_counts = orders_df["side"].value_counts().reset_index()
        side_counts.columns = ["tipo", "cantidad"]
        col1, col2 = st.columns([1, 2])
        with col1:
            fig_pie2 = px.pie(side_counts, values="cantidad", names="tipo", hole=0.45, title="Tipos de órdenes")
            fig_pie2.update_layout(height=280, template="plotly_dark")
            st.plotly_chart(fig_pie2, use_container_width=True)
        with col2:
            st.caption("buy = compra | sell = venta por señal | trailing_stop_sell = protección puesta (no es una venta todavía)")
            st.dataframe(orders_df, use_container_width=True, hide_index=True)
    else:
        st.caption("Todavía no se ejecutó ninguna orden.")

with tab_news:
    st.subheader("📰 Noticias que influyeron en decisiones de compra")
    news_events = load_table("SELECT ts, message FROM events WHERE message LIKE '%noticia%' ORDER BY id DESC LIMIT 30")
    if not news_events.empty:
        st.dataframe(news_events, use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no se registró ninguna noticia.")

with tab_screener:
    st.subheader("🧭 Screener — buscar símbolos en suba")
    DEFAULT_UNIVERSE = (
        "AAPL,MSFT,GOOGL,NVDA,TSLA,AMZN,META,XOM,CVX,COP,SLB,OXY,"
        "CAT,DE,HON,GE,BA,ALB,SQM,LAC,RIO,YPF,GGAL,PAM,BMA,VIST,MELI,GLOB,SPY,QQQ,DIA"
    )
    universe_input = st.text_area("Símbolos candidatos (separados por coma)", value=DEFAULT_UNIVERSE, height=80)
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
            st.success(f"🟢 {len(buys)} símbolo(s) con señal de compra: {', '.join(buys['symbol'])}")
        else:
            st.info("Ningún símbolo da señal de compra ahora.")
        cols_to_show = [c for c in ["symbol", "signal", "reason", "sma_fast", "sma_slow", "rsi", "last_close"] if c in scan_df.columns]
        st.dataframe(scan_df[cols_to_show], use_container_width=True, hide_index=True)
        if not buys.empty:
            st.code(",".join(list(dict.fromkeys(Config.SYMBOLS + list(buys["symbol"])))), language=None)

with tab_bt:
    st.subheader("🧪 Resultados de backtesting")
    try:
        bt_results = load_table("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 20")
    except Exception:
        bt_results = pd.DataFrame()
    if not bt_results.empty:
        st.dataframe(bt_results, use_container_width=True, hide_index=True)
        last_run = bt_results.iloc[0]["run_ts"]
        try:
            curve = load_table(f"SELECT ts, equity, symbol FROM backtest_equity_curve WHERE run_ts = '{last_run}' ORDER BY id ASC")
            if not curve.empty:
                fig_bt = go.Figure()
                for sym in curve["symbol"].unique():
                    sym_curve = curve[curve["symbol"] == sym]
                    fig_bt.add_trace(go.Scatter(x=sym_curve["ts"], y=sym_curve["equity"], name=sym, mode="lines"))
                fig_bt.update_layout(height=320, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_bt, use_container_width=True)
        except Exception:
            pass
    else:
        st.caption("Todavía no corriste ningún backtest.")

    st.divider()
    st.subheader("🎛️ Resultados de optimización")
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
        ("Trailing Stop", "Orden de venta que sube con el precio y nunca baja — protege ganancias sin techo fijo."),
        ("Kill switch", "Interruptor de emergencia que frena todas las operaciones nuevas."),
        ("Paper trading", "Operar con dinero simulado, precios reales."),
        ("Win rate", "% de operaciones cerradas en ganancia."),
        ("Timeframe", "Tamaño de cada vela de precio (15 min, 1 día) — no es el horario de mercado."),
        ("Buy & Hold", "Comprar y no vender nunca — la referencia para medir si una estrategia activa vale la pena."),
        ("ADR", "Certificado de acción extranjera cotizando en dólares en una bolsa de EEUU."),
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

st.caption(f"Última actualización: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} — recargá para refrescar.")
