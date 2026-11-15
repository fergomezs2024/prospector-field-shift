"""Revisa que el equipo pueda correr el Prospector: versión de Python, librerías, programa de mapas y acceso a cada servicio de datos.
Uso:  python -m prospector.diagnostico
"""
import sys, os, importlib

def main():
    mal = 0
    def linea(ok, que, nota=""):
        nonlocal mal; mal += 0 if ok else 1; print(("  bien  " if ok else "  FALLA ") + que + (f" — {nota}" if nota else ""))
    print("Python", sys.version.split()[0]); linea(sys.version_info >= (3, 12), "versión de Python", "" if sys.version_info >= (3, 12) else "se necesita 3.12 o superior (probado con 3.14); o usa Docker: docker compose up --build")
    print("Librerías")
    for m in ("fastapi", "uvicorn", "numpy", "scipy", "sklearn", "rasterio", "affine", "shapely", "pysheds", "pystac_client", "planetary_computer", "overturemaps", "pyarrow", "requests", "PIL", "matplotlib", "pydantic", "shapefile"):
        try: importlib.import_module(m); linea(True, m)
        except Exception as e: linea(False, m, f"instala con: pip install -r requirements.txt ({str(e)[:60]})")
    try:
        from . import datos; exe = datos._overture(); linea(os.path.exists(exe) or exe == "overturemaps", "programa overturemaps", exe)
    except Exception as e: linea(False, "programa overturemaps", str(e)[:80])
    print("Servicios de datos (se necesita internet)")
    try:
        import requests
        for nom, url in (("NASA POWER (clima)", "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=AG&latitude=0&longitude=0&start=20240101&end=20240102&format=JSON"),
                         ("Planetary Computer (relieve, cobertura, HLS)", "https://planetarycomputer.microsoft.com/api/stac/v1"), ("Esri World Imagery (imagen)", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/2/1/1"),
                         ("SoilGrids (suelo)", "https://rest.isric.org/soilgrids/v2.0/docs"), ("Nominatim (buscador de lugares)", "https://nominatim.openstreetmap.org/status")):
            try: r = requests.get(url, timeout=25, headers={"User-Agent": "prospector-diagnostico"}); linea(r.status_code < 500, nom, f"respondió {r.status_code}")
            except Exception as e: linea(False, nom, str(e)[:70])
    except Exception: pass
    print("\nTodo en orden. Inicia con:  python -m uvicorn prospector.api:app --port 8790   y abre http://localhost:8790 (no abras el archivo index.html directamente)." if not mal
          else f"\nHay {mal} punto(s) por resolver arriba. La aplicación se abre siempre desde http://localhost:8790, no desde el archivo index.html.")
    return 1 if mal else 0

if __name__ == "__main__": sys.exit(main())
