"""Validación dirigida: para cada cultivo del motor se toman puntos al azar DONDE ESE CULTIVO SE SIEMBRA DE VERDAD (CROPGRIDS, al menos 2 % de la tierra
de la celda de 5,6 km), repartidos por regiones del mundo, y se mira si el motor lo reconoce. Sirve para los cultivos que en la muestra general casi no aparecen.
No ajusta nada: solo mide.   Uso:  python -m prospector.validar_dirigida [puntos_por_cultivo=30] [semilla=41]
"""
import os, sys, json, math
import numpy as np, rasterio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from . import cultivos, cultivado, mundo, calendario
from .validar_mundo import region, bajar, DC, DV
SE_DA = ("se da bien", "se da, con riesgo", "se da, con cosecha baja")

def muestra(n, semilla):
    M = mundo._cargar(); V = M["meta"]["vars"]; ia, ie = V.index("arcilla"), V.index("arena"); esc = 0.1 if np.nanmedian(M["crudo"][:, ia]) > 100 else 1.0
    donde = {int(f) * 2160 + int(c): i for i, (f, c) in enumerate(zip(M["fila"], M["col"]))}; rng = np.random.default_rng(semilla); pts = []
    lat = 90 - (np.arange(3600) + 0.5) * 0.05; ha_celda = (111.32 ** 2 * 0.05 ** 2 * 100 * np.maximum(np.cos(np.radians(lat)), 0.05))[:, None]
    for clave, nom in cultivado.CROPGRIDS.items():
        f = os.path.join(cultivado.D, "cropgrids", f"CROPGRIDSv1.08_{nom}.nc")
        if not os.path.exists(f): continue
        with rasterio.open(f'netcdf:"{f}":harvarea') as s: a = s.read(1).astype("float32")
        a[(a < 0) | (a > 1e6)] = 0; fi, co = np.nonzero(100 * a / ha_celda >= 2.0)
        if not len(fi): continue
        la, lo = 90 - (fi + 0.5) * 0.05, -180 + (co + 0.5) * 0.05; reg = np.array([region(x, y) for x, y in zip(la, lo)]); regs = sorted(set(reg)); elegidos = []
        for r in regs:                                                       # igual cantidad por región donde el cultivo existe
            cand = np.flatnonzero(reg == r); elegidos += list(rng.choice(cand, size=min(len(cand), max(int(math.ceil(n / len(regs))), 1)), replace=False))
        for i in elegidos[:n + len(regs)]:
            k = donde.get(int((90 - la[i]) * 6) * 2160 + int((lo[i] + 180) * 6))
            if k is None: continue
            pts.append(dict(cultivo=clave, lat=round(float(la[i]), 3), lon=round(float(lo[i]), 3), region=str(reg[i]), arcilla=float(M["crudo"][k, ia] * esc), arena=float(M["crudo"][k, ie] * esc)))
    return pts

def punto(p):
    f = os.path.join(DC, f"{p['lat']:.3f}_{p['lon']:.3f}.json")
    try:
        c, anio, mes, J = cultivos.leer_clima(f); z = float(json.load(open(f))["geometry"]["coordinates"][2])
        ev = cultivos.evaluar(c, anio, mes, J, p["lat"], z, cultivos.suelo_de(p["arcilla"], p["arena"])["awc"], lon=p["lon"], usar_calendario=True, solo={p["cultivo"]})
        return dict(p, veredicto=ev["cultivos"][0]["veredicto"], lluvia=ev["clima"]["lluvia_reciente"])
    except Exception as e: return dict(p, error=str(e)[:200])

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30; semilla = int(sys.argv[2]) if len(sys.argv) > 2 else 41
    os.makedirs(DC, exist_ok=True); pts = muestra(n, semilla); print(len(pts), "puntos; descargando clima…", flush=True)
    with ThreadPoolExecutor(5) as ex: bien = list(ex.map(bajar, pts))
    pts = [p for p, b in zip(pts, bien) if b]; print(len(pts), "con clima; simulando…", flush=True)
    with ProcessPoolExecutor(10) as ex: res = list(ex.map(punto, pts, chunksize=2))
    json.dump(res, open(os.path.join(DV, f"dirigida_{semilla}.json"), "w"), ensure_ascii=False); ok = [r for r in res if "error" not in r]
    L = ["# Validación dirigida: ¿el motor reconoce cada cultivo donde de verdad se siembra?", "",
         f"{len(ok)} puntos elegidos al azar entre las celdas donde cada cultivo ocupa al menos 2 % de la tierra (CROPGRIDS, hacia 2020), repartidos por regiones del mundo. Semilla {semilla}. "
         "Clima: NASA POWER diario 2001-2024. Con ajuste al calendario local cuando existe. Solo mide; nada se ajustó con estos puntos.", "",
         "| Cultivo | Puntos | Regiones | Se da sin riego | Solo con riego | No lo reconoce | ¿Tiene calendario local? |", "|---|---|---|---|---|---|---|"]
    tot = [0, 0, 0]
    for k in cultivos.CULTIVOS:
        r = [x for x in ok if x["cultivo"] == k]
        if not r: continue
        a = sum(x["veredicto"] in SE_DA for x in r); b = sum(x["veredicto"] == "solo con riego" for x in r); tot = [tot[0] + a, tot[1] + b, tot[2] + len(r)]
        L.append(f"| {cultivos.CULTIVOS[k]['nombre']} | {len(r)} | {len({x['region'] for x in r})} | {round(100 * a / len(r))} % | {round(100 * b / len(r))} % | {round(100 * (len(r) - a - b) / len(r))} % | {'sí' if k in calendario.CODIGOS else 'no'} |")
    L += [f"| **Todos** | {tot[2]} | | **{round(100 * tot[0] / tot[2])} %** | **{round(100 * tot[1] / tot[2])} %** | **{round(100 * (tot[2] - tot[0] - tot[1]) / tot[2])} %** | |", "",
          "«No lo reconoce» es el error que importa: el cultivo se siembra ahí y el motor dice que no se da ni con riego.",
          "Límite: CROPGRIDS reparte estadísticas nacionales y regionales sobre mapas de tierra cultivada; en celdas aisladas puede atribuir un cultivo que no está exactamente ahí."]
    open(os.path.join(DV, "INFORME_dirigida.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
