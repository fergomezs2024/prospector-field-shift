"""Prospector · adquisición de datos para CUALQUIER polígono del mundo, en una grilla métrica (UTM local).

Fuentes (todas abiertas, sin cuenta):
  Relieve      NASADEM 30 m (NASA; 60°N-56°S) y, fuera de ese rango, Copernicus GLO-30  · Planetary Computer
  Imagen       Sentinel-2 L2A color real 10 m (textura del terreno)                     · Planetary Computer
  Vegetación   HLS v2 (NASA, Landsat+Sentinel-2 armonizados, 30 m) -> NDVI con Fmask    · Planetary Computer
  Cobertura    ESA WorldCover 10 m
  Suelo        SoilGrids 2.0 (ISRIC) 0-5 cm: arcilla, arena, carbono orgánico           · WCS
  Clima        NASA POWER diario desde 2001 (MERRA-2 + CERES) y lluvia GPM IMERG        · API POWER
Todo se guarda en prospector/cache/<id>/ y no se vuelve a bajar.
"""
import os
for _k, _v in dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF,.tiff", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
                   GDAL_HTTP_MULTIPLEX="YES", GDAL_HTTP_VERSION="2", VSI_CACHE="TRUE", GDAL_CACHEMAX="512", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="1", GDAL_HTTP_TIMEOUT="45", GDAL_HTTP_CONNECTTIMEOUT="15", GDAL_HTTP_LOW_SPEED_TIME="30", GDAL_HTTP_LOW_SPEED_LIMIT="1000").items():
    os.environ.setdefault(_k, _v)             # lectura remota de COG: sin listados de carpeta, conexiones reutilizadas
import json, hashlib, math, numpy as np, requests, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_geom, transform as tr_pts
from rasterio.features import geometry_mask
from concurrent.futures import ThreadPoolExecutor
import planetary_computer as pc
from pystac_client import Client
# Ninguna consulta de red puede esperar sin límite (la firma de Planetary Computer no trae tiempo máximo propio)
_pedir = requests.Session.request
def _pedir_con_limite(self, *a, **kw):
    if kw.get("timeout") is None: kw["timeout"] = (10, 60)
    return _pedir(self, *a, **kw)
requests.Session.request = _pedir_con_limite

class Cancelado(Exception): pass

RAIZ = os.environ.get("PROSPECTOR_CACHE") or os.path.join(os.path.dirname(__file__), "cache")   # carpeta de trabajo: un volumen persistente en un despliegue
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"

def _anillo(geo):
    g = geo.get("geometry", geo)
    if g["type"] == "Polygon": return g["coordinates"][0]
    if g["type"] == "MultiPolygon": return max((p[0] for p in g["coordinates"]), key=len)
    raise ValueError("Se espera un polígono GeoJSON")

def definir_grilla(geo, margen_frac=0.6, margen_min_m=400.0):
    """Grilla UTM local que cubre el polígono más un margen (para ver vecinos y drenaje)."""
    an = _anillo(geo); lons = [p[0] for p in an]; lats = [p[1] for p in an]
    lonc, latc = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
    epsg = (32600 if latc >= 0 else 32700) + int((lonc + 180) // 6) + 1
    xs, ys = tr_pts("EPSG:4326", f"EPSG:{epsg}", lons, lats)
    w, hgt = max(xs) - min(xs), max(ys) - min(ys)
    m = max(margen_min_m, margen_frac * max(w, hgt))
    x0, x1, y0, y1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
    lado = max(x1 - x0, y1 - y0)
    res = 10.0 if lado <= 6000 else (30.0 if lado <= 20000 else 90.0)
    x0, y1 = math.floor(x0 / res) * res, math.ceil(y1 / res) * res
    ancho, alto = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    T = from_origin(x0, y1, res, res)
    bx, by = tr_pts(f"EPSG:{epsg}", "EPSG:4326", [x0, x0 + ancho * res, x0, x0 + ancho * res], [y1, y1, y1 - alto * res, y1 - alto * res])
    bbox = [min(bx), min(by), max(bx), max(by)]
    pol_utm = transform_geom("EPSG:4326", f"EPSG:{epsg}", {"type": "Polygon", "coordinates": [an]})
    return dict(epsg=epsg, res=res, ancho=ancho, alto=alto, transform=list(T)[:6], bbox=bbox, centro=[lonc, latc],
                poligono=an, poligono_utm=pol_utm["coordinates"][0])

def _vrt_leer(href, G, banda=1, resampling=Resampling.bilinear, dtype=None):
    from affine import Affine
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=f"EPSG:{G['epsg']}", transform=Affine(*G["transform"]), width=G["ancho"], height=G["alto"],
                       resampling=resampling) as v:
            a = v.read(banda, out_dtype=dtype) if dtype else v.read(banda)
            return a, src.nodata

