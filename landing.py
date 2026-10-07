"""
landing.py
Portada pública del Puma-Code Trading Agent (demo en paper trading).
Explica qué es, usa datos reales de la base (equity, señales, asteroide 3D) y lleva al panel completo con un botón.
No tiene contraseña: no muestra ni permite nada sensible (los controles del panel piden clave de administrador).
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import Config

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
.ln-orb img.ic {position: relative; width: 64%; height: auto;
                filter: drop-shadow(0 0 6px rgba(120,225,255,.65)) drop-shadow(0 0 22px rgba(79,209,232,.55)) drop-shadow(0 0 54px rgba(192,138,78,.40));
                animation: lnfloat 7s ease-in-out infinite, lnglow 4.5s ease-in-out infinite;}
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
.ln-rules {display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 10px; margin: 14px 0 8px;}
.ln-rule {padding: 11px 14px; border-radius: 10px; background: rgba(9,15,29,.74); border: 1px solid rgba(245,200,75,.22);}
.ln-rule b {display: block; font: 700 20px 'JetBrains Mono', monospace; color: #F5C84B;}
.ln-rule span {font-size: 12px; color: #9FB4D6;}
.ln-cols {display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; margin-top: 10px;}
.ln-col {padding: 16px 18px; border-radius: 14px; background: rgba(9,15,29,.74); border: 1px solid rgba(120,170,255,.18);}
.ln-col > b {font: 700 16px 'Chakra Petch', sans-serif; color: #EAF1FB; display: block; margin-bottom: 6px;}
.ln-col p b {color: #EAF1FB;}
.ln-col p {margin: 0; color: #A9B8D0; font-size: 14px; line-height: 1.55;}
.ln-note {margin-top: 12px; font-size: 12px; color: #7F93B4; line-height: 1.5; max-width: 760px;}
.ln-foot {text-align: center; margin: 34px 0 6px; font: 500 10px 'Chakra Petch', sans-serif; letter-spacing: .22em; color: #5E7194;}
.ln-foot img {height: 36px; width: auto; display: block; margin: 0 auto 8px; opacity: .85;}
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
@media (prefers-reduced-motion: reduce) {.ln-ring, .ln-halo, .ln-orb img.ic {animation: none;}}
</style>
"""


def _pct(x: float, decimals: int = 1) -> str:
    """0.03 -> '3%', 0.015 -> '1,5%' (coma decimal)."""
    s = f"{x * 100:.{decimals}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") + "%"


def _money(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


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


def render_landing(img_b64, equity_df, sigs, positions, asteroid_fn, style_fig, on_enter):
    """Dibuja la portada pública. `on_enter` se llama al tocar los botones que llevan al panel completo."""
    st.markdown(LANDING_CSS, unsafe_allow_html=True)

    icon = img_b64("hero_logo.png") or img_b64("icon-512.png")
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
        dtxt = f"{d:+.2f}".replace(".", ",")
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
              f'<p>Cada minuto lee las velas de <b>{n_acc} acciones</b> y <b>{n_cry} criptomonedas</b>. '
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

    # ---- Cripto conservadora ----
    tf_h = Config.CRYPTO_TIMEFRAME_MINUTES / 60
    tf_txt = f"{tf_h:g}".replace(".", ",") + " h" if Config.CRYPTO_TIMEFRAME_MINUTES >= 60 else f"{Config.CRYPTO_TIMEFRAME_MINUTES} min"
    worst = Config.CRYPTO_MAX_POSITION_PCT * Config.CRYPTO_TRAILING_STOP_PCT
    rules = [
        (tf_txt, "por vela: decide con calma"),
        (_pct(Config.CRYPTO_MAX_POSITION_PCT), "del capital por operación"),
        (_pct(Config.CRYPTO_MAX_EXPOSURE_PCT), "techo total en cripto"),
        (str(Config.CRYPTO_MAX_TRADES_PER_DAY or "sin tope"), "compras por día como máximo"),
        (f"{Config.CRYPTO_COOLDOWN_MINUTES / 60:g} h".replace(".", ","), "de pausa tras cada cierre"),
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
                f'<div class="ln-rules">{rules_html}</div><div class="ln-grid" style="grid-template-columns:minmax(235px,420px)">{cripto_card}</div>',
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
