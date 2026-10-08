"""
screener_core.py
Lógica PURA del screener automático (sin base de datos ni broker): puntaje de cada acción y regla de decisión
(comprar / reemplazar). La usan dos lugares con exactamente las mismas reglas:
  - screener_auto.py + main.py  -> el agente en vivo (solo si AUTO_SCREENER / AUTO_ROTATION están activados)
  - lab.py                      -> el laboratorio de pruebas, para medir con datos históricos si estas reglas tienen ventaja

El puntaje se arma con tres señales, todas medidas contra el resto del universo (ranking percentil, 0 a 1):
  - momentum de ~6 meses, sin contar la última semana  (es la señal con más evidencia académica)   peso 55%
  - momentum de ~1 mes                                                                              peso 25%
  - variación de hoy (confirmación de que "está en alza" ahora)                                      peso 20%
Además una acción solo es ELEGIBLE (puede comprarse) si su tendencia está sana: precio por encima de su media de
50 días, media de 20 por encima de la de 50, sin caída fuerte hoy, sin estar sobrecomprada (RSI < 78) y con
momentum de 6 meses positivo. Esto evita comprar "lo que más subió" cuando ya está agotado o roto.
"""
import numpy as np
import pandas as pd

# Universo por defecto: acciones grandes y líquidas de varios sectores, más algunas de imanes / motores / robótica.
# Se puede cambiar con la variable AUTO_UNIVERSE (símbolos separados por coma).
DEFAULT_UNIVERSE = (
    "AAPL,MSFT,NVDA,AMZN,GOOGL,META,AVGO,ORCL,AMD,CRM,ADBE,NFLX,INTC,CSCO,QCOM,"
    "JPM,BAC,V,MA,GS,UNH,JNJ,LLY,PFE,MRK,ABBV,"
    "WMT,COST,PG,KO,PEP,MCD,HD,NKE,XOM,CVX,CAT,DE,GE,HON,LMT,BA,DIS,"
    "TSLA,MP,ALNT,RRX,SPY,QQQ"
)

W_LONG, W_SHORT, W_DAY = 0.55, 0.25, 0.20
MIN_BARS = 135   # 126 de momentum + 5 de salto + margen

COLUMNS = ["price", "day_chg", "mom_short", "mom_long", "rsi", "eligible", "score", "rank", "top_rank", "why"]


def parse_universe(text: str) -> list:
    out, seen = [], set()
    for s in (text or "").split(","):
        s = s.strip().upper()
        if s and "/" not in s and s not in seen:   # los pares cripto no entran en este screener
            seen.add(s)
            out.append(s)
    return out