def _guardar(path, arr, G, nodata=None):
    from affine import Affine
    prof = dict(driver="GTiff", height=G["alto"], width=G["ancho"], count=1 if arr.ndim == 2 else arr.shape[0], dtype=arr.dtype,
                crs=f"EPSG:{G['epsg']}", transform=Affine(*G["transform"]), compress="deflate", nodata=nodata)
    with rasterio.open(path, "w", **prof) as d:
        d.write(arr, 1) if arr.ndim == 2 else d.write(arr)

def _mosaico(cat, coleccion, asset, G, resampling, dtype="float32", vacio=np.nan):
    items = list(cat.search(collections=[coleccion], bbox=G["bbox"]).items())
    out = np.full((G["alto"], G["ancho"]), vacio, dtype)
    for it in items:
        a, nd = _vrt_leer(it.assets[asset].href, G, resampling=resampling, dtype=dtype)
        ok = np.isfinite(a) if dtype.startswith("float") else (a != 0)
        if nd is not None: ok &= a != nd
        llenar = ok & (np.isnan(out) if dtype.startswith("float") else (out == vacio))
        out[llenar] = a[llenar]
    return out, len(items)

def descargar_caminos(d, G, margen=0.012):
    """Caminos, calles y vías de Overture en la ventana del terreno más ~1,2 km: sirve para saber cuál es el camino más cercano aunque quede fuera de la vista."""
    import subprocess, sys
    b = G["bbox"]; exe = os.path.join(os.path.dirname(sys.executable), "overturemaps")
    subprocess.run([exe, "download", f"--bbox={b[0] - margen},{b[1] - margen},{b[2] + margen},{b[3] + margen}", "-f", "geojson", "--type=segment", "-o", f"{d}/_cam.geojson"], check=True, timeout=240, capture_output=True)
    fc = json.load(open(f"{d}/_cam.geojson"))
    fc["features"] = [dict(type="Feature", geometry=f["geometry"], properties=dict(tipo=f["properties"].get("subtype"), clase=f["properties"].get("class"), nombre=((f["properties"].get("names") or {}).get("primary"))))
                      for f in fc["features"] if f.get("geometry") and f["geometry"]["type"] in ("LineString", "MultiLineString") and f["properties"].get("subtype") in ("road", "rail")]
    fc["ampliado"] = True; json.dump(fc, open(f"{d}/caminos.geojson", "w"))
    for x in ("_cam.geojson", "_cam.geojson.state"):
        if os.path.exists(f"{d}/{x}"): os.remove(f"{d}/{x}")
    return len(fc["features"])

