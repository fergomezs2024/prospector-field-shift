"""Pruebas automáticas del Prospector contra el servidor local (puerto 8790) y los terrenos ya analizados.
Uso:  python -m prospector.pruebas        (sale con código 1 si algo falla)
"""
import sys, json, requests
from . import calendario

B = "http://localhost:8790"; fallos = []; hechas = 0
def ok(cond, nombre, detalle=""):
    global hechas; hechas += 1
    if not cond: fallos.append(f"{nombre} {detalle}"); print("  FALLA", nombre, detalle)
def pide(ruta, **kw):
    r = requests.get(B + ruta, timeout=240, **kw); return r

def main():
    areas = pide("/api/areas").json(); ok(isinstance(areas, list) and areas, "historial de terrenos")
    listos = [a for a in areas if a.get("cultivable_ha") is not None or a.get("completo")] or areas
    probados = 0
    for a in areas:
        i = a["id"]
        if pide(f"/api/cultivos/{i}").status_code != 200: continue
        probados += 1; print("terreno", i, a.get("nombre"))
        t = pide(f"/api/terreno/{i}?motivo=prueba").json(); ok(t.get("superficie_ha", 0) > 0 or "superficie" in json.dumps(t), f"{i} datos del terreno")
        m = pide(f"/api/malla/{i}").json(); ok(m["ancho"] > 2 and m["alto"] > 2 and len(m["poligono"]) >= 4, f"{i} malla 3D")
        for capa in ("imagen", "pendiente", "flujo", "humedad", "altitud", "aptitud", "cultivo", "plan"):
            for q in ("", "?solo=1"):
                r = pide(f"/api/capa/{i}/{capa}.png{q}"); ok(r.status_code == 200 and r.content[:4] == b"\x89PNG", f"{i} capa {capa}{q}", str(r.status_code))
        c = pide(f"/api/cultivos/{i}").json(); nombres = [x["clave"] for x in c["cultivos"]]
        ok(len(nombres) >= 15, f"{i} biblioteca de cultivos", str(len(nombres)))
        for x in c["cultivos"]:
            ok(0 <= x["buenos_de_10"] <= 10 and 0 <= x["apto"] <= 1.0001, f"{i} {x['clave']} rangos"); ok(x["veredicto"] in ("se da bien", "se da, con riesgo", "se da, con cosecha baja", "solo con riego", "no se recomienda", "no se da"), f"{i} {x['clave']} veredicto")
            if x.get("mensual"): ok(all(len(v) == 12 for v in x["mensual"].values()), f"{i} {x['clave']} 12 meses")
        for z in c["zonas"]:
            ok(all(e["secuencia"] and all(k in nombres for k in e["secuencia"]) for e in z["estrategias"]), f"{i} zona {z['nombre']} rotaciones"); ok(0 <= z.get("mejor", 0) < max(len(z["estrategias"]), 1), f"{i} zona {z['nombre']} mejor")
        for q in ("", "?bosque=habilitar", "?ladera=dejar&cabecera=0", "?camino=10&construccion=20", "?entrada=5,5"):
            r = pide(f"/api/loteo/{i}{q}"); ok(r.status_code == 200, f"{i} loteo{q}", str(r.status_code))
            if r.status_code != 200: continue
            lo = r.json(); suma = lo["usado_ha"] + sum(f["ha"] for f in lo["fuera"])
            ok(lo["usado_ha"] <= lo["total_ha"] + 0.01, f"{i} loteo{q} no siembra más que el terreno"); ok(abs(suma - lo["total_ha"]) <= max(0.03 * lo["total_ha"], 0.05), f"{i} loteo{q} cuadra la superficie", f"{suma:.2f} vs {lo['total_ha']}")
            ok(abs(sum(l["ha"] for l in lo["lotes"]) - lo["usado_ha"]) < 0.05, f"{i} loteo{q} lotes suman lo sembrado"); ok(all(c2["largo_m"] >= 15 for c2 in lo["caminos_nuevos"]), f"{i} loteo{q} caminos")
        e = pide(f"/api/entorno/{i}").json(); ok(e["ancho"] == m.get("ancho_meta", e["ancho"]), f"{i} entorno")
        ok(pide(f"/api/punto/{i}?c=-5&r=-5").json().get("fuera") is True, f"{i} punto fuera del terreno")
        if probados >= 4: break
    ok(probados >= 1, "al menos un terreno con plan")
    ok(pide("/api/terreno/noexiste").status_code == 404, "terreno desconocido da 404"); ok(pide("/api/capa/noexiste/plan.png").status_code == 404, "capa de terreno desconocido da 404")
    # calendario mundial: lugares conocidos
    if calendario.disponible():
        k = calendario.consultar(75.8, 30.9).get("wwh", {}).get("rf"); ok(k and 290 <= k["siembra"] <= 335, "calendario: trigo de Punjab se siembra en oct-nov", str(k))
        k = calendario.consultar(-93.6, 42.0).get("mai", {}).get("rf"); ok(k and 100 <= k["siembra"] <= 150, "calendario: maíz de Iowa se siembra en abr-may", str(k))
        ok(calendario.consultar(0, -70) == {}, "calendario: sin datos en la Antártica")
    print(f"\n{hechas - len(fallos)} de {hechas} comprobaciones pasan" + ("" if not fallos else f"; {len(fallos)} fallan:\n  - " + "\n  - ".join(fallos))); sys.exit(1 if fallos else 0)

if __name__ == "__main__": main()
