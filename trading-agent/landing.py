"""
landing.py
Portada pública del Puma-Code Trading Agent (demo en paper trading).
Explica qué es, usa datos reales de la base (equity, señales, asteroide 3D) y lleva al panel completo con un botón.
No tiene contraseña: no muestra ni permite nada sensible (los controles del panel piden clave de administrador).
"""
import os
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import i18n

from config import Config
from lab_data import LAB_META, LAB_ROWS

G, Y, R, B, DIM = "#3EE89A", "#F5C84B", "#FF5F6D", "#8FB4FF", "#7F93B4"

LANDING_CSS = """
<style>
[data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
.block-container {max-width: 1080px !important; padding-top: 2.2vh !important;}
.ln-hero {display: flex; flex-direction: column; align-items: center; text-align: center; padding: 6px 0 4px;}
.ln-orb {position: relative; width: min(260px, 62vw); aspect-ratio: 1; display: grid; place-items: center; margin: 4px 0 2px;}
.ln-halo {position: absolute; inset: -6%; border-radius: 50%;
          background: radial-gradient(circle, rgba(79,209,232,.34) 0%, rgba(192,138,78,.18) 40%, rgba(79,209,232,.06) 62%, transparent 74%);
          filter: blur(16px); animation: lnpulse 5s ease-in-out infinite;}
.ln-orb img.ic {position: relative; display: block; width: 64%; height: auto; aspect-ratio: 450 / 414; object-fit: contain;
                image-rendering: auto;}
.ln-ring {position: absolute; border-radius: 50%; border: 1px solid rgba(120,170,255,.22);}
.ln-ring.r1 {inset: 0; animation: lnspin 38s linear infinite;
             box-shadow: 0 0 26px rgba(79,209,232,.20), inset 0 0 26px rgba(79,209,232,.10); border-color: rgba(120,200,255,.34);}
.ln-ring.r2 {inset: -9%; border-style: dashed; border-color: rgba(120,170,255,.16); animation: lnspin 70s linear infinite reverse;}
.ln-ring.r3 {inset: 13%; border-color: rgba(120,170,255,.16); animation: lnspin 26s linear infinite;
             box-shadow: 0 0 18px rgba(192,138,78,.14), inset 0 0 18px rgba(192,138,78,.08);}
.ln-dot {position: absolute; width: 9px; height: 9px; border-radius: 50%; margin: -4.5px 0 0 -4.5px;}
.ln-dot.g {background: #3EE89A; box-shadow: 0 0 6px #3EE89A, 0 0 16px #3EE89A;}
.ln-dot.y {background: #F5C84B; box-shadow: 0 0 6px #F5C84B, 0 0 16px #F5C84B;}
.ln-dot.r {background: #FF5F6D; box-shadow: 0 0 6px #FF5F6D, 0 0 16px #FF5F6D;}
.ln-title {font: 700 clamp(28px, 7vw, 44px)/1.05 'Chakra Petch', sans-serif; letter-spacing: .26em; margin: 6px 0 0; padding-left: .26em; color: #EAF1FB;}
.ln-title2 {font: 600 clamp(13px, 3.6vw, 18px) 'Chakra Petch', sans-serif; letter-spacing: .5em; padding-left: .5em; margin: 6px 0 14px;
            background: linear-gradient(90deg, #D9A05B, #4FD1E8); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;}
.ln-lead {max-width: 640px; color: #B9C7DE; font-size: clamp(15px, 3.8vw, 17px); line-height: 1.55; margin: 0 auto 10px;}
.ln-chips {display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin: 6px 0 10px;}
.ln-chips span {font: 600 10px 'Chakra Petch', sans-serif; letter-spacing: .14em; padding: 5px 10px; border-radius: 999px;
                border: 1px solid rgba(120,170,255,.28); color: #9FB4D6; background: rgba(9,15,29,.6);}
.ln-chips span.p {border-color: rgba(245,200,75,.5); color: #F5C84B; background: rgba(245,200,75,.08);}
.ln-h {font: 600 12px 'Chakra Petch', sans-serif; letter-spacing: .24em; color: #3EE89A; text-transform: uppercase; margin: 34px 0 6px;}
.ln-h2 {font: 700 clamp(20px, 5vw, 27px)/1.2 'Chakra Petch', sans-serif; color: #EAF1FB; margin: 0 0 8px;}
.ln-p {color: #A9B8D0; font-size: 15px; line-height: 1.6; max-width: 760px; margin: 0 0 14px;}
.ln-stats {display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 14px 0 6px;}
.ln-stat {padding: 14px 16px; border-radius: 12px; background: rgba(9,15,29,.74); border: 1px solid rgba(120,170,255,.18);}
.ln-stat .k {font: 600 10px 'Chakra Petch', sans-serif; letter-spacing: .16em; color: #7F93B4; text-transform: uppercase;}
.ln-stat .v {font: 700 26px 'JetBrains Mono', monospace; color: #EAF1FB; margin-top: 4px;}
.ln-stat .s {font: 500 12px 'JetBrains Mono', monospace; color: #7F93B4; margin-top: 2px;}
.ln-stat .g {color: #3EE89A;} .ln-stat .y {color: #F5C84B;} .ln-stat .r {color: #FF5F6D;}
.ln-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(235px, 1fr)); gap: 14px; align-items: start; margin-top: 10px;}
details.ln-card {border-radius: 14px; background: rgba(9,15,29,.74); border: 1px solid rgba(120,170,255,.18); overflow: hidden;
                 transition: border-color .2s, box-shadow .2s;}
details.ln-card:hover {border-color: rgba(62,232,154,.45); box-shadow: 0 0 28px rgba(62,232,154,.08);}
details.ln-card[open] {border-color: rgba(62,232,154,.55);}
details.ln-card summary {list-style: none; cursor: pointer; display: block; position: relative;}
details.ln-card summary::-webkit-details-marker {display: none;}
details.ln-card .ln-img svg {display: block; width: 100%; height: auto;}
details.ln-card .ln-ct {padding: 12px 16px 14px; display: flex; flex-direction: column; gap: 2px;}
details.ln-card .ln-n {font: 600 10px 'JetBrains Mono', monospace; color: #3EE89A; letter-spacing: .18em;}
details.ln-card .ln-ct b {font: 700 17px 'Chakra Petch', sans-serif; color: #EAF1FB;}
details.ln-card .ln-ct em {font-style: normal; font-size: 12px; color: #7F93B4;}
details.ln-card summary::after {content: "+"; position: absolute; right: 12px; bottom: 12px; width: 24px; height: 24px; border-radius: 50%;
                                 display: grid; place-items: center; font: 600 16px 'JetBrains Mono', monospace; color: #3EE89A;
                                 border: 1px solid rgba(62,232,154,.5); background: rgba(4,6,13,.7);}
details.ln-card[open] summary::after {content: "\\2212";}
.ln-body {padding: 0 16px 16px; color: #B9C7DE; font-size: 14px; line-height: 1.6;}
.ln-body p {margin: 8px 0;}
.ln-body .ex {margin-top: 10px; padding: 10px 12px; border-radius: 8px; background: rgba(79,209,232,.07); border-left: 3px solid #4FD1E8; color: #CFE3F5;}
.ln-body .ex i {font-style: normal; font: 600 10px 'Chakra Petch', sans-serif; letter-spacing: .14em; color: #4FD1E8; display: block; margin-bottom: 3px;}
.ln-rules {display: grid; grid-template-columns: repeat(auto-fit, minmax(min(270px, 46%), 1fr)); gap: 10px; margin: 14px 0 8px;}
.ln-rule {padding: 11px 14px; border-radius: 10px; background: rgba(9,15,29,.74); border: 1px solid rgba(245,200,75,.22);}
.ln-rule b {display: block; font: 700 20px 'JetBrains Mono', monospace; color: #F5C84B;}
.ln-rule span {font-size: 12px; color: #9FB4D6;}
.ln-cols {display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; margin-top: 10px;}
.ln-cols.f4 {grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));}
.ln-col {padding: 16px 18px; border-radius: 14px; background: rgba(9,15,29,.74); border: 1px solid rgba(120,170,255,.18);}
.ln-col > b {font: 700 16px 'Chakra Petch', sans-serif; color: #EAF1FB; display: block; margin-bottom: 6px;}
.ln-col p b {color: #EAF1FB;}
.ln-col p {margin: 0; color: #A9B8D0; font-size: 14px; line-height: 1.55;}
.ln-table {width: 100%; border-collapse: collapse; margin-top: 8px; font: 500 13px 'JetBrains Mono', monospace;}
.ln-table th {text-align: left; font: 600 10px 'Chakra Petch', sans-serif; letter-spacing: .14em; color: #7F93B4; text-transform: uppercase; padding: 6px 10px; border-bottom: 1px solid rgba(120,170,255,.2);}
.ln-table td {padding: 7px 10px; color: #CFE0F5; border-bottom: 1px solid rgba(120,170,255,.08);}
.ln-table td.g {color: #3EE89A;} .ln-table td.r {color: #FF5F6D;}
.ln-sub {font: 600 11px 'Chakra Petch', sans-serif; letter-spacing: .16em; color: #9FB4D6; text-transform: uppercase; margin: 6px 0 2px;}
.ln-table tr.ln-ref td {color: #EAF1FB; font-weight: 700; background: rgba(79,209,232,.07);}
.ln-note {margin-top: 12px; font-size: 12px; color: #7F93B4; line-height: 1.5; max-width: 760px;}
.ln-foot {text-align: center; margin: 34px 0 6px; font: 500 10px 'Chakra Petch', sans-serif; letter-spacing: .22em; color: #5E7194;}
.ln-legal {max-width: 640px; margin: 10px auto 0; text-align: center; font: 400 10px/1.55 'Chakra Petch', sans-serif; color: #5E7194; opacity: .85;}
.ln-legal b {font-weight: 600; color: #7E90B3;}
.ln-foot img {height: 36px; width: auto; display: block; margin: 0 auto 8px; opacity: .85;}
[class*="st-key-admin_pop"] {align-items: center !important; margin-bottom: 18px;}
[class*="st-key-admin_pop"] button {font: 500 10px 'Chakra Petch', sans-serif; letter-spacing: .24em; text-transform: uppercase; min-height: 0; padding: 2px 10px;
                                    border: 0 !important; background: transparent !important; color: #5E7194 !important; opacity: .55;}
[class*="st-key-admin_pop"] button:hover {opacity: 1; color: #9FB4D6 !important;}
[class*="st-key-admin_pop"] button p {font: inherit; color: inherit;}
[class*="st-key-cta_"] {align-items: center !important; margin: 10px 0;}
[class*="st-key-cta_"] .stElementContainer, [class*="st-key-cta_"] .stButton {width: auto !important; display: flex; justify-content: center;}
[class*="st-key-cta_"] button {padding: 12px 34px; border-radius: 999px; border: 0 !important; font: 700 15px 'Chakra Petch', sans-serif; letter-spacing: .12em;
                               background: linear-gradient(90deg, #C08A4E, #4FD1E8) !important; color: #04060D !important;
                               box-shadow: 0 6px 26px rgba(79,209,232,.30);}
[class*="st-key-cta_"] button:hover {filter: brightness(1.1); transform: translateY(-1px);}
[class*="st-key-cta_"] button p {font: inherit; color: inherit;}
@keyframes lnspin {to {transform: rotate(360deg);}}
@keyframes lnfloat {0%, 100% {transform: translateY(0);} 50% {transform: translateY(-7px);}}
@keyframes lnglow {0%, 100% {filter: drop-shadow(0 0 6px rgba(120,225,255,.55)) drop-shadow(0 0 20px rgba(79,209,232,.45)) drop-shadow(0 0 46px rgba(192,138,78,.32));}
                   50% {filter: drop-shadow(0 0 9px rgba(150,235,255,.85)) drop-shadow(0 0 30px rgba(79,209,232,.70)) drop-shadow(0 0 70px rgba(192,138,78,.50));}}
@keyframes lnpulse {0%, 100% {opacity: .75; transform: scale(1);} 50% {opacity: 1; transform: scale(1.06);}}
@media (prefers-reduced-motion: reduce) {.ln-ring, .ln-halo {animation: none;}}
</style>
"""


