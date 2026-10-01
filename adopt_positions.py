"""
adopt_positions.py
Pone trailing stop a posiciones abiertas que todavía no lo tengan.

Uso:
    python adopt_positions.py
"""
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from broker_alpaca import AlpacaBroker
from risk_engine import RiskEngine
from logger_db import init_db
from alerts import send_alert


def main():
    init_db()
    broker = AlpacaBroker()
    risk = RiskEngine()
    trail_pct = risk.trailing_stop_percent()

    positions = broker.get_open_positions()
    if not positions:
        print("No tenés posiciones abiertas.")
        return

    print(f"Posiciones encontradas: {[p.symbol for p in positions]}\n")

    for pos in positions:
        symbol = pos.symbol
        qty = int(float(pos.qty))

        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        open_orders = broker.trading_client.get_orders(req)
        sell_orders = [o for o in open_orders if str(o.side).lower().endswith("sell")]

        if sell_orders:
            print(f"{symbol}: ya protegido. Se omite.")
            continue

        print(f"{symbol}: sin protección. Poniendo trailing stop de {trail_pct}% para {qty} acciones...")
        order = broker.submit_trailing_stop_sell(symbol, qty, trail_pct, reason="adopción de posición existente")
        if order:
            print(f"  OK — orden {order.id}")
            send_alert(f"🛡️ Trailing stop agregado: {symbol} x{qty} @ {trail_pct}%")
        else:
            print("  FALLÓ.")

    print("\nListo.")


if __name__ == "__main__":
    main()
