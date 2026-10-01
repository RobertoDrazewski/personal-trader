"""
alerts.py
Alertas por Telegram. Opcional pero recomendado.
"""
import requests

from config import Config
from logger_db import log_event


def send_alert(message: str):
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": Config.TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        log_event("warning", f"No se pudo enviar alerta por Telegram: {e}")
