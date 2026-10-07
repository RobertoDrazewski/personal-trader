"""
config.py
Carga toda la configuración del agente desde variables de entorno.
En Railway, estas variables se setean en el panel de cada servicio
(no hace falta archivo .env ahí). Localmente, sigue leyendo .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "si", "sí")


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def is_crypto(symbol: str) -> bool:
    """Los pares cripto de Alpaca llevan barra: BTC/USD, ETH/USD, etc."""
    return "/" in symbol


def norm_symbol(symbol: str) -> str:
    """Alpaca devuelve las posiciones cripto sin barra (BTCUSD). Para comparar, sacamos la barra."""
    return symbol.replace("/", "").upper()


def _get_symbols(name: str, default: str) -> list:
    return [s.strip().upper() for s in os.getenv(name, default).split(",") if s.strip()]


class Config:
    # --- Alpaca ---
    APCA_API_KEY_ID = os.getenv("APCA_API_KEY_ID", "")
    APCA_API_SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "")

    MODE = os.getenv("MODE", "paper").strip().lower()
    IS_PAPER = MODE != "live"

    # --- Universo de símbolos a operar ---
    SYMBOLS = _get_symbols("SYMBOLS", "AAPL,MSFT,SPY")

    # --- Cripto (opcional) ---
    # Vacío = el agente NO opera cripto. Ejemplo: CRYPTO_SYMBOLS=BTC/USD,ETH/USD
    # Se elige después de correr backtest_crypto.py (ver README).
    CRYPTO_SYMBOLS = _get_symbols("CRYPTO_SYMBOLS", "")
    MAX_CRYPTO_POSITIONS = _get_int("MAX_CRYPTO_POSITIONS", 2)
    # La cripto se mueve mucho más que las acciones: por defecto, posición más chica
    # y trailing stop más ancho (con 3% en velas de 15 min se dispararía todo el tiempo).
    CRYPTO_MAX_POSITION_PCT = _get_float("CRYPTO_MAX_POSITION_PCT", 0.05)
    CRYPTO_TRAILING_STOP_PCT = _get_float("CRYPTO_TRAILING_STOP_PCT", 0.05)
    # Comisión taker de Alpaca cripto (por lado). Solo la usa el backtest.
    CRYPTO_FEE_PCT = _get_float("CRYPTO_FEE_PCT", 0.0025)

    # --- Timeframe de la estrategia ---
    TIMEFRAME_MINUTES = _get_int("TIMEFRAME_MINUTES", 15)
    LOOKBACK_BARS = _get_int("LOOKBACK_BARS", 200)

    # --- Reglas de riesgo ---
    MAX_POSITION_PCT = _get_float("MAX_POSITION_PCT", 0.08)
    DAILY_LOSS_LIMIT_PCT = _get_float("DAILY_LOSS_LIMIT_PCT", 0.03)
    MAX_DRAWDOWN_PCT = _get_float("MAX_DRAWDOWN_PCT", 0.15)
    STOP_LOSS_PCT = _get_float("STOP_LOSS_PCT", 0.02)
    TRAILING_STOP_PCT = _get_float("TRAILING_STOP_PCT", 0.03)
    MAX_OPEN_POSITIONS = _get_int("MAX_OPEN_POSITIONS", 3)

    # --- Loop ---
    POLL_INTERVAL_SECONDS = _get_int("POLL_INTERVAL_SECONDS", 60)

    # --- Filtro de noticias antes de comprar ---
    USE_NEWS_FILTER = _get_bool("USE_NEWS_FILTER", True)
    NEWS_NEGATIVE_BLOCK_CONFIDENCE = _get_float("NEWS_NEGATIVE_BLOCK_CONFIDENCE", 0.6)

    # --- LLM para análisis de noticias/sentimiento ---
    # En la nube (Railway no tiene GPU), lo recomendado es "openai" en vez de "ollama".
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()  # "openai" | "ollama" | "none"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # --- Alertas Telegram ---
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # --- Base de datos ---
    # Railway inyecta esto solo cuando conectás el plugin de Postgres al servicio
    # (como variable de referencia ${{Postgres.DATABASE_URL}}).
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    @classmethod
    def validate(cls):
        problems = []
        if not cls.APCA_API_KEY_ID or not cls.APCA_API_SECRET_KEY:
            problems.append("Faltan APCA_API_KEY_ID / APCA_API_SECRET_KEY")
        if cls.LLM_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            problems.append("LLM_PROVIDER=openai pero falta OPENAI_API_KEY")
        if not cls.SYMBOLS and not cls.CRYPTO_SYMBOLS:
            problems.append("SYMBOLS y CRYPTO_SYMBOLS están vacíos")
        bad = [s for s in cls.CRYPTO_SYMBOLS if not is_crypto(s)]
        if bad:
            problems.append(f"CRYPTO_SYMBOLS debe usar el formato con barra (BTC/USD). Revisá: {bad}")
        wrong = [s for s in cls.SYMBOLS if is_crypto(s)]
        if wrong:
            problems.append(f"Los pares cripto van en CRYPTO_SYMBOLS, no en SYMBOLS: {wrong}")
        if not cls.DATABASE_URL:
            problems.append("Falta DATABASE_URL — conectá el plugin de Postgres a este servicio en Railway")
        return problems
