"""
optimize.py
Prueba combinaciones de parámetros sobre datos históricos (in-sample —
validar en un período distinto antes de usar en producción).

Uso:
    python optimize.py AAPL 730
    python optimize.py MSFT 365 15
"""
import sys
import itertools
import psycopg2
from datetime import datetime, timezone

from alpaca.data.historical import StockHistoricalDataClient

from config import Config
from backtest import fetch_history, simulate
from logger_db import init_db, _dsn

MIN_TRADES_FOR_RANKING = 15

SMA_FAST_OPTIONS = [5, 10, 15, 20]
SMA_SLOW_OPTIONS = [20, 30, 50, 100]
RSI_LEN_OPTIONS = [14]
RSI_BUY_MAX_OPTIONS = [60, 70, 80]
TRAILING_STOP_OPTIONS = [0.02, 0.03, 0.05, 0.08]


def score(summary: dict) -> float:
    dd = max(summary["max_drawdown_pct"], 0.001)
    return summary["total_return_pct"] / dd


def save_result(run_ts, symbol, params, summary):
    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS optimize_results (
                id SERIAL PRIMARY KEY, run_ts TEXT, symbol TEXT,
                sma_fast INTEGER, sma_slow INTEGER, rsi_len INTEGER, rsi_buy_max REAL,
                trailing_stop_pct REAL, num_trades INTEGER, win_rate REAL,
                total_return_pct REAL, max_drawdown_pct REAL, score REAL
            )
        """)
        cur.execute(
            "INSERT INTO optimize_results (run_ts, symbol, sma_fast, sma_slow, rsi_len, rsi_buy_max, "
            "trailing_stop_pct, num_trades, win_rate, total_return_pct, max_drawdown_pct, score) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (run_ts, symbol, params["sma_fast"], params["sma_slow"], params["rsi_len"],
             params["rsi_buy_max"], params["trailing_stop"], summary["num_trades"],
             summary["win_rate"], summary["total_return_pct"], summary["max_drawdown_pct"], score(summary)),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    init_db()
    if len(sys.argv) < 2:
        print("Uso: python optimize.py SYMBOL [dias_atras] [timeframe_minutos] [lookback_bars]")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    days_back = int(sys.argv[2]) if len(sys.argv) >= 3 else 730
    minutes = int(sys.argv[3]) if len(sys.argv) >= 4 else 1440
    lookback = int(sys.argv[4]) if len(sys.argv) >= 5 else max(SMA_SLOW_OPTIONS) + 5

    client = StockHistoricalDataClient(Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY)
    run_ts = datetime.now(timezone.utc).isoformat()

    print(f"Descargando histórico de {symbol} ({days_back} días, velas de {minutes} min)...")
    df = fetch_history(client, symbol, days_back, minutes)
    if df is None or len(df) < lookback + 20:
        print("No hay suficientes datos históricos.")
        sys.exit(1)
    print(f"{len(df)} barras descargadas. Probando combinaciones...\n")

    combos = [c for c in itertools.product(
        SMA_FAST_OPTIONS, SMA_SLOW_OPTIONS, RSI_LEN_OPTIONS, RSI_BUY_MAX_OPTIONS, TRAILING_STOP_OPTIONS
    ) if c[0] < c[1]]

    results = []
    for i, (sma_fast, sma_slow, rsi_len, rsi_buy_max, trailing) in enumerate(combos):
        summary = simulate(df, symbol, lookback, sma_fast_len=sma_fast, sma_slow_len=sma_slow,
                            rsi_len=rsi_len, rsi_buy_max=rsi_buy_max, trailing_stop_pct=trailing)
        params = {"sma_fast": sma_fast, "sma_slow": sma_slow, "rsi_len": rsi_len,
                   "rsi_buy_max": rsi_buy_max, "trailing_stop": trailing}
        results.append((params, summary))
        save_result(run_ts, symbol, params, summary)
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(combos)} combinaciones probadas...")

    print(f"\nListo. {len(combos)} combinaciones guardadas en Postgres.\n")

    valid = [(p, s) for p, s in results if s["num_trades"] >= MIN_TRADES_FOR_RANKING]
    if not valid:
        print(f"Ninguna combinación alcanzó el mínimo de {MIN_TRADES_FOR_RANKING} operaciones.")
        return

    valid.sort(key=lambda x: score(x[1]), reverse=True)
    print(f"{'='*70}\nTOP 5 combinaciones\n{'='*70}")
    for params, summary in valid[:5]:
        print(f"SMA {params['sma_fast']}/{params['sma_slow']} | RSI<{params['rsi_buy_max']} | "
              f"trailing {params['trailing_stop']*100:.0f}% -> retorno {summary['total_return_pct']*100:.2f}% | "
              f"drawdown {summary['max_drawdown_pct']*100:.2f}% | {summary['num_trades']} trades | "
              f"win rate {summary['win_rate']*100:.1f}% | score {score(summary):.2f}")

    print("\nOJO: validar estos parámetros en OTRO período antes de usarlos en producción (ver README).")


if __name__ == "__main__":
    main()
