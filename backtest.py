"""
backtest.py
Simula la estrategia barra por barra contra datos históricos.

Uso:
    python backtest.py
    python backtest.py AAPL 180
    python backtest.py AAPL 1095 1440 50
"""
import sys
import psycopg2
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

from config import Config
from strategy import compute_signal
from logger_db import init_db, _dsn

STARTING_CAPITAL_PER_SYMBOL = 10000.0


def fetch_history(client, symbol: str, days_back: int, minutes: int) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(minutes, TimeFrameUnit.Minute) if minutes != 1440 else TimeFrame.Day,
        start=start, end=end, feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(req)
    df = bars.df
    if df is None or df.empty:
        return None
    if symbol in df.index.get_level_values(0):
        df = df.loc[symbol]
    return df


def simulate(df: pd.DataFrame, symbol: str, lookback: int,
             sma_fast_len: int = 10, sma_slow_len: int = 30, rsi_len: int = 14, rsi_buy_max: float = 70,
             stop_loss_pct: float = None, trailing_stop_pct: float = None, max_position_pct: float = None):
    stop_loss_pct = Config.STOP_LOSS_PCT if stop_loss_pct is None else stop_loss_pct
    trailing_stop_pct = Config.TRAILING_STOP_PCT if trailing_stop_pct is None else trailing_stop_pct
    max_position_pct = Config.MAX_POSITION_PCT if max_position_pct is None else max_position_pct

    cash = STARTING_CAPITAL_PER_SYMBOL
    position_qty = 0
    entry_price = 0.0
    initial_stop = 0.0
    trailing_stop = 0.0
    peak_price = 0.0

    trades = []
    equity_curve = []

    for i in range(lookback, len(df)):
        window = df.iloc[i - lookback: i]
        result = compute_signal(window, sma_fast_len, sma_slow_len, rsi_len, rsi_buy_max)
        price = float(df["close"].iloc[i])
        ts = df.index[i]

        if position_qty > 0:
            if price > peak_price:
                peak_price = price
                trailing_stop = round(peak_price * (1 - trailing_stop_pct), 2)
            effective_stop = max(initial_stop, trailing_stop)
            if price <= effective_stop or result["signal"] == "sell":
                pnl = (price - entry_price) * position_qty
                cash += position_qty * price
                trades.append({"entry": entry_price, "exit": price, "qty": position_qty, "pnl": pnl, "exit_ts": str(ts)})
                position_qty = 0
        elif result["signal"] == "buy":
            max_dollars = cash * max_position_pct
            qty = int(max_dollars // price)
            if qty > 0:
                entry_price = price
                peak_price = price
                initial_stop = round(price * (1 - stop_loss_pct), 2)
                trailing_stop = round(price * (1 - trailing_stop_pct), 2)
                cash -= qty * price
                position_qty = qty

        current_equity = cash + (position_qty * price if position_qty else 0)
        equity_curve.append({"ts": str(ts), "equity": current_equity})

    if position_qty > 0:
        last_price = float(df["close"].iloc[-1])
        pnl = (last_price - entry_price) * position_qty
        cash += position_qty * last_price
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

    return {
        "symbol": symbol, "trades": trades, "equity_curve": equity_curve,
        "final_equity": final_equity, "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd, "num_trades": len(trades), "win_rate": win_rate,
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_equity_curve (
                id SERIAL PRIMARY KEY, run_ts TEXT, symbol TEXT, ts TEXT, equity REAL
            )
        """)
        cur.execute(
            "INSERT INTO backtest_results (run_ts, symbol, num_trades, win_rate, total_return_pct, max_drawdown_pct) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (run_ts, summary["symbol"], summary["num_trades"], summary["win_rate"],
             summary["total_return_pct"], summary["max_drawdown_pct"]),
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
    symbols = Config.SYMBOLS
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
        print(f"  {symbol}: retorno {summary['total_return_pct']*100:.2f}% | drawdown {summary['max_drawdown_pct']*100:.2f}% | "
              f"{summary['num_trades']} trades | win rate {summary['win_rate']*100:.1f}%\n")

    print("Listo. Resultados guardados en Postgres — visibles en el dashboard.\n")


if __name__ == "__main__":
    main()
