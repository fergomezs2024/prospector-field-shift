"""Contrasta la tabla de cultivos por región (CROPGRIDS sumado en regiones de Natural Earth) con lo que dicen las estadísticas oficiales
recopiladas región por región (archivos JSON con la fuente de cada dato). Solo mide; no cambia la tabla.
Uso:  python -m prospector.contraste_regiones <carpeta_con_json> <salida.md>
"""
import os, sys, json, glob, unicodedata
from . import regiones
FORRAJE = {"mixedgrass", "grassnes", "fornes", "maizefor", "sorghumfor", "ryefor", "beetfor", "cabbagefor", "carrotfor", "turnipfor", "swedefor", "oilseedfor", "legumenes", "vegetablenes", "clover", "vetch"}
IGUAL = {"vegetablenes": "vegfor", "pimento": "chilleetc", "greencorn": "maize", "greenpea": "pea", "greenbean": "bean", "stringbean": "bean", "greenbroadbean": "broadbean", "greenonion": "onion"}
def norma(s): return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if c.isalnum())
def can(k): return IGUAL.get(k, k)

def main(carpeta, salida):
    ids, T = regiones._cargar(); por_pais = {}
    for r in T["regiones"][1:]: por_pais.setdefault(r["iso3"], []).append(r)
    filas = []; sin = []; paises = {}
    for f in sorted(glob.glob(os.path.join(carpeta, "*.json"))):
        for p in json.load(open(f)).get("countries", []):
            iso = p["iso3"]; cand = por_pais.get(iso, [])
            for rg in p.get("regions", []):
                of = [can(k) for k in rg.get("crops", []) if k not in FORRAJE]
                if len(of) < 2: continue
                n = norma(rg["name"]); m = [c for c in cand if n and (n == norma(c["nombre"]) or n == norma(c["local"]))] or [c for c in cand if n and len(n) >= 5 and (n in norma(c["nombre"]) or n in norma(c["local"]) or norma(c["local"]) in n or norma(c["nombre"]) in n) and min(len(norma(c["local"])), len(norma(c["nombre"]))) >= 5]
                if len(m) != 1: sin.append(f"{iso} · {rg['name']}"); continue
                cg = [can(k) for k, ha, pc in m[0].get("top", []) if k not in FORRAJE][:8]
                if not cg: sin.append(f"{iso} · {rg['name']} (sin cultivos en la tabla)"); continue
                com = len(set(of) & set(cg)); d = dict(iso=iso, pais=p["name"], region=rg["name"], oficial=of, tabla=cg, comunes=com, de=len(of), primero=of[0] in cg[:3], mismo_primero=of[0] == cg[0], conf=rg.get("confidence", ""), base=rg.get("basis", ""), fuente=rg.get("source_url", ""))
                filas.append(d); paises.setdefault(iso, []).append(d)
    pc = lambda a, b: f"{round(100 * a / b)} %" if b else "—"; N = len(filas)
    L = ["# Contraste: cultivos por región según la tabla (CROPGRIDS) y según estadísticas oficiales", "",
         f"Regiones comparadas: **{N}** de {len(paises)} países. Las estadísticas oficiales se recopilaron región por región, con la dirección de cada fuente (carpeta `investigacion/cultivos_por_pais/`). "
         "La tabla es CROPGRIDS v1.08 (hacia 2020) sumado dentro de cada región de Natural Earth. Se excluyen forrajes y praderas, que las estadísticas de cultivos no suelen traer.", "",
         "| Qué se midió | Resultado |", "|---|---|",
         f"| El cultivo principal según la estadística oficial está entre los 3 principales de la tabla | {pc(sum(d['primero'] for d in filas), N)} |",
         f"| El cultivo principal es exactamente el mismo | {pc(sum(d['mismo_primero'] for d in filas), N)} |",
         f"| De los cultivos que lista la estadística oficial, cuántos están entre los 8 principales de la tabla | {pc(sum(d['comunes'] for d in filas), sum(d['de'] for d in filas))} |",
         f"| Regiones oficiales que no se pudieron emparejar por nombre con la tabla | {len(sin)} |", "",
         "## Por país", "", "| País | Regiones | Cultivo principal entre los 3 de la tabla | Cultivos oficiales presentes en la tabla |", "|---|---|---|---|"]
    for iso, ds in sorted(paises.items(), key=lambda x: x[1][0]["pais"]):
        L.append(f"| {ds[0]['pais']} | {len(ds)} | {pc(sum(d['primero'] for d in ds), len(ds))} | {pc(sum(d['comunes'] for d in ds), sum(d['de'] for d in ds))} |")
    mal = [d for d in filas if not d["primero"]]
    L += ["", "## Regiones donde el cultivo principal oficial no está entre los 3 de la tabla", "", "| País | Región | Oficial | Tabla | Base y confianza de la fuente |", "|---|---|---|---|---|"]
    nom = lambda ks: ", ".join(regiones.NOMBRE.get(k, k) for k in ks[:5])
    for d in mal: L.append(f"| {d['pais']} | {d['region']} | {nom(d['oficial'])} | {nom(d['tabla'])} | {d['base']}, {d['conf']} |")
    L += ["", "Leer con cuidado: las fuentes oficiales son de años distintos, algunas listan por producción y no por superficie, y varias no cubren todos los cultivos (por ejemplo, solo granos). "
          "Una diferencia no dice por sí sola cuál de las dos fuentes está equivocada.", "", "Regiones sin emparejar: " + ("; ".join(sin) if sin else "ninguna") + "."]
    open(salida, "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L[:14 + len(paises)])); print(f"\n{len(mal)} regiones con diferencia en el cultivo principal; {len(sin)} sin emparejar")

if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
