"""
dashboard.py
Panel espacial de Puma-Code Trading Agent: acciones y cripto lado a lado,
asteroide 3D con las señales en vivo, y todos los paneles de siempre
(equity, velas, RSI, noticias, screener, operaciones, riesgo).
"""
import os
import re
import hmac
import time
import json
import base64
from datetime import datetime, timezone

import pandas as pd
import psycopg2
import psycopg2.errors
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from config import Config, is_crypto, norm_symbol, timeframe_for
from logger_db import init_db, get_state, set_state, delete_state, _dsn
from broker_alpaca import AlpacaBroker
from landing import render_landing
from seo import patch_index_html
import i18n
from strategy import compute_signal

APP_TITLE = "Puma-Code Trading Agent"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

G, Y, R, B, DIM = "#3EE89A", "#F5C84B", "#FF5F6D", "#8FB4FF", "#7F93B4"

try:
    page_icon_img = Image.open(os.path.join(STATIC_DIR, "favicon.png"))
except Exception:
    page_icon_img = "🤖"

def _auto_top():
    """Último Top del screener automático que dejó el agente en la base (o None si está apagado)."""
    try:
        raw = get_state("auto_top")
        return json.loads(raw) if raw else None
    except Exception:
        return None


@st.cache_resource
def _seo_once():
    return patch_index_html()


_seo_once()  # vista previa al compartir el link (ver seo.py)

st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon_img)

# Idioma Español / English: botón fijo arriba del todo y traducción de toda la pantalla (ver i18n.py)
i18n.install()
i18n.init_lang()
i18n.render_toggle()

# ---------- Ícono para "Agregar a pantalla de inicio" (iOS/Android) ----------
# Streamlit descarta los <link>/<meta> que se escriben con st.markdown, y sin apple-touch-icon el iPhone
# inventa un ícono con la inicial ("P"). Por eso se inyectan en el <head> real de la página con JavaScript.
components.html("""
<script>
(function () {
  try {
    var d = window.parent.document, h = d.head;
    function put(tag, attrs, key) {
      d.querySelectorAll(key).forEach(function (n) { n.remove(); });
      var el = d.createElement(tag);
      for (var k in attrs) el.setAttribute(k, attrs[k]);
      h.appendChild(el);
    }
    put("link", {rel: "apple-touch-icon", sizes: "180x180", href: "/app/static/apple-touch-icon.png"}, 'link[rel="apple-touch-icon"]');
    put("link", {rel: "icon", type: "image/png", href: "/app/static/favicon.png"}, 'link[rel="icon"],link[rel="shortcut icon"]');
    put("link", {rel: "manifest", href: "/app/static/manifest.json"}, 'link[rel="manifest"]');
    put("meta", {name: "apple-mobile-web-app-capable", content: "yes"}, 'meta[name="apple-mobile-web-app-capable"]');
    put("meta", {name: "mobile-web-app-capable", content: "yes"}, 'meta[name="mobile-web-app-capable"]');
    put("meta", {name: "apple-mobile-web-app-title", content: "PC Trading"}, 'meta[name="apple-mobile-web-app-title"]');
    put("meta", {name: "apple-mobile-web-app-status-bar-style", content: "black-translucent"}, 'meta[name="apple-mobile-web-app-status-bar-style"]');
    put("meta", {name: "theme-color", content: "#04060D"}, 'meta[name="theme-color"]');
  } catch (e) {}
})();
</script>
""", height=0)
st.markdown(
    "<style>.stElementContainer:has(iframe[height=\"0\"]) {position: absolute; height: 0; overflow: hidden; margin: 0;}</style>",
    unsafe_allow_html=True,
)

# =========================================================================
# ESTILO: galaxia, paneles de vidrio, tipografía técnica
# =========================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

