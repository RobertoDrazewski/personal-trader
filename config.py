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


class Config:
    # --- Alpaca ---
    APCA_API_KEY_ID = os.getenv("APCA_API_KEY_ID", "")
    APCA_API_SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "")

    MODE = os.getenv("MODE", "paper").strip().lower()
    IS_PAPER = MODE != "live"

    # --- Universo de símbolos a operar ---
    SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "AAPL,MSFT,SPY").split(",") if s.strip()]

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
        if not cls.SYMBOLS:
            problems.append("SYMBOLS está vacío")
        if not cls.DATABASE_URL:
            problems.append("Falta DATABASE_URL — conectá el plugin de Postgres a este servicio en Railway")
        return problems
