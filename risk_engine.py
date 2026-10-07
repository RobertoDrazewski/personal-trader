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

from config import Config, norm_symbol
from logger_db import log_event, get_state, set_state, delete_state

STATE_KEY = "risk_state"
KILL_SWITCH_KEY = "kill_switch"
CRYPTO_BUYS_KEY = "crypto_buys_today"        # "YYYY-MM-DD:n"
CRYPTO_CLOSE_PREFIX = "crypto_last_close:"   # + BTCUSD -> hora ISO del último cierre
CRYPTO_HALT_KEY = "crypto_halt"              # "day:YYYY-MM-DD|motivo" (vence al día siguiente) o "manual|motivo"
CRYPTO_PL_KEY = "crypto_pl_today"            # "YYYY-MM-DD:monto realizado en USD"
CRYPTO_STREAK_KEY = "crypto_loss_streak"     # cierres cripto seguidos en pérdida


# ---------- Ritmo conservador de la cripto ----------
# Se guarda en la base (agent_state) para que sobreviva a los reinicios del agente en Railway.
def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def crypto_buys_today() -> int:
    raw = get_state(CRYPTO_BUYS_KEY)
    if raw and raw.startswith(_today_utc() + ":"):
        try:
            return int(raw.split(":")[1])
        except ValueError:
            return 0
    return 0


def crypto_note_buy():
    set_state(CRYPTO_BUYS_KEY, f"{_today_utc()}:{crypto_buys_today() + 1}")


def crypto_note_close(symbol: str):
    set_state(CRYPTO_CLOSE_PREFIX + norm_symbol(symbol), datetime.now(timezone.utc).isoformat())


def crypto_pl_today() -> float:
    """Resultado cripto ya realizado hoy (UTC), en USD."""
    raw = get_state(CRYPTO_PL_KEY)
    if raw and raw.startswith(_today_utc() + ":"):
        try:
            return float(raw.split(":", 1)[1])
        except ValueError:
            return 0.0
    return 0.0


def crypto_loss_streak() -> int:
    try:
        return int(get_state(CRYPTO_STREAK_KEY) or 0)
    except ValueError:
        return 0


def crypto_record_result(pnl: float) -> int:
    """Registra el resultado de un cierre cripto. Devuelve la racha actual de pérdidas."""
    set_state(CRYPTO_PL_KEY, f"{_today_utc()}:{crypto_pl_today() + pnl:.2f}")
    streak = crypto_loss_streak() + 1 if pnl < 0 else 0
    set_state(CRYPTO_STREAK_KEY, str(streak))
    return streak


def crypto_halt(reason: str, until_tomorrow: bool):
    set_state(CRYPTO_HALT_KEY, (f"day:{_today_utc()}|" if until_tomorrow else "manual|") + reason)


def crypto_halt_reason():
    """Motivo por el que la cripto está frenada, o None si puede operar."""
    raw = get_state(CRYPTO_HALT_KEY)
    if not raw or "|" not in raw:
        return None
    kind, reason = raw.split("|", 1)
    if kind.startswith("day:") and kind[4:] != _today_utc():
        return None   # el freno diario venció
    return reason


def crypto_resume():
    """Reactiva la cripto a mano y reinicia la racha."""
    delete_state(CRYPTO_HALT_KEY)
    set_state(CRYPTO_STREAK_KEY, "0")


def crypto_buy_blocked(symbol: str, equity: float, crypto_value: float, new_value: float):
    """
    Devuelve el motivo por el que NO conviene comprar ahora, o None si se puede.
    Solo frena compras nuevas: las ventas y los stops nunca se bloquean.
    """
    halted = crypto_halt_reason()
    if halted:
        return f"cripto frenada: {halted}"
    cap = Config.CRYPTO_MAX_TRADES_PER_DAY
    if cap > 0 and crypto_buys_today() >= cap:
        return f"ya se hicieron {cap} compras cripto hoy (CRYPTO_MAX_TRADES_PER_DAY)"

    raw = get_state(CRYPTO_CLOSE_PREFIX + norm_symbol(symbol))
    if raw and Config.CRYPTO_COOLDOWN_MINUTES > 0:
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(raw)).total_seconds() / 60
            if elapsed < Config.CRYPTO_COOLDOWN_MINUTES:
                return f"pausa tras el último cierre: faltan {Config.CRYPTO_COOLDOWN_MINUTES - elapsed:.0f} min (CRYPTO_COOLDOWN_MINUTES)"
        except ValueError:
            pass

    limit = equity * Config.CRYPTO_MAX_EXPOSURE_PCT
    if crypto_value + new_value > limit * 1.0001:
        return (f"tope de cripto: tendrías ${crypto_value + new_value:,.0f} invertidos y el máximo es "
                f"${limit:,.0f} ({Config.CRYPTO_MAX_EXPOSURE_PCT:.0%} del equity, CRYPTO_MAX_EXPOSURE_PCT)")
    return None


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