def _pct(x: float, decimals: int = 1) -> str:
    """0.03 -> '3%', 0.015 -> '1,5%' (coma decimal)."""
    s = f"{x * 100:.{decimals}f}".rstrip("0").rstrip(".")
    return i18n.dec(s) + "%"


def _money(v: float) -> str:
    return "$" + i18n.thousands(f"{v:,.0f}")


# ---------- Imágenes (SVG propio, se expanden al tocarlas) ----------
def _svg(inner: str) -> str:
    return ('<svg viewBox="0 0 240 130" xmlns="http://www.w3.org/2000/svg" role="img">'
            '<rect width="240" height="130" fill="#0A1020"/>'
            '<g stroke="#1B2A44" stroke-width="1"><path d="M0 32H240M0 65H240M0 98H240"/></g>' + inner + '</svg>')


def _svg_mira() -> str:
    closes = [88, 84, 90, 80, 76, 82, 70, 66, 72, 58]
    candles = ""
    prev = 92
    for i, c in enumerate(closes):
        x = 22 + i * 20
        up = c < prev
        col = G if up else R
        top, bot = min(c, prev), max(c, prev)
        candles += (f'<line x1="{x}" x2="{x}" y1="{top - 7}" y2="{bot + 7}" stroke="{col}" stroke-width="1.5"/>'
                    f'<rect x="{x - 5}" y="{top}" width="10" height="{max(bot - top, 3)}" fill="{col}"/>')
        prev = c
    fast = " ".join(f"{22 + i * 20},{y}" for i, y in enumerate([90, 86, 86, 82, 78, 78, 72, 68, 68, 62]))
    slow = " ".join(f"{22 + i * 20},{y}" for i, y in enumerate([92, 90, 89, 87, 85, 83, 80, 77, 74, 71]))
    return _svg(candles + f'<polyline points="{fast}" fill="none" stroke="{Y}" stroke-width="2"/>'
                f'<polyline points="{slow}" fill="none" stroke="{B}" stroke-width="2"/>'
                f'<text x="12" y="20" fill="{DIM}" font-size="10" font-family="monospace">VELAS · SMA 10 / 30 · RSI</text>')


