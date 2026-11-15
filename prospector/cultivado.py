"""Qué se cultiva de verdad en cada zona y con qué rendimiento (datos observados, no simulados).

- CROPGRIDS v1.08 (Tang et al. 2024, Scientific Data; CC-BY 4.0): superficie cosechada de 173 cultivos hacia 2020, celdas de 0,05° (unos 5,6 km).
- GDHY v1.2+v1.3 (Iizumi y Sakai 2020, Scientific Data; CC-BY 4.0): rendimiento anual de maíz, arroz, trigo y soya, celdas de 0,5° (unos 55 km), 1981-2016.
Se usan para mostrar la práctica real de la zona y para validar el motor; nunca para inventar un rendimiento.
"""
import os, math
import numpy as np, rasterio
from rasterio.windows import Window

D = os.environ.get("PROSPECTOR_DATOS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "mundo_datos")
CROPGRIDS = dict(trigo="wheat", cebada="barley", centeno="rye", avena="oats", maiz="maize", sorgo="sorghum", arroz="rice", mijo="millet", lenteja="lentil", garbanzo="chickpea", arveja="pea", haba="broadbean",
                 poroto="bean", soya="soybean", mani="groundnut", raps="rapeseed", girasol="sunflower", papa="potato", quinoa="quinoa", alfalfa="alfalfa", algodon="cotton", yuca="cassava")
GDHY = dict(trigo="wheat", maiz="maize", arroz="rice", soya="soybean")

def disponible(): return os.path.isdir(os.path.join(D, "cropgrids")) and len(os.listdir(os.path.join(D, "cropgrids"))) >= 10

def superficie(lon, lat, vecinos=2):
    """{cultivo: {pct_celda, pct_zona}}: % de la tierra cosechada con ese cultivo en la celda de 5,6 km y en su entorno (5×5 celdas ≈ 28 km)."""
    fi, co = int((90 - lat) / 0.05), int((lon + 180) / 0.05); out = {}
    if not (0 <= fi < 3600 and 0 <= co < 7200): return out
    f0, c0 = max(fi - vecinos, 0), max(co - vecinos, 0); w = Window(c0, f0, min(co + vecinos, 7199) - c0 + 1, min(fi + vecinos, 3599) - f0 + 1)
    ha_celda = 111.32 ** 2 * 0.05 ** 2 * 100 * max(math.cos(math.radians(lat)), 0.05)
    for clave, nom in CROPGRIDS.items():
        f = os.path.join(D, "cropgrids", f"CROPGRIDSv1.08_{nom}.nc")
        if not os.path.exists(f): continue
        with rasterio.open(f'netcdf:"{f}":harvarea') as s: a = s.read(1, window=w).astype(float)
        a[(a < 0) | (a > 1e6)] = 0.0
        out[clave] = dict(pct_celda=round(100 * float(a[fi - f0, co - c0]) / ha_celda, 2), pct_zona=round(100 * float(a.mean()) / ha_celda, 2))
    return out

def rendimiento(lon, lat):
    """{cultivo: {t_ha, minimo, maximo, anios}}: rendimiento observado 2007-2016 en la celda de 55 km (solo maíz, arroz, trigo y soya)."""
    fi, co = int((lat + 90) / 0.5), int((lon % 360) / 0.5); out = {}                 # GDHY va de sur a norte y de 0 a 360° de longitud
    if not (0 <= fi < 360 and 0 <= co < 720): return out
    for clave, nom in GDHY.items():
        v = []
        for y in range(2007, 2017):
            f = os.path.join(D, "gdhy", nom, f"yield_{y}.nc4")
            if not os.path.exists(f): continue
            with rasterio.open(f) as s: x = float(s.read(1, window=Window(co, 359 - fi if ORIENTACION_NORTE_ARRIBA else fi, 1, 1))[0, 0])
            if 0 < x < 50: v.append(x)
        if len(v) >= 3: out[clave] = dict(t_ha=round(float(np.mean(v)), 1), minimo=round(min(v), 1), maximo=round(max(v), 1), anios=len(v))
    return out

ORIENTACION_NORTE_ARRIBA = True      # comprobado con lugares conocidos: maíz de Iowa ~10 t/ha, trigo de Francia ~7 t/ha
