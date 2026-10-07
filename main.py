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

from config import Config, is_crypto, norm_symbol, timeframe_for
from logger_db import init_db, log_event, log_equity, log_signal, get_state, set_state, delete_state
from risk_engine import (RiskEngine, crypto_buy_blocked, crypto_note_buy, crypto_note_close, crypto_record_result,
                         crypto_halt, crypto_halt_reason, crypto_pl_today)
from broker_alpaca import AlpacaBroker
from strategy import compute_signal
from alerts import send_alert
from news_source import get_latest_headline
from llm_analysis import analyze_news

CRYPTO_PEAK_PREFIX = "crypto_peak:"
_last_block_msg = {}   # evita repetir en el log el mismo motivo de bloqueo cada minuto
_news_blocked_at = {}  # cripto: hora (time.time) de la última compra frenada por noticia negativa
NEWS_RECHECK_SECONDS = 1800
_last_equity = None    # equity del ciclo anterior, para detectar caídas anormales


def critical(message: str):
    """Alarma crítica: queda en el log del panel y llega por Telegram."""
    try:
        log_event("critical", message)
    except Exception:
        pass
    send_alert(f"🚨 CRÍTICO — {message}")


def crypto_net_pnl(unrealized_pl: float, market_value: float) -> float:
    """P&L de una posición cripto descontando las comisiones estimadas de entrada y salida (CRYPTO_FEE_PCT por lado).
    El P&L que informa el broker no incluye la comisión de la venta, así que sin esto los frenos verían menos pérdida."""
    mv = abs(float(market_value))
    entry_value = mv - float(unrealized_pl)
    return float(unrealized_pl) - Config.CRYPTO_FEE_PCT * (entry_value + mv)


def register_crypto_close(symbol: str, pnl):
    """Anota un cierre cripto (pausa, resultado del día y racha). Si la racha de pérdidas llega al máximo, frena la cripto."""
    crypto_note_close(symbol)
    if pnl is None:
        return
    streak = crypto_record_result(pnl)
    mx = Config.CRYPTO_MAX_CONSECUTIVE_LOSSES
    if mx > 0 and streak >= mx and not crypto_halt_reason():
        why = f"{streak} cierres seguidos en pérdida"
        crypto_halt(why, until_tomorrow=False)
        critical(f"Cripto FRENADA: {why}. No compra más cripto hasta que la reactives en la pestaña Control.")


def check_crypto_daily_loss(broker: AlpacaBroker, positions, equity: float):
    """Si la pérdida cripto del día (cerrada + abierta) pasa el límite, cierra todo lo cripto y frena hasta mañana."""
    pct = Config.CRYPTO_DAILY_LOSS_PCT
    if pct <= 0 or crypto_halt_reason():
        return
    crypto_pos = [p for p in positions if broker.is_crypto_position(p)]
    total = crypto_pl_today() + sum(crypto_net_pnl(p.unrealized_pl, p.market_value) for p in crypto_pos)
    if total > -equity * pct:
        return
    why = f"pérdida cripto del día ${total:,.2f} (límite {pct:.1%} del equity)"
    crypto_halt(why, until_tomorrow=True)
    for p in crypto_pos:
        pnl = crypto_net_pnl(p.unrealized_pl, p.market_value)
        if broker.close_position(p.symbol, reason="stop trading cripto"):
            _clear_peak(p.symbol)
            register_crypto_close(p.symbol, pnl)
    critical(f"Cripto FRENADA hasta mañana: {why}. Se cerraron las posiciones cripto.")


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
                pnl = crypto_net_pnl(p.unrealized_pl, p.market_value)
                if broker.close_position(p.symbol, reason=reason):
                    _clear_peak(p.symbol)
                    register_crypto_close(p.symbol, pnl)
                    send_alert(f"🛡️ CIERRE {p.symbol} — {reason}")
        except Exception as e:
            log_event("error", f"Error protegiendo la posición cripto {p.symbol}: {e}")


