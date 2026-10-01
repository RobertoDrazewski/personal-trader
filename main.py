"""
main.py
Loop principal del agente. En Railway, este es el start command del
servicio "agent": python -u main.py
"""
import sys
import time

from config import Config
from logger_db import init_db, log_event, log_equity, log_signal
from risk_engine import RiskEngine
from broker_alpaca import AlpacaBroker
from strategy import compute_signal
from alerts import send_alert
from news_source import get_latest_headline
from llm_analysis import analyze_news


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


def run_cycle(broker: AlpacaBroker, risk: RiskEngine):
    equity, cash = broker.get_equity_and_cash()
    can_trade, reason = risk.check_account_health(equity)

    daily_pl_pct, drawdown_pct = risk.snapshot_metrics(equity)
    log_equity(equity, cash, daily_pl_pct, drawdown_pct)

    mercado = "abierto" if broker.is_market_open() else "cerrado"
    log_event("info", f"Ciclo OK — equity=${equity:,.2f} | mercado {mercado} | drawdown={drawdown_pct:.2%}")

    if not can_trade:
        log_event("warning", f"Trading pausado: {reason}")
        return
    if not broker.is_market_open():
        return

    open_positions = broker.get_open_positions_count()

    for symbol in Config.SYMBOLS:
        try:
            df = broker.get_recent_bars(symbol, Config.TIMEFRAME_MINUTES, Config.LOOKBACK_BARS)
            result = compute_signal(df)
            log_signal(symbol, result["signal"], result)

            has_position = broker.has_open_position(symbol)

            if result["signal"] == "buy" and not has_position:
                if not risk.can_open_new_position(open_positions):
                    log_event("info", f"{symbol}: señal de compra ignorada — máximo de posiciones abiertas alcanzado.")
                    continue
                price = result.get("last_close")
                if not price:
                    continue
                qty = risk.position_size(equity, price)
                if qty <= 0:
                    continue

                buy_reason = result["reason"]
                if Config.USE_NEWS_FILTER:
                    headline = get_latest_headline(symbol)
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
                            continue
                        buy_reason = f"{buy_reason} | noticia: {sentiment['sentiment']}"

                order = broker.submit_market_order(symbol, qty, "buy", reason=buy_reason)
                if order:
                    filled_order = broker.wait_for_fill(str(order.id))
                    if filled_order:
                        trail_pct = risk.trailing_stop_percent()
                        ts_order = broker.submit_trailing_stop_sell(symbol, qty, trail_pct, reason="protección post-compra")
                        open_positions += 1
                        if ts_order:
                            send_alert(f"🟢 COMPRA {symbol} x{qty} @ ~{price} — {buy_reason}\n   Trailing stop: {trail_pct}%")
                        else:
                            send_alert(f"⚠️ COMPRA {symbol} x{qty} ejecutada, pero el trailing stop FALLÓ.")
                    else:
                        send_alert(f"⚠️ Compra de {symbol} x{qty} enviada pero no se confirmó el fill a tiempo.")

            elif result["signal"] == "sell" and has_position:
                broker.cancel_open_orders_for_symbol(symbol)
                broker.close_position(symbol, reason=result["reason"])
                open_positions -= 1
                send_alert(f"🔴 VENTA/cierre {symbol} — {result['reason']}")

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

    log_event("info", f"Agente iniciado. Símbolos: {Config.SYMBOLS} | Modo: {Config.MODE.upper()}")
    send_alert(f"🤖 Agente de trading iniciado en modo {Config.MODE.upper()} (Railway).")

    while True:
        try:
            if risk.is_kill_switch_active():
                log_event("critical", "Kill switch activo — el agente no opera. Esperando...")
            else:
                run_cycle(broker, risk)
        except Exception as e:
            log_event("error", f"Error inesperado en el ciclo principal: {e}")
            send_alert(f"⚠️ Error en el agente: {e}")

        time.sleep(Config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
