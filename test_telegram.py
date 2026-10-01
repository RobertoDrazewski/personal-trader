"""
test_telegram.py
Prueba rápida de que las alertas de Telegram funcionan.
"""
from alerts import send_alert
from config import Config

if __name__ == "__main__":
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
    else:
        send_alert("✅ Prueba de conexión — si ves esto, las alertas de Telegram están funcionando.")
        print("Mensaje de prueba enviado.")