# ---------- Un símbolo ----------
def process_symbol(broker: AlpacaBroker, risk: RiskEngine, symbol: str, equity: float, held: set, counts: dict):
    crypto = is_crypto(symbol)
    kind = "crypto" if crypto else "stock"

    df = broker.get_recent_bars(symbol, timeframe_for(symbol), Config.LOOKBACK_BARS)
    live_price = float(df["close"].iloc[-1]) if df is not None and len(df) else None
    if crypto and df is not None and len(df) > 1:
        # Con velas largas (hasta 4 h) la última vela está a medias y puede cruzar y des-cruzar varias veces.
        # El backtest decide con velas cerradas, así que el agente también (el precio de compra sí es el actual).
        df = df.iloc[:-1]
    result = compute_signal(df)
    log_signal(symbol, result["signal"], result)

    has_position = norm_symbol(symbol) in held

    if result["signal"] == "buy" and not has_position:
        if not risk.can_open_new_position(counts[kind], crypto=crypto):
            log_event("info", f"{symbol}: señal de compra ignorada — máximo de posiciones {'cripto' if crypto else 'de acciones'} alcanzado.")
            return
        price = (live_price if crypto else None) or result.get("last_close")
        if not price:
            return
        qty = risk.position_size(equity, price, crypto=crypto)
        if qty <= 0:
            return

        if crypto:
            blocked = crypto_buy_blocked(symbol, equity, counts.get("crypto_value", 0.0), qty * price)
            if blocked:
                if _last_block_msg.get(symbol) != blocked.split(":")[0]:
                    log_event("info", f"{symbol}: señal de compra ignorada — {blocked}")
                    _last_block_msg[symbol] = blocked.split(":")[0]
                return
            _last_block_msg.pop(symbol, None)

        buy_reason = result["reason"]
        if crypto and time.time() - _news_blocked_at.get(symbol, 0) < NEWS_RECHECK_SECONDS:
            return   # con velas largas la señal dura horas: no se vuelve a consultar el LLM cada minuto
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
                    if crypto:
                        _news_blocked_at[symbol] = time.time()
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
            counts["crypto_value"] = counts.get("crypto_value", 0.0) + qty * fill_price
            crypto_note_buy()
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
        vals = broker.get_position_values(symbol) if crypto else None
        pnl = crypto_net_pnl(*vals) if vals else None
        if broker.close_position(symbol, reason=result["reason"]):
            held.discard(norm_symbol(symbol))
            counts[kind] -= 1
            if crypto:
                _clear_peak(symbol)
                register_crypto_close(symbol, pnl)
            send_alert(f"🔴 VENTA/cierre {symbol} — {result['reason']}")


# ---------- Un ciclo ----------
def run_cycle(broker: AlpacaBroker, risk: RiskEngine):
    global _last_equity
    equity, cash = broker.get_equity_and_cash()

    # Alarma: caída anormal del equity entre dos ciclos seguidos -> algo está mal, se frena todo.
    prev, _last_equity = _last_equity, equity
    if prev and Config.SUDDEN_DROP_PCT > 0 and (prev - equity) / prev >= Config.SUDDEN_DROP_PCT:
        risk.activate_kill_switch(f"caída anormal del equity: ${prev:,.2f} -> ${equity:,.2f}")
        critical(f"Equity cayó {(prev - equity) / prev:.1%} en un ciclo (${prev:,.2f} -> ${equity:,.2f}). "
                 f"KILL SWITCH activado: no se abren posiciones nuevas. Revisá el panel.")
        return
    can_trade, reason = risk.check_account_health(equity)

    daily_pl_pct, drawdown_pct = risk.snapshot_metrics(equity)
    log_equity(equity, cash, daily_pl_pct, drawdown_pct)

    positions = broker.get_open_positions()

    # La protección de cripto corre siempre, aunque el trading esté pausado.
    if Config.CRYPTO_SYMBOLS or any(broker.is_crypto_position(p) for p in positions):
        protect_crypto_positions(broker, positions)
        positions = broker.get_open_positions()
        check_crypto_daily_loss(broker, positions, equity)
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
    crypto_value = sum(abs(float(p.market_value)) for p in positions if broker.is_crypto_position(p))
    counts = {"crypto": n_crypto, "stock": len(positions) - n_crypto, "crypto_value": crypto_value}

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
    global _last_equity
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

    errors = 0
    while True:
        try:
            if risk.is_kill_switch_active():
                _last_equity = None   # al desactivarlo no se compara contra el equity de antes de la pausa
                log_event("critical", "Kill switch activo — el agente no abre posiciones nuevas. Esperando...")
                # Aun así, las posiciones cripto que ya estén abiertas siguen vigiladas.
                protect_crypto_positions(broker)
            else:
                run_cycle(broker, risk)
            errors = 0
        except Exception as e:
            errors += 1
            log_event("error", f"Error inesperado en el ciclo principal ({errors} seguidos): {e}")
            if errors == 3:
                send_alert(f"⚠️ El agente lleva 3 ciclos seguidos con error: {e}")
            if errors == Config.MAX_CYCLE_ERRORS:
                try:
                    risk.activate_kill_switch(f"{errors} ciclos seguidos con error ({e})")
                except Exception:
                    pass
                critical(f"{errors} ciclos seguidos con error (último: {e}). KILL SWITCH activado por seguridad.")

        time.sleep(Config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
