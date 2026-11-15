"""Calendario mundial de cultivos (GGCMI Phase 3, Jägermeyr et al. 2021, CC-BY 4.0; 0,5° ≈ 55 km).

Para cada zona del mundo da el día en que los agricultores siembran y cosechan cada cultivo, en secano y con riego.
Reúne MIRCA, SAGE, Iizumi et al. 2019, RiceAtlas, ChinaCropPhen, India AgStat, CONAB (Brasil) y ABARES (Australia).
Sirve para dos cosas: ajustar el largo del ciclo a las variedades que de verdad se usan en la zona, y contrastar
la fecha de siembra que propone la simulación con la práctica local.
"""
import os, functools
import numpy as np, rasterio

DIR = os.path.join(os.environ.get("PROSPECTOR_DATOS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "mundo_datos"), "ggcmi")
FUENTES = {1: "MIRCA2000", 2: "SAGE", 3: "Iizumi et al. 2019", 4: "RiceAtlas", 5: "Dimou et al. 2018", 6: "ChinaCropPhen", 7: "India AgStat", 8: "CONAB (Brasil)", 9: "ABARES (Australia)"}
# cultivo de la biblioteca -> (código GGCMI, cómo se le dice a esa variante, cultivo de referencia si no es el mismo)
CODIGOS = {"trigo": [("wwh", "trigo de invierno", None), ("swh", "trigo de primavera", None)], "cebada": [("bar", "cebada", None)], "centeno": [("rye", "centeno", None)],
           "avena": [("bar", "avena", "cebada")], "maiz": [("mai", "maíz", None)], "sorgo": [("sor", "sorgo", None)], "arroz": [("ri1", "arroz", None)], "mijo": [("mil", "mijo", None)],
           "lenteja": [("pea", "lenteja", "legumbres de grano")], "garbanzo": [("pea", "garbanzo", "legumbres de grano")], "arveja": [("pea", "arveja", None)], "haba": [("pea", "haba", "legumbres de grano")],
           "poroto": [("bea", "poroto", None)], "soya": [("soy", "soya", None)], "mani": [("nut", "maní", None)], "raps": [("rap", "raps", None)], "girasol": [("sun", "girasol", None)],
           "papa": [("pot", "papa", None)], "algodon": [("cot", "algodón", None)], "yuca": [("cas", "yuca", None)]}

def disponible(): return os.path.isdir(DIR) and any(f.endswith(".nc4") for f in os.listdir(DIR))

@functools.lru_cache(maxsize=None)
def _capa(cod, agua, var):
    f = os.path.join(DIR, f"{cod}_{agua}_ggcmi_crop_calendar_phase3_v1.01.nc4")
    if not os.path.exists(f): return None
    with rasterio.open(f'netcdf:"{f}":{var}') as s: return s.read(1)

def consultar(lon, lat):
    """{código: {rf: {siembra, cosecha, dias, fuente}, ir: {...}}} para la celda de 0,5° que contiene el punto."""
    fi, co = int(np.clip((90 - lat) / 0.5, 0, 359)), int(np.clip((lon + 180) / 0.5, 0, 719)); out = {}
    for cod in sorted({c for v in CODIGOS.values() for c, _, _ in v}):
        for agua in ("rf", "ir"):
            p, m, g, s = (_capa(cod, agua, v) for v in ("planting_day", "maturity_day", "growing_season_length", "data_source_used"))
            if p is None or not (0 < p[fi, co] < 400) or not (0 < g[fi, co] < 400): continue
            out.setdefault(cod, {})[agua] = dict(siembra=int(round(float(p[fi, co]))), cosecha=int(round(float(m[fi, co]))), dias=int(round(float(g[fi, co]))),
                                                 fuente=FUENTES.get(int(round(float(s[fi, co]))) if s is not None and s[fi, co] < 100 else 0, "GGCMI"))
    return out
