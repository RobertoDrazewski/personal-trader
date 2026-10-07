"""
main.py
Loop principal del agente. En Railway, este es el start command del
servicio "agent": python -u main.py

Opera acciones (solo con el mercado abierto) y, si CRYPTO_SYMBOLS no está
vacío, también cripto (24/7) con la misma estrategia, el mismo motor de
riesgo y el mismo kill switch.
"""
import sys
import time

from config import Config, is_crypto, norm_symbol
from logger_db import init_db, log_event, log_equity, log_signal, get_state, set_state, delete_state
from risk_engine import RiskEngine
from broker_alpaca import AlpacaBroker
from strategy import compute_signal
from alerts import send_alert
from news_source import get_latest_headline
from llm_analysis import analyze_news

CRYPTO_PEAK_PREFIX = "crypto_peak:"


def confirm_live_mode_or_exit():
    if Config.IS_PAPER:
        return
    print("=" * 60)
    print("  ATENCIÓN: MODE=live — esto opera con PLATA REAL.")
    print("=" * 60)
    resp = input("Escribí CONFIRMO para continuar, o cualquier otra cosa para salir: ")
    if resp.strip() != "CONFIRMO":
        print("No confirmado. Cerrando. Cambiá MODE=paper si fue un error.")
        sys.exit(0)
    log_event("critical", "Arranque en modo LIVE confirmado manualmente.")


# ---------- Trailing stop de cripto (lo maneja el agente: Alpaca no lo ofrece para cripto) ----------
def _get_peak(symbol: str):
    raw = get_state(CRYPTO_PEAK_PREFIX + norm_symbol(symbol))
    return float(raw) if raw else None


def _set_peak(symbol: str, value: float):
    set_state(CRYPTO_PEAK_PREFIX + norm_symbol(symbol), repr(float(value)))


def _clear_peak(symbol: str):
    delete_state(CRYPTO_PEAK_PREFIX + norm_symbol(symbol))


def protect_crypto_positions(broker: AlpacaBroker, positions=None):
    """
    Revisa cada posición cripto abierta: sube el precio pico y vende si el precio
    cae más del trailing stop desde ese pico. Corre en cada ciclo, incluso con el
    trading pausado o el kill switch activo, para que ninguna posición cripto
    quede sin protección. Se evalúa cada POLL_INTERVAL_SECONDS (no es una orden
    server-side como la de las acciones).
    """
    if positions is None:
        positions = broker.get_open_positions()
    for p in positions:
        if not broker.is_crypto_position(p):
            continue
        try:
            price = float(p.current_price)
            peak = _get_peak(p.symbol)
            if peak is None or price > peak:
                peak = price
                _set_peak(p.symbol, peak)
            trail = Config.CRYPTO_TRAILING_STOP_PCT
            stop_price = peak * (1 - trail)
            if price <= stop_price:
                reason = f"trailing stop cripto {trail:.1%} (pico {peak:,.2f}, precio {price:,.2f})"
                if broker.close_position(p.symbol, reason=reason):
                    _clear_peak(p.symbol)
                    send_alert(f"🛡️ CIERRE {p.symbol} — {reason}")
        except Exception as e:
            log_event("error", f"Error protegiendo la posición cripto {p.symbol}: {e}")


