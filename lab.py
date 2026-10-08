"""
lab.py — Laboratorio de pruebas de estrategias.

Responde UNA pregunta con datos históricos, antes de arriesgar nada: ¿esta estrategia le gana a simplemente
comprar el índice (SPY), después de costos, y sigue ganando en un período que no se usó para elegirla?

Compara, sobre velas DIARIAS de varios años y un universo de acciones líquidas:
  - SPY comprar y mantener (la vara a superar)
  - La estrategia actual del agente (cruce de medias SMA + RSI, con stops), aplicada a todo el universo
  - Turtle Traders (rupturas de máximos con tamaño por volatilidad ATR), con y sin filtro de mercado
  - Momentum 12-1 (comprar lo más fuerte de los últimos 12 meses, rebalanceo mensual) con y sin filtro de mercado
  - Las reglas del screener automático del agente (Top N por puntaje)
Y corre un SEGUNDO universo "sin sesgo de supervivencia": ETFs (índices, sectores, bonos, oro, internacional). Un ETF
existe igual en cualquier año, así que no hay "acciones que ya sabemos que subieron". Si el momentum funciona acá, es
mucho más creíble que lo que muestre sobre acciones sueltas de hoy.

Cómo se evita engañarse:
  - Costos incluidos en cada operación (SLIPPAGE_PCT por lado; las acciones no pagan comisión en Alpaca).
  - Sin "mirar el futuro": la señal de un día se ejecuta recién al cierre del día siguiente.
  - Los parámetros están fijados de antemano (no se optimizan acá) y se muestra el período "en muestra" (primer 60%)
    y el "fuera de muestra" (último 40%). Una estrategia buena tiene que verse bien en AMBOS.
  - Se muestran varias variantes de cada idea: si solo una variante gana, es frágil y probablemente casualidad.

Uso (desde la carpeta del proyecto, con las variables APCA_* configuradas):
    python lab.py            # 8 años pedidos, feed gratuito IEX (suele alcanzar ~6 años)
    python lab.py 8 sip      # pide el feed SIP (más historia); si tu plan no lo permite, vuelve solo a IEX
    python lab.py 5          # 5 años
No opera ni toca la base de datos. Descarga datos diarios de Alpaca (gratis) y los guarda en lab_cache.pkl.
"""
import os
import sys
import pickle
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import screener_core as sc

WARMUP = 260            # velas que se descartan al inicio: las estrategias necesitan ~1 año de historia
SPLIT = 0.60            # primer 60% = "en muestra"; último 40% = "fuera de muestra"
TRADING_DAYS = 252
CACHE_FILE = "lab_cache.pkl"
BENCH = "SPY"
ETF_UNIVERSE = "SPY,QQQ,IWM,EFA,EEM,XLK,XLF,XLE,XLV,XLY,XLP,XLI,XLU,XLB,XLRE,XLC,TLT,GLD"