def preparar(geo, anio_ini=2021, anio_fin=2025, clima_ini=2001, registro=print, solo_rapido=False, nombre=None, progreso=None, cancelado=None):
    an = _anillo(geo)
    ident = hashlib.sha1(json.dumps([[round(c, 6) for c in p[:2]] for p in an]).encode()).hexdigest()[:12]
    d = os.path.join(RAIZ, ident); os.makedirs(d, exist_ok=True)
    fmeta = f"{d}/meta.json"
    G = json.load(open(fmeta)) if os.path.exists(fmeta) else definir_grilla(geo)
    G["id"] = ident; G.setdefault("fuentes", {})
    if nombre: G["nombre"] = nombre
    cat = Client.open(STAC, modifier=pc.sign_inplace, timeout=(10, 40))
    from affine import Affine
    T = Affine(*G["transform"])
    # ---- relieve: dos mediciones independientes (NASADEM y Copernicus GLO-30); se promedian y su diferencia da el margen de error
    if not os.path.exists(f"{d}/dem.tif") or not os.path.exists(f"{d}/relieve.json"):
        nas, n1 = _mosaico(cat, "nasadem", "elevation", G, Resampling.bilinear)
        cop, n2 = _mosaico(cat, "cop-dem-glo-30", "data", G, Resampling.bilinear)
        ok1, ok2 = n1 > 0 and np.isnan(nas).mean() < 0.2, n2 > 0 and np.isnan(cop).mean() < 0.2
        info = dict(nasadem=bool(ok1), copernicus=bool(ok2))
        if ok1 and ok2:
            dem = np.nanmean(np.stack([nas, cop]), 0); dif = np.abs(nas - cop)
            info.update(dif_mediana_m=round(float(np.nanmedian(dif)), 2), dif_p90_m=round(float(np.nanpercentile(dif, 90)), 2), sesgo_m=round(float(np.nanmedian(nas - cop)), 2))
            np.save(f"{d}/relieve_dif.npy", dif.astype("float32")); fuente = "Promedio de NASADEM (NASA, radar 2000) y Copernicus GLO-30 (radar 2011-2015), 30 m"
        elif ok1: dem, fuente = nas, "NASADEM 30 m (NASA)"
        elif ok2: dem, fuente = cop, "Copernicus DEM GLO-30"
        else: raise RuntimeError("No hay relieve disponible para esta zona")
        if np.isnan(dem).any(): dem[np.isnan(dem)] = np.nanmedian(dem)
        _guardar(f"{d}/dem.tif", dem.astype("float32"), G); G["fuentes"]["relieve"] = fuente; json.dump(info, open(f"{d}/relieve.json", "w"))
        for viejo in ("terreno.json", "terreno.npz", "cultivo.json", "cultivo.npz"):      # el relieve cambió: se recalcula lo que depende de él
            if os.path.exists(f"{d}/{viejo}"): os.remove(f"{d}/{viejo}")
        registro(f"relieve: {fuente}" + (f" · diferencia típica entre ambos {info['dif_mediana_m']} m" if ok1 and ok2 else ""))
    # ---- edificaciones: Overture Maps (OpenStreetMap + Microsoft + Google), huellas vectoriales
    if not os.path.exists(f"{d}/edificios.geojson"):
        import subprocess, sys
        b = G["bbox"]; exe = os.path.join(os.path.dirname(sys.executable), "overturemaps")
        try:
            subprocess.run([exe, "download", f"--bbox={b[0]},{b[1]},{b[2]},{b[3]}", "-f", "geojson", "--type=building", "-o", f"{d}/_edif.geojson"], check=True, timeout=180, capture_output=True)
            fc = json.load(open(f"{d}/_edif.geojson"))
            fc["features"] = [dict(type="Feature", geometry=f["geometry"], properties=dict(fuente=((f["properties"].get("sources") or [{}])[0].get("dataset")), altura=f["properties"].get("height"),
                               clase=f["properties"].get("class"))) for f in fc["features"] if f.get("geometry") and f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
            json.dump(fc, open(f"{d}/edificios.geojson", "w"))
            for x in ("_edif.geojson", "_edif.geojson.state"):
                if os.path.exists(f"{d}/{x}"): os.remove(f"{d}/{x}")
            G["fuentes"]["edificaciones"] = f"Overture Maps (OpenStreetMap + Microsoft + Google): {len(fc['features'])} huellas en la ventana"; registro(f"edificaciones: {len(fc['features'])}")
        except Exception as e:
            registro(f"edificaciones: no disponibles ({str(e)[:80]})")
    # ---- caminos, calles y vías: Overture Maps (transporte), en una ventana ampliada para saber por dónde se llega
    if not os.path.exists(f"{d}/caminos.geojson"):
        try:
            n = descargar_caminos(d, G); G["fuentes"]["caminos"] = f"Overture Maps, transporte (OpenStreetMap y otros): {n} tramos hasta 1,2 km alrededor"; registro(f"caminos: {n} tramos")
        except Exception as e:
            registro(f"caminos: no disponibles ({str(e)[:80]})")
    # ---- cobertura
    if not os.path.exists(f"{d}/worldcover.tif"):
        wc, nn = _mosaico(cat, "esa-worldcover", "map", G, Resampling.mode, dtype="uint8", vacio=0)
        _guardar(f"{d}/worldcover.tif", wc, G, nodata=0); G["fuentes"]["cobertura"] = "ESA WorldCover 10 m"; registro(f"cobertura: {nn} teselas")
    # ---- textura color real (Sentinel-2 10 m, escenas con menos nubes)
    if not solo_rapido and not os.path.exists(f"{d}/textura.tif"):   # no frena el 3D: la vista usa la imagen HD
        its = list(cat.search(collections=["sentinel-2-l2a"], bbox=G["bbox"], datetime=f"{anio_fin-1}-01-01/{anio_fin}-12-31",
                              query={"eo:cloud_cover": {"lt": 8}}).items())
        its.sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
        acum = []
        for it in its[:6]:
            try:
                with rasterio.open(it.assets["visual"].href) as src, WarpedVRT(src, crs=f"EPSG:{G['epsg']}", transform=T, width=G["ancho"],
                                                                               height=G["alto"], resampling=Resampling.bilinear) as v:
                    a = v.read([1, 2, 3]).astype("float32"); a[:, (a.sum(0) == 0)] = np.nan; acum.append(a)
            except Exception as e: registro(f"textura: escena omitida ({e})")
            if len(acum) >= 3 and np.isfinite(np.nanmedian(np.stack(acum), 0)).all(): break
        if acum:
            rgb = np.nanmedian(np.stack(acum), 0); rgb[np.isnan(rgb)] = 0
            _guardar(f"{d}/textura.tif", rgb.astype("uint8"), G); G["fuentes"]["imagen"] = f"Sentinel-2 L2A 10 m, mediana de {len(acum)} escenas {anio_fin-1}-{anio_fin}"
            registro(f"imagen: {len(acum)} escenas")
    G["fuentes"].setdefault("relieve", "NASADEM 30 m (NASA) / Copernicus GLO-30"); G["fuentes"].setdefault("cobertura", "ESA WorldCover 10 m")
    G["fuentes"].setdefault("imagen", "Sentinel-2 L2A 10 m")
    if solo_rapido:
        G["mascara_celdas"] = int((~geometry_mask([{"type": "Polygon", "coordinates": [G["poligono_utm"]]}], (G["alto"], G["ancho"]), T)).sum())
        json.dump(G, open(fmeta, "w")); return d, G
    # ---- NDVI HLS
    if not os.path.exists(f"{d}/hls_ndvi.npz"):
        esc = []
        for col, nir in (("hls2-l30", "B05"), ("hls2-s30", "B8A")):
            for it in cat.search(collections=[col], bbox=G["bbox"], datetime=f"{anio_ini}-01-01/{anio_fin}-12-31",
                                 query={"eo:cloud_cover": {"lt": 80}}).items(): esc.append((it, nir))
        registro(f"HLS: {len(esc)} escenas {anio_ini}-{anio_fin}")
        hechos = [0]
        def leer(arg):
            it, nir = arg
            hechos[0] += 1
            if cancelado and cancelado(): return None
            if progreso: progreso(hechos[0] / max(len(esc), 1))
            try:
                red, _ = _vrt_leer(it.assets["B04"].href, G, dtype="float32"); n, _ = _vrt_leer(it.assets[nir].href, G, dtype="float32")
                fm, _ = _vrt_leer(it.assets["Fmask"].href, G, resampling=Resampling.nearest, dtype="int32")
                malo = (fm & 0b00001110).astype(bool) | ((fm >> 5) & 1).astype(bool) | (red <= 0) | (n <= 0) | (fm == 255)
                nd = (n - red) / (n + red); nd[malo] = np.nan
                if np.isfinite(nd).mean() < 0.3: return None
                return it.datetime.strftime("%Y-%m-%d"), nd.astype("float16")
            except Exception: return None
        with ThreadPoolExecutor(16) as ex: res = [r for r in ex.map(leer, esc) if r]
        if cancelado and cancelado(): raise Cancelado()
        res.sort(key=lambda r: r[0])
        np.savez_compressed(f"{d}/hls_ndvi.npz", fechas=np.array([r[0] for r in res]), ndvi=np.stack([r[1] for r in res]) if res else np.zeros((0, G["alto"], G["ancho"]), "float16"))
        G["fuentes"]["vegetacion"] = f"HLS v2 30 m (NASA), {len(res)} escenas útiles {anio_ini}-{anio_fin}"; registro(f"HLS útiles: {len(res)}")
    # ---- suelo
    for var in ("clay", "sand", "soc"):
        fs = f"{d}/suelo_{var}.tif"
        if os.path.exists(fs): continue
        b = G["bbox"]; pad = 0.01
        url = (f"https://maps.isric.org/mapserv?map=/map/{var}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={var}_0-5cm_mean"
               f"&FORMAT=image/tiff&SUBSET=long({b[0]-pad},{b[2]+pad})&SUBSET=lat({b[1]-pad},{b[3]+pad})"
               "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326")
        try:
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.content[:4] in (b"II*\x00", b"MM\x00*"):
                open(f"{d}/_sg_{var}.tif", "wb").write(r.content)
                a, _ = _vrt_leer(f"{d}/_sg_{var}.tif", G, dtype="float32"); a[a <= 0] = np.nan
                _guardar(fs, a, G); os.remove(f"{d}/_sg_{var}.tif"); G["fuentes"]["suelo"] = "SoilGrids 2.0 250 m (ISRIC), 0-5 cm"
            else: registro(f"suelo {var}: sin respuesta válida ({r.status_code})")
        except Exception as e: registro(f"suelo {var}: {e}")
    # ---- clima
    if not os.path.exists(f"{d}/clima.json"):
        par = "T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,GWETTOP,GWETROOT,PRECTOTCORR,IMERG_PRECTOT"
        lonc, latc = G["centro"]
        import datetime
        fin = min(anio_fin, datetime.date.today().year - 1)
        url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={par}&community=AG&latitude={latc:.4f}&longitude={lonc:.4f}"
               f"&start={clima_ini}0101&end={fin}1231&format=JSON&time-standard=UTC")
        r = requests.get(url, timeout=600); r.raise_for_status(); json.dump(r.json(), open(f"{d}/clima.json", "w"))
        G["fuentes"]["clima"] = f"NASA POWER diario {clima_ini}-{fin} (MERRA-2, CERES) + GPM IMERG"; registro("clima: ok")
    # ---- máscara del polígono
    G["mascara_celdas"] = int((~geometry_mask([{"type": "Polygon", "coordinates": [G["poligono_utm"]]}], (G["alto"], G["ancho"]), T)).sum())
    json.dump(G, open(fmeta, "w"))
    return d, G