# ---------- Un símbolo ----------
def process_symbol(broker: AlpacaBroker, risk: RiskEngine, symbol: str, equity: float, held: set, counts: dict):
    crypto = is_crypto(symbol)
    kind = "crypto" if crypto else "stock"

    df = broker.get_recent_bars(symbol, Config.TIMEFRAME_MINUTES, Config.LOOKBACK_BARS)
    result = compute_signal(df)
    log_signal(symbol, result["signal"], result)

    has_position = norm_symbol(symbol) in held

    if result["signal"] == "buy" and not has_position:
        if not risk.can_open_new_position(counts[kind], crypto=crypto):
            log_event("info", f"{symbol}: señal de compra ignorada — máximo de posiciones {'cripto' if crypto else 'de acciones'} alcanzado.")
            return
        price = result.get("last_close")
        if not price:
            return
        qty = risk.position_size(equity, price, crypto=crypto)
        if qty <= 0:
            return

        buy_reason = result["reason"]
        if Config.USE_NEWS_FILTER:
            headline = get_latest_headline(norm_symbol(symbol) if crypto else symbol)
            if headline:
                sentiment = analyze_news(symbol, headline)
                log_event(
                    "info",
                    f"{symbol}: noticia '{headline[:80]}' -> sentimiento {sentiment['sentiment']} "
                    f"(confianza {sentiment['confidence']:.2f})",
                )
                if (sentiment["sentiment"] == "negative"
                        and sentiment["confidence"] >= Config.NEWS_NEGATIVE_BLOCK_CONFIDENCE):
                    log_event("info", f"{symbol}: compra CANCELADA por noticia negativa — {sentiment['reason']}")
                    return
                buy_reason = f"{buy_reason} | noticia: {sentiment['sentiment']}"

        qty_label = f"{qty:.6f}" if crypto else f"{qty}"
        order = broker.submit_market_order(symbol, qty, "buy", reason=buy_reason)
        if not order:
            return
        filled_order = broker.wait_for_fill(str(order.id))
        if not filled_order:
            send_alert(f"⚠️ Compra de {symbol} x{qty_label} enviada pero no se confirmó el fill a tiempo.")
            return

        held.add(norm_symbol(symbol))
        counts[kind] += 1

        if crypto:
            fill_price = float(filled_order.filled_avg_price or price)
            _set_peak(symbol, fill_price)
            send_alert(
                f"🟢 COMPRA {symbol} x{qty_label} @ ~{fill_price:,.2f} — {buy_reason}\n"
                f"   Trailing stop cripto: {risk.trailing_stop_percent(crypto=True)}% (lo vigila el agente)"
            )
        else:
            trail_pct = risk.trailing_stop_percent()
            ts_order = broker.submit_trailing_stop_sell(symbol, qty, trail_pct, reason="protección post-compra")
            if ts_order:
                send_alert(f"🟢 COMPRA {symbol} x{qty_label} @ ~{price} — {buy_reason}\n   Trailing stop: {trail_pct}%")
            else:
                send_alert(f"⚠️ COMPRA {symbol} x{qty_label} ejecutada, pero el trailing stop FALLÓ.")

    elif result["signal"] == "sell" and has_position:
        if not crypto:
            broker.cancel_open_orders_for_symbol(symbol)
        if broker.close_position(symbol, reason=result["reason"]):
            held.discard(norm_symbol(symbol))
            counts[kind] -= 1
            if crypto:
                _clear_peak(symbol)
            send_alert(f"🔴 VENTA/cierre {symbol} — {result['reason']}")


# ---------- Un ciclo ----------
def run_cycle(broker: AlpacaBroker, risk: RiskEngine):
    equity, cash = broker.get_equity_and_cash()
    can_trade, reason = risk.check_account_health(equity)

    daily_pl_pct, drawdown_pct = risk.snapshot_metrics(equity)
    log_equity(equity, cash, daily_pl_pct, drawdown_pct)

    positions = broker.get_open_positions()

    # La protección de cripto corre siempre, aunque el trading esté pausado.
    if Config.CRYPTO_SYMBOLS or any(broker.is_crypto_position(p) for p in positions):
        protect_crypto_positions(broker, positions)
        positions = broker.get_open_positions()

    stock_market_open = broker.is_market_open() if Config.SYMBOLS else False
    mercado = "abierto" if stock_market_open else "cerrado"
    cripto = f" | cripto 24/7 ({len(Config.CRYPTO_SYMBOLS)} pares)" if Config.CRYPTO_SYMBOLS else ""
    log_event("info", f"Ciclo OK — equity=${equity:,.2f} | mercado {mercado}{cripto} | drawdown={drawdown_pct:.2%}")

    if not can_trade:
        log_event("warning", f"Trading pausado: {reason}")
        return

    held = {norm_symbol(p.symbol) for p in positions}
    n_crypto = sum(1 for p in positions if broker.is_crypto_position(p))
    counts = {"crypto": n_crypto, "stock": len(positions) - n_crypto}

    if stock_market_open:
        for symbol in Config.SYMBOLS:
            try:
                process_symbol(broker, risk, symbol, equity, held, counts)
            except Exception as e:
                log_event("error", f"Error procesando {symbol}: {e}")

    for symbol in Config.CRYPTO_SYMBOLS:
        try:
            process_symbol(broker, risk, symbol, equity, held, counts)
        except Exception as e:
            log_event("error", f"Error procesando {symbol}: {e}")


def main():
    problems = Config.validate()
    if problems:
        for p in problems:
            print(f"CONFIG ERROR: {p}")
        sys.exit(1)

    init_db()
    confirm_live_mode_or_exit()

    broker = AlpacaBroker()
    risk = RiskEngine()

    log_event(
        "info",
        f"Agente iniciado. Acciones: {Config.SYMBOLS} | Cripto: {Config.CRYPTO_SYMBOLS or 'desactivada'} | Modo: {Config.MODE.upper()}",
    )
    send_alert(f"🤖 Agente de trading iniciado en modo {Config.MODE.upper()} (Railway).")

    while True:
        try:
            if risk.is_kill_switch_active():
                log_event("critical", "Kill switch activo — el agente no abre posiciones nuevas. Esperando...")
                # Aun así, las posiciones cripto que ya estén abiertas siguen vigiladas.
                protect_crypto_positions(broker)
            else:
                run_cycle(broker, risk)
        except Exception as e:
            log_event("error", f"Error inesperado en el ciclo principal: {e}")
            send_alert(f"⚠️ Error en el agente: {e}")

        time.sleep(Config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
