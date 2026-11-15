"""Descarga, una sola vez, los datos mundiales que usa el Prospector (unos 280 MB en total).

Uso:  python -m prospector.obtener_datos            (todo)
      python -m prospector.obtener_datos ggcmi      (solo una parte: tabla, ggcmi, cropgrids, gdhy)

  tabla      tabla mundial de clima y suelo (WorldClim 2.1, SoilGrids, ESA CCI Land Cover, Natural Earth); la construye prospector.mundo
  ggcmi      calendario mundial de cultivos GGCMI Phase 3 (Jägermeyr et al. 2021, CC-BY 4.0)
  cropgrids  superficie cosechada por cultivo, CROPGRIDS v1.08 (Tang et al. 2024, CC-BY 4.0)
  gdhy       rendimientos observados, GDHY (Iizumi y Sakai 2020, CC-BY 4.0)

Sin estos datos la aplicación funciona igual, pero no muestra el ajuste al calendario local ni lo que se siembra de verdad en la zona.
La carpeta de destino es prospector/mundo_datos, o la que indique la variable de entorno PROSPECTOR_DATOS.
"""
import os, sys, zipfile, requests
from . import mundo, cultivado

D = mundo.D

_bajar = mundo._bajar            # con reintentos, sin colgarse y retomando lo ya bajado

def tabla():
    if mundo.disponible(): return print("tabla mundial: ya está")
    mundo.construir()

def ggcmi():
    d = os.path.join(D, "ggcmi"); os.makedirs(d, exist_ok=True)
    for f in requests.get("https://zenodo.org/api/records/5062513", timeout=60).json()["files"]:
        if f["key"].endswith(".nc4"): _bajar(f["links"]["self"], os.path.join(d, f["key"]))
    print("ggcmi:", len(os.listdir(d)), "archivos")

def cropgrids():
    d = os.path.join(D, "cropgrids"); os.makedirs(d, exist_ok=True)
    quiero = {f"CROPGRIDSv1.08_{n}.nc" for n in cultivado.CROPGRIDS.values()}
    if quiero <= set(os.listdir(d)) and os.path.exists(cultivado.F_OTROS): return print("cropgrids: ya está")
    z = _bajar("https://ndownloader.figshare.com/files/44950942", os.path.join(d, "nc.zip"))      # todos los cultivos; se guardan solo los que simula el motor
    with zipfile.ZipFile(z) as a:
        for m in a.namelist():
            if os.path.basename(m) in quiero:
                with open(os.path.join(d, os.path.basename(m)), "wb") as f: f.write(a.read(m))
    n = cultivado.construir_otros(z, registro=lambda m: None)      # resumen de los cultivos que el motor no simula (uva, frutales, hortalizas…)
    os.remove(z); print("cropgrids:", len(os.listdir(d)), "cultivos simulados y", n, "solo informados")

def gdhy():
    d = os.path.join(D, "gdhy"); os.makedirs(d, exist_ok=True)
    if all(os.path.exists(os.path.join(d, n, "yield_2016.nc4")) for n in cultivado.GDHY.values()): return print("gdhy: ya está")
    z = _bajar("https://doi.pangaea.de/10.1594/PANGAEA.909132?format=textfile", os.path.join(d, "gdhy.zip"))
    with zipfile.ZipFile(z) as a:
        for m in a.namelist():
            p = m.strip("/").split("/")
            if len(p) >= 2 and p[-2] in cultivado.GDHY.values() and p[-1] in {f"yield_{y}.nc4" for y in range(2007, 2017)}:
                os.makedirs(os.path.join(d, p[-2]), exist_ok=True)
                with open(os.path.join(d, p[-2], p[-1]), "wb") as f: f.write(a.read(m))
    os.remove(z); print("gdhy:", sorted(os.listdir(d)))

PASOS = dict(tabla=(tabla, "Tabla mundial de clima y suelo (WorldClim, SoilGrids, ESA CCI)", "no se compara el lugar con otros parecidos del mundo"),
             ggcmi=(ggcmi, "Calendario local de cultivos (GGCMI)", "las fechas salen de valores generales, sin ajuste local"),
             cropgrids=(cropgrids, "Superficie sembrada por cultivo (CROPGRIDS)", "no se informa qué se siembra de verdad en la zona"),
             gdhy=(gdhy, "Rendimientos medidos (GDHY)", "no se muestra el rendimiento medido de maíz, arroz, trigo y soya"))

if __name__ == "__main__":
    # Cada conjunto de datos se baja por separado: si uno falla (servidor caído), los demás siguen y al final se dice cuál faltó.
    os.makedirs(D, exist_ok=True); pedidos = sys.argv[1:] or list(PASOS); fallaron = []
    for paso in pedidos:
        if paso not in PASOS: print(f"«{paso}» no existe. Opciones: {', '.join(PASOS)}"); continue
        print("→", paso, flush=True)
        try: PASOS[paso][0]()
        except Exception as e: fallaron.append(paso); print(f"   FALLÓ: {str(e)[:200]}", flush=True)
    print("\nResumen")
    for paso in pedidos:
        if paso in PASOS: print(f"  {'FALTA' if paso in fallaron else 'listo'}  {PASOS[paso][1]}" + (f" — sin esto, {PASOS[paso][2]}" if paso in fallaron else ""))
    if fallaron:
        print(f"\nLa aplicación funciona igual y avisa en pantalla qué dato falta. Para reintentar solo lo que faltó:\n  python -m prospector.obtener_datos {' '.join(fallaron)}")
        sys.exit(1)
