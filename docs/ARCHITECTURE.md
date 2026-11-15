# Architecture

Prospector is one Python service that serves both the API and the web client. There is no database: each analysed field is a folder of files, addressed by a hash of its polygon.

```
browser (MapLibre GL JS + three.js, one HTML page)
        │  JSON / PNG over HTTP
        ▼
FastAPI service (prospector/api.py)
        │
        ├── datos.py      download of open data for the field window (COG over HTTP, STAC, NASA POWER)
        ├── terreno.py    slope, aspect, drainage, buildings, roads
        ├── region.py     what cultivated land around the field looks like; suitability classes
        ├── cultivos.py   crop engine: 31 crops × sowing dates × 24 years
        ├── calendario.py local crop calendar (GGCMI)
        ├── cultivado.py  observed harvested area (CROPGRIDS) and yields (GDHY)
        ├── loteo.py      plots, buffers, access route
        └── mundo.py      global table of climate and soil (places with similar conditions)
        │
        ▼
cache folder (one sub-folder per field)  +  global reference data (read-only)
```

Code names, comments and the interface are in Spanish.

## Backend

| Module | What it does |
|---|---|
| `api.py` | HTTP routes, job tracking, rendering of map layers to PNG |
| `datos.py` | Defines the field grid (10 m, local UTM) and downloads elevation, land cover, imagery, buildings, roads, soil and weather. All requests have timeouts; a failed source does not block the rest |
| `terreno.py` | Elevation = mean of NASADEM and Copernicus GLO-30; their difference is the height margin of error. Slope, aspect, flow direction and accumulation (pysheds) |
| `region.py` | Learns from the cultivated land of the surrounding area and classifies each cell. Parcels mapped as vineyard, orchard or nursery become their own class (already planted), separate from woodland |
| `cultivos.py` | Crop engine (below), rotations, soil loss, techniques |
| `loteo.py` | Field layout (below) |
| `validar_mundo.py`, `informe_validacion.py` | Global validation and its report |
| `pruebas.py` | Smoke tests against a running server |
| `regiones.py` | Main crops of every country and first-level region: CROPGRIDS summed by region, FAOSTAT by country |
| `obtener_datos.py` | One-time download of the global reference data. Each source is independent: if one server is down the others continue, and the summary says what is missing |

An analysis runs in three steps so the user sees something quickly: terrain (seconds), comparison with the surrounding cropland, then the long history (vegetation, soil, weather). A job can be paused and resumed; what was already downloaded is kept.

## Crop engine (`cultivos.py`)

Input: daily weather 2001–2024 for the field (NASA POWER; rainfall from GPM IMERG) and soil texture (SoilGrids).

For each crop, each candidate sowing date and each year:

1. Thermal time (growing degree days) sets the length of the cycle.
2. Reference evapotranspiration with FAO-56 Penman-Monteith, and crop coefficients Kc.
3. Daily soil water balance, with deep-soil storage and a 180-day fallow before sowing.
4. Yield response to water with FAO-33.
5. Frost and heat at flowering; temperature is judged only on growth days.

The chosen date is the one with the highest median relative yield. Output is a relative yield (0–1) and a count of good years out of ten — not tonnes.

Verdicts: grows / grows with a low harvest (median ≥ 0.35 and at most 2 failures in 10 years) / only with irrigation / does not grow.

Local adjustment: cycle length is fitted to the GGCMI crop calendar of the area (between 0.75 and 1.30 times the general value), and the local sowing date is adopted when it yields at least 85 % of the best simulated date. Without a local calendar, general parameters are used and the interface says so.

Each crop is one row of the `CULTIVOS` table. Adding an annual crop means adding a row; perennial crops (fruit trees, vines) need a different model.

Rotations are compared by good years out of ten, water use, months of bare soil and soil loss (RUSLE: R from Renard and Freimund 1994, K from Williams 1995, C from Panagos et al. 2015, LS from the terrain).

## Field layout (`loteo.py`)

- Fine grid, four times the terrain grid.
- Buffers by distance transform; plots by connected components.
- Plots of up to 6 ha separated by 4 m service lanes; fragments under 0.15 ha are left out.
- Questions put to the farmer: trees, moderate slope, road, buildings, headland, entrance.
- Access: least-cost route from the nearest drivable road (Dijkstra on an 8-neighbour grid). Cost rises with slope, channels, trees, crossing plots and leaving the property.
- Output: plots, used and unused area with the reason, metres of new road, area to clear, estimated annual water and work stages.

## Frontend (`web/index.html`)

A single page, no build step. MapLibre GL JS for the map and drawing; three.js for the 3D terrain, extruded neighbouring buildings, trees (Kenney Nature Kit) and instanced crop plants that grow month by month. Libraries are vendored in `web/vendor`, so the page needs no CDN.

## API

| Route | Purpose |
|---|---|
| `POST /api/prospectar` | Start the analysis of a polygon (GeoJSON) |
| `POST /api/analizar/{id}` · `POST /api/pausar/{id}` | Resume or pause an analysis |
| `GET /api/estado/{id}` | Progress of each step |
| `GET /api/areas` | Fields already analysed |
| `GET /api/terreno/{id}` · `GET /api/malla/{id}` | Field summary and 3D mesh |
| `GET /api/capa/{id}/{layer}.png` | A map layer rendered as an image |
| `GET /api/punto/{id}` | Explanation for one point |
| `GET /api/cultivos/{id}` | Crops, rotations and techniques per zone |
| `GET /api/loteo/{id}` | Field layout for the farmer's answers |
| `GET /api/entorno/{id}` · `/api/edificios/{id}` · `/api/caminos/{id}` | Surroundings for the 3D view |
| `GET /api/salud` | Health check |

Interactive documentation is served at `/docs` (OpenAPI).
