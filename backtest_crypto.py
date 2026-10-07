"""
backtest_crypto.py
Compara varios pares cripto con la estrategia actual para elegir cuáles
vale la pena operar (CRYPTO_SYMBOLS), en vez de elegirlos a ojo.

Para cada par muestra:
  - retorno y drawdown de la estrategia sobre todo el período
  - cuánto habría dado "comprar y mantener" con la MISMA exposición
    (si la estrategia no le gana a eso, no aporta nada)
  - retorno en la primera y en la segunda mitad del período
    (un par que gana solo en una mitad probablemente fue suerte)
  - un veredicto: consistente / irregular / pocos trades

Uso:
    python backtest_crypto.py                       # 180 días, velas de 15 min, pares por defecto
    python backtest_crypto.py 365 15                # 365 días
    python backtest_crypto.py 180 15 BTC/USD,ETH/USD,SOL/USD

Necesita las keys de Alpaca en .env. La base de datos es opcional: si no
conecta, igual imprime la tabla (solo no guarda los resultados).
"""
import sys
from datetime import datetime, timezone

from config import Config
from backtest import fetch_history, simulate, save_to_db
from logger_db import init_db

DEFAULT_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "BCH/USD"]
MIN_TRADES = 15


def score(summary: dict) -> float:
    return summary["total_return_pct"] / max(summary["max_drawdown_pct"], 0.001)


def verdict(full: dict, first: dict, second: dict) -> str:
    if full["num_trades"] < MIN_TRADES:
        return "pocos trades"
    same_exposure_bh = full["buy_hold_pct"] * full["position_pct"]
    if (full["total_return_pct"] > 0 and first["total_return_pct"] > 0
            and second["total_return_pct"] > 0 and full["total_return_pct"] > same_exposure_bh):
        return "consistente"
    return "irregular"


def main():
    days_back = int(sys.argv[1]) if len(sys.argv) >= 2 else 180
    minutes = int(sys.argv[2]) if len(sys.argv) >= 3 else Config.CRYPTO_TIMEFRAME_MINUTES
    pairs = [p.strip().upper() for p in sys.argv[3].split(",")] if len(sys.argv) >= 4 else DEFAULT_PAIRS
    lookback = Config.LOOKBACK_BARS

    db_ok = True
    try:
        init_db()
    except Exception as e:
        db_ok = False
        print(f"(Aviso: no se pudo conectar a la base, los resultados no se van a guardar: {e})\n")

    run_ts = datetime.now(timezone.utc).isoformat()
    print(f"Ritmo conservador: pausa {Config.CRYPTO_COOLDOWN_MINUTES} min tras cada cierre, máx. {Config.CRYPTO_MAX_TRADES_PER_DAY or 'sin límite'} compras/día por par, posición {Config.CRYPTO_MAX_POSITION_PCT:.0%}")
    print(f"\n{'='*78}\nBACKTEST CRIPTO — {days_back} días — velas {minutes} min — {len(pairs)} pares\n{'='*78}\n")

    rows = []
    for pair in pairs:
        print(f"Descargando {pair}...")
        try:
            df = fetch_history(None, pair, days_back, minutes)
        except Exception as e:
            print(f"  No se pudo descargar {pair}: {e}\n")
            continue
        if df is None or len(df) < lookback * 2 + 40:
            print(f"  Datos insuficientes para {pair}. Se omite.\n")
            continue

        full = simulate(df, pair, lookback)
        mid = len(df) // 2
        first = simulate(df.iloc[:mid], pair, lookback)
        second = simulate(df.iloc[mid - lookback:], pair, lookback)
        rows.append((pair, full, first, second))
        if db_ok:
            try:
                save_to_db(run_ts, full)
            except Exception as e:
                print(f"  (No se pudo guardar {pair} en la base: {e})")

    if not rows:
        print("No hubo resultados.")
        return

    rows.sort(key=lambda r: score(r[1]), reverse=True)
    header = f"{'PAR':<10}{'TRADES':>7}{'RETORNO':>10}{'DRAWDOWN':>10}{'WIN%':>7}{'B&H*':>9}{'1ª MITAD':>10}{'2ª MITAD':>10}  VEREDICTO"
    print("\n" + header)
    print("-" * len(header))
    for pair, full, first, second in rows:
        bh = full["buy_hold_pct"] * full["position_pct"]
        print(f"{pair:<10}{full['num_trades']:>7}{full['total_return_pct']*100:>9.2f}%{full['max_drawdown_pct']*100:>9.2f}%"
              f"{full['win_rate']*100:>6.0f}%{bh*100:>8.2f}%{first['total_return_pct']*100:>9.2f}%{second['total_return_pct']*100:>9.2f}%  "
              f"{verdict(full, first, second)}")

    good = [r[0] for r in rows if verdict(r[1], r[2], r[3]) == "consistente"]
    print("\n* B&H = comprar y mantener con la misma exposición que usa la estrategia.")
    print("  Retorno medido sobre USD 10.000 por par; incluye comisión de {:.2%} por lado.".format(Config.CRYPTO_FEE_PCT))
    if good:
        print(f"\nPares consistentes: {', '.join(good)}")
        print(f"Para activarlos en Railway (servicio agent):  CRYPTO_SYMBOLS={','.join(good[:3])}")
    else:
        print("\nNingún par fue consistente en ambas mitades y a la vez le ganó a comprar y mantener.")
        print("Eso es información útil: con estos parámetros, mejor NO activar cripto todavía.")
    print("\nOJO: el pasado no garantiza nada, y estos números son in-sample. Probá primero en paper varios días.\n")


if __name__ == "__main__":
    main()