def _rsi_last(close: pd.DataFrame, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean().iloc[-1]
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def compute_scores(close: pd.DataFrame, min_price: float = 10.0) -> pd.DataFrame:
    """
    `close`: precios de cierre diarios, una columna por símbolo, filas ordenadas por fecha (la última es "hoy").
    Devuelve una fila por símbolo con puntaje (0-100), si es elegible y por qué no lo es. Ordenado de mejor a peor.
    """
    if close is None or close.empty or len(close) < MIN_BARS:
        return pd.DataFrame(columns=COLUMNS)
    close = close.dropna(axis=1, how="all")
    last, prev = close.iloc[-1], close.iloc[-2]
    day = last / prev - 1
    m_short = last / close.iloc[-22] - 1
    m_long = close.iloc[-6] / close.iloc[-6 - 126] - 1          # 6 meses, terminando hace una semana
    sma20 = close.iloc[-20:].mean()
    sma50 = close.iloc[-50:].mean()
    full50 = close.iloc[-50:].notna().all()
    rsi = _rsi_last(close)

    valid = last.notna() & prev.notna() & m_short.notna() & m_long.notna() & full50 & rsi.notna()
    r_long = m_long[valid].rank(pct=True)
    r_short = m_short[valid].rank(pct=True)
    r_day = day[valid].rank(pct=True)
    score = pd.Series(np.nan, index=close.columns)
    score[valid] = 100 * (W_LONG * r_long + W_SHORT * r_short + W_DAY * r_day)

    why = pd.Series("", index=close.columns, dtype=object)
    checks = [
        (~valid, "sin historial suficiente"),
        (last < min_price, f"precio menor a ${min_price:g}"),
        (m_long <= 0, "momentum de 6 meses negativo"),
        (last <= sma50, "debajo de su media de 50 días"),
        (sma20 <= sma50, "tendencia corta por debajo de la larga"),
        (day <= -0.01, "cae más de 1% hoy"),
        (rsi >= 78, "sobrecomprada (RSI alto)"),
    ]
    for cond, text in reversed(checks):      # la primera condición que falla queda como motivo
        why[cond.fillna(True)] = text
    eligible = valid & (why == "")

    out = pd.DataFrame({
        "price": last, "day_chg": day, "mom_short": m_short, "mom_long": m_long, "rsi": rsi,
        "eligible": eligible, "score": score, "why": why,
    })
    out = out[out["score"].notna()].sort_values("score", ascending=False)
    out["rank"] = np.arange(1, len(out) + 1)
    top_rank = pd.Series(np.nan, index=out.index)
    elig_idx = out.index[out["eligible"]]
    top_rank[elig_idx] = np.arange(1, len(elig_idx) + 1)
    out["top_rank"] = top_rank
    return out[COLUMNS]


def top_n(scores: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Las N mejores acciones elegibles, de mayor a menor puntaje."""
    if scores is None or scores.empty:
        return pd.DataFrame(columns=COLUMNS)
    return scores[scores["eligible"]].head(n)


def decide(scores: pd.DataFrame, held: set, open_slots: int, replaceable: dict, top_n_: int = 3,
           min_score: float = 70.0, margin: float = 15.0, replacements_left: int = 1,
           min_hold_minutes: float = 1440.0) -> dict:
    """
    Decide qué hacer con el resultado del screener. Devuelve {"action": "none"|"buy"|"replace", "buy", "sell", "reason"}.

    - Hay lugar libre            -> compra la mejor candidata que no tengamos.
    - No hay lugar               -> reemplaza SOLO a una posición que abrió el propio screener (`replaceable`:
                                    símbolo -> minutos desde que se compró, o None si no se sabe), y solo si:
                                      * esa posición perdió fuerza (tendencia rota o salió del grupo de cabeza),
                                      * la candidata la supera por al menos `margin` puntos,
                                      * la posición lleva al menos `min_hold_minutes` abierta,
                                      * quedan reemplazos disponibles hoy.
    Que una posición esté en pérdida NO es motivo para venderla: lo es que su tendencia se haya roto.
    """
    none = {"action": "none", "buy": None, "sell": None, "reason": ""}
    if scores is None or scores.empty:
        return {**none, "reason": "sin datos del screener"}

    held = {s.upper() for s in held}
    cands = scores[(scores["eligible"]) & (scores["top_rank"] <= top_n_) & (scores["score"] >= min_score)]
    cands = cands[~cands.index.isin(held)]
    if cands.empty:
        return {**none, "reason": "ninguna candidata supera los filtros"}
    cand = cands.index[0]
    cscore = float(cands.iloc[0]["score"])

    if open_slots > 0:
        return {"action": "buy", "buy": cand, "sell": None,
                "reason": f"{cand} entra al Top {top_n_} del screener (puntaje {cscore:.0f})"}

    if replacements_left <= 0:
        return {**none, "reason": "sin lugar y ya se hicieron los reemplazos permitidos hoy"}

    weak_pool = []
    for sym, age in replaceable.items():
        sym = sym.upper()
        if sym not in scores.index:
            continue
        if age is not None and age < min_hold_minutes:
            continue
        row = scores.loc[sym]
        lost_strength = (not bool(row["eligible"])) or (float(row["top_rank"]) > 2 * top_n_)
        if lost_strength:
            weak_pool.append((float(row["score"]), sym, str(row["why"]) or "salió del grupo de cabeza"))
    if not weak_pool:
        return {**none, "reason": f"{cand} es candidata pero no hay lugar ni posición propia debilitada para reemplazar"}
    weak_pool.sort()
    wscore, weak, wwhy = weak_pool[0]
    if cscore - wscore < margin:
        return {**none, "reason": f"{cand} no supera a {weak} por el margen mínimo ({cscore - wscore:.0f} < {margin:.0f} puntos)"}
    return {"action": "replace", "buy": cand, "sell": weak,
            "reason": f"reemplaza a {weak} ({wwhy}, puntaje {wscore:.0f}) por {cand} (puntaje {cscore:.0f})"}
