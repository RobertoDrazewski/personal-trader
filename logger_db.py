"""
logger_db.py
Persistencia en Postgres (antes era SQLite local). El cambio es necesario
porque ahora el agente y el dashboard corren en servicios separados en
Railway, cada uno en su propio contenedor — un archivo local ya no alcanza,
necesitan una base compartida por red.
"""
import json
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config import Config


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dsn():
    url = Config.DATABASE_URL
    # psycopg2 a veces requiere el esquema "postgresql://" en vez de "postgres://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


@contextmanager
def _conn():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                details TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                order_id TEXT,
                status TEXT,
                reason TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                equity REAL NOT NULL,
                cash REAL,
                daily_pl_pct REAL,
                drawdown_pct REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)
        # Estado compartido entre servicios: kill switch, drawdown pico, límite diario.
        # Antes vivía en archivos locales (KILL_SWITCH.flag, equity_state.json) —
        # ahora tiene que estar acá porque agente y dashboard son contenedores distintos.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)


def log_signal(symbol: str, signal: str, details: dict):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO signals (ts, symbol, signal, details) VALUES (%s, %s, %s, %s)",
            (_now(), symbol, signal, json.dumps(details, default=str)),
        )


def log_order(symbol: str, side: str, qty: float, order_id: str, status: str, reason: str = ""):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (ts, symbol, side, qty, order_id, status, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (_now(), symbol, side, qty, order_id, status, reason),
        )


def log_equity(equity: float, cash: float, daily_pl_pct: float, drawdown_pct: float):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO equity_snapshots (ts, equity, cash, daily_pl_pct, drawdown_pct) VALUES (%s, %s, %s, %s, %s)",
            (_now(), equity, cash, daily_pl_pct, drawdown_pct),
        )


def log_event(level: str, message: str):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO events (ts, level, message) VALUES (%s, %s, %s)",
            (_now(), level, message),
        )
    print(f"[{_now()}] [{level.upper()}] {message}")


# ---------- Estado compartido (key-value genérico) ----------
def get_state(key: str, default=None):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM agent_state WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def set_state(key: str, value: str):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_state (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value),
        )


def delete_state(key: str):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM agent_state WHERE key = %s", (key,))
