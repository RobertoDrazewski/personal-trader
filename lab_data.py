"""
lab_data.py
Resultados del laboratorio (lab.py) que se muestran en la landing. Son cifras FIJAS copiadas de una corrida real.
Para actualizarlas: corré `python lab.py 8 sip`, copiá los números de las filas que querés mostrar y cambiá esta tabla.

Cada fila: (nombre, retorno anual todo el período %, retorno anual fuera de muestra %, Sharpe fuera de muestra, mayor caída fuera de muestra %)
"""

LAB_META = {
    "date": "2026-10-08",         # fecha de la corrida
    "period": "2019-10 – 2026-10",
    "years": 6.9,
    "oos_from": "2023-12",        # desde cuándo cuenta "fuera de muestra"
    "feed": "SIP",
}

LAB_ROWS = [
    # (nombre, retorno todo %, retorno fuera %, sharpe fuera, caída fuera %, es_referencia)
    ("SPY comprar y mantener (referencia)", 16.4, 20.8, 1.30, 18.8, True),
    ("Cruce de medias 10/30 (el que usa el agente)", 4.3, 3.9, 1.13, 2.8, False),
    ("Turtle 55/20 con filtro de mercado", 16.7, 17.4, 1.32, 9.1, False),
    ("Momentum 12-1, 10 acciones (con sesgo)", 30.3, 40.4, 1.34, 27.0, False),
    ("Screener del agente, Top 3", 25.1, 28.7, 0.98, 24.0, False),
    ("Screener del agente, Top 5", 20.3, 17.3, 0.79, 20.3, False),
    ("Momentum de ETFs, 5 (sin sesgo)", 13.9, 20.6, 1.29, 12.6, False),
]
