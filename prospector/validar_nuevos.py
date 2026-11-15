"""Mide los cultivos que no tienen calendario mundial (hortalizas e industriales) sobre la misma muestra de la validación mundial.
No ajusta nada. Compara el veredicto del motor con lo que de verdad se siembra (CROPGRIDS) y revisa que no aparezcan cultivos en zonas áridas sin cultivo.
Uso:  python -m prospector.validar_nuevos resultados_31.json
"""
import os, sys, json
from concurrent.futures import ProcessPoolExecutor
from . import cultivos, cultivado, calendario
DV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validacion"); DC = os.path.join(DV, "clima")
NUEVOS = [k for k in cultivos.CULTIVOS if k not in calendario.CODIGOS and k in cultivado.CROPGRIDS]
SE_DA = ("se da bien", "se da, con riesgo", "se da, con cosecha baja")

def punto(p):
    try:
        f = os.path.join(DC, f"{p['lat']:.3f}_{p['lon']:.3f}.json"); c, anio, mes, J = cultivos.leer_clima(f)
        ev = cultivos.evaluar(c, anio, mes, J, p["lat"], p["z"], cultivos.suelo_de(p["arcilla"], p["arena"])["awc"], lon=p["lon"], usar_calendario=True, solo=set(NUEVOS))
        return dict(clase=p["clase"], lluvia=p["lluvia"], riego=p.get("riego", 0), sup=cultivado.superficie(p["lon"], p["lat"]), v={x["clave"]: x["veredicto"] for x in ev["cultivos"]})
    except Exception as e: return dict(error=str(e)[:200])

if __name__ == "__main__":
    R = [r for r in json.load(open(os.path.join(DV, sys.argv[1]))) if "error" not in r]
    with ProcessPoolExecutor(10) as ex: res = [r for r in ex.map(punto, R, chunksize=2) if "error" not in r]
    cult = [r for r in res if r["clase"] == "cultivo"]; arid = [r for r in res if r["clase"] != "cultivo" and r["lluvia"] < 250]
    L = ["# Cultivos sin calendario mundial: medición sobre la muestra de validación", "",
         f"Puntos: {len(cult)} en tierras de cultivo y {len(arid)} áridos sin cultivo. «Se siembra» = el cultivo ocupa al menos 1 % de la tierra en los 28 km alrededor (CROPGRIDS). Solo se mide; nada se ajustó con esto.", "",
         "| Cultivo | Puntos donde se siembra | Se da sin riego | Solo con riego | No lo reconoce | Puntos donde está ausente | Ahí el motor dice que se daría sin riego |", "|---|---|---|---|---|---|---|"]
    for k in NUEVOS:
        si = [r for r in cult if r["sup"].get(k, {}).get("pct_zona", 0) >= 1]; no = [r for r in cult if k in r["sup"] and r["sup"][k]["pct_zona"] < 0.05]
        a = sum(r["v"][k] in SE_DA for r in si); b = sum(r["v"][k] == "solo con riego" for r in si); pc = lambda x, n: f"{round(100 * x / n)} %" if n else "—"
        L.append(f"| {cultivos.CULTIVOS[k]['nombre']} | {len(si)} | {pc(a, len(si))} | {pc(b, len(si))} | {pc(len(si) - a - b, len(si))} | {len(no)} | {pc(sum(r['v'][k] in SE_DA for r in no), len(no))} |")
    fa = sum(any(v in SE_DA for v in r["v"].values()) for r in arid)
    L += ["", f"Zonas áridas sin cultivo (menos de 250 mm al año): en {fa} de {len(arid)} puntos alguno de estos cultivos sale «se da sin riego» (debería ser 0).", "",
          "Con menos de 8 puntos donde se siembra, el porcentaje no dice nada: la muestra es muy chica."]
    open(os.path.join(DV, "INFORME_cultivos_nuevos.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
