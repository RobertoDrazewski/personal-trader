"""
backtest.py
Simula la estrategia barra por barra contra datos históricos.
Funciona con acciones (AAPL) y con pares cripto (BTC/USD).

Uso:
    python backtest.py
    python backtest.py AAPL 180
    python backtest.py AAPL 1095 1440 50
    python backtest.py BTC/USD 180 15
"""
import sys
import psycopg2
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

from config import Config, is_crypto
from strategy import compute_signal
from logger_db import init_db, _dsn

STARTING_CAPITAL_PER_SYMBOL = 10000.0

_crypto_client = None


def _get_crypto_client():
    global _crypto_client
    if _crypto_client is None:
        _crypto_client = CryptoHistoricalDataClient(Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY)
    return _crypto_client


def fetch_history(client, symbol: str, days_back: int, minutes: int) -> pd.DataFrame:
    """`client` es el cliente de acciones; para pares cripto se usa el cliente cripto automáticamente."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    timeframe = TimeFrame(minutes, TimeFrameUnit.Minute) if minutes != 1440 else TimeFrame.Day
    if is_crypto(symbol):
        req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start, end=end)
        bars = _get_crypto_client().get_crypto_bars(req)
    else:
        req = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=timeframe, start=start, end=end, feed=DataFeed.IEX,
        )
        bars = client.get_stock_bars(req)
    df = bars.df
    if df is None or df.empty:
        return None
    if symbol in df.index.get_level_values(0):
        df = df.loc[symbol]
    return df


_EWM_W = {}


def _ewm_weights(m: int, alpha: float):
    """Pesos del último valor de un EWM (adjust=False) sobre m datos: igual que pandas, pero en una sola multiplicación."""
    key = (m, alpha)
    if key not in _EWM_W:
        w = alpha * (1 - alpha) ** np.arange(m - 1, -1, -1)
        w[0] = (1 - alpha) ** (m - 1)
        _EWM_W[key] = w
    return _EWM_W[key]


def fast_signal(w: np.ndarray, sma_fast_len: int, sma_slow_len: int, rsi_len: int, rsi_buy_max: float) -> str:
    """
    Misma lógica que strategy.compute_signal (cruce de SMAs + filtro RSI), pero con numpy
    sobre la ventana en vez de pandas. Es ~20x más rápido; solo devuelve 'buy' / 'sell' / 'hold'.
    """
    n = len(w)
    if n < max(sma_slow_len, rsi_len) + 5:
        return "hold"
    last_fast, prev_fast = w[-sma_fast_len:].mean(), w[-sma_fast_len - 1:-1].mean()
    last_slow, prev_slow = w[-sma_slow_len:].mean(), w[-sma_slow_len - 1:-1].mean()
    delta = np.diff(w)
    alpha = 1.0 / rsi_len
    weights = _ewm_weights(len(delta), alpha)
    avg_gain = float(np.dot(np.maximum(delta, 0.0), weights))
    avg_loss = float(np.dot(np.maximum(-delta, 0.0), weights))
    rs = avg_gain / (avg_loss if avg_loss != 0 else 1e-10)
    last_rsi = 100 - (100 / (1 + rs))
    if prev_fast <= prev_slow and last_fast > last_slow and last_rsi < rsi_buy_max:
        return "buy"
    if prev_fast >= prev_slow and last_fast < last_slow:
        return "sell"
    return "hold"


def simulate(df: pd.DataFrame, symbol: str, lookback: int,
             sma_fast_len: int = 10, sma_slow_len: int = 30, rsi_len: int = 14, rsi_buy_max: float = 70,
             stop_loss_pct: float = None, trailing_stop_pct: float = None, max_position_pct: float = None,
             fee_pct: float = None):
    crypto = is_crypto(symbol)
    stop_loss_pct = Config.STOP_LOSS_PCT if stop_loss_pct is None else stop_loss_pct
    if trailing_stop_pct is None:
        trailing_stop_pct = Config.CRYPTO_TRAILING_STOP_PCT if crypto else Config.TRAILING_STOP_PCT
    if max_position_pct is None:
        max_position_pct = Config.CRYPTO_MAX_POSITION_PCT if crypto else Config.MAX_POSITION_PCT
    if fee_pct is None:
        fee_pct = Config.CRYPTO_FEE_PCT if crypto else 0.0

    cash = STARTING_CAPITAL_PER_SYMBOL
    position_qty = 0.0
    entry_price = 0.0
    initial_stop = 0.0
    trailing_stop = 0.0
    peak_price = 0.0

    trades = []
    equity_curve = []

    closes = df["close"].to_numpy(dtype=float)
    for i in range(lookback, len(df)):
        result = {"signal": fast_signal(closes[i - lookback: i], sma_fast_len, sma_slow_len, rsi_len, rsi_buy_max)}
        price = float(closes[i])
        ts = df.index[i]

        if position_qty > 0:
            if price > peak_price:
                peak_price = price
                trailing_stop = round(peak_price * (1 - trailing_stop_pct), 6)
            effective_stop = max(initial_stop, trailing_stop)
            if price <= effective_stop or result["signal"] == "sell":
                proceeds = position_qty * price * (1 - fee_pct)
                pnl = proceeds - position_qty * entry_price * (1 + fee_pct)
                cash += proceeds
                trades.append({"entry": entry_price, "exit": price, "qty": position_qty, "pnl": pnl, "exit_ts": str(ts)})
                position_qty = 0.0
        elif result["signal"] == "buy":
            max_dollars = cash * max_position_pct
            # Acciones: cantidad entera. Cripto: fraccionaria.
            qty = (max_dollars / (price * (1 + fee_pct))) if crypto else int(max_dollars // price)
            if qty > 0:
                entry_price = price
                peak_price = price
                initial_stop = round(price * (1 - stop_loss_pct), 6)
                trailing_stop = round(price * (1 - trailing_stop_pct), 6)
                cash -= qty * price * (1 + fee_pct)
                position_qty = qty

        current_equity = cash + (position_qty * price if position_qty else 0)
        equity_curve.append({"ts": str(ts), "equity": current_equity})

    if position_qty > 0:
        last_price = float(df["close"].iloc[-1])
        proceeds = position_qty * last_price * (1 - fee_pct)
        pnl = proceeds - position_qty * entry_price * (1 + fee_pct)
        cash += proceeds
        trades.append({"entry": entry_price, "exit": last_price, "qty": position_qty, "pnl": pnl, "exit_ts": "fin_periodo"})

    final_equity = cash
    total_return_pct = (final_equity - STARTING_CAPITAL_PER_SYMBOL) / STARTING_CAPITAL_PER_SYMBOL
    peak = STARTING_CAPITAL_PER_SYMBOL
    max_dd = 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        dd = (peak - point["equity"]) / peak if peak else 0
        max_dd = max(max_dd, dd)
    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = (len(wins) / len(trades)) if trades else 0.0

    # Referencia: comprar al principio del período simulado y no vender nunca.
    first_price = float(df["close"].iloc[lookback])
    last_price = float(df["close"].iloc[-1])
    buy_hold_pct = (last_price - first_price) / first_price if first_price else 0.0

    return {
        "symbol": symbol, "trades": trades, "equity_curve": equity_curve,
        "final_equity": final_equity, "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd, "num_trades": len(trades), "win_rate": win_rate,
        "buy_hold_pct": buy_hold_pct, "position_pct": max_position_pct,
    }


def save_to_db(run_ts: str, summary: dict):
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id SERIAL PRIMARY KEY, run_ts TEXT, symbol TEXT, num_trades INTEGER,
                win_rate REAL, total_return_pct REAL, max_drawdown_pct REAL
            )
        """)
        # Columna agregada al sumar cripto: referencia de "comprar y mantener".
        cur.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS buy_hold_pct REAL")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_equity_curve (
                id SERIAL PRIMARY KEY, run_ts TEXT, symbol TEXT, ts TEXT, equity REAL
            )
        """)
        cur.execute(
            "INSERT INTO backtest_results (run_ts, symbol, num_trades, win_rate, total_return_pct, max_drawdown_pct, buy_hold_pct) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (run_ts, summary["symbol"], summary["num_trades"], summary["win_rate"],
             summary["total_return_pct"], summary["max_drawdown_pct"], summary.get("buy_hold_pct")),
        )
        for point in summary["equity_curve"]:
            cur.execute(
                "INSERT INTO backtest_equity_curve (run_ts, symbol, ts, equity) VALUES (%s, %s, %s, %s)",
                (run_ts, summary["symbol"], point["ts"], point["equity"]),
            )
        conn.commit()
    finally:
        conn.close()


def main():
    init_db()
    symbols = Config.SYMBOLS + Config.CRYPTO_SYMBOLS
    days_back, minutes, lookback = 180, Config.TIMEFRAME_MINUTES, Config.LOOKBACK_BARS

    if len(sys.argv) >= 2:
        symbols = [sys.argv[1].upper()]
    if len(sys.argv) >= 3:
        days_back = int(sys.argv[2])
    if len(sys.argv) >= 4:
        minutes = int(sys.argv[3])
    if len(sys.argv) >= 5:
        lookback = int(sys.argv[4])

    client = StockHistoricalDataClient(Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY)
    run_ts = datetime.now(timezone.utc).isoformat()

    print(f"\n{'='*60}\nBACKTEST — últimos {days_back} días — velas {minutes}min — {symbols}\n{'='*60}\n")

    for symbol in symbols:
        print(f"Descargando histórico de {symbol}...")
        df = fetch_history(client, symbol, days_back, minutes)
        if df is None or len(df) < lookback + 10:
            print(f"  No hay suficientes datos para {symbol}. Se omite.\n")
            continue
        summary = simulate(df, symbol, lookback)
        save_to_db(run_ts, summary)
        same_exposure_bh = summary["buy_hold_pct"] * summary["position_pct"]
        print(f"  {symbol}: retorno {summary['total_return_pct']*100:.2f}% | drawdown {summary['max_drawdown_pct']*100:.2f}% | "
              f"{summary['num_trades']} trades | win rate {summary['win_rate']*100:.1f}% | "
              f"comprar y mantener (misma exposición): {same_exposure_bh*100:.2f}%\n")

    print("Listo. Resultados guardados en Postgres — visibles en el dashboard.\n")


if __name__ == "__main__":
    main()
