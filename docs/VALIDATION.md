# Validation

Full report with every table (in Spanish): [validation/INFORME_es.md](validation/INFORME_es.md). Raw results per point: [validation/resultados_31.json](validation/resultados_31.json).

## Method

- 360 random points: 270 on cropland and 90 on land with no cropland, spread evenly over nine world regions.
- Weather for each point: NASA POWER daily, 2001–2024.
- Compared with independent data: real cropland (ESA CCI Land Cover 2020), harvested area per crop (CROPGRIDS) and sowing calendar (GGCMI).
- Three samples were run (seeds 2026, 777 and 31). The first two were used to find and fix errors. **Seed 31 was not used to adjust anything**; its figures are the ones reported.

## Results (seed 31)

| Measured | Result | Base |
|---|---|---|
| Rainfed cropland where the engine finds at least one crop that grows without irrigation | 91 % | 239 points |
| Same, without the local calendar adjustment | 88 % | 239 points |
| Arid land with no cropland (under 250 mm a year) where it finds one — should be zero | 0 % | 25 points |
| A crop is really sown there and the engine recognises it | 93 % | 870 cases |
| … as rainfed | 76 % | |
| … only with irrigation | 17 % | |
| … not recognised | 7 % | |
| Median difference in sowing date against the local calendar, with local adjustment | 30 days | 4010 cases |
| Same, without local adjustment | 61 days | 3701 cases |
| Expected difference when picking a date at random | about 91 days | |

With the local adjustment the engine knows the local date and adopts it when the yield is nearly the same, so agreement on sowing dates **is not an independent test**. Dates are presented to the user as tentative.

## By region (rainfed cropland, with local adjustment)

| Region | Points | Hit rate |
|---|---|---|
| Latin America | 30 | 100 % |
| North America | 30 | 97 % |
| East and South-East Asia | 19 | 100 % |
| South Asia | 16 | 94 % |
| Europe | 29 | 100 % |
| Oceania | 29 | 83 % |
| Russia and Central Asia | 29 | 93 % |
| North Africa and Middle East | 29 | 55 % |
| Sub-Saharan Africa | 28 | 100 % |

## Where it fails

- North Africa and the Middle East: 55 %.
- Peas: not recognised in 50 % of the places where they are sown (8 points only).
- Rice and rapeseed: not recognised in 20 % of cases.
- Sowing dates for peas, potatoes and barley: 76, 74 and 61 days from the local calendar.
- On land with no cropland in general, the engine says something would grow in 59 % of points. That is not an error by itself: it includes forests, grassland and cities where the climate does allow farming.

## Errors the validation exposed and that were fixed

- The verdict was too strict for low-yield rainfed farming (Oceania scored 70 %): a "grows, with a low harvest" verdict was added.
- A bug in deep-soil water made millet "grow" with 82 mm of rain a year: fixed; false positives in arid land went to 0 %.

## What this validation does not prove

- No comparison with yields in tonnes per hectare: the engine does not predict them.
- Land cover says there is cropland, not which crop; the calendar is a 55 km grid.
- 16 of the 23 crops are compared with the calendar and 15 with CROPGRIDS — those with data in these sources.
- Terrain classification, field layout and rotations were not validated.
- No farmer or agronomist has reviewed the results.

## Rerun it

```bash
python -m prospector.obtener_datos                 # global reference data, once
python -m prospector.validar_mundo 30 10 31        # 30 cropland + 10 non-cropland points per region, seed 31
python -m prospector.informe_validacion resultados_31.json INFORME.md
```

Results are written to `prospector/validacion/`. The first run downloads weather for every point and takes a while.
