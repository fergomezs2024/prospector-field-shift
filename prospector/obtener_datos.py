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

def _bajar(url, dst):
    if os.path.exists(dst): return dst
    r = requests.get(url, timeout=1800, stream=True); r.raise_for_status()
    with open(dst + ".part", "wb") as f:
        for ch in r.iter_content(1 << 20): f.write(ch)
    os.replace(dst + ".part", dst); return dst

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

if __name__ == "__main__":
    os.makedirs(D, exist_ok=True)
    for paso in (sys.argv[1:] or ["tabla", "ggcmi", "cropgrids", "gdhy"]):
        print("→", paso, flush=True); dict(tabla=tabla, ggcmi=ggcmi, cropgrids=cropgrids, gdhy=gdhy)[paso]()