.stApp {
    background-color: #04060D;
    background-image:
        radial-gradient(1.2px 1.2px at 6% 12%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 14% 64%, #cfe0ff 50%, transparent 52%),
        radial-gradient(1.4px 1.4px at 23% 31%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 31% 88%, #cfe0ff 50%, transparent 52%),
        radial-gradient(1.2px 1.2px at 42% 7%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 51% 52%, #b9ccff 50%, transparent 52%),
        radial-gradient(1.5px 1.5px at 58% 93%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 66% 22%, #cfe0ff 50%, transparent 52%),
        radial-gradient(1.2px 1.2px at 74% 71%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 83% 9%, #b9ccff 50%, transparent 52%),
        radial-gradient(1.4px 1.4px at 91% 47%, #fff 50%, transparent 52%),
        radial-gradient(1px 1px at 96% 84%, #cfe0ff 50%, transparent 52%),
        radial-gradient(1px 1px at 37% 46%, #9fb8ee 50%, transparent 52%),
        radial-gradient(1px 1px at 9% 91%, #fff 50%, transparent 52%),
        radial-gradient(60% 45% at 82% 8%, rgba(96,64,210,.26), transparent 70%),
        radial-gradient(55% 50% at 10% 78%, rgba(20,120,210,.20), transparent 70%),
        radial-gradient(45% 40% at 52% 44%, rgba(40,70,160,.18), transparent 72%);
    background-attachment: fixed;
    font-family: 'Chakra Petch', system-ui, sans-serif;
}
[data-testid="stHeader"] {background: transparent;}
.block-container {padding: 1rem 1.2rem 1.5rem; max-width: 1500px;}
h1, h2, h3, h4 {font-family: 'Chakra Petch', sans-serif !important; letter-spacing: .04em;}

/* Paneles: cada st.container(key="pn_...") */
[class*="st-key-pn_"] {
    background: rgba(9,15,29,.74);
    border: 1px solid rgba(120,170,255,.17);
    border-radius: 10px;
    padding: 12px 14px;
    backdrop-filter: blur(6px);
}
.pt, .stMarkdown p.pt {font: 600 11px/1.2 'Chakra Petch', sans-serif !important; letter-spacing: .14em !important; text-transform: uppercase;
     color: #7F93B4 !important; margin: 0 0 10px !important; display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.mn {font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums;}
.g {color: #3EE89A;} .y {color: #F5C84B;} .r {color: #FF5F6D;} .b {color: #8FB4FF;} .dim {color: #7F93B4;}
.pill {font: 600 10px 'Chakra Petch'; letter-spacing: .12em; padding: 4px 8px; border-radius: 999px; border: 1px solid; white-space: nowrap;}
.pill.g {border-color: rgba(62,232,154,.5); background: rgba(62,232,154,.1);}
.pill.y {border-color: rgba(245,200,75,.5); background: rgba(245,200,75,.1);}
.pill.r {border-color: rgba(255,95,109,.5); background: rgba(255,95,109,.1);}
.pill.b {border-color: rgba(143,180,255,.5); background: rgba(143,180,255,.1);}
.row {display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 7px 0;
      border-bottom: 1px solid rgba(120,170,255,.09); font-size: 13px;}
.row:last-child {border-bottom: 0;}
.bar {height: 5px; border-radius: 3px; background: rgba(120,170,255,.14); overflow: hidden;}
.bar > i {display: block; height: 100%; border-radius: 3px;}

/* Encabezado */
.pc-top {display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px;}
.pc-brand {display: flex; align-items: center; gap: 12px;}
.pc-brand img {height: 44px; width: auto; object-fit: contain;}
.pc-brand .t1 {font: 700 15px 'Chakra Petch'; letter-spacing: .2em;}
.pc-brand .t2 {font: 500 11px 'Chakra Petch'; letter-spacing: .18em; color: #7F93B4;}

/* Cuenta y billeteras */
.pc-acct {display: flex; flex-wrap: wrap; gap: 8px 22px; align-items: baseline; margin: 2px 0 12px;
          padding: 10px 14px; border: 1px solid rgba(120,170,255,.14); border-radius: 10px; background: rgba(9,15,29,.55);}
.pc-acct .k {font: 600 10px 'Chakra Petch'; letter-spacing: .16em; color: #7F93B4; text-transform: uppercase;}
.pc-acct .v {font: 500 15px 'JetBrains Mono', monospace;}
.pc-acct .big {font: 700 26px 'JetBrains Mono', monospace; color: #E8EEF5;}
.pc-wallets {display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px;}
.pc-wallet {border-radius: 10px; padding: 14px 18px; background: rgba(9,15,29,.74); border: 1px solid; backdrop-filter: blur(6px);}
.pc-wallet.s {border-color: rgba(62,232,154,.45); box-shadow: 0 0 28px rgba(62,232,154,.10);}
.pc-wallet.c {border-color: rgba(143,180,255,.42); box-shadow: 0 0 28px rgba(100,140,255,.10);}
.pc-wallet .num {font: 700 34px/1.05 'JetBrains Mono', monospace; letter-spacing: -.02em; margin: 2px 0 8px;}
.pc-wallet.s .num {color: #3EE89A; text-shadow: 0 0 18px rgba(62,232,154,.45);}
.pc-wallet.c .num {color: #8FB4FF; text-shadow: 0 0 18px rgba(100,150,255,.45);}
.pc-wallet .sub {font: 500 13px 'JetBrains Mono', monospace;}

/* Asteroide */
.pc-chips {display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;}
.pc-chip {font: 500 11px 'JetBrains Mono', monospace; padding: 3px 7px; border-radius: 4px; border: 1px solid;}
.pc-chip.g {border-color: rgba(62,232,154,.5); color: #3EE89A;}
.pc-chip.y {border-color: rgba(245,200,75,.5); color: #F5C84B;}
.pc-chip.r {border-color: rgba(255,95,109,.5); color: #FF5F6D;}
.pc-count {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px;}
.pc-count > div {background: rgba(5,9,19,.6); border: 1px solid rgba(120,170,255,.12); border-radius: 8px; padding: 8px; text-align: center;}
.pc-count b {display: block; font: 700 22px 'JetBrains Mono', monospace;}
.pc-count span {font: 500 10px 'Chakra Petch'; letter-spacing: .1em; color: #7F93B4;}

/* Cinta de actividad */
.pc-ticker {overflow: hidden; white-space: nowrap;}
.pc-track {display: inline-flex; gap: 34px; animation: pcmarq 70s linear infinite; padding-right: 34px;}
.pc-tr {display: inline-flex; gap: 8px; align-items: baseline; font: 500 12px 'JetBrains Mono', monospace;}
@keyframes pcmarq {to {transform: translateX(-50%);}}
@media (prefers-reduced-motion: reduce) {.pc-track {animation: none;}}

/* Móvil: el asteroide sube arriba de los paneles laterales */
@media (max-width: 640px) {
    .block-container {padding: .6rem .6rem 1rem;}
    .pc-wallet {padding: 10px 12px;}
    .pc-wallet .num {font-size: 21px;}
    .pc-wallet .sub {font-size: 11px;}
    .pc-acct {gap: 6px 14px; padding: 8px 10px;}
    .pc-acct .big {font-size: 20px;}
    .pc-acct .v {font-size: 13px;}
    [data-testid="stColumn"]:has(.st-key-col_mid), [data-testid="column"]:has(.st-key-col_mid) {order: -1;}
    [class*="st-key-pn_candles"] [data-testid="stHorizontalBlock"] {flex-direction: row !important; flex-wrap: nowrap !important; gap: .5rem !important;}
    [class*="st-key-pn_candles"] [data-testid="stColumn"], [class*="st-key-pn_candles"] [data-testid="column"] {min-width: 0 !important; flex: 1 1 0 !important; width: auto !important;}
}
/* Tablas y métricas con el mismo aire */
[data-testid="stDataFrame"] {border: 1px solid rgba(120,170,255,.14); border-radius: 8px;}
.st-key-back_home button {font-family: 'Chakra Petch', sans-serif; letter-spacing: .12em; font-size: 12px; padding: 2px 12px; min-height: 0;
                          border-color: rgba(120,170,255,.28); color: #9FB4D6; background: rgba(9,15,29,.6);}
.st-key-back_home button:hover {border-color: rgba(62,232,154,.6); color: #3EE89A;}
.stTabs [data-baseweb="tab-list"] {gap: 4px;}
.stTabs [data-baseweb="tab"] {font-family: 'Chakra Petch', sans-serif; letter-spacing: .06em;}
.stTabs [aria-selected="true"] {color: #3EE89A !important;}
</style>
""", unsafe_allow_html=True)

init_db()

def img_b64(filename: str):
    """Imagen de static/ embebida en base64 (no depende de que Streamlit sirva el archivo)."""
    try:
        with open(os.path.join(STATIC_DIR, filename), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# =========================================================================
# ACCESO: el panel es público (demo en paper). Solo las acciones de control (kill switch, reactivar
# cripto) piden la contraseña de administrador: ADMIN_PASSWORD, o APP_PASSWORD si ya la tenías puesta.
# Sin ninguna de las dos, los controles quedan deshabilitados.
# =========================================================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or os.getenv("APP_PASSWORD") or ""

# =========================================================================
# DATOS
# =========================================================================
def load_table(query: str) -> pd.DataFrame:
    """Lee una tabla con tope de tiempo: si algo la tiene bloqueada (por ejemplo un backtest que está
    guardando datos), esta consulta falla en unos segundos en vez de congelar todo el panel."""
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '20s'")
        cur.execute("SET lock_timeout = '4s'")
        conn.commit()
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


@st.cache_data(ttl=30, show_spinner=False)
def fetch_positions():
    """Posiciones abiertas como dicts simples (cacheables). kind: 'stock' | 'crypto'."""
    try:
        out = []
        for p in get_broker().get_open_positions():
            out.append({
                "symbol": p.symbol,
                "kind": "crypto" if AlpacaBroker.is_crypto_position(p) else "stock",
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "current_price": float(p.current_price),
            })
        return out, None
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_bars(symbol: str, minutes: int, lookback: int):
    try:
        return get_broker().get_recent_bars(symbol, minutes, lookback)
    except Exception:
        return None


def fmt_qty(q) -> str:
    q = float(q)
    return str(int(q)) if q.is_integer() else f"{q:.6f}".rstrip("0").rstrip(".")


def money(v: float, sign: bool = False) -> str:
    s = f"{abs(v):,.2f}"
    if sign:
        return f"{'+' if v >= 0 else '−'}${s}"
    return f"{'−' if v < 0 else ''}${s}"


def tone(v: float) -> str:
    return "g" if v >= 0 else "r"


def classify(signal: str, d: dict):
    """Devuelve (tono, fuerte). g = bueno, y = intermedio, r = malo. Fuerte = señal de acción real."""
    if signal == "buy":
        return "g", True
    if signal == "sell":
        return "r", True
    fast, slow, rsi = d.get("sma_fast"), d.get("sma_slow"), d.get("rsi")
    if fast and slow:
        spread = (fast - slow) / slow
        if spread > 0.002 and (rsi is None or rsi < 70):
            return "g", False
        if spread < -0.002:
            return "r", False
    return "y", False


def latest_signals() -> list:
    """Última lectura guardada por el agente para cada símbolo."""
    try:
        df = load_table(
            "SELECT DISTINCT ON (symbol) symbol, signal, details, ts FROM signals "
            "WHERE id > (SELECT COALESCE(MAX(id), 0) - 5000 FROM signals) ORDER BY symbol, id DESC"
        )
    except Exception:
        return []
    out = []
    for _, row in df.iterrows():
        try:
            d = json.loads(row["details"]) if row["details"] else {}
        except Exception:
            d = {}
        t, strong = classify(row["signal"], d)
        out.append({"symbol": row["symbol"], "signal": row["signal"], "tone": t, "strong": strong,
                    "rsi": d.get("rsi"), "price": d.get("last_close"), "ts": row["ts"],
                    "reason": d.get("reason") or ""})
    return out


SCREENER_STOCKS = (
    "AAPL,MSFT,GOOGL,NVDA,TSLA,AMZN,META,XOM,CVX,COP,SLB,OXY,"
    "CAT,DE,HON,GE,BA,ALB,SQM,LAC,RIO,YPF,GGAL,PAM,BMA,VIST,MELI,GLOB,SPY,QQQ,DIA"
)
SCREENER_CRYPTO = "BTC/USD,ETH/USD,SOL/USD,LTC/USD,DOGE/USD,AVAX/USD,LINK/USD"


@st.cache_data(ttl=300, show_spinner="Escaneando el universo del Screener… / Scanning the Screener universe…")
def scan_universe(symbols: tuple) -> list:
    out = []
    for sym in symbols:
        try:
            df = get_broker().get_recent_bars(sym, timeframe_for(sym), Config.LOOKBACK_BARS)
            res = compute_signal(df)
            t, strong = classify(res["signal"], res)
            out.append({"symbol": sym, "signal": res["signal"], "tone": t, "strong": strong,
                        "rsi": res.get("rsi"), "price": res.get("last_close"), "ts": "",
                        "reason": res.get("reason") or ""})
        except Exception:
            continue
    return out


# =========================================================================
# ASTEROIDE 3D (Three.js desde cdnjs; cada punto pertenece a un símbolo y toma el color de su señal)
# =========================================================================
ASTEROID_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;background:transparent;overflow:hidden;font-family:'JetBrains Mono',monospace}
#wrap{position:relative;width:100%;height:__H__px}
canvas{display:block;width:100%;height:100%;touch-action:pan-y;cursor:crosshair}
#hov{position:absolute;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;border:1.5px solid rgba(255,255,255,.9);
     box-shadow:0 0 10px rgba(255,255,255,.55);pointer-events:none;display:none}
#tip{z-index:2;display:none}
.tag{position:absolute;transform:translate(-50%,-50%);font:500 11px 'JetBrains Mono',monospace;padding:2px 6px;border-radius:4px;
     border:1px solid;background:rgba(4,6,13,.86);white-space:nowrap;pointer-events:none}
.tag.g{color:#3EE89A;border-color:rgba(62,232,154,.55)}.tag.r{color:#FF5F6D;border-color:rgba(255,95,109,.55)}.tag.y{color:#F5C84B;border-color:rgba(245,200,75,.55)}
#fallback{display:none;color:#7F93B4;font:13px sans-serif;text-align:center;padding-top:40%}
#ring{position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;border:2px solid #fff;
      box-shadow:0 0 14px currentColor;pointer-events:none;display:none}
#card{position:absolute;left:10px;right:10px;bottom:10px;max-width:340px;margin:0 auto;padding:10px 12px;border-radius:10px;
      background:rgba(6,10,22,.93);border:1px solid rgba(127,147,180,.35);color:#DCE6F7;font-size:12px;line-height:1.45;
      display:none;backdrop-filter:blur(6px)}
#card .hd{display:flex;align-items:center;gap:8px;margin-bottom:4px}
#card .sym{font:700 17px 'Chakra Petch','JetBrains Mono',monospace;letter-spacing:.5px}
#card .pill{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid;letter-spacing:.6px}
#card .g{color:#3EE89A;border-color:rgba(62,232,154,.55)}#card .r{color:#FF5F6D;border-color:rgba(255,95,109,.55)}#card .y{color:#F5C84B;border-color:rgba(245,200,75,.55)}
#card .x{margin-left:auto;cursor:pointer;color:#7F93B4;font-size:16px;line-height:1;padding:0 4px}
#card .kv{display:flex;gap:14px;color:#9FB1CF;margin:2px 0 4px}#card .kv b{color:#fff;font-weight:600}
#card .why{color:#B8C7E3}
#card > .pill{display:inline-block}
#card .pos{margin-top:8px;padding-top:7px;border-top:1px solid rgba(127,147,180,.22)}
#card .ph{display:flex;align-items:center;gap:8px;color:#9FB1CF;margin-bottom:2px}
#card .pill.b{color:#6FB6FF;border-color:rgba(111,182,255,.6)}
#card .plr{font-weight:700;font-size:13px}#card .dimr{color:#6F82A3}
.tag.b{color:#6FB6FF;border-color:rgba(111,182,255,.6)}
</style></head><body>
<div id="wrap"><canvas id="c"></canvas><div id="labels"></div><div id="hov"></div><div class="tag" id="tip"></div><div id="ring"></div>
<div id="card"></div><div id="fallback">No se pudo cargar el visor 3D.</div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
(function(){
var items = __ITEMS__;
if (typeof THREE === "undefined" || !items.length) { document.getElementById("fallback").style.display = "block"; return; }
var COL = {g: 0x3ee89a, y: 0xf5c84b, r: 0xff5f6d};
var wrap = document.getElementById("wrap"), canvas = document.getElementById("c"), labelsEl = document.getElementById("labels");
var renderer = new THREE.WebGLRenderer({canvas: canvas, alpha: true, antialias: true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
var scene = new THREE.Scene();
var camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
var group = new THREE.Group(); scene.add(group);

// aleatorio determinista (el asteroide no "salta" en cada recarga si los datos no cambian)
var seed = 7; function rnd(){ seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
function gauss(){ return (rnd() + rnd() + rnd() + rnd() - 2) / 0.58; }

function fib(i, n){ var y = 1 - (i / Math.max(n - 1, 1)) * 2, r = Math.sqrt(Math.max(0, 1 - y * y)), th = Math.PI * (3 - Math.sqrt(5)) * i;
  return new THREE.Vector3(Math.cos(th) * r, y, Math.sin(th) * r); }
function lumpy(d){ return 1 + 0.17 * Math.sin(3.1 * d.x + 1.0) * Math.cos(2.3 * d.y) + 0.11 * Math.sin(5.0 * d.z + 2.0) + 0.07 * Math.sin(8.0 * d.x * d.y); }

var S = items.length, perSym = Math.max(26, Math.min(240, Math.floor(1100 / S)));
var sigma = Math.max(0.22, Math.sqrt(4 * Math.PI / S) / 2.4);
var P = [], pos = [], col = [], centroids = [], owner = [];
items.forEach(function(it, si){
  var c = fib(si, S).multiplyScalar(1), acc = new THREE.Vector3(), n = 0;
  for (var j = 0; j < perSym; j++){
    var d = c.clone().add(new THREE.Vector3(gauss(), gauss(), gauss()).multiplyScalar(sigma)).normalize();
    var r = lumpy(d) * (0.62 + 0.38 * Math.sqrt(rnd()));
    var v = new THREE.Vector3(d.x * 1.12, d.y * 0.92, d.z).multiplyScalar(r);
    P.push(v); owner.push(si); pos.push(v.x, v.y, v.z);
    var cc = new THREE.Color(COL[it.tone]); var k = 0.55 + 0.45 * rnd(); col.push(cc.r * k, cc.g * k, cc.b * k);
    acc.add(v); n++;
  }
  centroids.push(acc.multiplyScalar(1 / n));
});
// polvo estelar alrededor (puntos chicos, aparte: no se pueden elegir)
var dpos = [], dcol = [];
for (var i = 0; i < 260; i++){
  var dd = new THREE.Vector3(gauss(), gauss(), gauss()).normalize().multiplyScalar(1.5 + rnd() * 1.4);
  dpos.push(dd.x, dd.y, dd.z); var t = 0.25 + 0.5 * rnd(); dcol.push(0.45 * t, 0.62 * t, 1.0 * t);
}
// disco más sólido que antes: los puntos se ven más grandes y definidos
function dot(){ var c = document.createElement("canvas"); c.width = c.height = 64; var x = c.getContext("2d");
  var g = x.createRadialGradient(32, 32, 0, 32, 32, 32); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.5, "rgba(255,255,255,.95)"); g.addColorStop(0.8, "rgba(255,255,255,.4)"); g.addColorStop(1, "rgba(255,255,255,0)");
  x.fillStyle = g; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); }
var dotTex = dot();
var geo = new THREE.BufferGeometry();
geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
var baseCol = col.slice();
var BASE = 0.115;
var mat = new THREE.PointsMaterial({size: BASE, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true});
group.add(new THREE.Points(geo, mat));
var dgeo = new THREE.BufferGeometry();
dgeo.setAttribute("position", new THREE.Float32BufferAttribute(dpos, 3)); dgeo.setAttribute("color", new THREE.Float32BufferAttribute(dcol, 3));
group.add(new THREE.Points(dgeo, new THREE.PointsMaterial({size: 0.05, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true})));

// hilos entre puntos vecinos
var lp = [], lc = [];
for (var a = 0; a < P.length; a++){
  var best = [];
  for (var b = 0; b < P.length; b += 1){
    if (a === b) continue; var dist = P[a].distanceToSquared(P[b]); if (dist < 0.035) best.push([dist, b]);
  }
  best.sort(function(m, n){ return m[0] - n[0]; });
  for (var q = 0; q < Math.min(2, best.length); q++){
    var bb = best[q][1]; if (bb < a) continue;
    lp.push(P[a].x, P[a].y, P[a].z, P[bb].x, P[bb].y, P[bb].z);
    lc.push(0.35, 0.5, 0.9, 0.35, 0.5, 0.9);
  }
}
var lg = new THREE.BufferGeometry();
lg.setAttribute("position", new THREE.Float32BufferAttribute(lp, 3)); lg.setAttribute("color", new THREE.Float32BufferAttribute(lc, 3));
group.add(new THREE.LineSegments(lg, new THREE.LineBasicMaterial({vertexColors: true, transparent: true, opacity: 0.16, depthWrite: false})));

// etiquetas: símbolos con señal real (compra/venta) y los que tenés en cartera (marcados con ◆), máximo 10
var tags = [];
items.map(function(it, i){ return {it: it, i: i}; }).filter(function(o){ return o.it.strong || o.it.pos; }).slice(0, 10).forEach(function(o){
  var el = document.createElement("div"); el.className = "tag " + (o.it.pos ? "b" : o.it.tone);
  el.textContent = (o.it.pos ? "\\u25C6 " : "") + o.it.symbol + (o.it.strong ? (o.it.tone === "g" ? " \\u25B2" : " \\u25BC") : "");
  labelsEl.appendChild(el); tags.push({el: el, c: centroids[o.i]});
});

group.rotation.x = 0.35;
var auto = true, drag = false, lastX = 0, downX = 0, downY = 0, moved = 0, selected = -1, selPt = -1, hoverIdx = -1, resumeT = null;
var ringEl = document.getElementById("ring"), cardEl = document.getElementById("card"), hovEl = document.getElementById("hov"), tipEl = document.getElementById("tip");
var SIGTXT = {buy: ["COMPRA", "g"], sell: ["VENTA", "r"], hold: ["MANTENER", "y"]};
var TONETXT = {g: "Tendencia alcista", y: "Sin dirección clara", r: "Tendencia bajista"};

function paint(){
  // el símbolo elegido queda brillante; el resto se atenúa
  var arr = geo.attributes.color.array;
  for (var i = 0; i < baseCol.length; i++){
    var o = Math.floor(i / 3), f = 1;
    if (selected >= 0 && o < owner.length) f = (owner[o] === selected) ? 1.6 : 0.3;
    arr[i] = Math.min(1, baseCol[i] * f);
  }
  geo.attributes.color.needsUpdate = true;
}
function showCard(si){
  var it = items[si], sg = SIGTXT[it.signal] || SIGTXT.hold;
  cardEl.innerHTML = "";
  function el(tag, cls, txt){ var e = document.createElement(tag); if (cls) e.className = cls; if (txt !== undefined) e.textContent = txt; return e; }
  var hd = el("div", "hd");
  hd.appendChild(el("span", "sym", it.symbol));
  hd.appendChild(el("span", "pill " + sg[1], "SEÑAL: " + sg[0]));
  var x = el("span", "x", "\\u00D7"); x.onclick = function(){ select(-1); }; hd.appendChild(x);
  cardEl.appendChild(hd);
  var kv = el("div", "kv");
  var pr = el("span"); pr.appendChild(document.createTextNode("Precio ")); pr.appendChild(el("b", "", it.price ? "$" + Number(it.price).toLocaleString("en-US", {maximumFractionDigits: 4}) : "—")); kv.appendChild(pr);
  var rs = el("span"); rs.appendChild(document.createTextNode("RSI ")); rs.appendChild(el("b", "", it.rsi == null ? "—" : Number(it.rsi).toFixed(0))); kv.appendChild(rs);
  cardEl.appendChild(kv);
  cardEl.appendChild(el("div", "pill " + it.tone, TONETXT[it.tone]));
  var ps = el("div", "pos");
  if (it.pos){
    var pc = it.pos.pl >= 0 ? "g" : "r", sgn = it.pos.pl >= 0 ? "+" : "\\u2212";
    var head = el("div", "ph"); head.appendChild(el("span", "pill b", "EN CARTERA"));
    head.appendChild(el("span", "", (it.pos.kind === "crypto" ? "cripto" : "acciones")));
    ps.appendChild(head);
    var q = Number(it.pos.qty), qs = Number.isInteger(q) ? String(q) : q.toFixed(6).replace(/0+$/, "").replace(/\\.$/, "");
    var l1 = el("div", "kv"); var a1 = el("span"); a1.appendChild(document.createTextNode("Tenés ")); a1.appendChild(el("b", "", qs)); l1.appendChild(a1);
    var a2 = el("span"); a2.appendChild(document.createTextNode("Valor ")); a2.appendChild(el("b", "", "$" + Number(it.pos.value).toLocaleString("en-US", {maximumFractionDigits: 2}))); l1.appendChild(a2);
    ps.appendChild(l1);
    var l2 = el("div", "plr " + pc, "P&L abierto " + sgn + "$" + Math.abs(it.pos.pl).toLocaleString("en-US", {maximumFractionDigits: 2}) + "  (" + sgn + Math.abs(it.pos.pl_pct).toFixed(2) + "%)");
    ps.appendChild(l2);
  } else {
    ps.appendChild(el("div", "dimr", "Sin posición abierta"));
  }
  cardEl.appendChild(ps);
  var why = it.reason || "Sin motivo registrado en la última lectura.";
  var w = el("div", "why", why); w.style.marginTop = "6px"; cardEl.appendChild(w);
  if (it.ts){ var t = el("div", "", "Lectura: " + it.ts); t.style.cssText = "color:#6F82A3;font-size:10px;margin-top:4px"; cardEl.appendChild(t); }
  cardEl.style.display = "block";
}
function select(si, pt){
  selected = si; selPt = (pt === undefined ? -1 : pt); paint();
  if (si < 0){ cardEl.style.display = "none"; ringEl.style.display = "none"; auto = true; return; }
  showCard(si);
  ringEl.style.color = "#" + COL[items[si].tone].toString(16).padStart(6, "0");
  ringEl.style.display = "block";
}
// punto exacto bajo el cursor/dedo (radio en píxeles; los de adelante ganan a los de atrás)
function pickPoint(cx, cy, radius){
  var rect = canvas.getBoundingClientRect(), w = rect.width, h = rect.height, mx = cx - rect.left, my = cy - rect.top;
  group.updateMatrixWorld();
  var best = -1, bd = radius * radius, vv = new THREE.Vector3();
  for (var i = 0; i < P.length; i++){
    vv.copy(P[i]).applyMatrix4(group.matrixWorld);
    var front = vv.z > -0.35; vv.project(camera);
    var dx = (vv.x * 0.5 + 0.5) * w - mx, dy = (-vv.y * 0.5 + 0.5) * h - my, d = dx * dx + dy * dy + (front ? 0 : 400);
    if (d < bd){ bd = d; best = i; }
  }
  return best;
}
function setHover(i){
  hoverIdx = i;
  if (i < 0){ hovEl.style.display = "none"; tipEl.style.display = "none"; return; }
  var it = items[owner[i]];
  tipEl.className = "tag " + it.tone;
  tipEl.textContent = it.symbol + (it.strong ? (it.tone === "g" ? " \\u25B2" : " \\u25BC") : "");
  hovEl.style.display = "block"; tipEl.style.display = "block";
}
// si no cae sobre ningún punto, la nube de símbolo más cercana
function pickCluster(cx, cy){
  var rect = canvas.getBoundingClientRect(), w = rect.width, h = rect.height, mx = cx - rect.left, my = cy - rect.top, vv = new THREE.Vector3();
  group.updateMatrixWorld();
  var cb = -1, cd = 60 * 60;
  for (var s = 0; s < centroids.length; s++){
    vv.copy(centroids[s]).applyMatrix4(group.matrixWorld); vv.project(camera);
    var ex = (vv.x * 0.5 + 0.5) * w - mx, ey = (-vv.y * 0.5 + 0.5) * h - my, e = ex * ex + ey * ey;
    if (e < cd){ cd = e; cb = s; }
  }
  return cb;
}
canvas.addEventListener("pointerdown", function(e){ setHover(-1); drag = true; auto = false; lastX = e.clientX; downX = e.clientX; downY = e.clientY; moved = 0; if (resumeT) clearTimeout(resumeT); });
canvas.addEventListener("pointerleave", function(){ if (!drag) setHover(-1); });
window.addEventListener("pointerup", function(e){
  if (!drag) return; drag = false;
  if (moved < 6 && e.target === canvas){
    var pi = pickPoint(e.clientX, e.clientY, e.pointerType === "mouse" ? 16 : 28);
    var s = pi >= 0 ? owner[pi] : pickCluster(e.clientX, e.clientY);
    select(s, pi);   // si tocás el vacío (s = -1) se cierra la ficha
  }
  // mientras hay una ficha abierta, el asteroide queda quieto para poder leerla
  resumeT = setTimeout(function(){ if (selected < 0) auto = true; }, 2500);
});
// en el celular, si el navegador toma el gesto para hacer scroll, el arrastre se cancela: hay que soltarlo igual
window.addEventListener("pointercancel", function(){
  drag = false;
  resumeT = setTimeout(function(){ if (selected < 0) auto = true; }, 800);
});
window.addEventListener("pointermove", function(e){
  if (drag){ moved = Math.max(moved, Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY)); group.rotation.y += (e.clientX - lastX) * 0.008; lastX = e.clientX; return; }
  // con mouse: resalta el punto bajo el cursor y frena el giro para poder hacerle clic
  if (e.pointerType === "mouse" && e.target === canvas) setHover(pickPoint(e.clientX, e.clientY, 14));
});

function resize(){
  var w = wrap.clientWidth, h = wrap.clientHeight; renderer.setSize(w, h, false);
  camera.aspect = w / h; camera.position.z = Math.max(3.3, 3.3 / Math.min(1, camera.aspect) * 0.92); camera.updateProjectionMatrix();
}
resize(); window.addEventListener("resize", resize);
var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
var v = new THREE.Vector3();
function frame(t){
  // con "Reducir movimiento" activado (común en iPhone) gira más lento en vez de quedarse quieto
  if (auto && hoverIdx < 0) group.rotation.y += reduce ? 0.0012 : 0.0028;
  mat.size = reduce ? BASE : BASE + 0.008 * Math.sin(t / 700);
  renderer.render(scene, camera);
  group.updateMatrixWorld();
  var w = wrap.clientWidth, h = wrap.clientHeight;
  tags.forEach(function(tg){
    v.copy(tg.c).applyMatrix4(group.matrixWorld);
    var front = v.z > -0.15; v.project(camera);
    tg.el.style.left = ((v.x * 0.5 + 0.5) * w) + "px"; tg.el.style.top = ((-v.y * 0.5 + 0.5) * h) + "px";
    tg.el.style.opacity = front ? 1 : 0.18;
  });
  if (selected >= 0){
    // el aro marca el punto exacto que tocaste (o el centro de la nube si tocaste entre puntos)
    v.copy(selPt >= 0 ? P[selPt] : centroids[selected]).applyMatrix4(group.matrixWorld); var fr = v.z > -0.2; v.project(camera);
    ringEl.style.left = ((v.x * 0.5 + 0.5) * w) + "px"; ringEl.style.top = ((-v.y * 0.5 + 0.5) * h) + "px";
    ringEl.style.opacity = fr ? 1 : 0.25;
  }
  if (hoverIdx >= 0){
    v.copy(P[hoverIdx]).applyMatrix4(group.matrixWorld); v.project(camera);
    var hx = (v.x * 0.5 + 0.5) * w, hy = (-v.y * 0.5 + 0.5) * h;
    hovEl.style.left = hx + "px"; hovEl.style.top = hy + "px";
    tipEl.style.left = hx + "px"; tipEl.style.top = (hy - 22) + "px";
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
})();
</script></body></html>
"""


def asteroid(items: list, height: int = 470, positions: list = None):
    held = {}
    for p in (positions or []):
        cost = p["market_value"] - p["unrealized_pl"]
        held[norm_symbol(p["symbol"])] = {
            "qty": p["qty"], "value": p["market_value"], "pl": p["unrealized_pl"],
            "pl_pct": (p["unrealized_pl"] / cost * 100) if cost else 0.0, "kind": p["kind"],
        }
    payload = [{"symbol": i["symbol"], "tone": i["tone"], "strong": bool(i["strong"]),
                "signal": i.get("signal") or "hold", "price": i.get("price"), "rsi": i.get("rsi"),
                "reason": str(i.get("reason") or "")[:240], "ts": str(i.get("ts") or "")[:16].replace("T", " "),
                "pos": held.get(norm_symbol(i["symbol"]))}
               for i in items]
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = ASTEROID_HTML.replace("__H__", str(height)).replace("__ITEMS__", data)
    components.html(html, height=height)


# =========================================================================
# GRÁFICOS (estilo oscuro)
# =========================================================================
def style_fig(fig, height, margin=None):
    fig.update_layout(
        height=height, margin=margin or dict(l=0, r=0, t=10, b=10),
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono, monospace", color=DIM, size=10),
    )
    return fig


def sma(series, n):
    return series.rolling(n).mean()


def rsi_series(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - (100 / (1 + avg_gain / avg_loss.replace(0, 1e-10)))


def mini_candle(df, bars=60):
    f, s = sma(df["close"], 10), sma(df["close"], 30)
    d = df.tail(bars)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=d.index, open=d["open"], high=d["high"], low=d["low"], close=d["close"],
        increasing_line_color=G, decreasing_line_color=R, increasing_fillcolor=G, decreasing_fillcolor=R,
        line=dict(width=1), showlegend=False))
    fig.add_trace(go.Scatter(x=d.index, y=f.tail(bars), line=dict(color=B, width=1.1), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=d.index, y=s.tail(bars), line=dict(color=Y, width=1.1), showlegend=False, hoverinfo="skip"))
    style_fig(fig, 150, dict(l=0, r=0, t=0, b=0))
    fig.update_layout(xaxis_rangeslider_visible=False, xaxis=dict(visible=False),
                      yaxis=dict(side="right", showgrid=True, gridcolor="rgba(255,255,255,.06)", tickfont=dict(size=9)))
    return fig


# =========================================================================
# LANDING (entrada pública) o PANEL EN VIVO. El enlace ?panel=1 abre el panel directo.
# =========================================================================
def admin_login(pw: str) -> bool:
    """Valida la contraseña de administrador; si es correcta, esta sesión puede usar los controles."""
    if ADMIN_PASSWORD and hmac.compare_digest((pw or "").encode(), ADMIN_PASSWORD.encode()):
        st.session_state["admin"] = True
        return True
    time.sleep(1)   # freno simple contra adivinar la clave a fuerza bruta
    return False


def go_panel():
    st.session_state["view"] = "panel"
    st.query_params["panel"] = "1"


def go_home():
    st.session_state["view"] = "landing"
    if "panel" in st.query_params:
        del st.query_params["panel"]


if "view" not in st.session_state:
    st.session_state["view"] = "panel" if st.query_params.get("panel") else "landing"

if st.session_state["view"] == "landing":
    _eq = pd.DataFrame()
    try:
        _eq = load_table("SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT 500")
    except Exception:
        pass
    _pos, _ = fetch_positions()
    _bt = pd.DataFrame()
    try:
        _bt = load_table("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 300")
    except Exception:
        pass
    render_landing(
        bt_df=_bt, img_b64=img_b64, equity_df=_eq, sigs=latest_signals(), positions=_pos,
        asteroid_fn=asteroid, style_fig=style_fig, on_enter=go_panel, fetch_bars=fetch_bars,
        admin_login=admin_login, admin_enabled=bool(ADMIN_PASSWORD), auto_top=_auto_top(),
    )
    st.stop()

with st.container(key="back_home"):
    st.button("← Inicio", on_click=go_home)

# =========================================================================
# ENCABEZADO, CUENTA Y BILLETERAS
# =========================================================================
kill_active = get_state("kill_switch") == "active"
crypto_halt_txt = None
try:
    _h = get_state("crypto_halt") or ""
    if "|" in _h:
        _k, _r = _h.split("|", 1)
        if not (_k.startswith("day:") and _k[4:] != datetime.now(timezone.utc).strftime("%Y-%m-%d")):
            crypto_halt_txt = _r
except Exception:
    pass
logo64 = logo_b64()
logo_html = f'<img src="data:image/png;base64,{logo64}">' if logo64 else ""
mode_pill = '<span class="pill y">PAPER · SIN DINERO REAL</span>' if Config.IS_PAPER else '<span class="pill r">LIVE · DINERO REAL</span>'
state_pill = '<span class="pill r">DETENIDO · KILL SWITCH</span>' if kill_active else '<span class="pill g">OPERANDO</span>'
st.markdown(
    f'<div class="pc-top"><div class="pc-brand">{logo_html}<div><div class="t1">PUMA CODE</div>'
    f'<div class="t2">TRADING AGENT</div></div></div>'
    f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">{mode_pill}{state_pill}'
    f'<span class="mn dim" style="font-size:12px">{datetime.now(timezone.utc).strftime("%H:%M:%S")} UTC</span></div></div>',
    unsafe_allow_html=True,
)

equity_df = load_table("SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT 500")
positions, positions_error = fetch_positions()

if not equity_df.empty:
    last = equity_df.iloc[0]
    equity_now = float(last["equity"])
    cash_now = float(last["cash"]) if pd.notna(last["cash"]) else 0.0
    daily_pct = float(last["daily_pl_pct"] or 0)
    daily_usd = equity_now - equity_now / (1 + daily_pct) if daily_pct > -1 else 0.0
    dd_now = float(last["drawdown_pct"] or 0)
else:
    equity_now = cash_now = daily_pct = daily_usd = dd_now = 0.0

st.markdown(
    f'<div class="pc-acct">'
    f'<div><div class="k">Equity total</div><div class="big">{money(equity_now) if not equity_df.empty else "sin datos"}</div></div>'
    f'<div><div class="k">Efectivo</div><div class="v">{money(cash_now)}</div></div>'
    f'<div><div class="k">Hoy</div><div class="v {tone(daily_usd)}">{money(daily_usd, True)} ({daily_pct*100:+.2f}%)</div></div>'
    f'<div><div class="k">Drawdown / límite</div><div class="v">{dd_now*100:.2f}% / {Config.MAX_DRAWDOWN_PCT*100:.0f}%</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)


def wallet_card(kind: str) -> str:
    mine = [p for p in positions if p["kind"] == kind]
    invested = sum(p["market_value"] for p in mine)
    upl = sum(p["unrealized_pl"] for p in mine)
    cost = invested - upl
    pct = (upl / cost * 100) if cost else 0.0
    cap = Config.MAX_CRYPTO_POSITIONS if kind == "crypto" else Config.MAX_OPEN_POSITIONS
    share = (invested / equity_now * 100) if equity_now else 0.0
    label, cls = ("Cripto", "c") if kind == "crypto" else ("Acciones", "s")
    extra = ""
    if kind == "crypto" and not Config.CRYPTO_SYMBOLS:
        extra = '<div class="sub dim" style="margin-top:6px">Cripto desactivada (CRYPTO_SYMBOLS vacío)</div>'
    return (
        f'<div class="pc-wallet {cls}"><p class="pt" style="margin-bottom:6px"><span>{label} · invertido</span>'
        f'<span class="mn" style="white-space:nowrap">{len(mine)}/{cap}</span></p>'
        f'<div class="num">{money(invested)}</div>'
        f'<div class="sub"><span class="{tone(upl)}">{money(upl, True)} ({pct:+.2f}%)</span> '
        f'<span class="dim">· {share:.1f}% del equity</span></div>{extra}</div>'
    )


st.markdown(f'<div class="pc-wallets">{wallet_card("stock")}{wallet_card("crypto")}</div>', unsafe_allow_html=True)
if positions_error:
    st.caption(f"No se pudo consultar Alpaca: {positions_error}")

# =========================================================================
tab_panel, tab_graficos, tab_ops, tab_news, tab_screener, tab_bt, tab_glosario, tab_control = st.tabs([
    "Panel", "Gráficos", "Operaciones", "Noticias", "Screener", "Backtest", "Glosario", "Control"
])

# ----------------------------- PANEL -----------------------------
with tab_panel:
    sigs = latest_signals()
    col_l, col_m, col_r = st.columns([1, 1.5, 1])

    # ---- Izquierda: equity, posiciones, riesgo, noticias ----
    with col_l:
        with st.container(key="pn_equity"):
            st.markdown('<p class="pt"><span>Equity</span><span class="mn dim">vs. primer registro</span></p>', unsafe_allow_html=True)
            if not equity_df.empty:
                chart_df = equity_df.sort_values("id").copy()
                chart_df["ts_dt"] = pd.to_datetime(chart_df["ts"])
                range_label = st.radio("Rango", ["1D", "1M", "1Y", "Todo"], horizontal=True,
                                       label_visibility="collapsed", index=0, key="eq_range")
                now = chart_df["ts_dt"].max()
                cutoff = {"1D": now - pd.Timedelta(days=1), "1M": now - pd.Timedelta(days=30),
                          "1Y": now - pd.Timedelta(days=365)}.get(range_label, chart_df["ts_dt"].min())
                view_df = chart_df[chart_df["ts_dt"] >= cutoff]
                if view_df.empty:
                    view_df = chart_df
                try:
                    first_eq = float(load_table("SELECT equity FROM equity_snapshots ORDER BY id ASC LIMIT 1").iloc[0, 0])
                except Exception:
                    first_eq = float(chart_df["equity"].iloc[0])
                cur_val, start_val = view_df["equity"].iloc[-1], view_df["equity"].iloc[0]
                pct_change = ((cur_val - start_val) / start_val * 100) if start_val else 0
                st.markdown(
                    f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">'
                    f'<span class="mn" style="font-size:1.5rem;font-weight:700">${cur_val:,.2f}</span>'
                    f'<span class="mn {tone(pct_change)}" style="font-weight:600">{pct_change:+.2f}%</span></div>',
                    unsafe_allow_html=True)
                # Zoom al rango real (como Alpaca): si el eje arranca en $0, las fluctuaciones chicas se ven planas.
                lo = min(view_df["equity"].min(), first_eq)
                hi = max(view_df["equity"].max(), first_eq)
                span = (hi - lo) or max(hi * 0.001, 1)
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=view_df["ts_dt"], y=view_df["equity"], mode="lines", fill="tozeroy",
                                         line=dict(color=G, width=2), fillcolor="rgba(62,232,154,0.10)",
                                         hovertemplate="$%{y:,.2f}<extra></extra>"))
                fig.add_hline(y=first_eq, line_dash="dash", line_color="rgba(245,200,75,.6)", line_width=1)
                style_fig(fig, 190)
                fig.update_layout(
                    xaxis=dict(showgrid=False, tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", tickprefix="$", tickformat=",.0f",
                               range=[lo - span * 0.25, hi + span * 0.25]),
                    hovermode="x unified")
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                diff = cur_val - first_eq
                st.markdown(f'<div class="mn dim" style="font-size:11px"><span class="y">- - -</span> primer registro '
                            f'{money(first_eq)} · ahora <span class="{tone(diff)}">{money(diff, True)}</span></div>',
                            unsafe_allow_html=True)
            else:
                st.info("Todavía no hay datos de equity.")

        with st.container(key="pn_positions"):
            st.markdown(f'<p class="pt"><span>Posiciones abiertas</span><span class="mn">{len(positions)}</span></p>', unsafe_allow_html=True)
            if positions:
                rows = "".join(
                    f'<div class="row"><span><b>{p["symbol"]}</b> <span class="dim mn" style="font-size:11px">'
                    f'{"cripto" if p["kind"] == "crypto" else "acción"} · {fmt_qty(p["qty"])}</span></span>'
                    f'<span class="mn {tone(p["unrealized_pl"])}">{money(p["unrealized_pl"], True)}</span></div>'
                    for p in positions)
                st.markdown(rows, unsafe_allow_html=True)
            else:
                st.markdown('<div class="dim" style="font-size:13px">Sin posiciones abiertas (100% en efectivo).</div>', unsafe_allow_html=True)

        with st.container(key="pn_risk"):
            n_c = sum(1 for p in positions if p["kind"] == "crypto")
            n_s = len(positions) - n_c
            loss_today = max(-daily_pct, 0)

            def risk_row(label, value, limit, text):
                frac = min(value / limit, 1.0) if limit else 0
                color = G if frac < 0.5 else (Y if frac < 0.85 else R)
                return (f'<div style="margin-bottom:11px"><div class="mn" style="display:flex;justify-content:space-between;'
                        f'font-size:12px;margin-bottom:5px"><span class="dim">{label}</span><span>{text}</span></div>'
                        f'<div class="bar"><i style="width:{frac*100:.0f}%;background:{color}"></i></div></div>')

            pill = '<span class="pill r">DETENIDO</span>' if kill_active else '<span class="pill g">ARMADO</span>'
            st.markdown(
                f'<p class="pt"><span>Riesgo y kill switch</span>{pill}</p>'
                + risk_row("Caída máxima", dd_now, Config.MAX_DRAWDOWN_PCT, f"{dd_now*100:.1f}% / {Config.MAX_DRAWDOWN_PCT*100:.0f}%")
                + risk_row("Pérdida del día", loss_today, Config.DAILY_LOSS_LIMIT_PCT, f"{loss_today*100:.1f}% / {Config.DAILY_LOSS_LIMIT_PCT*100:.0f}%")
                + risk_row("Cupo acciones", n_s, Config.MAX_OPEN_POSITIONS, f"{n_s} / {Config.MAX_OPEN_POSITIONS}")
                + risk_row("Cupo cripto", n_c, Config.MAX_CRYPTO_POSITIONS, f"{n_c} / {Config.MAX_CRYPTO_POSITIONS}"),
                unsafe_allow_html=True)

        with st.container(key="pn_news"):
            st.markdown('<p class="pt"><span>Noticias · sentimiento</span><span class="mn dim">filtro '
                        f'{"activo" if Config.USE_NEWS_FILTER else "apagado"}</span></p>', unsafe_allow_html=True)
            try:
                news_df = load_table("SELECT ts, message FROM events WHERE message LIKE '%noticia%' ORDER BY id DESC LIMIT 4")
            except Exception:
                news_df = pd.DataFrame()
            if news_df.empty:
                st.markdown('<div class="dim" style="font-size:13px">Todavía no se evaluó ninguna noticia.</div>', unsafe_allow_html=True)
            else:
                label = {"positive": ("POSITIVA", "g"), "negative": ("NEGATIVA", "r"), "neutral": ("NEUTRAL", "y")}
                html = ""
                for msg in news_df["message"]:
                    m = re.match(r"^(\S+): noticia '(.*)' -> sentimiento (\w+)", msg)
                    if m:
                        txt, (lbl, cls) = f"{m.group(1)}: {m.group(2)}", label.get(m.group(3), (m.group(3).upper(), "y"))
                    else:
                        txt, (lbl, cls) = msg[:90], ("AVISO", "y")
                    html += (f'<div class="row" style="align-items:flex-start"><span style="font-size:12px;line-height:1.35">{txt}</span>'
                             f'<span class="pill {cls}">{lbl}</span></div>')
                st.markdown(html, unsafe_allow_html=True)

    # ---- Centro: asteroide ----
    with col_m:
        with st.container(key="col_mid"):
            with st.container(key="pn_asteroid"):
                extended = st.toggle("Ampliar con el universo del Screener (más lento)", value=False, key="ast_ext")
                universe = list(sigs)
                if extended:
                    have = {s["symbol"] for s in universe}
                    todo = tuple(s for s in (SCREENER_STOCKS + "," + SCREENER_CRYPTO).split(",") if s not in have)
                    universe += scan_universe(todo)
                universe.sort(key=lambda s: s["symbol"])
                st.markdown(f'<p class="pt"><span>Esfera de señales · {len(universe)} símbolos</span>'
                            f'<span class="mn dim">arrastrá para girar · tocá un punto</span></p>', unsafe_allow_html=True)
                if universe:
                    asteroid(universe, positions=positions)
                    n = {t: [s for s in universe if s["tone"] == t] for t in "gyr"}
                    st.markdown(
                        f'<div class="pc-count"><div><b class="g">{len(n["g"])}</b><span>BUENAS</span></div>'
                        f'<div><b class="y">{len(n["y"])}</b><span>INTERMEDIAS</span></div>'
                        f'<div><b class="r">{len(n["r"])}</b><span>MALAS</span></div></div>',
                        unsafe_allow_html=True)
                    chips = "".join(f'<span class="pc-chip {s["tone"]}">{s["symbol"]}'
                                    f'{"" if s["rsi"] is None else " · RSI " + format(s["rsi"], ".0f")}</span>'
                                    for s in sorted(universe, key=lambda s: ("gyr".index(s["tone"]), s["symbol"]))[:24])
                    st.markdown(f'<div class="pc-chips">{chips}</div>', unsafe_allow_html=True)
                    st.markdown('<div class="dim" style="font-size:11px;margin-top:8px">Cada nube de puntos es un símbolo. '
                                'Verde: tendencia alcista o señal de compra · amarillo: sin dirección clara · '
                                'rojo: tendencia bajista o señal de venta. Se actualiza con cada lectura del agente.</div>',
                                unsafe_allow_html=True)
                else:
                    st.info("Todavía no hay señales guardadas. Aparecen cuando el agente completa su primer ciclo.")

            with st.container(key="pn_last"):
                try:
                    last_order = load_table("SELECT * FROM orders ORDER BY id DESC LIMIT 1")
                except Exception:
                    last_order = pd.DataFrame()
                st.markdown('<p class="pt"><span>Última acción</span></p>', unsafe_allow_html=True)
                if not last_order.empty:
                    o = last_order.iloc[0]
                    side_label = {"buy": ("COMPRÓ", "g"), "sell": ("VENDIÓ", "r"),
                                  "trailing_stop_sell": ("PROTEGIÓ", "b")}.get(o["side"], (str(o["side"]).upper(), "y"))
                    st.markdown(
                        f'<div class="row"><span><span class="pill {side_label[1]}">{side_label[0]}</span> '
                        f'<b>{fmt_qty(o["qty"])} de {o["symbol"]}</b></span><span class="mn dim" style="font-size:11px">{str(o["ts"])[:16].replace("T", " ")}</span></div>'
                        f'<div class="dim" style="font-size:12px;margin-top:6px">Motivo: {o["reason"]}</div>',
                        unsafe_allow_html=True)
                else:
                    st.markdown('<div class="dim" style="font-size:13px">Todavía no hizo ninguna operación.</div>', unsafe_allow_html=True)

    # ---- Derecha: velas, RSI, screener ----
    with col_r:
        with st.container(key="pn_candles"):
            st.markdown(f'<p class="pt"><span>Velas · SMA 10/30</span><span class="mn dim">{Config.TIMEFRAME_MINUTES} min{f" · cripto {Config.CRYPTO_TIMEFRAME_MINUTES} min" if Config.CRYPTO_SYMBOLS else ""}</span></p>', unsafe_allow_html=True)
            # 2 acciones + 2 cripto; si falta alguna clase, se completa con la otra hasta 4 gráficos.
            chosen_syms = Config.SYMBOLS[:2] + Config.CRYPTO_SYMBOLS[:2]
            extra_syms = [s for s in Config.SYMBOLS + Config.CRYPTO_SYMBOLS if s not in chosen_syms]
            show = (chosen_syms + extra_syms)[:4]
            pairs = [show[i:i + 2] for i in range(0, len(show), 2)]
            for pair in pairs:
                cols = st.columns(2)
                for c, sym in zip(cols, pair):
                    with c:
                        df = fetch_bars(sym, timeframe_for(sym), max(Config.LOOKBACK_BARS, 100))
                        if df is None or df.empty:
                            st.markdown(f'<div class="dim" style="font-size:12px"><b>{sym}</b> sin datos</div>', unsafe_allow_html=True)
                            continue
                        w = df.tail(60)
                        chg = (w["close"].iloc[-1] / w["close"].iloc[0] - 1) * 100
                        st.markdown(f'<div style="display:flex;justify-content:space-between;font-size:12px"><b>{sym}</b>'
                                    f'<span class="mn {tone(chg)}">{chg:+.2f}%</span></div>'
                                    f'<div class="mn" style="font-size:12px">{w["close"].iloc[-1]:,.2f}</div>', unsafe_allow_html=True)
                        st.plotly_chart(mini_candle(df), width="stretch", config={"displayModeBar": False}, key=f"mc_{sym}")

        with st.container(key="pn_rsi"):
            rsi_options = Config.SYMBOLS + Config.CRYPTO_SYMBOLS
            if rsi_options:
                rsym = st.selectbox("RSI de", rsi_options, key="rsi_sym", label_visibility="collapsed")
                df = fetch_bars(rsym, timeframe_for(rsym), max(Config.LOOKBACK_BARS, 100))
                if df is not None and not df.empty:
                    rs = rsi_series(df["close"]).tail(80)
                    st.markdown(f'<p class="pt"><span>RSI 14 · {rsym}</span><span class="mn y">{rs.iloc[-1]:.1f}</span></p>', unsafe_allow_html=True)
                    fig = go.Figure(go.Scatter(x=rs.index, y=rs, line=dict(color=B, width=1.5)))
                    fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,95,109,.6)")
                    fig.add_hline(y=30, line_dash="dot", line_color="rgba(62,232,154,.6)")
                    style_fig(fig, 120, dict(l=0, r=0, t=0, b=0))
                    fig.update_layout(yaxis=dict(range=[0, 100], showgrid=False, side="right"), xaxis=dict(visible=False))
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="rsi_chart")

        with st.container(key="pn_screener"):
            st.markdown('<p class="pt"><span>Screener</span><span class="mn dim">últimas señales</span></p>', unsafe_allow_html=True)
            order = {"buy": 0, "sell": 1, "hold": 2}
            top = sorted(sigs, key=lambda s: (order.get(s["signal"], 3), s["symbol"]))[:5]
            pill_for = {"buy": ("COMPRA", "g"), "sell": ("VENTA", "r"), "hold": ("ESPERA", "y")}
            if top:
                st.markdown("".join(
                    f'<div class="row"><b>{s["symbol"]}</b><span class="mn dim">{"RSI —" if s["rsi"] is None else "RSI " + format(s["rsi"], ".0f")}</span>'
                    f'<span class="pill {pill_for.get(s["signal"], ("—", "y"))[1]}">{pill_for.get(s["signal"], ("—", "y"))[0]}</span></div>'
                    for s in top), unsafe_allow_html=True)
            else:
                st.markdown('<div class="dim" style="font-size:13px">Sin lecturas todavía.</div>', unsafe_allow_html=True)

    # ---- Cinta de actividad ----
    with st.container(key="pn_ticker"):
        try:
            recent = load_table("SELECT ts, symbol, side, qty FROM orders ORDER BY id DESC LIMIT 14")
        except Exception:
            recent = pd.DataFrame()
        if recent.empty:
            st.markdown('<p class="pt" style="margin:0"><span>Actividad</span><span class="mn dim">sin operaciones todavía</span></p>', unsafe_allow_html=True)
        else:
            lab = {"buy": ("COMPRA", G), "sell": ("VENTA", R), "trailing_stop_sell": ("PROTECCIÓN", B)}
            items_html = "".join(
                f'<span class="pc-tr"><b style="color:{lab.get(r.side, (r.side.upper(), Y))[1]}">{lab.get(r.side, (r.side.upper(), Y))[0]}</b>'
                f'<span>{r.symbol}</span><span class="dim">{fmt_qty(r.qty)}</span><span class="dim">{str(r.ts)[11:16]}</span></span>'
                for r in recent.itertuples())
            st.markdown(f'<div style="display:flex;gap:16px;align-items:center"><span class="pt" style="margin:0;flex:none">Actividad</span>'
                        f'<div class="pc-ticker" style="flex:1;min-width:0"><div class="pc-track">{items_html}{items_html}</div></div></div>',
                        unsafe_allow_html=True)

# ----------------------------- GRÁFICOS -----------------------------
with tab_graficos:
    st.subheader("Elegí un símbolo")
    options = Config.SYMBOLS + Config.CRYPTO_SYMBOLS or ["BTC/USD"]
    gc1, gc2 = st.columns([2, 1])
    picked = gc1.selectbox("Símbolo", options, index=0, key="g_sym")
    custom = gc2.text_input("o escribí otro", placeholder="SOL/USD o NVDA", key="g_custom").strip().upper()
    chosen = custom or picked
    if chosen:
        try:
            df = get_broker().get_recent_bars(chosen, timeframe_for(chosen), max(Config.LOOKBACK_BARS, 100))
            if df is not None and not df.empty:
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name=chosen,
                                             increasing_line_color=G, decreasing_line_color=R))
                fig.add_trace(go.Scatter(x=df.index, y=sma(df["close"], 10), line=dict(color=B, width=1.3), name="SMA 10"))
                fig.add_trace(go.Scatter(x=df.index, y=sma(df["close"], 30), line=dict(color=Y, width=1.3), name="SMA 30"))
                style_fig(fig, 420, dict(l=5, r=5, t=30, b=10))
                fig.update_layout(xaxis_rangeslider_visible=False, title=f"{chosen} — {timeframe_for(chosen)}min",
                                  legend=dict(orientation="h", y=1.08),
                                  yaxis=dict(gridcolor="rgba(255,255,255,.06)"), xaxis=dict(gridcolor="rgba(255,255,255,.04)"))
                st.plotly_chart(fig, width="stretch")

                fig_rsi = go.Figure(go.Scatter(x=df.index, y=rsi_series(df["close"]), line=dict(color="#A78BFA", width=1.3), name="RSI"))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color=R)
                fig_rsi.add_hline(y=30, line_dash="dot", line_color=G)
                style_fig(fig_rsi, 160, dict(l=5, r=5, t=10, b=10))
                fig_rsi.update_layout(yaxis_range=[0, 100])
                st.plotly_chart(fig_rsi, width="stretch")

                result = compute_signal(df)
                st.info(f"**Señal: {result['signal'].upper()}** — {result.get('reason', '')}")
            else:
                st.warning("No se pudieron traer datos.")
        except Exception as e:
            st.error(f"Error: {e}")

# ----------------------------- OPERACIONES -----------------------------
with tab_ops:
    st.subheader("Historial de órdenes")
    orders_df = load_table("SELECT ts, symbol, side, qty, status, reason FROM orders ORDER BY id DESC LIMIT 100")
    if not orders_df.empty:
        side_counts = orders_df["side"].value_counts().reset_index()
        side_counts.columns = ["tipo", "cantidad"]
        col1, col2 = st.columns([1, 2])
        with col1:
            fig_pie2 = px.pie(side_counts, values="cantidad", names="tipo", hole=0.45,
                              color_discrete_sequence=[G, R, B, Y])
            style_fig(fig_pie2, 260, dict(l=0, r=0, t=10, b=10))
            fig_pie2.update_layout(legend=dict(orientation="h", y=-0.15))
            st.plotly_chart(fig_pie2, width="stretch")
        with col2:
            st.caption("buy = compra | sell = venta | trailing_stop_sell = protección puesta (acciones)")
            st.dataframe(orders_df, width="stretch", hide_index=True)
    else:
        st.caption("Todavía no se ejecutó ninguna orden.")

# ----------------------------- NOTICIAS -----------------------------
with tab_news:
    st.subheader("Noticias evaluadas")
    news_events = load_table("SELECT ts, message FROM events WHERE message LIKE '%noticia%' ORDER BY id DESC LIMIT 30")
    if not news_events.empty:
        st.dataframe(news_events, width="stretch", hide_index=True)
    else:
        st.info("Todavía no se registró ninguna noticia.")

# ----------------------------- SCREENER -----------------------------
@st.cache_resource
def _scan_gate():
    return {"t": 0.0}


def _scan_allowed() -> bool:
    """Panel público: un escaneo manual cada 45 s para todos los visitantes, así nadie satura la API de Alpaca."""
    gate = _scan_gate()
    if time.time() - gate["t"] < 45:
        st.info("Se hizo un escaneo hace instantes. Probá de nuevo en unos segundos.")
        return False
    gate["t"] = time.time()
    return True


with tab_screener:
    st.subheader("Screener")
    _top = _auto_top()
    if _top and _top.get("rows"):
        st.markdown("**Screener automático — Top del momento**")
        _df = pd.DataFrame(_top["rows"][: max(int(_top.get("top_n") or 3), 3)])
        _df = _df.rename(columns={"symbol": "Acción", "score": "Puntaje", "price": "Precio", "day_chg": "Hoy",
                                  "mom_long": "6 meses", "rsi": "RSI"})
        for c in ("Hoy", "6 meses"):
            if c in _df:
                _df[c] = _df[c].map(lambda v: "—" if v is None else f"{v * 100:+.1f}%")
        st.dataframe(_df, width="stretch", hide_index=True)
        try:
            _when = datetime.fromisoformat(_top["ts"]).strftime("%d/%m %H:%M UTC")
        except Exception:
            _when = "?"
        st.caption(f"{_top.get('eligible', 0)} acciones elegibles de {_top.get('scored', 0)} escaneadas · último escaneo {_when} · "
                   + ("la rotación automática está ACTIVADA (compra y reemplaza con los frenos de siempre)." if _top.get("rotation")
                      else "solo muestra el ranking: el agente no compra por él."))
        st.divider()
    st.markdown("**Escaneo manual**")
    universe_input = st.text_area("Símbolos candidatos (acciones y pares cripto con barra)",
                                  value=SCREENER_STOCKS + "," + SCREENER_CRYPTO, height=90)
    if st.button("Escanear ahora") and _scan_allowed():
        candidate_symbols = [s.strip().upper() for s in universe_input.split(",") if s.strip()][:45]
        progress = st.progress(0, text="Escaneando...")
        scan_results = []
        for i, sym in enumerate(candidate_symbols):
            try:
                df = get_broker().get_recent_bars(sym, timeframe_for(sym), Config.LOOKBACK_BARS)
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
            st.success(f"Señal de compra: {', '.join(buys['symbol'])}")
        else:
            st.info("Ningún símbolo da señal de compra ahora.")
        cols_to_show = [c for c in ["symbol", "signal", "reason", "sma_fast", "sma_slow", "rsi", "last_close"] if c in scan_df.columns]
        st.dataframe(scan_df[cols_to_show], width="stretch", hide_index=True)
        if not buys.empty:
            buy_stocks = [s for s in buys["symbol"] if not is_crypto(s)]
            buy_crypto = [s for s in buys["symbol"] if is_crypto(s)]
            if buy_stocks:
                st.caption("Para operarlas, variable SYMBOLS del servicio agent:")
                st.code(",".join(list(dict.fromkeys(Config.SYMBOLS + buy_stocks))), language=None)
            if buy_crypto:
                st.caption("Para operarlas, variable CRYPTO_SYMBOLS del servicio agent (antes corré backtest_crypto.py):")
                st.code(",".join(list(dict.fromkeys(Config.CRYPTO_SYMBOLS + buy_crypto))), language=None)

# ----------------------------- BACKTEST -----------------------------
with tab_bt:
    st.subheader("Backtesting")
    bt_error = False
    try:
        bt_results = load_table("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 30")
    except psycopg2.errors.UndefinedTable:
        bt_results = pd.DataFrame()
    except Exception:
        bt_results, bt_error = pd.DataFrame(), True
    if bt_error:
        st.warning("No pude leer los resultados del backtest: la tabla está ocupada (tarda demasiado en responder). "
                   "Suele pasar si hay un backtest guardando datos en este momento. Esperá a que termine y recargá.")
    elif not bt_results.empty:
        st.dataframe(bt_results, width="stretch", hide_index=True)
        st.caption("buy_hold_pct = lo que habría dado comprar y mantener con el 100% del capital; "
                   "para comparar de igual a igual, multiplicalo por el % de posición (8% acciones, 5% cripto).")
    else:
        st.caption("Todavía no corriste ningún backtest (python backtest.py o python backtest_crypto.py).")
    st.divider()
    st.subheader("Optimización")
    try:
        opt_results = load_table(
            "SELECT symbol, sma_fast, sma_slow, rsi_buy_max, trailing_stop_pct, num_trades, "
            "win_rate, total_return_pct, max_drawdown_pct, score FROM optimize_results ORDER BY score DESC LIMIT 15"
        )
        if not opt_results.empty:
            st.dataframe(opt_results, width="stretch", hide_index=True)
        else:
            st.caption("Todavía no corriste el optimizador.")
    except Exception:
        st.caption("Todavía no corriste el optimizador.")

# ----------------------------- GLOSARIO -----------------------------
with tab_glosario:
    st.subheader("Glosario")
    glossary = [
        ("Equity", "El valor total de tu cuenta: efectivo + lo que valen tus posiciones abiertas."),
        ("Billetera de acciones / cripto", "Alpaca tiene una sola cuenta. Cada billetera muestra cuánto hay invertido en esa clase de activo y su ganancia o pérdida abierta."),
        ("P&L (Profit & Loss)", "Ganancia o pérdida en dólares."),
        ("Drawdown", "Cuánto cayó tu cuenta desde su punto más alto."),
        ("SMA (Media Móvil Simple)", "Promedio del precio de cierre de los últimos N períodos."),
        ("Cruce alcista", "La media rápida cruza por encima de la lenta — señal de tendencia hacia arriba."),
        ("Cruce bajista", "La media rápida cruza por debajo de la lenta — señal de reversión a la baja."),
        ("RSI", "Mide 0-100 qué tan sobrecomprado/sobrevendido está un activo. >70 sobrecomprado, <30 sobrevendido."),
        ("Esfera de señales", "Cada nube de puntos es un símbolo. Verde = tendencia alcista o señal de compra, amarillo = sin dirección clara, rojo = tendencia bajista o señal de venta."),
        ("Trailing Stop", "Orden de venta que sube con el precio y nunca baja — protege ganancias. En acciones la ejecuta Alpaca; en cripto la vigila el agente cada minuto."),
        ("Stop trading cripto", "Freno automático solo de la cripto: si la pérdida cripto del día supera CRYPTO_DAILY_LOSS_PCT del equity, cierra las posiciones cripto y no compra más hasta mañana; si hay CRYPTO_MAX_CONSECUTIVE_LOSSES cierres seguidos en pérdida, queda frenada hasta que la reactives en Control."),
        ("Alarma crítica", "Aviso 🚨 por Telegram y en el log. Salta si el equity cae de golpe entre dos ciclos (SUDDEN_DROP_PCT) o si el agente acumula MAX_CYCLE_ERRORS ciclos seguidos con error: en ambos casos se activa el kill switch."),
        ("Pausa tras cierre / tope diario", "Con CRYPTO_COOLDOWN_MINUTES no se recompra un par recién cerrado, y CRYPTO_MAX_TRADES_PER_DAY limita las compras cripto por día. CRYPTO_MAX_EXPOSURE_PCT es el techo de plata total en cripto."),
        ("Kill switch", "Interruptor de emergencia que frena todas las operaciones nuevas."),
        ("Paper trading", "Operar con dinero simulado, precios reales."),
        ("Cripto 24/7", "Los pares cripto (BTC/USD, ETH/USD...) cotizan todo el día, todos los días; las acciones solo con el mercado abierto."),
        ("Par cripto (BTC/USD)", "Una criptomoneda cotizada en dólares: BTC/USD es cuántos dólares vale 1 bitcoin. En las órdenes y los datos se escribe con barra (BTC/USD); en las posiciones de Alpaca aparece sin barra (BTCUSD)."),
        ("Qué es cada cripto", "BTC = Bitcoin · ETH = Ethereum · SOL = Solana · LTC = Litecoin · DOGE = Dogecoin · AVAX = Avalanche · LINK = Chainlink · BCH = Bitcoin Cash. Son los pares que compara el backtest cripto."),
        ("CRYPTO_SYMBOLS", "Variable de Railway que activa la cripto. Va en el servicio del agente (para que opere) y también en el del dashboard (para que lo muestre). Si ves 'Cripto desactivada', está vacía en ese servicio."),
        ("Cantidad fraccionaria", "En cripto se compran fracciones (por ejemplo 0,0123 BTC). En acciones el agente compra unidades enteras."),
        ("Posición y cupo cripto", "Cada compra cripto usa hasta el 5% del equity (CRYPTO_MAX_POSITION_PCT) y hay un cupo propio de 2 posiciones (MAX_CRYPTO_POSITIONS), independiente del de acciones: una clase no deja sin lugar a la otra."),
        ("Trailing stop de cripto", "Alpaca no ofrece trailing stop para cripto, así que lo hace el agente por software: guarda el precio máximo desde la compra y vende si el precio cae 5% (CRYPTO_TRAILING_STOP_PCT) desde ese pico. Se revisa en cada ciclo del agente, incluso con el kill switch activo; no es una orden puesta en el broker."),
        ("Volatilidad", "Cuánto se mueve el precio. La cripto suele moverse mucho más que las acciones, por eso su posición es más chica y su stop más amplio."),
        ("Comisión cripto", "Alpaca cobra una comisión por operar cripto (hasta 0,25% por operación en el nivel base; verificá la tarifa vigente en Alpaca). El backtest la descuenta (CRYPTO_FEE_PCT) para no mostrar ganancias que en la práctica no existirían."),
        ("Orden GTC", "'Good 'til canceled': la orden queda vigente hasta ejecutarse o cancelarse. Las órdenes cripto usan GTC (no admiten DAY, que vence al cierre del día como en las acciones)."),
        ("Backtest cripto: veredicto", "Consistente = al menos 15 operaciones, ganancia en las dos mitades del período y mejor resultado que comprar y mantener. Irregular = no cumple alguna de esas condiciones. Pocos trades = muy pocas operaciones para sacar conclusiones."),
        ("Primera y segunda mitad", "El backtest cripto parte el período en dos. Si una estrategia solo gana en una de las mitades, probablemente fue suerte y no una ventaja real."),
        ("In-sample", "Resultados medidos sobre los mismos datos con los que se eligió la estrategia. Tienden a verse mejor que lo que pasará después: el pasado no garantiza el futuro. Por eso conviene probar varios días en paper antes de confiar."),
        ("◆ En cartera (asteroide)", "Los símbolos marcados con ◆ son los que tenés abiertos. Al tocar un punto de cualquier símbolo se abre su ficha con la señal, el precio, el RSI y, si lo tenés, tu posición y su P&L."),
        ("Win rate", "% de operaciones cerradas en ganancia."),
        ("Timeframe", "Tamaño de cada vela de precio — no es el horario de mercado."),
        ("Buy & Hold", "Comprar y no vender nunca — referencia para medir si una estrategia activa vale la pena. En el backtest cripto se compara con la misma exposición que usa la estrategia (columna B&H*)."),
        ("ADR", "Certificado de acción extranjera cotizando en dólares en EEUU."),
        ("ETF", "Fondo que agrupa muchos activos en un solo papel (ej. SPY = S&P 500)."),
    ]
    for term, definition in glossary:
        with st.expander(f"**{term}**"):
            st.write(definition)

# ----------------------------- CONTROL -----------------------------
with tab_control:
    st.subheader("Control manual")
    admin = bool(st.session_state.get("admin"))
    if not admin:
        if ADMIN_PASSWORD:
            st.caption("Vista pública de solo lectura. Los controles son solo para el administrador.")
            with st.form("admin_login", border=False):
                _pw = st.text_input("Contraseña de administrador", type="password")
                if st.form_submit_button("Desbloquear controles"):
                    if _pw == ADMIN_PASSWORD:
                        st.session_state["admin"] = True
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta.")
        else:
            st.caption("Vista pública de solo lectura. Los controles están deshabilitados "
                       "(definí ADMIN_PASSWORD en este servicio para habilitarlos).")
    else:
        kcol1, kcol2 = st.columns(2)
        with kcol1:
            if not kill_active and st.button("Activar kill switch"):
                set_state("kill_switch", "active")
                st.rerun()
        with kcol2:
            if kill_active and st.button("Desactivar kill switch"):
                delete_state("kill_switch")
                st.rerun()
    st.caption(f"Acciones: {', '.join(Config.SYMBOLS) or '—'} · Cripto: {', '.join(Config.CRYPTO_SYMBOLS) or 'desactivada'}")
    if Config.CRYPTO_SYMBOLS:
        if crypto_halt_txt:
            st.warning(f"Cripto frenada: {crypto_halt_txt}")
            if admin and st.button("Reactivar cripto"):
                delete_state("crypto_halt")
                set_state("crypto_loss_streak", "0")
                st.rerun()
        else:
            st.caption(f"Cripto operando · se frena sola con pérdida del día > {Config.CRYPTO_DAILY_LOSS_PCT:.1%} del equity "
                       f"o {Config.CRYPTO_MAX_CONSECUTIVE_LOSSES} cierres seguidos en pérdida.")
    st.divider()
    st.subheader("Log de eventos")
    try:
        _lvl = "" if admin else "WHERE level <> 'error' "
        events_df = load_table(f"SELECT ts, level, message FROM events {_lvl}ORDER BY id DESC LIMIT 100")
    except Exception:
        events_df = pd.DataFrame()
        st.warning("No pude leer el log de eventos ahora mismo. Recargá en unos segundos.")
    if not events_df.empty:
        st.dataframe(events_df, width="stretch", hide_index=True)
    else:
        st.caption("Sin eventos todavía.")

st.caption(f"Actualizado: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} — recargá para refrescar.")
