"""
strategy.py
Estrategia: cruce de medias móviles + filtro de RSI. Parametrizable para
que el optimizador pueda probar combinaciones; sin pasar nada, usa los
valores de producción actuales.
"""
import pandas as pd


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def compute_signal(df: pd.DataFrame, sma_fast_len: int = 10, sma_slow_len: int = 30,
                    rsi_len: int = 14, rsi_buy_max: float = 70, rsi_sell_min: float = None) -> dict:
    if df is None or len(df) < max(sma_slow_len, rsi_len) + 5:
        return {"signal": "hold", "reason": "datos insuficientes"}

    close = df["close"]
    sma_fast = _sma(close, sma_fast_len)
    sma_slow = _sma(close, sma_slow_len)
    rsi = _rsi(close, rsi_len)

    if sma_fast.isna().iloc[-1] or sma_slow.isna().iloc[-1] or rsi.isna().iloc[-1]:
        return {"signal": "hold", "reason": "no se pudieron calcular indicadores (datos insuficientes)"}

    last_fast, prev_fast = sma_fast.iloc[-1], sma_fast.iloc[-2]
    last_slow, prev_slow = sma_slow.iloc[-1], sma_slow.iloc[-2]
    last_rsi = rsi.iloc[-1]

    crossed_up = prev_fast <= prev_slow and last_fast > last_slow
    crossed_down = prev_fast >= prev_slow and last_fast < last_slow

    details = {
        "sma_fast": round(float(last_fast), 4),
        "sma_slow": round(float(last_slow), 4),
        "rsi": round(float(last_rsi), 2),
        "last_close": round(float(close.iloc[-1]), 4),
    }

    if crossed_up and last_rsi < rsi_buy_max:
        return {"signal": "buy", "reason": "cruce alcista SMA rápida/lenta + RSI ok", **details}

    if crossed_down:
        return {"signal": "sell", "reason": "cruce bajista SMA (reversión de tendencia)", **details}

    return {"signal": "hold", "reason": "sin condiciones de entrada/salida", **details}
