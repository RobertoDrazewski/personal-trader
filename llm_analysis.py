"""
llm_analysis.py
Interpreta una noticia y devuelve sentimiento. Es advisory — nunca decide
la orden final, eso lo hace risk_engine.py. En la nube, usa OpenAI por
default (Railway no tiene GPU para correr un modelo local como Ollama).
"""
import json
import requests

from config import Config
from logger_db import log_event

SYSTEM_PROMPT = (
    "Sos un analista financiero neutral. Te paso un titular o resumen de noticia "
    "sobre una empresa o el mercado. Respondé SOLO con un JSON válido, sin texto "
    "adicional, con este formato exacto:\n"
    '{"sentiment": "positive" | "negative" | "neutral", "confidence": 0.0-1.0, "reason": "..."}'
)


def analyze_news(symbol: str, headline: str) -> dict:
    if Config.LLM_PROVIDER == "none":
        return {"sentiment": "neutral", "confidence": 0.0, "reason": "LLM deshabilitado"}
    if Config.LLM_PROVIDER == "ollama":
        return _analyze_with_ollama(symbol, headline)
    if Config.LLM_PROVIDER == "openai":
        return _analyze_with_openai(symbol, headline)
    return {"sentiment": "neutral", "confidence": 0.0, "reason": "LLM_PROVIDER desconocido"}


def _analyze_with_ollama(symbol: str, headline: str) -> dict:
    try:
        resp = requests.post(
            f"{Config.OLLAMA_HOST}/api/chat",
            json={
                "model": Config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Símbolo: {symbol}\nNoticia: {headline}"},
                ],
                "stream": False, "format": "json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["message"]["content"])
        return {
            "sentiment": parsed.get("sentiment", "neutral"),
            "confidence": float(parsed.get("confidence", 0.0)),
            "reason": parsed.get("reason", ""),
        }
    except Exception as e:
        log_event("warning", f"Ollama no disponible ({e}). Sigo sin señal de sentimiento.")
        return {"sentiment": "neutral", "confidence": 0.0, "reason": f"error: {e}"}


def _analyze_with_openai(symbol: str, headline: str) -> dict:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}"},
            json={
                "model": Config.OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Símbolo: {symbol}\nNoticia: {headline}"},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        return {
            "sentiment": parsed.get("sentiment", "neutral"),
            "confidence": float(parsed.get("confidence", 0.0)),
            "reason": parsed.get("reason", ""),
        }
    except Exception as e:
        log_event("warning", f"OpenAI falló ({e}). Sigo sin señal de sentimiento.")
        return {"sentiment": "neutral", "confidence": 0.0, "reason": f"error: {e}"}