def _svg_decide() -> str:
    return _svg(
        f'<polyline points="20,100 80,84 140,52 220,30" fill="none" stroke="{Y}" stroke-width="2.5"/>'
        f'<polyline points="20,70 80,68 140,64 220,60" fill="none" stroke="{B}" stroke-width="2.5"/>'
        f'<circle cx="116" cy="65" r="9" fill="none" stroke="{G}" stroke-width="2"/><circle cx="116" cy="65" r="3.5" fill="{G}"/>'
        f'<rect x="12" y="12" width="74" height="22" rx="11" fill="rgba(62,232,154,.14)" stroke="{G}"/>'
        f'<text x="49" y="27" fill="{G}" font-size="11" font-weight="700" text-anchor="middle" font-family="monospace">COMPRA</text>'
        f'<text x="226" y="118" fill="{DIM}" font-size="9" text-anchor="end" font-family="monospace">cruce + RSI + noticia</text>')


def _svg_protege() -> str:
    return _svg(
        f'<g transform="translate(24 6) scale(.8)"><path d="M120 14 L166 30 V66 C166 94 144 108 120 118 C96 108 74 94 74 66 V30 Z" fill="rgba(62,232,154,.12)" stroke="{G}" stroke-width="2.5"/>'
        f'<path d="M99 66 L114 81 L144 50" fill="none" stroke="{G}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>'
        f'<polyline points="14,40 34,34 52,44 70,26" fill="none" stroke="{DIM}" stroke-width="1.5"/>'
        f'<line x1="14" x2="64" y1="52" y2="52" stroke="{R}" stroke-width="1.5" stroke-dasharray="4 3"/>'
        f'<text x="14" y="66" fill="{R}" font-size="9" font-family="monospace">stop</text>'
        f'<text x="226" y="118" fill="{DIM}" font-size="9" text-anchor="end" font-family="monospace">stop · límites · kill switch</text>')


def _svg_aprende() -> str:
    return _svg(
        f'<circle cx="120" cy="66" r="40" fill="none" stroke="{B}" stroke-width="2.5" stroke-dasharray="8 6"/>'
        f'<polygon points="152,34 164,44 148,48" fill="{B}"/>'
        f'<rect x="100" y="70" width="9" height="16" fill="{R}"/><rect x="113" y="58" width="9" height="28" fill="{Y}"/>'
        f'<rect x="126" y="46" width="9" height="40" fill="{G}"/>'
        f'<text x="14" y="20" fill="{DIM}" font-size="10" font-family="monospace">MEDIR</text>'
        f'<text x="226" y="20" fill="{DIM}" font-size="10" text-anchor="end" font-family="monospace">DESCARTAR</text>'
        f'<text x="120" y="122" fill="{DIM}" font-size="10" text-anchor="middle" font-family="monospace">AJUSTAR</text>')


def _svg_cripto() -> str:
    return _svg(
        f'<circle cx="82" cy="64" r="36" fill="rgba(245,200,75,.10)" stroke="{Y}" stroke-width="3"/>'
        f'<text x="82" y="78" fill="{Y}" font-size="40" font-weight="700" text-anchor="middle" font-family="sans-serif">&#8383;</text>'
        f'<circle cx="168" cy="64" r="30" fill="none" stroke="{B}" stroke-width="2.5"/>'
        f'<line x1="168" y1="64" x2="168" y2="44" stroke="{B}" stroke-width="3" stroke-linecap="round"/>'
        f'<line x1="168" y1="64" x2="184" y2="72" stroke="{B}" stroke-width="3" stroke-linecap="round"/>'
        f'<text x="168" y="112" fill="{B}" font-size="11" text-anchor="middle" font-family="monospace">VELAS LENTAS</text>')


def _card(n: str, title: str, hint: str, svg: str, body: str) -> str:
    return (f'<details class="ln-card"><summary><div class="ln-img">{svg}</div>'
            f'<div class="ln-ct"><span class="ln-n">{n}</span><b>{title}</b><em>{hint}</em></div></summary>'
            f'<div class="ln-body">{body}</div></details>')


