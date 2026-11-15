# Validation

Full report with every table (in Spanish): [validation/INFORME_es.md](validation/INFORME_es.md). Raw results per point: [validation/resultados_97.json](validation/resultados_97.json).

## Method

Two kinds of sample, both drawn at random with a fixed seed and spread evenly over nine world regions. Weather for every point is NASA POWER daily, 2001–2024. Nothing is fitted automatically: each run only measures.

- **General sample:** 270 points on cropland and 90 on land with no cropland. Compared with real cropland (ESA CCI Land Cover 2020), harvested area per crop (CROPGRIDS) and sowing calendar (GGCMI).
- **Targeted sample:** about 30 points per crop, taken only where that crop occupies at least 2 % of the land (CROPGRIDS). It asks one question: where the crop is really grown, does the engine recognise it?

Samples used to find and fix errors (general seeds 2026, 777 and 31; targeted seed 41) are development samples. **The figures below come from samples drawn after the last change to the engine and never used to adjust it** (general seed 97; targeted seed 53).

## Results on the unseen general sample (seed 97)

| Measured | Result | Base |
|---|---|---|
| Rainfed cropland where the engine finds at least one crop that grows without irrigation | 94 % | 235 points |
| Same, without the local calendar adjustment | 96 % | 235 points |
| Arid land with no cropland (under 250 mm a year) where it finds one — should be zero | 0 % | 27 points |
| A crop is really sown there and the engine recognises it | 97 % | 919 cases |
| … as rainfed | 81 % | |
| … only with irrigation | 15 % | |
| … not recognised | 3 % | |
| Median difference in sowing date against the local calendar, with local adjustment | 33 days | 3995 cases |
| Same, without local adjustment | 75 days | 3675 cases |
| Expected difference when picking a date at random | about 91 days | |

With the local adjustment the engine knows the local date and adopts it when the yield is nearly the same, so agreement on sowing dates **is not an independent test**. Dates are presented to the user as tentative.

### By region (rainfed cropland, with local adjustment)

| Region | Points | Hit rate |
|---|---|---|
| Latin America | 30 | 100 % |
| North America | 30 | 97 % |
| East and South-East Asia | 22 | 100 % |
| South Asia | 9 | 100 % |
| Europe | 28 | 96 % |
| Oceania | 30 | 87 % |
| Russia and Central Asia | 29 | 97 % |
| North Africa and Middle East | 29 | 76 % |
| Sub-Saharan Africa | 28 | 100 % |

### Where it fails

- North Africa and the Middle East: 76 %; Oceania: 87 %.
- Maize is not recognised at 10 % of the points where it is sown; rice and cassava at 8 %; soybean at 6 %.
- Sowing dates for peas and potatoes stay about 75 days from the local calendar.
- The engine is permissive: on land with no cropland it says something would grow at 49 % of points, and where a crop is absent it often says it would grow (wheat 80 %, barley 73 %). That is not an error by itself — a crop can be suitable and not grown for market reasons — but it means a "grows" verdict is weaker evidence than a "does not grow" one.

## Targeted sample

951 points where each of the 30 crops with CROPGRIDS data is really grown (seed 53, drawn after the last change to the engine). Full table: [validation/INFORME_dirigida_es.md](validation/INFORME_dirigida_es.md).

| Measured | Result |
|---|---|
| The engine recognises the crop where it is sown | 94 % (66 % rainfed, 28 % only with irrigation) |
| Not recognised | 6 % |

Crops it misses most: broad bean (32 %), pepper (27 %), pea (20 %), cabbage (17 %), rapeseed (11 %). The app says so on the card of the four weakest. The eight vegetable and industrial crops added on the last day are covered by this sample: tomato, sugar beet, onion and watermelon are missed at 0–3 % of points, tobacco at 6 %, safflower at 9 %.

Before the fixes listed below, the same test on the development sample (seed 41) gave 17 % not recognised, with alfalfa at 77 %, pea at 60 % and tomato at 40 %.

## What the validation changed

Each of these was found by a validation run, fixed with a physical reason, and then re-measured on a sample the fix had not seen:

- The verdict was too strict for low-yield rainfed farming: a "grows, with a low harvest" verdict was added. It now also requires rain to cover at least half of the crop's water demand, after an intermediate version produced false positives in arid land (3 of 25 points).
- A bug in deep-soil water made millet "grow" with 82 mm of rain a year.
- Perennial forage (alfalfa) was judged on the yearly mean temperature, winter dormancy included. It is now judged on growing days, as annual crops are.
- Spring sowing after snowmelt was penalised for "dry sowing" although the soil was wet. Emergence now depends on topsoil moisture.
- Heat was counted over almost 40 % of the cycle; it is now counted at flowering.
- With irrigation and a limited yield the verdict was "not recommended"; it is now "only with irrigation", and the text states the expected yield.
- Millet parameters covered only tropical pearl millet; the thermal range was widened for temperate millets.

## What this validation does not prove

- No comparison with yields in tonnes per hectare: the engine does not predict them.
- Land cover says there is cropland, not which crop; the calendar is a 55 km grid; CROPGRIDS spreads national and regional statistics over cropland maps and can place a crop in a cell where it is not.
- Weather is a 55 km cell average: in mountains the valleys where crops grow are warmer than the cell, and the engine misses them.
- Terrain classification, field layout, rotations and terraces were not validated.
- No farmer or agronomist has reviewed the results.

## Regions and countries

The table of main crops by region (CROPGRIDS summed inside Natural Earth regions) was contrasted with official statistics collected region by region: see [validation/CONTRASTE_regiones_es.md](validation/CONTRASTE_regiones_es.md).

| Measured | Result |
|---|---|
| Regions compared | 379, in 53 countries |
| The main crop in the official statistics is among the table's top three | 93 % |
| The main crop is exactly the same | 72 % |
| Crops listed by the official statistics that are among the table's top eight | 82 % |
| Official regions that could not be matched by name | 160 |

The official figures were collected with AI research agents, each entry with the URL it was read from ([validation/regional_sources/](validation/regional_sources/)). They come from different years; some rank by production rather than area or cover grains only; European data come in grouped statistical regions that do not match the table's provinces; South and South-East Asia stopped at 8 of 11 countries because of network failures. A difference does not say by itself which source is wrong.

## Rerun it

```bash
python -m prospector.obtener_datos                 # global reference data, once
python -m prospector.validar_mundo 270 90 97       # general sample: 270 cropland + 90 non-cropland points, seed 97
python -m prospector.informe_validacion resultados_97.json INFORME.md
python -m prospector.validar_dirigida 30 53        # targeted sample: about 30 points per crop, seed 53
```

Results are written to `prospector/validacion/`. The first run downloads weather for every point and takes a while.
