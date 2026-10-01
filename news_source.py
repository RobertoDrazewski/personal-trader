"""
news_source.py
Trae la noticia más reciente de un símbolo vía Alpaca News API (gratis,
incluido en el mismo plan).
"""
from datetime import datetime, timedelta, timezone

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from config import Config
from logger_db import log_event

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = NewsClient(Config.APCA_API_KEY_ID, Config.APCA_API_SECRET_KEY)
    return _client


def get_latest_headline(symbol: str, lookback_hours: int = 24):
    try:
        client = _get_client()
        req = NewsRequest(
            symbols=symbol,
            start=datetime.now(timezone.utc) - timedelta(hours=lookback_hours),
            limit=1, sort="desc",
        )
        result = client.get_news(req)
        news_list = result.data.get("news", [])
        if not news_list:
            return None
        return news_list[0].headline
    except Exception as e:
        log_event("warning", f"No se pudo traer noticias de {symbol}: {e}")
        return None
