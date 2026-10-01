"""
broker_alpaca.py
Envoltorio sobre alpaca-py. Todo lo que toca al broker pasa por acá.
"""
from datetime import datetime, timedelta, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TrailingStopOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

from config import Config
from logger_db import log_event, log_order


class AlpacaBroker:
    def __init__(self):
        self.trading_client = TradingClient(
            Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY, paper=Config.IS_PAPER
        )
        self.data_client = StockHistoricalDataClient(
            Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY
        )
        log_event("info", f"Conectado a Alpaca en modo {'PAPER' if Config.IS_PAPER else 'LIVE'}.")

    def get_equity_and_cash(self):
        acct = self.trading_client.get_account()
        return float(acct.equity), float(acct.cash)

    def get_open_positions(self):
        return self.trading_client.get_all_positions()

    def get_open_positions_count(self) -> int:
        return len(self.get_open_positions())

    def has_open_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol for p in self.get_open_positions())

    def get_recent_bars(self, symbol: str, minutes: int, lookback: int):
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(5, lookback * minutes // 60 // 6 + 3))
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(minutes, TimeFrameUnit.Minute) if minutes != 1440 else TimeFrame.Day,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        bars = self.data_client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            return None
        if symbol in df.index.get_level_values(0):
            df = df.loc[symbol]
        return df.tail(lookback)

    def submit_market_order(self, symbol: str, qty: int, side: str, reason: str = ""):
        try:
            order_req = MarketOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = self.trading_client.submit_order(order_req)
            log_order(symbol, side, qty, str(order.id), str(order.status), reason)
            log_event("info", f"Orden enviada: {side.upper()} {qty} {symbol} — motivo: {reason}")
            return order
        except Exception as e:
            log_event("error", f"Falló el envío de orden {side} {qty} {symbol}: {e}")
            log_order(symbol, side, qty, "", "failed", str(e))
            return None

    def wait_for_fill(self, order_id: str, timeout_seconds: int = 15, poll_seconds: float = 1.0):
        import time
        elapsed = 0.0
        while elapsed < timeout_seconds:
            order = self.trading_client.get_order_by_id(order_id)
            if order.status == "filled":
                return order
            if order.status in ("canceled", "expired", "rejected"):
                log_event("warning", f"Orden {order_id} terminó como '{order.status}', no se llenó.")
                return None
            time.sleep(poll_seconds)
            elapsed += poll_seconds
        log_event("warning", f"Timeout esperando fill de la orden {order_id} ({timeout_seconds}s).")
        return None

    def submit_trailing_stop_sell(self, symbol: str, qty: int, trail_percent: float, reason: str = ""):
        try:
            order_req = TrailingStopOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC, trail_percent=trail_percent,
            )
            order = self.trading_client.submit_order(order_req)
            log_order(symbol, "trailing_stop_sell", qty, str(order.id), str(order.status), reason)
            log_event("info", f"Trailing stop puesto: {symbol} x{qty} @ trail {trail_percent}%")
            return order
        except Exception as e:
            log_event("error", f"Falló el envío del trailing stop para {symbol}: {e}")
            return None

    def close_position(self, symbol: str, reason: str = "stop/target/manual"):
        try:
            self.trading_client.close_position(symbol)
            log_event("info", f"Posición cerrada: {symbol} — motivo: {reason}")
            return True
        except Exception as e:
            log_event("error", f"Falló el cierre de posición {symbol}: {e}")
            return False

    def close_all_positions(self, reason: str = "kill switch"):
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            log_event("critical", f"TODAS las posiciones cerradas — motivo: {reason}")
        except Exception as e:
            log_event("error", f"Falló el cierre masivo de posiciones: {e}")

    def cancel_all_open_orders(self):
        try:
            self.trading_client.cancel_orders()
        except Exception as e:
            log_event("error", f"Falló la cancelación de órdenes abiertas: {e}")

    def cancel_open_orders_for_symbol(self, symbol: str):
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            open_orders = self.trading_client.get_orders(req)
            for o in open_orders:
                self.trading_client.cancel_order_by_id(o.id)
            if open_orders:
                log_event("info", f"Canceladas {len(open_orders)} orden(es) abierta(s) de {symbol}.")
        except Exception as e:
            log_event("error", f"Falló la cancelación de órdenes de {symbol}: {e}")

    def is_market_open(self) -> bool:
        clock = self.trading_client.get_clock()
        return clock.is_open
