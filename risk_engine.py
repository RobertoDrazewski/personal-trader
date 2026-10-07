"""
risk_engine.py
Reglas de riesgo, código determinista sin IA. El kill switch y el estado
persistido (equity pico, día, equity al inicio del día) ahora viven en la
base de datos compartida (Postgres) en vez de archivos locales — necesario
porque el agente y el dashboard son dos servicios separados en Railway, y
ambos necesitan ver el mismo estado.
"""
import json
import math
from datetime import datetime, timezone, date

from config import Config
from logger_db import log_event, get_state, set_state, delete_state

STATE_KEY = "risk_state"
KILL_SWITCH_KEY = "kill_switch"


class RiskEngine:
    def __init__(self):
        self.state = self._load_state()

    def _load_state(self):
        raw = get_state(STATE_KEY)
        if raw:
            return json.loads(raw)
        return {"peak_equity": None, "day": None, "equity_at_day_start": None}

    def _save_state(self):
        set_state(STATE_KEY, json.dumps(self.state))

    def _roll_day_if_needed(self, equity: float):
        today = date.today().isoformat()
        if self.state.get("day") != today:
            self.state["day"] = today
            self.state["equity_at_day_start"] = equity
            self._save_state()

    # ---------- Kill switch (compartido vía DB) ----------
    def is_kill_switch_active(self) -> bool:
        return get_state(KILL_SWITCH_KEY) == "active"

    def activate_kill_switch(self, reason: str):
        set_state(KILL_SWITCH_KEY, "active")
        log_event("critical", f"KILL SWITCH ACTIVADO: {reason}")

    def deactivate_kill_switch(self):
        delete_state(KILL_SWITCH_KEY)
        log_event("info", "Kill switch desactivado manualmente.")

    # ---------- Chequeo central ----------
    def check_account_health(self, equity: float) -> tuple[bool, str]:
        self._roll_day_if_needed(equity)

        if self.is_kill_switch_active():
            return False, "Kill switch activo."

        if self.state["peak_equity"] is None or equity > self.state["peak_equity"]:
            self.state["peak_equity"] = equity
            self._save_state()

        peak = self.state["peak_equity"]
        drawdown_pct = (peak - equity) / peak if peak else 0.0

        equity_day_start = self.state.get("equity_at_day_start") or equity
        daily_pl_pct = (equity - equity_day_start) / equity_day_start if equity_day_start else 0.0

        if drawdown_pct >= Config.MAX_DRAWDOWN_PCT:
            self.activate_kill_switch(
                f"Drawdown de {drawdown_pct:.2%} superó el límite de {Config.MAX_DRAWDOWN_PCT:.2%}"
            )
            return False, f"Drawdown máximo alcanzado ({drawdown_pct:.2%})."

        if daily_pl_pct <= -Config.DAILY_LOSS_LIMIT_PCT:
            log_event("warning", f"Límite de pérdida diaria alcanzado ({daily_pl_pct:.2%}). Pausa por hoy.")
            return False, f"Límite de pérdida diaria alcanzado ({daily_pl_pct:.2%})."

        return True, "OK"

    # ---------- Sizing y trailing stop ----------
    def position_size(self, equity: float, price: float, crypto: bool = False):
        """Acciones: cantidad entera. Cripto: fraccionaria, redondeada hacia abajo a 6 decimales."""
        if crypto:
            max_dollars = equity * Config.CRYPTO_MAX_POSITION_PCT
            qty = math.floor(max_dollars / price * 1_000_000) / 1_000_000
            return max(qty, 0.0)
        max_dollars = equity * Config.MAX_POSITION_PCT
        qty = int(max_dollars // price)
        return max(qty, 0)

    def stop_loss_price(self, entry_price: float) -> float:
        return round(entry_price * (1 - Config.STOP_LOSS_PCT), 2)

    def trailing_stop_percent(self, crypto: bool = False) -> float:
        pct = Config.CRYPTO_TRAILING_STOP_PCT if crypto else Config.TRAILING_STOP_PCT
        return round(pct * 100, 2)

    def can_open_new_position(self, current_open_positions: int, crypto: bool = False) -> bool:
        """Los cupos de acciones y cripto son independientes, así una clase no deja sin lugar a la otra."""
        limit = Config.MAX_CRYPTO_POSITIONS if crypto else Config.MAX_OPEN_POSITIONS
        return current_open_positions < limit

    def snapshot_metrics(self, equity: float):
        peak = self.state.get("peak_equity") or equity
        drawdown_pct = (peak - equity) / peak if peak else 0.0
        equity_day_start = self.state.get("equity_at_day_start") or equity
        daily_pl_pct = (equity - equity_day_start) / equity_day_start if equity_day_start else 0.0
        return daily_pl_pct, drawdown_pct
