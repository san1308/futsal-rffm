# Futsal RFFM

App propia (móvil primero) para seguir mi liga de fútbol sala sin pelearme con la web de la
Real Federación de Fútbol de Madrid: **Tercera División FS · Grupo 3 · 2026-27**.

- **Mi equipo**: posición, puntos, racha, próximo partido (con cuenta atrás y "Cómo llegar"),
  último resultado, la clasificación alrededor y todo el calendario del equipo.
- **Jornadas**: selector de jornada y partidos agrupados por día.
- **Tabla**: clasificación corta/completa con zonas de ascenso/descenso y racha.
- **Goleadores**: del grupo o solo de mi equipo.
- **Acta**: goles y tarjetas minuto a minuto, alineaciones, árbitros y pabellón.
- **Yo**: mis números sacados de las actas (convocatorias, titularidades, goles encajados, porterías a 0…).
- Instalable como app (PWA) y funciona sin cobertura con lo último cargado.

## Cómo saca los datos

La web de la RFFM es una app Next.js. No hay que hacer scraping de HTML:

| Dato | Fuente en rffm.es |
|---|---|
| Calendario y resultados | `/competicion/calendario?...` → JSON embebido en `__NEXT_DATA__` (`pageProps.calendar`) |
| Clasificación | `/api/standings?idGroup=…&round=…` |
| Goleadores | `/api/scorers?idGroup=…&idCompetition=…` |
| Jornadas | `/api/group-rounds?idGroup=…&fetchBy=standings` |
| Acta del partido | `/acta-partido/{codacta}` → `__NEXT_DATA__` (`pageProps.game`) |

El backend (FastAPI) los pide, los cachea en memoria (calendario y tabla 10 min, actas cerradas 7 días)
y si la RFFM se cae sirve el último dato bueno. El frontend es HTML + JS sin dependencias.

```
app/
  rffm.py      cliente de la RFFM (+ DemoClient con datos guardados)
  service.py   normalización: nombres cortos, autogoles, estadísticas personales…
  cache.py     caché TTL con "stale on error"
  main.py      API propia + sirve el frontend
static/        SPA (index.html, app.js, styles.css, sw.js)
tests/         tests con datos reales capturados el 4-oct-2026
```

## Despliegue en la Raspberry

```bash
git clone git@github.com:san1308/futsal-rffm.git && cd futsal-rffm
cp .env.example .env          # revisa MI_EQUIPO / MI_JUGADOR
docker compose up -d --build
curl localhost:8090/api/health
```

### Publicarlo con Cloudflare Tunnel

Añade una ruta más al túnel que ya usas para `domoticia.fun`:

- **Túnel gestionado desde el panel de Cloudflare**: Zero Trust → Networks → Tunnels → tu túnel →
  *Public Hostname* → `futsal.domoticia.fun` → `http://localhost:8090`.
- **Túnel con `config.yml`**: añade antes de la regla final `http_status:404`:
  ```yaml
  - hostname: futsal.domoticia.fun
    service: http://localhost:8090
  ```
  y `cloudflared tunnel route dns <tu-tunel> futsal.domoticia.fun`, luego reinicia cloudflared.

Si `cloudflared` corre en un contenedor, mete los dos en la misma red de Docker y usa
`http://futsal-rffm:8000` como servicio.

Opcional: protégelo con Cloudflare Access como el panel de la despensa (los datos son públicos,
pero así nadie más usa tu Raspberry como proxy de la RFFM).

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # tests con datos reales
DEMO=1 uvicorn app.main:app --reload     # sin red, con datos guardados
uvicorn app.main:app --reload            # contra la RFFM de verdad
```

API propia: `/api/calendar`, `/api/standings?round=N`, `/api/scorers`, `/api/match/{codacta}`,
`/api/team/{id}`, `/api/me`, `POST /api/refresh` (vacía la caché). Docs en `/api/docs`.

### Cambiar de temporada o de liga

Abre en rffm.es el calendario de la competición, copia `temporada`, `tipojuego`, `competicion` y
`grupo` de la URL al `.env`, y `docker compose up -d`. El código de tu equipo sale del enlace
`/fichaequipo/XXXX` y el tuyo de jugador, de las actas.

## Notas

- Uso personal y con caché para no cargar la web de la federación.
- Códigos observados en las actas: `tipo_gol 102` = autogol (suma al rival), `codigo_tipo_amonestacion 100` = amarilla.
  Otros códigos de tarjeta se tratan como roja hasta verlos en un acta real.
- Las actas no traen minutos jugados: los goles encajados de "Yo" se cuentan en los partidos que empiezas de titular.
