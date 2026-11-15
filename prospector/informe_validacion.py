"""Lee validacion/resultados.json y escribe validacion/INFORME.md con los números tal como salen."""
import os, json, collections
import numpy as np
from . import cultivos, cultivado

DV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validacion")
SE_DA = ("se da bien", "se da, con riesgo", "se da, con cosecha baja")

def main():
    import sys; arch = sys.argv[1] if len(sys.argv) > 1 else "resultados.json"; sal = sys.argv[2] if len(sys.argv) > 2 else "INFORME.md"
    R = [r for r in json.load(open(os.path.join(DV, arch))) if "error" not in r]; L = []
    cult = [r for r in R if r["clase"] == "cultivo"]; sin = [r for r in R if r["clase"] == "sin cultivo"]
    L += ["# Validación mundial del motor de cultivos", "", f"Puntos evaluados: **{len(cult)} en tierras de cultivo** y **{len(sin)} en tierras sin ningún cultivo**, repartidos por igual en 9 regiones del mundo "
          "(muestra al azar con semilla fija, de la tabla mundial de 10 minutos de arco). Clima: NASA POWER diario 2001-2024 de cada punto. "
          "Este informe solo mide; ningún parámetro se ajustó con estos resultados.", ""]
    # ---- A. fecha de siembra y ciclo contra el calendario GGCMI
    for modo, tit in (("general", "A. Motor general (parámetros de literatura, sin calendario local)"), ("local", "C. Motor con calibración local (ciclo ajustado al calendario de la zona)")):
        L += [f"## {tit}", "", "Comparación con el calendario mundial GGCMI en los puntos de cultivo. Elegir la fecha al azar daría una diferencia mediana de unos 91 días.", "",
              "| Cultivo | Puntos | Diferencia mediana de siembra (días) | Dentro de 30 días | Dentro de 60 días | Diferencia mediana de ciclo (días) | Sesgo de ciclo (días) |", "|---|---|---|---|---|---|---|"]
        todos = []
        for k in sorted({k for r in cult for k in r["cultivos"]}, key=lambda k: cultivos.CULTIVOS[k]["nombre"]):
            d = [r["cultivos"][k][modo] for r in cult if modo in r["cultivos"].get(k, {}) and "dif_siembra" in r["cultivos"][k][modo]]
            if len(d) < 8: continue
            ds = np.array([x["dif_siembra"] for x in d]); dc = np.array([x["dif_ciclo"] for x in d]); todos += list(ds)
            L.append(f"| {cultivos.CULTIVOS[k]['nombre']} | {len(d)} | {np.median(ds):.0f} | {100 * (ds <= 30).mean():.0f} % | {100 * (ds <= 60).mean():.0f} % | {np.median(np.abs(dc)):.0f} | {np.median(dc):+.0f} |")
        if todos: todos = np.array(todos); L += [f"| **Todos** | {len(todos)} | **{np.median(todos):.0f}** | **{100 * (todos <= 30).mean():.0f} %** | **{100 * (todos <= 60).mean():.0f} %** | | |"]
        if modo == "local": L += ["", "Ojo: en este modo el motor conoce la fecha local y la adopta cuando rinde casi lo mismo, así que la coincidencia de siembra no es una prueba independiente; sí lo es que el veredicto no empeore (sección B)."]
        L.append("")
    # ---- B. veredicto contra uso real del suelo
    L += ["## B. ¿El veredicto «se da» coincide con lo que se cultiva de verdad?", "",
          "Uso real: ESA CCI Land Cover 2020. «Secano» = tierras de cultivo con menos de 10 % de riego. Se cuenta si el motor encuentra **al menos un cultivo que se da sin riego**.", "",
          "| Grupo de puntos | Puntos | Motor general: algo se da sin riego | Con calibración local: algo se da sin riego |", "|---|---|---|---|"]
    def algo(r, modo): return any(v.get(modo, {}).get("veredicto") in SE_DA for v in r["cultivos"].values())
    grupos = [("Tierras de cultivo de secano", [r for r in cult if r["riego"] < 0.1]), ("Tierras de cultivo con riego (≥ 30 %)", [r for r in cult if r["riego"] >= 0.3]), ("Sin ningún cultivo", sin),
              ("Sin cultivo y áridas (menos de 250 mm al año)", [r for r in sin if r.get("lluvia", 1e9) < 250])]
    for nom, g in grupos:
        if g: L.append(f"| {nom} | {len(g)} | {100 * np.mean([algo(r, 'general') for r in g]):.0f} % | {100 * np.mean([algo(r, 'local') for r in g]):.0f} % |")
    L += ["", "Lectura: en secano el porcentaje debería ser alto (el motor reconoce que ahí se puede cultivar); en tierras áridas sin cultivo debería ser cercano a cero. "
          "En «sin ningún cultivo» no se espera cero: hay bosques, praderas y ciudades donde el clima sí permite cultivar.", "", "### Por región (tierras de cultivo de secano)", "",
          "| Región | Puntos | Motor general | Con calibración local |", "|---|---|---|---|"]
    for reg in sorted({r["region"] for r in cult}):
        g = [r for r in cult if r["region"] == reg and r["riego"] < 0.1]
        if g: L.append(f"| {reg} | {len(g)} | {100 * np.mean([algo(r, 'general') for r in g]):.0f} % | {100 * np.mean([algo(r, 'local') for r in g]):.0f} % |")
    # ---- cambio de veredicto por la calibración
    cam = collections.Counter()
    for r in cult:
        for k, v in r["cultivos"].items():
            if "general" in v and "local" in v and "dif_siembra" in v["general"]:
                a, b = v["general"]["veredicto"] in SE_DA, v["local"]["veredicto"] in SE_DA; cam["igual" if a == b else ("gana" if b else "pierde")] += 1
    n = max(sum(cam.values()), 1)
    # ---- E. cultivo por cultivo contra lo que de verdad se siembra (CROPGRIDS)
    if cultivado.disponible():
        for r in cult: r["sup"] = cultivado.superficie(r["lon"], r["lat"])
        L += ["", "## E. Cultivo por cultivo: ¿el motor dice «se da» donde ese cultivo se siembra de verdad?", "",
              "Dato real: CROPGRIDS (superficie cosechada hacia 2020, celdas de 5,6 km). «Se siembra» = el cultivo ocupa al menos 1 % de la tierra en los 28 km alrededor del punto. "
              "Acierto = el motor (con calibración local) dice que se da sin riego o solo con riego. «Ausente» = menos de 0,05 %.", "",
              "| Cultivo | Puntos donde se siembra | El motor dice que se da sin riego | …o solo con riego | No lo reconoce | Puntos donde está ausente | Ahí el motor dice que se daría |", "|---|---|---|---|---|---|---|"]
        tot = [0, 0, 0, 0]
        for k in sorted({k for r in cult for k in r["cultivos"]}, key=lambda k: cultivos.CULTIVOS[k]["nombre"]):
            si = [r for r in cult if r["sup"].get(k, {}).get("pct_zona", 0) >= 1 and "local" in r["cultivos"].get(k, {})]; no = [r for r in cult if k in r["sup"] and r["sup"][k]["pct_zona"] < 0.05 and "local" in r["cultivos"].get(k, {})]
            if len(si) < 8: continue
            a = sum(r["cultivos"][k]["local"]["veredicto"] in SE_DA for r in si); b = sum(r["cultivos"][k]["local"]["veredicto"] == "solo con riego" for r in si); c = len(si) - a - b
            d = np.mean([r["cultivos"][k]["local"]["veredicto"] in SE_DA for r in no]) if no else float("nan"); tot[0] += len(si); tot[1] += a; tot[2] += b; tot[3] += c
            L.append(f"| {cultivos.CULTIVOS[k]['nombre']} | {len(si)} | {100 * a / len(si):.0f} % | {100 * b / len(si):.0f} % | {100 * c / len(si):.0f} % | {len(no)} | {'' if not no else f'{100 * d:.0f} %'} |")
        if tot[0]: L.append(f"| **Todos** | {tot[0]} | **{100 * tot[1] / tot[0]:.0f} %** | **{100 * tot[2] / tot[0]:.0f} %** | **{100 * tot[3] / tot[0]:.0f} %** | | |")
        L += ["", "La última columna no es un error por sí sola: un cultivo puede darse y no sembrarse por mercado, costumbre o falta de agua de riego. Sí lo es la columna «No lo reconoce»."]
    L += ["", "## D. Qué cambia la calibración local", "", f"De {n} casos (cultivo × punto con calendario): en {100 * cam['igual'] / n:.0f} % el veredicto no cambia, en {100 * cam['gana'] / n:.0f} % pasa a «se da» y en {100 * cam['pierde'] / n:.0f} % deja de darse.", "",
          "## Límites de esta validación", "",
          "- El calendario GGCMI es una grilla de 0,5° (unos 55 km) con fechas por mes y con vacíos rellenados: no dice si el cultivo se siembra realmente en cada punto.",
          "- El uso del suelo dice que hay cultivos, no cuáles. No hay contraste con rendimientos medidos (toneladas por hectárea).",
          "- El suelo de cada punto viene de SoilGrids a 10 minutos de arco; el relieve del lugar no entra en esta prueba.",
          "- Los parámetros de los cultivos siguen siendo valores generales de FAO; esta prueba mide cuánto se equivocan, no los corrige."]
    open(os.path.join(DV, sal), "w").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__": main()