def _equity_chart(equity_df: pd.DataFrame, style_fig):
    df = equity_df.sort_values("id").copy()
    df["t"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["t"])
    if len(df) < 2:
        return None
    first = float(df["equity"].iloc[0])
    lo, hi = float(df["equity"].min()), float(df["equity"].max())
    pad = max((hi - lo) * 0.15, hi * 0.0005)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["t"], y=df["equity"], mode="lines", line=dict(color=G, width=2),
                             fill="tozeroy", fillcolor="rgba(62,232,154,.10)", hovertemplate="%{x|%d/%m %H:%M}<br>$%{y:,.2f}<extra></extra>"))
    fig.add_hline(y=first, line=dict(color=Y, width=1, dash="dash"))
    fig.update_yaxes(range=[lo - pad, hi + pad], gridcolor="rgba(120,170,255,.08)", tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(gridcolor="rgba(120,170,255,.05)")
    return style_fig(fig, 260, margin=dict(l=0, r=0, t=6, b=6))


def _btc_block(df: pd.DataFrame, style_fig):
    """Velas de 1 h de BTC/USD de los últimos días + números de volatilidad (todo calculado de los datos reales)."""
    df = df.dropna(subset=["open", "high", "low", "close"])
    if len(df) < 24:
        return None
    first, last = float(df["close"].iloc[0]), float(df["close"].iloc[-1])
    chg = (last / first - 1) * 100
    rng = (float(df["high"].max()) - float(df["low"].min())) / first * 100
    daily = df["close"].resample("1D").last().pct_change().dropna() * 100
    worst = float(daily.min()) if len(daily) else 0.0
    best = float(daily.max()) if len(daily) else 0.0
    days = max(1, round((df.index[-1] - df.index[0]).total_seconds() / 86400))
    fig = go.Figure(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=G, decreasing_line_color=R, increasing_fillcolor=G, decreasing_fillcolor=R,
        hovertemplate="%{x|%d/%m %H:%M}<br>cierre $%{close:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=first, line=dict(color=Y, width=1, dash="dash"))
    fig.update_yaxes(gridcolor="rgba(120,170,255,.08)", tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(gridcolor="rgba(120,170,255,.05)", rangeslider_visible=False)
    fig.update_layout(dragmode=False)
    return dict(fig=style_fig(fig, 300, margin=dict(l=0, r=0, t=6, b=6)), first=first, last=last, chg=chg, rng=rng,
                worst=worst, best=best, days=days)


def _fmt1(x: float, sign: bool = False) -> str:
    return i18n.dec(f"{x:+.1f}" if sign else f"{x:.1f}")



def _stock_signal_chart(df: pd.DataFrame, style_fig):
    """Velas + SMA 10/30 de una acción real, con los cruces marcados (así se ve una señal).
    El eje X es la posición de cada vela (no la hora) para que las noches y fines de semana no dejen huecos."""
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    if len(df) < 40:
        return None
    df["f"] = df["close"].rolling(10).mean()
    df["sl"] = df["close"].rolling(30).mean()
    diff = df["f"] - df["sl"]
    up = ((diff > 0) & (diff.shift() <= 0)).tail(100).to_numpy()
    dn = ((diff < 0) & (diff.shift() >= 0)).tail(100).to_numpy()
    df = df.tail(100)
    x = list(range(len(df)))
    labels = [t.strftime("%d/%m %H:%M") for t in df.index]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                                 increasing_line_color=G, decreasing_line_color=R, increasing_fillcolor=G, decreasing_fillcolor=R,
                                 name="Precio", showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=df["f"], mode="lines", line=dict(color=Y, width=1.8), name="Promedio rápido (10)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=df["sl"], mode="lines", line=dict(color=B, width=1.8), name="Promedio lento (30)", hoverinfo="skip"))
    xs_up = [i for i, v in zip(x, up) if v]
    xs_dn = [i for i, v in zip(x, dn) if v]
    if xs_up:
        fig.add_trace(go.Scatter(x=xs_up, y=[df["low"].iloc[i] * 0.9995 for i in xs_up], mode="markers", name="Cruce al alza", hoverinfo="skip",
                                 marker=dict(symbol="triangle-up", size=12, color=G, line=dict(color="#04060D", width=1))))
    if xs_dn:
        fig.add_trace(go.Scatter(x=xs_dn, y=[df["high"].iloc[i] * 1.0005 for i in xs_dn], mode="markers", name="Cruce a la baja", hoverinfo="skip",
                                 marker=dict(symbol="triangle-down", size=12, color=R, line=dict(color="#04060D", width=1))))
    lo, hi = float(df["low"].min()), float(df["high"].max())
    pad = (hi - lo) * 0.08
    step = max(1, len(x) // 5)
    fig.update_yaxes(range=[lo - pad, hi + pad], gridcolor="rgba(120,170,255,.08)", tickprefix="$")
    fig.update_xaxes(gridcolor="rgba(120,170,255,.05)", rangeslider_visible=False,
                     tickmode="array", tickvals=x[::step], ticktext=labels[::step])
    fig.update_layout(dragmode=False, legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)))
    return style_fig(fig, 330, margin=dict(l=0, r=0, t=30, b=6))


def _daily_move(df: pd.DataFrame):
    """Movimiento diario promedio (valor absoluto, en %) calculado con los cierres diarios."""
    if df is None or df.empty:
        return None
    d = df["close"].resample("1D").last().dropna().pct_change().abs().dropna() * 100
    return float(d.mean()) if len(d) >= 2 else None


def _vol_chart(vals: dict, style_fig):
    names = list(vals.keys())
    colors = [R if "/" in n else B for n in names]
    fig = go.Figure(go.Bar(x=names, y=[vals[n] for n in names], marker_color=colors,
                           text=[i18n.dec(f"{vals[n]:.1f}%") for n in names], textposition="outside",
                           hovertemplate="%{x}: %{y:.2f}% por día<extra></extra>"))
    fig.update_yaxes(gridcolor="rgba(120,170,255,.08)", ticksuffix="%", range=[0, max(vals.values()) * 1.25])
    fig.update_layout(dragmode=False)
    return style_fig(fig, 330, margin=dict(l=0, r=0, t=24, b=6))


def _bt_table(bt_df: pd.DataFrame):
    """Resultados de backtest de acciones guardados por el agente (última corrida de cada símbolo)."""
    if bt_df is None or bt_df.empty or "symbol" not in bt_df:
        return None
    d = bt_df[~bt_df["symbol"].astype(str).str.contains("/")].drop_duplicates("symbol").dropna(subset=["total_return_pct"]).copy()
    if d.empty:
        return None
    d = d.sort_values("total_return_pct", ascending=False)
    avg = float(d["total_return_pct"].mean()) * 100
    rows = ""
    for _, r in d.head(6).iterrows():
        ret = float(r["total_return_pct"]) * 100
        bh = r.get("buy_hold_pct")
        bh_txt = "—" if pd.isna(bh) else _fmt1(float(bh) * Config.MAX_POSITION_PCT * 100, True) + "%"
        wr = r.get("win_rate")
        rows += (f'<tr><td>{r["symbol"]}</td><td class="{"g" if ret >= 0 else "r"}">{_fmt1(ret, True)}%</td><td>{bh_txt}</td>'
                 f'<td>{int(r["num_trades"])}</td><td>{"—" if pd.isna(wr) else f"{float(wr) * 100:.0f}%"}</td></tr>')
    html = ('<table class="ln-table"><tr><th>Símbolo</th><th>Retorno</th><th>Comprar y mantener*</th><th>Operaciones</th><th>Aciertos</th></tr>'
            + rows + '</table>')
    return html, avg, len(d)


def _lab_table():
    """Tabla fija con los resultados del laboratorio (ver lab_data.py)."""
    rows = ""
    for name, r_all, r_oos, sh, dd, ref in LAB_ROWS:
        cls = ' class="ln-ref"' if ref else ""
        rows += (f'<tr{cls}><td>{name}</td><td>{_fmt1(r_all)}%</td><td>{_fmt1(r_oos)}%</td>'
                 f'<td>{i18n.dec(f"{sh:.2f}")}</td><td>{_fmt1(dd)}%</td></tr>')
    return ('<div style="overflow-x:auto"><table class="ln-table" style="min-width:560px"><tr><th>Estrategia</th><th>Retorno por año</th><th>Fuera de muestra</th>'
            '<th>Sharpe fuera de muestra</th><th>Mayor caída</th></tr>' + rows + '</table></div>')


def _top_table(auto_top):
    """Top N del screener automático (lo escribe el agente en la base). None si no está activado o no hay datos."""
    if not auto_top or not auto_top.get("rows"):
        return None
    n = int(auto_top.get("top_n") or 3)
    rows = ""
    for i, r in enumerate(auto_top["rows"][:n], 1):
        dc = r.get("day_chg")
        ml = r.get("mom_long")
        dtxt = "—" if dc is None else f'<span class="{"g" if dc >= 0 else "r"}">{_fmt1(dc * 100, True)}%</span>'
        mtxt = "—" if ml is None else f'{_fmt1(ml * 100, True)}%'
        rows += (f'<tr><td>{i}. {r["symbol"]}</td><td>{"—" if r.get("price") is None else "$" + format(r["price"], ",.2f")}</td>'
                 f'<td>{dtxt}</td><td>{mtxt}</td><td>{"—" if r.get("score") is None else format(r["score"], ".0f")}</td></tr>')
    html = ('<table class="ln-table"><tr><th>Acción</th><th>Precio</th><th>Hoy</th><th>6 meses</th><th>Puntaje</th></tr>' + rows + '</table>')
    when = ""
    try:
        t = datetime.fromisoformat(auto_top["ts"]).astimezone(timezone.utc)
        when = f' Último escaneo: {t:%d/%m %H:%M} UTC.'
    except Exception:
        pass
    return html, when, int(auto_top.get("eligible") or 0), int(auto_top.get("scored") or 0), bool(auto_top.get("rotation"))


def render_landing(img_b64, equity_df, sigs, positions, asteroid_fn, style_fig, on_enter, fetch_bars=None, admin_login=None, admin_enabled=False, bt_df=None, auto_top=None):
    """Dibuja la portada pública. `on_enter` se llama al tocar los botones que llevan al panel completo."""
    st.markdown(LANDING_CSS, unsafe_allow_html=True)

    # El logo se sirve como archivo (/app/static) y no como texto base64: se descarga una vez, queda en caché y no se
    # reenvía en cada recarga ni al cambiar de idioma (antes Chrome lo dibujaba cortado a la mitad).
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "hero_logo.png")):
        icon_html = '<img class="ic" src="/app/static/hero_logo.png?v=3" alt="Puma Code Trading Agent" decoding="sync">'
    else:
        icon = img_b64("icon-512.png")
        icon_html = f'<img class="ic" src="data:image/png;base64,{icon}" alt="Puma Code Trading Agent">' if icon else ""

    # ---- Hero ----
    st.markdown(
        '<div class="ln-hero"><div class="ln-orb"><div class="ln-halo"></div>'
        '<div class="ln-ring r2"><i class="ln-dot y" style="left:50%;top:0"></i><i class="ln-dot g" style="left:100%;top:50%"></i></div>'
        '<div class="ln-ring r1"><i class="ln-dot g" style="left:14.6%;top:14.6%"></i><i class="ln-dot r" style="left:85.4%;top:85.4%"></i>'
        '<i class="ln-dot y" style="left:50%;top:100%"></i></div>'
        '<div class="ln-ring r3"><i class="ln-dot g" style="left:50%;top:0"></i></div>'
        f'{icon_html}</div>'
        '<div class="ln-title">PUMA CODE</div><div class="ln-title2">TRADING AGENT</div>'
        '<p class="ln-lead">Un agente de trading autónomo que <b>está aprendiendo</b>. Lee el mercado, decide, se protege y deja '
        'cada paso a la vista. Hoy es una <b>demostración con dinero simulado</b>.</p>'
        '<div class="ln-chips"><span>ACCIONES</span><span>CRIPTO 24/7</span><span>RIESGO CONTROLADO</span>'
        '<span class="p">DEMOSTRATIVO · PAPER · SIN DINERO REAL</span></div></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="cta_top"):
        st.button("VER EL PANEL EN VIVO  →", on_click=on_enter, key="btn_top")

    # ---- Números reales ----
    equity_now = float(equity_df.iloc[0]["equity"]) if not equity_df.empty else None
    first_eq = float(equity_df.sort_values("id").iloc[0]["equity"]) if not equity_df.empty else None
    delta_html = ""
    if equity_now is not None and first_eq:
        d = (equity_now - first_eq) / first_eq * 100
        dtxt = i18n.dec(f"{d:+.2f}")
        delta_html = f'<div class="s"><span class="{"g" if d >= 0 else "r"}">{dtxt}%</span> desde el primer registro</div>'
    good = sum(1 for s in sigs if s["tone"] == "g")
    mid = sum(1 for s in sigs if s["tone"] == "y")
    bad = sum(1 for s in sigs if s["tone"] == "r")
    st.markdown('<div class="ln-h">Datos reales, no una maqueta</div>'
                '<div class="ln-h2">Esto es lo que está pasando ahora</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ln-stats">'
        f'<div class="ln-stat"><div class="k">Capital simulado</div><div class="v">{_money(equity_now) if equity_now is not None else "—"}</div>{delta_html}</div>'
        f'<div class="ln-stat"><div class="k">Símbolos vigilados</div><div class="v">{len(sigs) or "—"}</div><div class="s">acciones y cripto</div></div>'
        f'<div class="ln-stat"><div class="k">Señales ahora</div><div class="v"><span class="g">{good}</span> · <span class="y">{mid}</span> · <span class="r">{bad}</span></div>'
        '<div class="s">buenas · intermedias · malas</div></div>'
        f'<div class="ln-stat"><div class="k">Posiciones abiertas</div><div class="v">{len(positions)}</div><div class="s">dinero simulado</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    fig = _equity_chart(equity_df, style_fig) if not equity_df.empty else None
    if fig is not None:
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Curva real de la cuenta de prueba. La línea punteada es el punto de partida.")

    # ---- Asteroide ----
    st.markdown(
        '<div class="ln-h">La idea del asteroide</div>'
        '<div class="ln-h2">El mercado entero en una sola imagen</div>'
        '<p class="ln-p">Cada nube de puntos es un símbolo y cada punto es una lectura real del agente. El color cuenta la historia: '
        '<b style="color:#3EE89A">verde</b> es tendencia alcista o señal de compra, <b style="color:#F5C84B">amarillo</b> es sin dirección clara, '
        '<b style="color:#FF5F6D">rojo</b> es tendencia bajista o señal de venta. La forma se arma sola con los datos: '
        'cuando el mercado cambia, el asteroide cambia. <b>Arrastralo para girarlo y tocá un punto</b> para ver qué es.</p>',
        unsafe_allow_html=True,
    )
    if sigs:
        asteroid_fn(sigs, height=440, positions=positions)
    else:
        st.info("El agente todavía no registró lecturas.")

    # ---- Cómo piensa ----
    n_acc, n_cry = len(Config.SYMBOLS), len(Config.CRYPTO_SYMBOLS)
    cuenta = 100000
    pos_usd = cuenta * Config.MAX_POSITION_PCT
    cards = "".join([
        _card("01", "Mira el mercado", "Tocá para ver cómo", _svg_mira(),
              f'<p>Cada minuto lee las velas de <b>{n_acc} acciones</b> {i18n.tr('y')} <b>{n_cry} criptomonedas</b>. '
              'Con ellas calcula dos promedios móviles (uno rápido y uno lento) y el RSI, que mide si algo está caro o barato en el corto plazo.</p>'
              '<div class="ex"><i>EJEMPLO ILUSTRATIVO</i>Una vela de 15 minutos de AAPL resume cuatro precios: apertura, máximo, mínimo y cierre. '
              'El agente mira las últimas 200 para entender el momento de la acción.</div>'),
        _card("02", "Decide", "Tocá para ver cómo", _svg_decide(),
              '<p>Compra solo cuando el promedio rápido cruza hacia arriba al lento <b>y</b> el RSI no está sobrecomprado. '
              'Antes de ejecutar lee la última noticia del activo y una IA la clasifica; si es claramente negativa, cancela la compra.</p>'
              '<div class="ex"><i>EJEMPLO ILUSTRATIVO</i>El promedio rápido de una acción pasa por encima del lento, el RSI marca 52 '
              'y la noticia es neutral: el agente compra. Si la noticia fuera mala, no compra.</div>'),
        _card("03", "Se protege", "Tocá para ver cómo", _svg_protege(),
              f'<p>Cada compra nace con red de seguridad: un <b>trailing stop</b> del {_pct(Config.TRAILING_STOP_PCT, 0)} en acciones '
              f'y del {_pct(Config.CRYPTO_TRAILING_STOP_PCT, 0)} en cripto, un tope por posición, pausa si pierde {_pct(Config.DAILY_LOSS_LIMIT_PCT, 0)} en el día '
              f'y un <b>kill switch</b> que frena todo si la caída total llega a {_pct(Config.MAX_DRAWDOWN_PCT, 0)} o si el capital se desploma de golpe.</p>'
              f'<div class="ex"><i>EJEMPLO ILUSTRATIVO</i>Con una cuenta de {_money(cuenta)}, una posición de acciones no pasa de {_money(pos_usd)} '
              f'({_pct(Config.MAX_POSITION_PCT, 0)}). Si el precio cae {_pct(Config.TRAILING_STOP_PCT, 0)} desde su máximo, se vende sola.</div>'),
        _card("04", "Aprende", "Tocá para ver cómo", _svg_aprende(),
              '<p>Todo queda registrado: señales, órdenes y capital. Antes de usar una idea se prueba con el <b>backtest</b> sobre datos históricos. '
              'Aprender acá significa medir, descartar lo que no sirve y ajustar.</p>'
              '<div class="ex"><i>LO QUE PASÓ DE VERDAD</i>En las pruebas con cripto, velas de 15 minutos operaban demasiado y las comisiones se comían '
              'todo el resultado. El agente pasó a velas de 4 horas, con pausas y topes diarios.</div>'),
    ])
    st.markdown('<div class="ln-h">Cómo piensa</div><div class="ln-h2">Cuatro pasos, todos a la vista</div>'
                '<p class="ln-p">Tocá cada imagen para abrirla.</p>'
                f'<div class="ln-grid">{cards}</div>', unsafe_allow_html=True)

    # ---- La bolsa ----
    st_pos = [p for p in positions if p["kind"] == "stock"]
    inv = sum(p["market_value"] for p in st_pos)
    upl = sum(p["unrealized_pl"] for p in st_pos)
    upl_pct = upl / (inv - upl) * 100 if (inv - upl) else 0.0
    ucol = G if upl >= 0 else R
    st.markdown(
        '<div class="ln-h">La bolsa</div><div class="ln-h2">El terreno principal del agente</div>'
        '<p class="ln-p">Las acciones son donde el agente pasa la mayor parte del tiempo. Operar no tiene comisión, el mercado tiene horario y reglas claras '
        'y los precios se mueven de forma más moderada que en cripto. Eso le da más margen para que una estrategia simple se pueda probar y medir. '
        'Acá van los datos reales; no hace falta creerle a nadie.</p>'
        '<div class="ln-stats">'
        f'<div class="ln-stat"><div class="k">Acciones en cartera</div><div class="v">{len(st_pos)}/{Config.MAX_OPEN_POSITIONS}</div><div class="s">posiciones abiertas</div></div>'
        f'<div class="ln-stat"><div class="k">Invertido</div><div class="v">{_money(inv)}</div><div class="s">dinero simulado</div></div>'
        f'<div class="ln-stat"><div class="k">Resultado abierto</div><div class="v" style="color:{ucol}">{"+" if upl >= 0 else "-"}{_money(abs(upl))}</div>'
        f'<div class="s">{_fmt1(upl_pct, True)}% sobre lo invertido</div></div>'
        '<div class="ln-stat"><div class="k">Comisión por operar</div><div class="v">$0</div><div class="s">solo tasas regulatorias en ventas</div></div>'
        '</div>', unsafe_allow_html=True)

    if fetch_bars:
        held_syms = [p["symbol"] for p in st_pos]
        cand = [x["symbol"] for x in sigs if "/" not in x["symbol"] and x["tone"] == "g"]
        sym = (held_syms or cand or ["AAPL"])[0]
        try:
            fig_s = _stock_signal_chart(fetch_bars(sym, Config.TIMEFRAME_MINUTES, 140), style_fig)
        except Exception:
            fig_s = None
        vols = {}
        for name in ("SPY", "AAPL", "BTC/USD", "ETH/USD"):
            try:
                v = _daily_move(fetch_bars(name, 60, 168))
            except Exception:
                v = None
            if v is not None:
                vols[name] = v
        fig_v = _vol_chart(vols, style_fig) if len(vols) >= 2 else None
        if fig_s is not None or fig_v is not None:
            cl, cr = st.columns([1.35, 1], gap="large")
            with cl:
                if fig_s is not None:
                    st.markdown(f'<div class="ln-sub">Una señal real · {sym}</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_s, width="stretch", config={"displayModeBar": False})
                    st.caption("Velas de 15 minutos con los dos promedios. Cuando el rápido (amarillo) cruza hacia arriba al lento (azul) aparece ▲ y el agente evalúa comprar; "
                               "si cruza hacia abajo aparece ▼.")
            with cr:
                if fig_v is not None:
                    st.markdown('<div class="ln-sub">Cuánto se mueve cada uno por día</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_v, width="stretch", config={"displayModeBar": False})
                    st.caption("Movimiento diario promedio (sin importar si sube o baja), con datos reales recientes. "
                               "Las barras rojas son cripto: se mueve mucho más, por eso se trata con más cuidado.")

    bt = _bt_table(bt_df)
    if bt:
        tabla, avg, n = bt
        st.markdown(
            '<div class="ln-sub" style="margin-top:14px">Pruebas históricas en acciones (backtest)</div>'
            f'{tabla}'
            f'<div class="ln-note">Promedio de {n} acciones probadas: <b>{_fmt1(avg, True)}%</b> sobre el capital de prueba. '
            f'*Comprar y mantener se muestra ajustado a la misma exposición del agente ({_pct(Config.MAX_POSITION_PCT, 0)} por posición). '
            'Son pruebas sobre datos del pasado con los mismos parámetros que se eligieron, así que tienden a verse mejor que lo que pasará después. '
            'Por eso todavía es una demostración.</div>', unsafe_allow_html=True)

    top = _top_table(auto_top)
    if top:
        tabla, when, n_el, n_sc, rot = top
        modo = ("El agente puede comprar la mejor candidata cuando hay lugar y reemplazar a la que perdió fuerza, siempre con sus frenos de riesgo."
                if rot else "Por ahora solo se muestra: el agente no compra por este ranking.")
        st.markdown(
            '<div class="ln-sub" style="margin-top:14px">Top 3 del día · screener automático</div>'
            f'{tabla}'
            f'<div class="ln-note">De {n_sc} acciones escaneadas, {n_el} pasan los filtros de tendencia sana. El puntaje combina fuerza de los últimos meses, '
            f'del último mes y de hoy, comparada con las demás. {modo}{when} No es una recomendación de compra: es una demostración de cómo el agente prioriza.</div>',
            unsafe_allow_html=True)

    # ---- Laboratorio ----
    st.markdown(
        '<div class="ln-h">Laboratorio</div><div class="ln-h2">El agente se mide contra el mercado, sin maquillaje</div>'
        '<p class="ln-p">Antes de confiar en una idea se prueba con años de datos reales y se compara con lo más simple que existe: '
        'comprar el índice S&P 500 (SPY) y no tocarlo. Estos son los resultados de la última corrida, con costos incluidos.</p>'
        f'{_lab_table()}'
        f'<div class="ln-note">{LAB_META["period"]} ({i18n.dec(str(LAB_META["years"]))} años de velas diarias, feed {LAB_META["feed"]}). '
        f'«Fuera de muestra» es el tramo desde {LAB_META["oos_from"]}, que no se usó para elegir las reglas. '
        'Sharpe mide el retorno por unidad de riesgo; «mayor caída» es la peor baja desde un máximo, fuera de muestra.</div>'
        '<div class="ln-cols f4" style="margin-top:14px">'
        '<div class="ln-col"><b>Nada le ganó a SPY</b><p>Ninguna estrategia superó a comprar SPY de forma clara en los dos períodos. '
        'Es un resultado incómodo y es justamente el que hay que conocer antes de arriesgar dinero.</p></div>'
        '<div class="ln-col"><b>El cruce de medias rinde poco</b><p>La estrategia que hoy usa el agente casi no está invertida: '
        'cae poco, pero también sube poco. Por eso es una demostración y no una promesa.</p></div>'
        '<div class="ln-col"><b>El sesgo engaña</b><p>El momentum parece ganar con acciones sueltas, pero no se repite en ETFs. '
        'Probar solo con empresas que hoy existen y brillan infla el resultado.</p></div>'
        '<div class="ln-col"><b>Menos caída, no más ganancia</b><p>Lo único que se sostuvo fue una versión de Turtle con filtro de mercado: '
        'retorno parecido con casi la mitad de la caída. Baja el riesgo, no suma retorno.</p></div>'
        '</div>'
        '<div class="ln-note">Con tantas variantes probadas, alguna gana por casualidad; por eso un resultado solo cuenta si lo repiten sus variantes. '
        'El próximo paso para cualquier idea es probarla de 3 a 6 meses en paper trading antes de pensar en dinero real. '
        'Los resultados pasados no garantizan resultados futuros y esto no es asesoramiento financiero.</div>',
        unsafe_allow_html=True)

    # ---- Cripto conservadora ----
    tf_h = Config.CRYPTO_TIMEFRAME_MINUTES / 60
    tf_txt = i18n.dec(f"{tf_h:g}") + " h" if Config.CRYPTO_TIMEFRAME_MINUTES >= 60 else f"{Config.CRYPTO_TIMEFRAME_MINUTES} min"
    worst = Config.CRYPTO_MAX_POSITION_PCT * Config.CRYPTO_TRAILING_STOP_PCT
    rules = [
        (tf_txt, "por vela: decide con calma"),
        (_pct(Config.CRYPTO_MAX_POSITION_PCT), "del capital por operación"),
        (_pct(Config.CRYPTO_MAX_EXPOSURE_PCT), "techo total en cripto"),
        (str(Config.CRYPTO_MAX_TRADES_PER_DAY or "sin tope"), "compras por día como máximo"),
        (i18n.dec(f"{Config.CRYPTO_COOLDOWN_MINUTES / 60:g} h"), "de pausa tras cada cierre"),
        (_pct(Config.CRYPTO_DAILY_LOSS_PCT), "de pérdida diaria y se frena"),
    ]
    rules_html = "".join(f'<div class="ln-rule"><b>{v}</b><span>{t}</span></div>' for v, t in rules)
    cripto_card = _card(
        "CRIPTO", "Cripto, en modo conservador", "Tocá para ver el detalle", _svg_cripto(),
        f'<p>La cripto se mueve mucho más que las acciones, así que acá el agente es deliberadamente lento y chico. '
        f'En el peor caso, una operación pierde <b>{_pct(worst, 2)} del capital</b> ({_pct(Config.CRYPTO_MAX_POSITION_PCT)} de posición × {_pct(Config.CRYPTO_TRAILING_STOP_PCT, 0)} de stop), '
        'más comisiones.</p>'
        f'<p>Además se frena solo tras {Config.CRYPTO_MAX_CONSECUTIVE_LOSSES} cierres seguidos en pérdida, y las pruebas incluyen comisión '
        'y deslizamiento estimados.</p>'
        '<div class="ex"><i>PARA TENER EN CUENTA</i>En las pruebas históricas esta estrategia no mostró una ventaja clara en cripto. '
        'Por eso opera poco y por eso está en modo demostración: primero se mide, después se confía.</div>')
    st.markdown('<div class="ln-h">Cripto</div><div class="ln-h2">Poco, lento y con techo</div>'
                f'<div class="ln-rules">{rules_html}</div>', unsafe_allow_html=True)
    btc = None
    if fetch_bars:
        try:
            _df = fetch_bars("BTC/USD", 60, 168)
            btc = _btc_block(_df, style_fig) if _df is not None else None
        except Exception:
            btc = None
    card_html = f'<div class="ln-grid" style="grid-template-columns:1fr">{cripto_card}</div>'
    if btc is None:
        st.markdown(card_html.replace("1fr", "minmax(235px,420px)"), unsafe_allow_html=True)
    else:
        col_c, col_g = st.columns([1, 1.35], gap="large")
        with col_c:
            st.markdown(card_html, unsafe_allow_html=True)
        with col_g:
            col = G if btc["chg"] >= 0 else R
            verbo = "sube" if btc["chg"] >= 0 else "cae"
            st.markdown(
                f'<div class="ln-h" style="margin:0 0 4px">Bitcoin · últimos {btc["days"]} días</div>'
                f'<div class="ln-h2" style="font-size:22px">BTC/USD {_money(btc["last"])} '
                f'<span style="color:{col}">{_fmt1(btc["chg"], True)}%</span></div>',
                unsafe_allow_html=True)
            st.plotly_chart(btc["fig"], width="stretch", config={"displayModeBar": False})
            st.markdown(
                '<div class="ln-stats" style="grid-template-columns:repeat(3,1fr);margin-top:6px">'
                f'<div class="ln-stat"><div class="k">Variación</div><div class="v" style="font-size:20px;color:{col}">{_fmt1(btc["chg"], True)}%</div>'
                f'<div class="s">en los últimos {btc["days"]} días</div></div>'
                f'<div class="ln-stat"><div class="k">Rango</div><div class="v" style="font-size:20px">{_fmt1(btc["rng"])}%</div>'
                '<div class="s">de máximo a mínimo</div></div>'
                f'<div class="ln-stat"><div class="k">Peor día</div><div class="v" style="font-size:20px;color:{R if btc["worst"] < 0 else G}">{_fmt1(btc["worst"], True)}%</div>'
                f'<div class="s">mejor día {_fmt1(btc["best"], True)}%</div></div></div>'
                f'<div class="ln-note">Bitcoin {verbo} y se mueve con fuerza de un día para otro. Por eso el agente usa velas lentas, '
                'posiciones chicas y un freno automático. Datos reales de los últimos días, velas de 1 hora.</div>',
                unsafe_allow_html=True)

    # ---- Comisiones y costos ----
    fee, slip = Config.CRYPTO_FEE_PCT, Config.CRYPTO_SLIPPAGE_PCT
    rt = 2 * (fee + slip)
    pos_c = cuenta * Config.CRYPTO_MAX_POSITION_PCT
    fee_usd, slip_usd = pos_c * fee * 2, pos_c * slip * 2
    bar_w = 170
    fee_w, slip_w = bar_w * (2 * fee) / rt, bar_w * (2 * slip) / rt
    svg_costos = _svg(
        f'<text x="14" y="30" fill="{DIM}" font-size="10" font-family="monospace">ACCIONES</text>'
        f'<rect x="14" y="36" width="4" height="14" rx="2" fill="{G}"/>'
        f'<text x="26" y="48" fill="{G}" font-size="12" font-weight="700" font-family="monospace">$0 de comisión</text>'
        f'<text x="14" y="82" fill="{DIM}" font-size="10" font-family="monospace">CRIPTO · IDA Y VUELTA</text>'
        f'<rect x="14" y="88" width="{fee_w:.0f}" height="16" fill="{Y}"/>'
        f'<rect x="{14 + fee_w:.0f}" y="88" width="{slip_w:.0f}" height="16" fill="{B}"/>'
        f'<text x="{14 + bar_w + 8}" y="101" fill="#EAF1FB" font-size="12" font-weight="700" font-family="monospace">{_pct(rt, 1)}</text>')
    costo_card = _card(
        "COSTOS", "Lo que cuesta operar", "Tocá para ver un ejemplo", svg_costos,
        f'<p><b>Acciones:</b> Alpaca no cobra comisión por operar. Solo hay tasas regulatorias mínimas (SEC y FINRA) y únicamente en las ventas.</p>'
        f'<p><b>Cripto:</b> {_pct(fee, 2)} por lado en la tarifa base de Alpaca para órdenes a mercado (baja con el volumen operado), '
        f'más un deslizamiento estimado de {_pct(slip, 2)}: la diferencia entre el precio que se ve y el que realmente se ejecuta.</p>'
        f'<div class="ex"><i>EJEMPLO ILUSTRATIVO</i>Comprar y vender {_money(pos_c)} en cripto ({_pct(Config.CRYPTO_MAX_POSITION_PCT, 0)} de una cuenta de {_money(cuenta)}): '
        f'comisiones ≈ {_money(fee_usd)} y deslizamiento ≈ {_money(slip_usd)}, en total ≈ <b>{_money(fee_usd + slip_usd)}</b> ({_pct(rt, 1)} de la posición). '
        f'El precio tiene que moverse al menos {_pct(rt, 1)} a favor solo para quedar a mano.</div>')
    st.markdown(
        '<div class="ln-h">Comisiones</div><div class="ln-h2">Cada operación tiene un costo, y el agente lo tiene en cuenta</div>'
        '<p class="ln-p">Una estrategia puede acertar seguido y aun así perder plata si los costos se comen cada ganancia. '
        'Por eso las comisiones no son un detalle: son parte de la decisión.</p>'
        '<div class="ln-stats">'
        '<div class="ln-stat"><div class="k">Acciones</div><div class="v">$0</div><div class="s">de comisión por operar</div></div>'
        f'<div class="ln-stat"><div class="k">Cripto</div><div class="v">{_pct(fee, 2)}</div><div class="s">por lado, tarifa base</div></div>'
        f'<div class="ln-stat"><div class="k">Cripto, ida y vuelta</div><div class="v">≈ {_pct(rt, 1)}</div><div class="s">con deslizamiento estimado</div></div>'
        '</div>', unsafe_allow_html=True)
    cc, cd = st.columns([1, 1.35], gap="large")
    with cc:
        st.markdown(f'<div class="ln-grid" style="grid-template-columns:1fr">{costo_card}</div>', unsafe_allow_html=True)
    with cd:
        st.markdown(
            '<div class="ln-body" style="padding:0">'
            '<p><b>Cómo lo manejamos</b></p>'
            '<p>• Todas las pruebas históricas (backtest) descuentan comisión y deslizamiento. Sin descontar los costos, cualquier resultado se ve mejor de lo que sería en la realidad.</p>'
            '<p>• Los frenos automáticos del agente cuentan la comisión estimada: una pérdida con costos incluidos se ve completa, no recortada.</p>'
            '<p>• Para no regalar plata en comisiones, la cripto usa velas lentas, una pausa después de cada cierre y un máximo de compras por día. '
            'En las pruebas, con velas de 15 minutos las comisiones se comían todo el resultado.</p>'
            '<div class="ex"><i>HONESTIDAD</i>Las cifras de cripto son estimaciones del costo real, calculadas con la tarifa base publicada por Alpaca. '
            'Qué se descuenta exactamente en una cuenta de prueba (paper) puede diferir.</div></div>',
            unsafe_allow_html=True)

    # ---- Por qué un agente ----
    st.markdown(
        '<div class="ln-h">Por qué un agente</div><div class="ln-h2">Lo que una persona no puede hacer sola</div>'
        '<div class="ln-cols f4">'
        f'<div class="ln-col"><b>Vigila todo a la vez</b><p>Mira {n_acc} acciones y {n_cry} criptomonedas cada minuto. '
        'La cripto no cierra nunca; un agente no necesita dormir.</p></div>'
        '<div class="ln-col"><b>Sin emociones</b><p>No se entusiasma con una subida ni se asusta con una caída. '
        'Aplica las mismas reglas todos los días, también cuando duele.</p></div>'
        '<div class="ln-col"><b>Límites que no se negocian</b><p>Los topes de riesgo, los stops y el kill switch están en el código. '
        'No dependen del ánimo de nadie ni de una excepción de último momento.</p></div>'
        '<div class="ln-col"><b>Todo queda registrado</b><p>Cada señal, orden y resultado se guarda con su motivo. '
        'Eso permite medir qué funciona, descartar lo que no y mejorar.</p></div>'
        '</div>'
        '<div class="ln-note">Un agente no garantiza ganar: ejecuta una estrategia con disciplina. Su valor está en hacerlo sin emociones, '
        'dejarlo todo medido y poder mejorarlo con datos. Si la estrategia no sirve, el agente lo va a mostrar con números.</div>',
        unsafe_allow_html=True)

    # ---- Qué es / qué no es ----
    st.markdown(
        '<div class="ln-h">Qué es esto</div><div class="ln-h2">Una demostración honesta</div>'
        '<div class="ln-cols">'
        '<div class="ln-col"><b>Demostrativo</b><p>Opera en <b>paper trading</b>: precios reales del mercado, dinero simulado. '
        'Nada de lo que ves arriesga plata de nadie.</p></div>'
        '<div class="ln-col"><b>Está aprendiendo</b><p>Cada día suma datos. Se prueba, se mide y se corrige. '
        'Los resultados de hoy son parte del aprendizaje, no una promesa.</p></div>'
        '<div class="ln-col"><b>La meta</b><p>Si con el tiempo los números sostenidos nos convencen, construirlo como una herramienta '
        'de <b>ingresos pasivos</b>, con un sistema de acceso propio y mucho más control.</p></div>'
        '</div>'
        '<div class="ln-note">Esto es una demostración técnica y no constituye asesoramiento financiero. '
        'Los resultados pasados o simulados no garantizan resultados futuros.</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ln-h" style="text-align:center">¿Querés verlo por dentro?</div>', unsafe_allow_html=True)
    with st.container(key="cta_bottom"):
        st.button("VER EL PANEL EN VIVO  →", on_click=on_enter, key="btn_bottom")

    logo = img_b64("header_logo.png")
    foot_logo = f'<img src="data:image/png;base64,{logo}" alt="Puma Code">' if logo else ""
    st.markdown(f'<div class="ln-foot">{foot_logo}PUMA CODE · MENDOZA, ARGENTINA</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ln-legal">'
        '<b>Aviso:</b> Puma Code no se hace responsable de las decisiones ni de las acciones que cualquier persona '
        'tome con su dinero a partir de lo que se muestra acá. Es una demo educativa en paper trading; no es '
        'asesoramiento financiero.<br>'
        '<b>Fuentes:</b> precios de acciones (feed IEX), precios de cripto y noticias: Alpaca Markets (alpaca.markets). '
        'Datos de fuentes confiables; pueden tener demora o errores.<br>'
        f'© {datetime.now().year} Puma Code. Todos los derechos reservados.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ---- Acceso de administrador (chico, en el footer) ----
    if admin_login is not None:
        with st.container(key="admin_pop"):
            with st.popover("admin"):
                if not admin_enabled:
                    st.caption("No hay contraseña de administrador configurada (variable ADMIN_PASSWORD).")
                else:
                    with st.form("admin_form", border=False):
                        pw = st.text_input("Contraseña de administrador", type="password")
                        ok = st.form_submit_button("Entrar")
                    if ok:
                        if admin_login(pw):
                            on_enter()
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
