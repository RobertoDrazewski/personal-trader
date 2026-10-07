# Agente de Trading — Puma Code (versión Railway)

Agente de trading algorítmico sobre Alpaca (paper trading), con dashboard
visual, backtesting, optimización de parámetros, filtro de noticias con IA,
y deploy en la nube (Railway) como dos servicios separados compartiendo una
base Postgres.

## Arquitectura

```
┌─────────────────┐       ┌──────────────────┐
│  Servicio        │       │  Servicio          │
│  "agent"          │──────▶│  Postgres           │◀──────│  Servicio
│  (main.py, loop)  │       │  (compartido)        │       │  "dashboard"
└─────────────────┘       └──────────────────┘       └──────────────────┘
        │                                                        │
        └──────────────────────▶ Alpaca API ◀─────────────────────┘
                              (cada uno con las mismas keys)
```

Dos procesos independientes, misma base de datos, mismas credenciales de
Alpaca. El kill switch y el estado de riesgo (drawdown pico, pérdida diaria)
viven en la base — así ambos servicios ven lo mismo en todo momento.

## 1. Desarrollo local (opcional, para probar antes de desplegar)

Necesitás un Postgres accesible (local con Docker, o la URL externa que te
da Railway para tu base en la nube).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# completá .env con tus keys y tu DATABASE_URL
python main.py          # terminal 1
streamlit run dashboard.py   # terminal 2
```

## 2. Deploy en Railway — paso a paso

### 2.1 Subí el proyecto a GitHub
Railway despliega más fácil desde un repo. Si todavía no lo tenés en GitHub:
```bash
cd ~/trading-agent
git init
git add .
git commit -m "Trading agent para Railway"
```
Creá un repo nuevo en GitHub (puede ser privado) y pusheá.

**Importante**: confirmá que `.env` esté en `.gitignore` (nunca subas tus
keys reales a GitHub). Revisá que exista un archivo `.gitignore` con al
menos `.env`, `venv/`, `__pycache__/`.

### 2.2 Creá el proyecto en Railway
En [railway.com](https://railway.com), `New Project` → `Deploy from GitHub repo`
→ elegí tu repo.

### 2.3 Agregá Postgres
Dentro del proyecto: `+ New` → `Database` → `Add PostgreSQL`. Railway lo
provisiona solo, sin configuración manual.

### 2.4 Configurá el servicio del agente
Si Railway ya creó un servicio al importar el repo, usalo; si no, `+ New` →
`GitHub Repo` → el mismo repo otra vez.
- Nombre del servicio: `agent`
- Settings → Deploy → **Start Command**: `python -u main.py`
- Settings → Variables: pegá todas las de tu `.env.example` completadas
  (APCA keys, MODE=paper, SYMBOLS, parámetros de riesgo, OPENAI_API_KEY,
  Telegram, etc.)
- Para `DATABASE_URL`, usá una **variable de referencia** en vez de pegar
  el valor a mano: `${{Postgres.DATABASE_URL}}` (Railway autocompleta el
  nombre del servicio de Postgres al escribir `${{`).

### 2.5 Agregá el servicio del dashboard
`+ New` → `GitHub Repo` → el mismo repo otra vez (va a ser un tercer
servicio en el mismo proyecto).
- Nombre del servicio: `dashboard`
- Settings → Deploy → **Start Command**:
  ```
  streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
  ```
- Settings → Variables: las mismas que el agente (APCA keys, DATABASE_URL
  como referencia, etc.) **más** `APP_PASSWORD` (una contraseña que elijas
  vos, para que el dashboard no quede abierto a cualquiera con el link).
- Settings → Networking → **Generate Domain** — ahí te da la URL pública
  (algo como `tudashboard.up.railway.app`). Esa es la que vas a abrir desde
  tu celular o cualquier navegador.

### 2.6 Confirmá que ambos servicios arrancaron bien
En cada servicio, pestaña `Deployments` → mirá los logs. Deberías ver en
el del agente: `Conectado a Alpaca...`, `Agente iniciado...`, `Ciclo OK...`.
En el del dashboard: el log de arranque de Streamlit.

### 2.7 Pará el agente de tu Mac — MUY IMPORTANTE
Si lo dejás corriendo en Railway Y en tu Mac al mismo tiempo, vas a tener
**dos agentes operando la misma cuenta en paralelo**, pisándose entre sí
(ambos leyendo y escribiendo el mismo kill switch y límites de riesgo
compartidos, pero decidiendo señales de forma independiente — puede
generar comportamiento confuso, no necesariamente doble operación, pero
tampoco es el diseño). Apagá el de tu Mac:
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.pumacode.tradingagent.plist
```

## 3. Actualizar el agente después de un cambio de código

Con GitHub conectado, Railway redeploya solo al hacer push:
```bash
git add .
git commit -m "ajuste de estrategia"
git push
```
Ambos servicios (agent y dashboard) se reconstruyen automáticamente.

## 4. Variables de entorno — resumen

| Variable | Dónde se usa | Nota |
|---|---|---|
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | ambos servicios | mismas keys en los dos |
| `DATABASE_URL` | ambos servicios | `${{Postgres.DATABASE_URL}}` (referencia, no valor pegado) |
| `OPENAI_API_KEY` | agent | solo si `LLM_PROVIDER=openai` |
| `APP_PASSWORD` | dashboard | protege el link público |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | agent | alertas |
| `CRYPTO_SYMBOLS` | agent (y dashboard) | vacío = cripto apagada. Ej.: `BTC/USD,ETH/USD` (ver sección 8) |
| Resto (`SYMBOLS`, `MAX_POSITION_PCT`, `MAX_CRYPTO_POSITIONS`, etc.) | agent (y dashboard para mostrar límites) | igual que antes |

## 5. Backtest y optimización en la nube

Se pueden correr localmente apuntando a la `DATABASE_URL` externa de
Railway (Settings del servicio Postgres → `Connect` → copiás la URL
pública), o por SSH/shell desde el propio Railway CLI:
```bash
railway run python backtest.py AAPL 1095 1440 50
railway run python optimize.py AAPL 730
```

## 6. Kill switch

Ahora vive en la base de datos, no en un archivo. Se controla igual que
antes, pero desde el dashboard (pestaña Control) — el botón ya actualiza
la base compartida, visible al instante para el agente también.

## 7. Costo aproximado

Railway cobra por uso de cómputo + el plugin de Postgres (consumo chico
para este proyecto). Dos servicios livianos + una base chica normalmente
caen dentro de planes de entrada económicos — revisá el pricing actual en
railway.com antes de dejarlo corriendo indefinidamente, para no llevarte
una sorpresa en la facturación.

## 8. Cripto (mismo agente, mismo servicio, costo extra $0)

Alpaca opera cripto con la misma cuenta y las mismas keys. El agente actual
suma los pares de `CRYPTO_SYMBOLS` al mismo ciclo, con la misma estrategia, el
mismo motor de riesgo y el mismo kill switch. No hace falta un servicio nuevo.

**Antes de activar nada, elegí los pares con datos:**
```bash
python backtest_crypto.py            # 180 días, velas de 15 min, 8 pares
python backtest_crypto.py 365 15 BTC/USD,ETH/USD,SOL/USD
```
Muestra, por par, el retorno de la estrategia contra "comprar y mantener" con
la misma exposición, y si el resultado se sostiene en las dos mitades del
período. Si ningún par es consistente, no actives cripto todavía.

**Para activarla:** en Railway → servicio `agent` → Variables →
`CRYPTO_SYMBOLS=BTC/USD,ETH/USD` (los pares que hayan salido consistentes).

Diferencias con las acciones:
- Opera 24/7 (no espera a que abra el mercado).
- Cupo propio (`MAX_CRYPTO_POSITIONS`, 2 por defecto) y posición más chica
  (`CRYPTO_MAX_POSITION_PCT`, 5%), porque se mueve mucho más.
- Alpaca no ofrece trailing stop para cripto: lo vigila el agente cada
  `POLL_INTERVAL_SECONDS` (por defecto `CRYPTO_TRAILING_STOP_PCT`=5%) y vende a
  mercado si el precio cae ese porcentaje desde su pico. Sigue activo aunque el
  trading esté pausado o el kill switch encendido.
- Comisión de Alpaca cripto (~0,25% por lado) incluida en el backtest.
- Cantidades fraccionarias (0,0733 BTC), no enteras.
