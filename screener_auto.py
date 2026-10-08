"""
screener_auto.py
Pegamento entre el screener (screener_core.py, lógica pura) y el agente: baja los precios, puntúa el universo,
guarda el resultado en la base (agent_state) para que el panel y la landing lo muestren, y lleva la cuenta de qué
posiciones abrió el propio screener y cuántos reemplazos se hicieron hoy.

Todo vive en la tabla agent_state, así sobrevive a los reinicios del agente en Railway.
Solo se usa si AUTO_SCREENER o AUTO_ROTATION están activados (por defecto están apagados).
"""
import json
import math
import time
from datetime import datetime, timezone

import screener_core as core
from config import Config
from logger_db import get_state, set_state, delete_state, log_event

KEY_TOP = "auto_top"                 # JSON con el último Top N (lo lee el dashboard)
KEY_REPL = "auto_replacements"       # "YYYY-MM-DD:n"
KEY_BUY_PREFIX = "auto_buy_ts:"      # + símbolo -> hora ISO en que el screener abrió esa posición

_cache = {"scores": None, "at": 0.0}


def universe() -> list:
    return core.parse_universe(Config.AUTO_UNIVERSE or core.DEFAULT_UNIVERSE)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _num(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


# ---------- Escaneo ----------
def maybe_scan(broker, force: bool = False):
    """
    Devuelve el DataFrame de puntajes. Reescanea solo si pasaron AUTO_SCAN_MINUTES (un pedido de datos por escaneo).
    Si falla, devuelve el último resultado bueno (o None) y deja el motivo en el log: nunca rompe el ciclo del agente.
    """
    fresh = _cache["scores"] is not None and (time.time() - _cache["at"]) < Config.AUTO_SCAN_MINUTES * 60
    if fresh and not force:
        return _cache["scores"]
    try:
        syms = universe()
        closes = broker.get_daily_closes(syms, trading_days=220)
        if closes is None or closes.empty:
            raise RuntimeError("Alpaca no devolvió precios")
        scores = core.compute_scores(closes, min_price=Config.AUTO_MIN_PRICE)
        if scores.empty:
            raise RuntimeError("no hay historial suficiente para puntuar")
    except Exception as e:
        log_event("warning", f"Screener automático: no se pudo escanear ({e}).")
        _cache["at"] = time.time() - Config.AUTO_SCAN_MINUTES * 60 + 120   # reintenta en ~2 min, no cada ciclo
        return _cache["scores"]

    _cache["scores"], _cache["at"] = scores, time.time()
    top = core.top_n(scores, max(Config.AUTO_TOP_N, 5))
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "top_n": Config.AUTO_TOP_N,
        "rotation": bool(Config.AUTO_ROTATION),
        "universe": len(syms),
        "scored": int(len(scores)),
        "eligible": int(scores["eligible"].sum()),
        "rows": [
            {"symbol": sym, "score": _num(r["score"], 1), "price": _num(r["price"], 2),
             "day_chg": _num(r["day_chg"]), "mom_long": _num(r["mom_long"]), "rsi": _num(r["rsi"], 1)}
            for sym, r in top.iterrows()
        ],
    }
    try:
        set_state(KEY_TOP, json.dumps(payload))
    except Exception as e:
        log_event("warning", f"Screener automático: no se pudo guardar el resultado ({e}).")
    names = ", ".join(f"{r['symbol']} ({r['score']:.0f})" for r in payload["rows"][: Config.AUTO_TOP_N]) or "ninguna elegible"
    log_event("info", f"Screener automático: Top {Config.AUTO_TOP_N} = {names} · {payload['eligible']} elegibles de {payload['scored']}")
    return scores


def get_top():
    """Último Top guardado (para el dashboard y la landing), o None."""
    try:
        raw = get_state(KEY_TOP)
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ---------- Reemplazos del día ----------
def replacements_today() -> int:
    raw = get_state(KEY_REPL)
    if raw and raw.startswith(_today_utc() + ":"):
        try:
            return int(raw.split(":", 1)[1])
        except ValueError:
            return 0
    return 0


def note_replacement():
    set_state(KEY_REPL, f"{_today_utc()}:{replacements_today() + 1}")


# ---------- Posiciones que abrió el screener ----------
def note_buy(symbol: str):
    set_state(KEY_BUY_PREFIX + symbol.upper(), datetime.now(timezone.utc).isoformat())


def clear_buy(symbol: str):
    delete_state(KEY_BUY_PREFIX + symbol.upper())


def own_positions(held) -> dict:
    """Posiciones abiertas que compró el screener: {símbolo: minutos desde la compra}. Las demás no se tocan."""
    out = {}
    now = datetime.now(timezone.utc)
    for sym in held:
        raw = get_state(KEY_BUY_PREFIX + sym.upper())
        if not raw:
            continue
        try:
            out[sym.upper()] = (now - datetime.fromisoformat(raw)).total_seconds() / 60
        except ValueError:
            out[sym.upper()] = None
    return out


# ---------- Horario ----------
def minutes_since_open():
    """Minutos desde las 9:30 (hora de Nueva York) de hoy, o None si no se puede calcular."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
        return (now.hour * 60 + now.minute) - (9 * 60 + 30)
    except Exception:
        return None
