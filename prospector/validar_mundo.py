"""Validación mundial del motor de cultivos. No ajusta nada: solo mide.

Muestra puntos de todo el mundo y compara lo que dice el motor con datos observados independientes:
  A. Fecha de siembra y largo del ciclo del motor GENERAL (sin calendario) contra el calendario mundial GGCMI.
  B. Veredicto «se da» contra el uso real del suelo (ESA CCI 2020): en tierras de cultivo de secano el motor debería
     encontrar algo que se dé sin riego; en tierras sin ningún cultivo (desierto, frío) no debería.
  C. Lo mismo con la calibración local activada, para ver si mejora o empeora.
Uso:  python -m prospector.validar_mundo [n_cultivo] [n_sin_cultivo]
"""
import os, sys, json, time, math
import numpy as np, requests
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from . import cultivos, calendario, mundo

AQUI = os.path.dirname(os.path.abspath(__file__)); DV = os.path.join(AQUI, "validacion"); DC = os.path.join(DV, "clima")
CULT = ["trigo", "cebada", "centeno", "maiz", "sorgo", "arroz", "mijo", "soya", "poroto", "arveja", "mani", "raps", "girasol", "papa", "algodon", "yuca"]

def region(lat, lon):
    if lon < -30: return "América del Norte" if lat > 13 else "América Latina"
    if lon < 60: return "Europa" if lat > 36 else ("África del Norte y Medio Oriente" if lat > 15 else "África subsahariana")
    if lat < -10 and lon > 110: return "Oceanía"
    if lon < 95 and lat < 38: return "Asia del Sur"
    if lat > 45: return "Rusia y Asia Central"
    return "Asia del Este y Sudeste"

def bajar(p):
    f = os.path.join(DC, f"{p['lat']:.3f}_{p['lon']:.3f}.json")
    if os.path.exists(f): return True
    par = "T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR,IMERG_PRECTOT"
    for intento in range(4):
        try:
            r = requests.get(f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={par}&community=AG&latitude={p['lat']:.4f}&longitude={p['lon']:.4f}&start=20010101&end=20241231&format=JSON&time-standard=UTC", timeout=180)
            if r.status_code == 200 and "properties" in r.json(): json.dump(r.json(), open(f, "w")); return True
        except Exception: pass
        time.sleep(5 + 10 * intento)
    return False

def punto(p):
    f = os.path.join(DC, f"{p['lat']:.3f}_{p['lon']:.3f}.json")
    try:
        c, anio, mes, J = cultivos.leer_clima(f); z = float(json.load(open(f))["geometry"]["coordinates"][2]); awc = cultivos.suelo_de(p["arcilla"], p["arena"])["awc"]
        cal = calendario.consultar(p["lon"], p["lat"]); out = dict(p, z=z, cultivos={})
        for modo, usar in (("general", False), ("local", True)):
            ev = cultivos.evaluar(c, anio, mes, J, p["lat"], z, awc, lon=p["lon"], usar_calendario=usar, solo=set(CULT))
            for x in ev["cultivos"]:
                obs = [(cal.get(cod) or {}).get("rf") for cod, _, _ in calendario.CODIGOS.get(x["clave"], [])]; obs = [o for o in obs if o]
                r = dict(veredicto=x["veredicto"], buenos=x["buenos_de_10"], apto=x["apto"], con_riego=x.get("con_riego"), dia=(x.get("tecnico") or {}).get("dia_siembra"), ciclo=x.get("ciclo_dias"))
                if obs and r["dia"]:
                    difs = [abs((r["dia"] - o["siembra"] + 182) % 365 - 182) for o in obs]; k = int(np.argmin(difs)); r.update(dif_siembra=int(difs[k]), dif_ciclo=int(r["ciclo"] - obs[k]["dias"]), fuente=obs[k]["fuente"])
                out["cultivos"].setdefault(x["clave"], {})[modo] = r
            out[f"lluvia"] = ev["clima"]["lluvia_reciente"]; out["temp"] = ev["clima"]["temp_media"]
        return out
    except Exception as e:
        return dict(p, error=str(e)[:200])

def main(n_cult=240, n_sin=80, semilla=2026):
    os.makedirs(DC, exist_ok=True); M = mundo._cargar(); rng = np.random.default_rng(semilla); V = M["meta"]["vars"]; ia, ie = V.index("arcilla"), V.index("arena")
    esc = 0.1 if np.nanmedian(M["crudo"][:, ia]) > 100 else 1.0
    def muestra(sel, n, clase):
        idx = np.flatnonzero(sel); reg = np.array([region(M["lat"][i], M["lon"][i]) for i in idx]); pts = []
        for r in sorted(set(reg)):                                    # igual cantidad por región del mundo
            cand = idx[reg == r]; tomar = rng.choice(cand, size=min(len(cand), max(n // len(set(reg)), 1)), replace=False)
            pts += [dict(lat=float(M["lat"][i]), lon=float(M["lon"][i]), frac=float(M["frac"][i]), riego=float(M["riego"][i]), arcilla=float(M["crudo"][i, ia] * esc), arena=float(M["crudo"][i, ie] * esc), region=r, clase=clase) for i in tomar]
        return pts
    ok_suelo = np.isfinite(M["crudo"][:, ia]) & np.isfinite(M["crudo"][:, ie])
    pts = muestra((M["frac"] >= 0.4) & ok_suelo, n_cult, "cultivo") + muestra((M["frac"] <= 0.001) & ok_suelo & (np.abs(M["lat"]) < 62), n_sin, "sin cultivo")
    print(len(pts), "puntos; descargando clima…", flush=True)
    with ThreadPoolExecutor(5) as ex: bien = list(ex.map(bajar, pts))
    pts = [p for p, b in zip(pts, bien) if b]; print(len(pts), "con clima; simulando…", flush=True)
    with ProcessPoolExecutor(10) as ex: res = list(ex.map(punto, pts, chunksize=2))
    json.dump(res, open(os.path.join(DV, f"resultados_{semilla}.json"), "w"), ensure_ascii=False); print("listo", len(res), sum(1 for r in res if "error" in r), "errores", flush=True)

if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:]]; main(*a)