# ============================================================ datos
def fetch_prices(symbols: list, years: int = 8, feed: str = "iex") -> dict:
    """Velas diarias ajustadas por splits y dividendos, de Alpaca (feed IEX, gratis). {símbolo: DataFrame OHLCV}."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed, Adjustment
    from config import Config

    client = StockHistoricalDataClient(Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=int(years * 365.25))
    out = {}
    for i in range(0, len(symbols), 20):          # de a 20 símbolos por pedido
        chunk = symbols[i:i + 20]
        print(f"  descargando {chunk[0]}…{chunk[-1]}")
        req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day, start=start, end=end,
                               adjustment=Adjustment.ALL, feed=DataFeed.SIP if feed == "sip" else DataFeed.IEX)
        try:
            df = client.get_stock_bars(req).df
        except Exception as e:
            if feed == "sip":
                print(f"  El feed SIP no está disponible en tu plan ({str(e)[:90]}). Uso IEX.")
                return fetch_prices(symbols, years, "iex")
            raise
        if df is None or df.empty:
            continue
        for sym in df.index.get_level_values(0).unique():
            d = df.loc[sym][["open", "high", "low", "close", "volume"]].copy()
            d.index = pd.to_datetime(d.index).tz_convert(None).normalize()
            out[sym] = d
    return out


def load_prices(years: int = 8, feed: str = "iex", use_cache: bool = True) -> dict:
    universe = sc.parse_universe(sc.DEFAULT_UNIVERSE) + sc.parse_universe(ETF_UNIVERSE)
    universe = list(dict.fromkeys(universe + [BENCH]))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if use_cache and os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            blob = pickle.load(f)
        if blob.get("day") == today and blob.get("years") == years and blob.get("feed") == feed:
            print("Usando datos guardados de hoy (lab_cache.pkl).")
            return blob["prices"]
    print(f"Descargando {len(universe)} símbolos, {years} años de velas diarias de Alpaca (feed {feed.upper()})…")
    prices = fetch_prices(universe, years, feed)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump({"day": today, "years": years, "feed": feed, "prices": prices}, f)
    return prices


def wide(prices: dict, field: str) -> pd.DataFrame:
    df = pd.DataFrame({s: d[field] for s, d in prices.items()}).sort_index()
    return df[~df.index.duplicated(keep="last")]


# ============================================================ motor de simulación por pesos
def run_weights(W: pd.DataFrame, close: pd.DataFrame, cost: float):
    """
    W: pesos objetivo (fracción del equity por símbolo) decididos con el cierre de cada día.
    Se ejecutan al cierre del día SIGUIENTE (un día de demora: sin mirar el futuro) y pagan `cost` por unidad operada.
    Devuelve (curva de equity empezando en 1, exposición diaria, fracción del equity operada cada día).
    """
    r = close.pct_change().fillna(0.0).to_numpy()
    Wt = W.reindex(close.index).fillna(0.0).to_numpy()
    T, N = r.shape
    eq = np.ones(T)
    expo = np.zeros(T)
    traded = np.zeros(T)
    w = np.zeros(N)
    for i in range(1, T):
        pr = float(w @ r[i])
        eq[i] = eq[i - 1] * (1 + pr)
        w = w * (1 + r[i]) / (1 + pr) if (1 + pr) > 1e-12 else w
        tgt = Wt[i - 1]                       # decidido con el cierre de ayer, se ejecuta hoy
        dw = float(np.abs(tgt - w).sum())
        eq[i] *= (1 - cost * dw)
        traded[i] = dw
        w = tgt.copy()
        expo[i] = float(np.abs(w).sum())
    idx = close.index
    return pd.Series(eq, idx), pd.Series(expo, idx), pd.Series(traded, idx)


# ============================================================ estrategias (devuelven pesos objetivo)
def regime_ok(close: pd.DataFrame, n: int = 200) -> pd.Series:
    """Verdadero cuando el mercado (SPY) está por encima de su media de n días."""
    spy = close[BENCH]
    return (spy > spy.rolling(n).mean()).fillna(False)


def turtle_weights(close, high, low, n_in=55, n_out=20, atr_n=20, unit_risk=0.0025, cap=0.10,
                   stop_atr=2.0, use_regime=False) -> pd.DataFrame:
    """
    Turtle Traders: compra cuando el precio rompe el máximo de los últimos n_in días; sale si cae bajo el mínimo
    de los últimos n_out días o 2 ATR por debajo de la entrada. Cada posición arriesga ~`unit_risk` del equity por
    cada ATR de movimiento (más volátil = posición más chica), con tope `cap` por acción y sin apalancamiento.
    """
    hh = high.rolling(n_in).max().shift(1).to_numpy()
    ll = low.rolling(n_out).min().shift(1).to_numpy()
    pc = close.shift(1)
    tr = np.maximum(np.maximum(high - low, (high - pc).abs()), (low - pc).abs())
    atr = tr.rolling(atr_n).mean().to_numpy()
    C = close.to_numpy()
    reg = regime_ok(close).to_numpy() if use_regime else np.ones(len(close), dtype=bool)
    T, N = C.shape
    in_pos = np.zeros(N, dtype=bool)
    stop = np.full(N, np.nan)
    W = np.zeros((T, N))
    with np.errstate(invalid="ignore"):
        for t in range(T):
            exit_ = in_pos & ((C[t] < ll[t]) | (C[t] < stop) | (~reg[t] if use_regime else False))
            in_pos &= ~exit_
            enter = (~in_pos) & (C[t] > hh[t]) & reg[t] & ~np.isnan(atr[t])
            stop = np.where(enter, C[t] - stop_atr * atr[t], stop)
            in_pos |= enter
            if in_pos.any():
                w = np.where(in_pos, np.minimum(unit_risk / (atr[t] / C[t]), cap), 0.0)
                w = np.nan_to_num(w)
                tot = w.sum()
                W[t] = w / tot if tot > 1.0 else w
    return pd.DataFrame(W, index=close.index, columns=close.columns)


def momentum_weights(close, k=10, lookback=252, skip=21, use_regime=True) -> pd.DataFrame:
    """Momentum 12-1: a fin de mes compra las k acciones con mejor retorno de los últimos 12 meses (sin el último mes)."""
    mom = close.shift(skip) / close.shift(lookback) - 1
    dates = close.index.to_series()
    month_end = dates.groupby([dates.dt.year, dates.dt.month]).transform("max") == dates
    reg = regime_ok(close) if use_regime else pd.Series(True, index=close.index)
    W = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    for d in close.index[month_end.to_numpy()]:
        row = mom.loc[d].dropna()
        row = row[row > 0]
        pick = row.sort_values(ascending=False).head(k).index
        W.loc[d] = 0.0
        if bool(reg.loc[d]) and len(pick):
            W.loc[d, pick] = 1.0 / k
    return W.ffill().fillna(0.0)


def screener_weights(close, n=3, every=5, buffer=2, min_score=70.0) -> pd.DataFrame:
    """
    Las reglas del screener automático: cada `every` días puntúa el universo y mantiene las n mejores acciones
    elegibles. Una acción que ya tenemos se conserva mientras siga elegible y dentro de las n+buffer primeras
    (así no se rota por diferencias mínimas). Cada posición pesa 1/n.
    """
    T = len(close)
    W = np.zeros((T, close.shape[1]))
    cols = list(close.columns)
    held = []
    for t in range(sc.MIN_BARS, T):
        if (t - sc.MIN_BARS) % every == 0:
            scores = sc.compute_scores(close.iloc[: t + 1])
            if not scores.empty:
                keep = [s for s in held if s in scores.index and bool(scores.loc[s, "eligible"])
                        and scores.loc[s, "top_rank"] <= n + buffer]
                pool = scores[scores["eligible"] & (scores["score"] >= min_score)]
                fill = [s for s in pool.index if s not in keep][: max(0, n - len(keep))]
                held = keep + fill
            row = np.zeros(len(cols))
            for s in held:
                row[cols.index(s)] = 1.0 / n
            W[t] = row
        else:
            W[t] = W[t - 1]
    return pd.DataFrame(W, index=close.index, columns=close.columns)


def sma_strategy_equity(prices: dict, fast: int, slow: int, cost: float) -> pd.Series:
    """
    La estrategia ACTUAL del agente (cruce de SMA + filtro RSI, stop loss y trailing stop de config.py) corrida con
    el mismo simulador del agente (backtest.simulate) sobre cada acción del universo con la misma porción de capital
    cada una. La curva es el promedio: cuando una acción no está comprada, su parte queda en efectivo.
    """
    import backtest
    sleeves = {}
    for sym, df in prices.items():
        if sym == BENCH or len(df) < slow + 60:
            continue
        res = backtest.simulate(df, sym, lookback=slow + 30, sma_fast_len=fast, sma_slow_len=slow,
                                max_position_pct=1.0, fee_pct=0.0, slippage_pct=cost)
        s = pd.Series({pd.Timestamp(p["ts"]): p["equity"] / backtest.STARTING_CAPITAL_PER_SYMBOL
                       for p in res["equity_curve"]})
        sleeves[sym] = s
    df = pd.DataFrame(sleeves).sort_index().ffill().fillna(1.0)
    return df.mean(axis=1)


# ============================================================ métricas
def metrics(eq: pd.Series, expo: pd.Series = None, traded: pd.Series = None) -> dict:
    eq = eq / eq.iloc[0]
    ret = eq.pct_change().dropna()
    years = max(len(ret) / TRADING_DAYS, 1e-9)
    cagr = eq.iloc[-1] ** (1 / years) - 1
    vol = ret.std() * np.sqrt(TRADING_DAYS)
    sharpe = (ret.mean() / ret.std() * np.sqrt(TRADING_DAYS)) if ret.std() > 0 else 0.0
    maxdd = float(((eq.cummax() - eq) / eq.cummax()).max())
    out = {"cagr": float(cagr), "vol": float(vol), "sharpe": float(sharpe), "maxdd": maxdd,
           "total": float(eq.iloc[-1] - 1)}
    if expo is not None:
        out["expo"] = float(expo.mean())
    if traded is not None:
        out["turnover_y"] = float(traded.sum() / years)
    return out


def split_metrics(eq: pd.Series, expo=None, traded=None) -> dict:
    n = len(eq)
    k = int(n * SPLIT)
    full = metrics(eq, expo, traded)
    ins = metrics(eq.iloc[:k])
    oos = metrics(eq.iloc[k - 1:])
    return {"full": full, "is": ins, "oos": oos}


def _beats(m: dict, b: dict) -> bool:
    """Mejor retorno Y mejor Sharpe que la referencia, con un margen mínimo para no premiar diferencias de ruido."""
    return m["cagr"] > b["cagr"] + 0.01 and m["sharpe"] > b["sharpe"] + 0.10


def verdict(m: dict, bench: dict) -> str:
    """
    Conservador: para llamarla ventaja tiene que ganarle a SPY en AMBOS períodos (en muestra y fuera de muestra).
    `m` y `bench` son los resultados de split_metrics().
    """
    win_is, win_oos = _beats(m["is"], bench["is"]), _beats(m["oos"], bench["oos"])
    if win_is and win_oos:
        return "VENTAJA en ambos períodos (más retorno y mejor Sharpe que SPY)"
    if win_oos and not win_is:
        return "inconsistente: solo ganó fuera de muestra (puede ser suerte)"
    if win_is and not win_oos:
        return "se rompió fuera de muestra (típico de sobreajuste)"
    o, bo = m["oos"], bench["oos"]
    if o["sharpe"] > bo["sharpe"] and o["maxdd"] <= 0.75 * bo["maxdd"]:
        return "menor riesgo: cae mucho menos que SPY, aunque rinde menos"
    return "sin ventaja demostrada"


# ============================================================ corrida completa
def run_lab(prices: dict, cost: float = None, progress=print, group: str = "acciones") -> pd.DataFrame:
    """group: "acciones" (universo de acciones grandes, con sesgo de supervivencia) o "etfs" (sin ese sesgo)."""
    if cost is None:
        from config import Config
        cost = Config.SLIPPAGE_PCT
    if BENCH not in prices:
        raise ValueError("Falta SPY en los datos (es la referencia).")
    names = sc.parse_universe(sc.DEFAULT_UNIVERSE if group == "acciones" else ETF_UNIVERSE)
    prices = {k: v for k, v in prices.items() if k in names or k == BENCH}
    close, high, low = wide(prices, "close"), wide(prices, "high"), wide(prices, "low")
    close = close.ffill(limit=3)
    if len(close) < WARMUP + 250:
        raise ValueError(f"Hacen falta al menos {WARMUP + 250} velas diarias; hay {len(close)}.")

    strategies = {}   # nombre -> (curva, exposición, operado)

    def add_w(name, W):
        progress(f"  {name}")
        strategies[name] = run_weights(W, close, cost)

    progress("Simulando estrategias…")
    spy = close[BENCH]
    strategies["SPY comprar y mantener (referencia)"] = (spy / spy.iloc[0], pd.Series(1.0, index=close.index), pd.Series(0.0, index=close.index))
    if group == "acciones":
        for fast, slow in ((10, 30), (50, 200)):
            name = f"Actual: cruce SMA {fast}/{slow} + RSI + stops (diario)"
            progress(f"  {name}")
            eq = sma_strategy_equity({k: v for k, v in prices.items()}, fast, slow, cost).reindex(close.index).ffill().fillna(1.0)
            strategies[name] = (eq, None, None)
        add_w("Turtle 55/20", turtle_weights(close, high, low, 55, 20))
        add_w("Turtle 20/10", turtle_weights(close, high, low, 20, 10))
        add_w("Turtle 55/20 + filtro SPY>SMA200", turtle_weights(close, high, low, 55, 20, use_regime=True))
        add_w("Momentum 12-1 top 5 + filtro", momentum_weights(close, k=5))
        add_w("Momentum 12-1 top 10 + filtro", momentum_weights(close, k=10))
        add_w("Momentum 12-1 top 20 + filtro", momentum_weights(close, k=20))
        add_w("Momentum 12-1 top 10 sin filtro", momentum_weights(close, k=10, use_regime=False))
        add_w("Screener del agente: Top 3", screener_weights(close, n=3))
        add_w("Screener del agente: Top 5", screener_weights(close, n=5))
    else:
        # ETFs: pocos instrumentos y de naturaleza distinta (acciones de EE.UU., sectores, internacional, bonos, oro).
        # Momentum con filtro propio: solo se compra lo que sube en 12 meses; si nada sube, queda en efectivo.
        add_w("ETFs momentum 12-1 top 3 + filtro SPY>SMA200", momentum_weights(close, k=3))
        add_w("ETFs momentum 12-1 top 5 + filtro SPY>SMA200", momentum_weights(close, k=5))
        add_w("ETFs momentum 12-1 top 3 (solo lo que sube)", momentum_weights(close, k=3, use_regime=False))
        add_w("ETFs momentum 12-1 top 5 (solo lo que sube)", momentum_weights(close, k=5, use_regime=False))
        add_w("ETFs Turtle 55/20", turtle_weights(close, high, low, 55, 20))
        add_w("ETFs Turtle 55/20 + filtro SPY>SMA200", turtle_weights(close, high, low, 55, 20, use_regime=True))

    window = close.index[WARMUP:]
    rows, bench = [], None
    for name, (eq, expo, traded) in strategies.items():
        eq = eq.reindex(window).ffill()
        m = split_metrics(eq,
                          None if expo is None else expo.reindex(window),
                          None if traded is None else traded.reindex(window))
        if bench is None:
            bench = m
        rows.append({"estrategia": name, "m": m})
    out = []
    for r in rows:
        m = r["m"]
        out.append({
            "estrategia": r["estrategia"],
            "cagr_total": m["full"]["cagr"], "sharpe_total": m["full"]["sharpe"], "maxdd_total": m["full"]["maxdd"],
            "cagr_en_muestra": m["is"]["cagr"], "sharpe_en_muestra": m["is"]["sharpe"],
            "cagr_fuera": m["oos"]["cagr"], "sharpe_fuera": m["oos"]["sharpe"], "maxdd_fuera": m["oos"]["maxdd"],
            "exposicion": m["full"].get("expo", np.nan), "giro_anual": m["full"].get("turnover_y", np.nan),
            "veredicto": "—" if r["estrategia"].startswith("SPY") else verdict(m, bench),
        })
    res = pd.DataFrame(out)
    res.attrs["window"] = (window[0], window[-1], len(window))
    res.attrs["split_date"] = window[int(len(window) * SPLIT)]
    res.attrs["group"] = group
    res.attrs["n_symbols"] = close.shape[1]
    return res


def print_report(res: pd.DataFrame):
    start, end, n = res.attrs["window"]
    split_date = res.attrs["split_date"]
    group = res.attrs.get("group", "acciones")
    label = ("ACCIONES GRANDES (con sesgo de supervivencia)" if group == "acciones"
             else "ETFs (sin sesgo de supervivencia)")
    p = lambda x: "  —  " if pd.isna(x) else f"{x * 100:6.1f}%"
    print("\n" + "=" * 118)
    print(f"LABORATORIO · {label} · {res.attrs.get('n_symbols', '?')} símbolos")
    print(f"{start:%Y-%m-%d} a {end:%Y-%m-%d} ({n / TRADING_DAYS:.1f} años) · fuera de muestra desde {split_date:%Y-%m-%d}")
    print("=" * 118)
    print(f"{'Estrategia':<46}{'RETORNO/AÑO':>18}{'SHARPE':>14}{'MAYOR CAÍDA':>13}{'EXPOS.':>8}{'GIRO/AÑO':>10}")
    print(f"{'':<46}{'todo  | fuera':>18}{'todo | fuera':>14}{'(fuera)':>13}")
    print("-" * 118)
    for _, r in res.iterrows():
        print(f"{r['estrategia']:<46}{p(r['cagr_total'])}{p(r['cagr_fuera'])}"
              f"{r['sharpe_total']:7.2f}{r['sharpe_fuera']:6.2f}{p(r['maxdd_fuera']):>13}{p(r['exposicion']):>8}"
              f"{('%.1fx' % r['giro_anual']) if not pd.isna(r['giro_anual']) else '  —':>10}")
    print("-" * 118)
    print("VEREDICTO (contra SPY, en ambos períodos):")
    for _, r in res.iterrows():
        if r["veredicto"] != "—":
            print(f"  · {r['estrategia']:<46} {r['veredicto']}")
    winners = res[res["veredicto"].str.startswith(("VENTAJA", "menor"))]
    print("\nCÓMO LEER ESTO")
    if winners.empty:
        print("  Ninguna estrategia le ganó a comprar SPY de forma clara. Es información valiosa:")
        print("  conviene NO activar nada más agresivo y seguir midiendo en paper trading.")
    else:
        print(f"  {len(winners)} de {len(res) - 1} estrategias muestran algo. Desconfiá si solo gana UNA variante de una misma idea")
        print("  (fragilidad), o si en muestra se ve genial y fuera de muestra no. Que algo gane acá NO es una garantía.")
    print("  Con muchas variantes probadas, alguna gana por pura casualidad: por eso un resultado solo cuenta si lo repiten sus variantes.")
    print("\nLÍMITES (importan):")
    if group == "acciones":
        print("  · Sesgo de supervivencia: el universo son acciones grandes de HOY; las que quebraron o salieron no están, y eso")
        print("    infla los resultados de las estrategias de momentum. Tomá cualquier ventaja como optimista.")
    else:
        print("  · ETFs: sin sesgo de supervivencia, pero hay pocos instrumentos y algunos (TLT, GLD) no son acciones.")
    print("  · Sharpe con tasa libre de riesgo = 0. Costos: SLIPPAGE_PCT por lado, sin comisión (acciones/ETFs en Alpaca).")
    print("  · Las estrategias se fijaron de antemano, pero yo conozco la historia: 'fuera de muestra' no es puro.")
    print("  · El screener en vivo además usa trailing stop de 3% y filtro de noticias, que acá no se simulan.")
    print("  · Siguiente paso si algo pasa la prueba: paper trading de 3 a 6 meses ANTES de pensar en dinero real.\n")


def cross_check(res_stocks: pd.DataFrame, res_etfs: pd.DataFrame):
    """Compara los dos universos: ¿el momentum que 'gana' en acciones también gana donde no hay sesgo de supervivencia?"""
    win_s = res_stocks[res_stocks["estrategia"].str.contains("Momentum") & res_stocks["veredicto"].str.startswith("VENTAJA")]
    win_e = res_etfs[res_etfs["estrategia"].str.contains("momentum") & res_etfs["veredicto"].str.startswith("VENTAJA")]
    print("=" * 118)
    print("COMPARACIÓN ENTRE UNIVERSOS (la prueba clave contra el sesgo de supervivencia)")
    print("=" * 118)
    if len(win_s) and not len(win_e):
        print("  El momentum 'gana' en las acciones de hoy pero NO en los ETFs: es la huella típica del sesgo de supervivencia.")
        print("  La ventaja en acciones probablemente es espejismo (elegimos acciones que ya sabemos que subieron).")
    elif len(win_s) and len(win_e):
        print("  El momentum gana en los dos universos. Eso lo vuelve bastante más creíble, aunque no es garantía.")
        print("  Siguiente paso razonable: probarlo en paper trading 3 a 6 meses contra SPY.")
    elif len(win_e):
        print("  El momentum gana en ETFs (sin sesgo) pero no en acciones sueltas. Merece seguimiento en paper trading.")
    else:
        print("  El momentum no le gana de forma clara a SPY en ninguno de los dos universos.")
    print()


def main():
    args = sys.argv[1:]
    feed = "sip" if any(a.lower() == "sip" for a in args) else "iex"
    nums = [a for a in args if a.isdigit()]
    years = int(nums[0]) if nums else 8
    prices = load_prices(years, feed)
    res_s = run_lab(prices, group="acciones")
    print_report(res_s)
    res_e = run_lab(prices, group="etfs")
    print_report(res_e)
    cross_check(res_s, res_e)
    out = pd.concat([res_s.assign(universo="acciones"), res_e.assign(universo="etfs")], ignore_index=True)
    out.to_csv("lab_resultados.csv", index=False)
    print("Resultados guardados en lab_resultados.csv\n")


if __name__ == "__main__":
    main()
