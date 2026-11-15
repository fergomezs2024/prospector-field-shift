"""Prospector · ¿se puede cultivar aquí?  Se aprende de los terrenos que HOY se cultivan alrededor.

Idea: en un radio de 7,5 km se identifican los potreros cultivados con tres evidencias independientes:
  (1) documentado: ESA WorldCover 2021 (clase cultivo)      (2) documentado: Impact Observatory LULC anual (clase cultivos)
  (3) observado:   ciclo anual de verdor en HLS (NASA, 30 m): el NDVI sube y baja al menos 0,25 en el año.
Con esos potreros (positivos) y con el suelo natural no cultivado (negativos) se entrena un clasificador
(gradient boosting) sobre el relieve y el suelo: pendiente, altura sobre el cauce (HAND), distancia al cauce,
índice topográfico de humedad, curvatura, posición en la ladera, orientación, arcilla y arena.
Se valida con validación cruzada ESPACIAL (bloques de 3 km) y se aplica al terreno elegido.
La probabilidad se lee como: "de cada 10 terrenos como este en la zona, N están cultivados".
En EE. UU. se agrega el registro USDA CDL con el nombre de los cultivos vecinos.
"""
import os, json, math, warnings, numpy as np, rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform as tr_pts, reproject
from rasterio.features import geometry_mask
from concurrent.futures import ThreadPoolExecutor
from scipy.ndimage import gaussian_filter, distance_transform_edt, laplace, binary_dilation
import planetary_computer as pc
from pystac_client import Client
if not hasattr(np, "in1d"): np.in1d = np.isin
from pysheds.grid import Grid
from . import datos

VARS = ["pendiente", "hand", "dist_cauce", "twi", "curvatura", "posicion", "norte", "este", "arcilla", "arena"]
EXPLICA = {"pendiente": ("la pendiente", "%", 1), "hand": ("la altura sobre el cauce más cercano", "m", 0),
           "dist_cauce": ("la distancia al cauce", "m", 0), "arcilla": ("la arcilla del suelo", "%", 0)}
CLASES = {1: ("Sí se puede cultivar", "#2e9e5b"), 2: ("Se puede con cuidado: pendiente moderada", "#e3c23a"), 3: ("No conviene: pendiente fuerte", "#c8553d"),
          4: ("Cauce y su franja: no se cultiva", "#3b8fd9"), 5: ("Agua, construcciones o caminos", "#7d7d7d"),
          6: ("Terreno apto, pero hoy con árboles o matorral", "#9b7fd1"), 7: ("Ya plantado: viña o frutales", "#d9822b")}

def plantado(d, G):
    """Celdas que el mapa de uso del suelo marca como viña, huerto frutal o vivero, y qué tipos son. Si no hay dato, todo falso."""
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom
    sh = (G["alto"], G["ancho"]); out = np.zeros(sh, bool); tipos = set(); f = f"{d}/uso.geojson"
    if not os.path.exists(f):
        try: datos.descargar_uso(d, G)
        except Exception: return out, []
    gs = []
    for x in json.load(open(f))["features"]:
        try: gs.append(transform_geom("EPSG:4326", f"EPSG:{G['epsg']}", x["geometry"])); tipos.add(datos.PLANTADO.get(x["properties"].get("clase"), "plantación"))
        except Exception: continue
    if gs: out = rasterize([(g, 1) for g in gs], out_shape=sh, transform=Affine(*G["transform"]), all_touched=False).astype(bool)
    return out, sorted(tipos)
CDL = {1: "maíz", 2: "algodón", 3: "arroz", 4: "sorgo", 5: "soya", 6: "girasol", 10: "maní", 12: "maíz dulce", 21: "cebada", 22: "trigo candeal",
       23: "trigo de primavera", 24: "trigo de invierno", 26: "trigo de invierno/soya", 27: "centeno", 28: "avena", 31: "canola", 36: "alfalfa",
       37: "otros henos", 41: "remolacha", 42: "porotos secos", 43: "papas", 53: "arvejas", 61: "barbecho", 69: "uva", 75: "almendros", 76: "nogales"}

def _grilla_region(G, radio):
    P = np.array(G["poligono_utm"]); res = 30.0
    cx, cy = round(P[:, 0].mean() / 2500) * 2500, round(P[:, 1].mean() / 2500) * 2500   # centro ajustado a una retícula de 2,5 km: terrenos vecinos comparten zona
    x0, y1 = math.floor((cx - radio) / res) * res, math.ceil((cy + radio) / res) * res; n = int(2 * radio / res)
    bx, by = tr_pts(f"EPSG:{G['epsg']}", "EPSG:4326", [x0, x0 + n * res, x0, x0 + n * res], [y1, y1, y1 - n * res, y1 - n * res])
    return dict(epsg=G["epsg"], res=res, ancho=n, alto=n, transform=list(from_origin(x0, y1, res, res))[:6], bbox=[min(bx), min(by), max(bx), max(by)])

def _lulc_reciente(cat, R):
    its = list(cat.search(collections=["io-lulc-annual-v02"], bbox=R["bbox"]).items())
    if not its: return None, None
    ult = max(i.properties["start_datetime"] for i in its); out = np.zeros((R["alto"], R["ancho"]), "uint8")
    for it in [i for i in its if i.properties["start_datetime"] == ult]:
        a, _ = datos._vrt_leer(it.assets["data"].href, R, resampling=Resampling.mode, dtype="uint8"); out[(out == 0) & (a > 0)] = a[(out == 0) & (a > 0)]
    return out, ult[:4]

def _cdl(cat, R):
    its = [i for i in cat.search(collections=["usda-cdl"], bbox=R["bbox"]).items() if "cropland" in i.assets]
    if not its: return None, None
    ult = max(i.properties["start_datetime"] for i in its); out = np.zeros((R["alto"], R["ancho"]), "uint8")
    for it in [i for i in its if i.properties["start_datetime"] == ult]:
        a, _ = datos._vrt_leer(it.assets["cropland"].href, R, resampling=Resampling.nearest, dtype="uint8"); out[(out == 0) & (a > 0)] = a[(out == 0) & (a > 0)]
    return out, ult[:4]

def _hls_estacional(cat, R, anio_fin, registro, progreso=None, cancelado=None):
    """Pocas escenas limpias por mes (2 años) -> amplitud anual de NDVI y mes del máximo."""
    grupos = {}
    for col, nir in (("hls2-l30", "B05"), ("hls2-s30", "B8A")):
        for it in cat.search(collections=[col], bbox=R["bbox"], datetime=f"{anio_fin-1}-01-01/{anio_fin}-12-31", query={"eo:cloud_cover": {"lt": 30}}).items():
            grupos.setdefault((it.datetime.year, it.datetime.month), []).append((it.properties.get("eo:cloud_cover", 100), it, nir))
    esc = [(it, nir) for k in grupos for _, it, nir in sorted(grupos[k], key=lambda x: x[0])[:2]]
    R2 = dict(R, res=R["res"] * 2, ancho=R["ancho"] // 2, alto=R["alto"] // 2, transform=[R["transform"][0] * 2, 0.0, R["transform"][2], 0.0, R["transform"][4] * 2, R["transform"][5]])   # se lee a 60 m: 4 veces menos datos
    hechos = [0]
    registro(f"región: {len(esc)} escenas HLS limpias de {anio_fin-1}-{anio_fin}")
    def leer(arg):
        it, nir = arg
        hechos[0] += 1
        if cancelado and cancelado(): return None
        if progreso: progreso(hechos[0] / max(len(esc), 1))
        try:
            red, _ = datos._vrt_leer(it.assets["B04"].href, R2, dtype="float32"); n, _ = datos._vrt_leer(it.assets[nir].href, R2, dtype="float32")
            fm, _ = datos._vrt_leer(it.assets["Fmask"].href, R2, resampling=Resampling.nearest, dtype="int32")
            malo = (fm & 0b00001110).astype(bool) | ((fm >> 5) & 1).astype(bool) | (red <= 0) | (n <= 0) | (fm == 255)
            with np.errstate(all="ignore"): nd = (n - red) / (n + red)
            nd[malo] = np.nan; return it.datetime.month, nd.astype("float16")
        except Exception: return None
    with ThreadPoolExecutor(16) as ex: res = [r for r in ex.map(leer, esc) if r]
    if cancelado and cancelado(): raise datos.Cancelado()
    meses = np.array([r[0] for r in res]); st = np.stack([r[1] for r in res]).astype("float32")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        men = np.stack([np.nanmedian(st[meses == m], 0) if (meses == m).any() else np.full(st.shape[1:], np.nan) for m in range(1, 13)])
        p10, p90 = np.nanpercentile(st, 10, 0), np.nanpercentile(st, 90, 0)
        pico = np.where(np.isfinite(men).any(0), np.nanargmax(np.where(np.isfinite(men), men, -9), 0) + 1, 0)
    al = lambda a: np.repeat(np.repeat(a, 2, 0), 2, 1)[:R["alto"], :R["ancho"]]
    return al(p10), al(p90), al(pico.astype("uint8")), len(res)

def _estacion(mes, sur):
    m = ((mes + 6 - 1) % 12) + 1 if sur else mes          # equivalente en el hemisferio norte
    return "invierno-primavera" if m in (2, 3, 4, 5) else ("verano" if m in (6, 7, 8, 9) else "otoño")

def _zona(G, R, registro, progreso, anio_fin, cancelado=None):
    """Datos y modelo de la zona (15 x 15 km). Se guardan por zona: un segundo terreno cercano los reutiliza."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import roc_auc_score, balanced_accuracy_score
    pg = progreso or (lambda f: None)
    rd = os.path.join(datos.RAIZ, "_regiones", f"{R['epsg']}_{int(R['transform'][2])}_{int(R['transform'][5])}"); os.makedirs(rd, exist_ok=True)
    if os.path.exists(f"{rd}/modelo.npz") and os.path.exists(f"{rd}/modelo.json"):
        registro("zona ya conocida: se reutiliza lo aprendido"); pg(1.0)
        z = np.load(f"{rd}/modelo.npz"); return {k: z[k] for k in z.files}, json.load(open(f"{rd}/modelo.json"))
    TR = Affine(*R["transform"]); res = R["res"]; cat = Client.open(datos.STAC, modifier=pc.sign_inplace, timeout=(10, 40))
    fr = f"{rd}/region_datos.npz"
    if os.path.exists(fr):
        z = np.load(fr); dem, wc, io, p10, p90, pico, clay, sand = (z[k] for k in ("dem", "wc", "io", "p10", "p90", "pico", "clay", "sand")); cdl = z["cdl"] if "cdl" in z.files else None; meta_r = json.loads(str(z["meta"]))
    else:
        registro("zona: relieve y mapas de cultivo de 15 × 15 km alrededor…")
        dem, _ = datos._mosaico(cat, "nasadem", "elevation", R, Resampling.bilinear)
        if np.isnan(dem).mean() > 0.2: dem, _ = datos._mosaico(cat, "cop-dem-glo-30", "data", R, Resampling.bilinear)
        dem[np.isnan(dem)] = np.nanmedian(dem); pg(0.06)
        wc, _ = datos._mosaico(cat, "esa-worldcover", "map", R, Resampling.mode, dtype="uint8", vacio=0); pg(0.12)
        io, anio_io = _lulc_reciente(cat, R)
        if io is None: io, anio_io = np.zeros_like(wc), None
        cdl, anio_cdl = _cdl(cat, R); pg(0.2)
        p10, p90, pico, nesc = _hls_estacional(cat, R, anio_fin, registro, lambda f: pg(0.2 + 0.6 * f), cancelado)
        clay = np.full(dem.shape, np.nan, "float32"); sand = clay.copy()
        import requests
        for var, dst in (("clay", clay), ("sand", sand)):
            try:
                b = R["bbox"]; q = requests.get(f"https://maps.isric.org/mapserv?map=/map/{var}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={var}_0-5cm_mean"
                    f"&FORMAT=image/tiff&SUBSET=long({b[0]-.01},{b[2]+.01})&SUBSET=lat({b[1]-.01},{b[3]+.01})&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326"
                    "&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326", timeout=120)
                if q.content[:4] in (b"II*\x00", b"MM\x00*"):
                    open(f"{rd}/_{var}.tif", "wb").write(q.content); a, _ = datos._vrt_leer(f"{rd}/_{var}.tif", R, dtype="float32"); a[a <= 0] = np.nan; dst[:] = a / 10; os.remove(f"{rd}/_{var}.tif")
            except Exception as e: registro(f"zona: suelo {var} no disponible ({e})")
        meta_r = dict(anio_io=anio_io, anio_cdl=anio_cdl, escenas=nesc)
        extra = {"cdl": cdl} if cdl is not None else {}
        np.savez_compressed(fr, dem=dem.astype("float32"), wc=wc, io=io, p10=p10.astype("float32"), p90=p90.astype("float32"), pico=pico, clay=clay, sand=sand, meta=json.dumps(meta_r), **extra)
    pg(0.82); registro("zona: calculando relieve, cauces y altura sobre el cauce…")
    dem_s = gaussian_filter(dem.astype(float), 1.0); gy, gx = np.gradient(dem_s, res, res); pend = np.hypot(gx, gy); asp = np.arctan2(-gx, gy)
    with rasterio.open(f"{rd}/_dem.tif", "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1, dtype="float32", crs=f"EPSG:{R['epsg']}", transform=TR) as ds: ds.write(dem.astype("float32"), 1)
    grid = Grid.from_raster(f"{rd}/_dem.tif"); dg = grid.read_raster(f"{rd}/_dem.tif"); dg = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dg)))
    dm = (64, 128, 1, 2, 4, 8, 16, 32); fdir = grid.flowdir(dg, dirmap=dm); acc = grid.accumulation(fdir, dirmap=dm)
    cauce = np.asarray(acc) * res * res >= 5e4
    hand = np.asarray(grid.compute_hand(fdir, dg, grid.view(acc) * res * res >= 5e4, dirmap=dm)).astype(float); hand[~np.isfinite(hand)] = np.nanmedian(hand[np.isfinite(hand)]); hand = np.clip(hand, 0, None)
    os.remove(f"{rd}/_dem.tif"); pg(0.88)
    F = dict(pendiente=pend * 100, hand=hand, dist_cauce=distance_transform_edt(~cauce) * res, twi=np.log((np.asarray(acc) * res) / np.maximum(pend, 0.001)),
             curvatura=laplace(dem_s) / res ** 2 * 1e4, posicion=dem_s - gaussian_filter(dem.astype(float), 500 / res), norte=np.cos(asp) * np.minimum(pend * 10, 1),
             este=np.sin(asp) * np.minimum(pend * 10, 1), arcilla=np.where(np.isnan(clay), np.nanmedian(clay) if np.isfinite(clay).any() else 25, clay),
             arena=np.where(np.isnan(sand), np.nanmedian(sand) if np.isfinite(sand).any() else 40, sand))
    X = np.stack([F[v] for v in VARS], -1).reshape(-1, len(VARS)).astype("float32")
    amp = p90 - p10; mapa_cult = (wc == 40) | (io == 5)
    pos = mapa_cult & (amp >= 0.25); nat = np.isin(wc, [10, 20, 30, 60]) & ~(io == 5) & ~np.isin(io, [1, 7]); neg = nat & ~pos
    y = np.where(pos, 1, np.where(neg, 0, -1)).ravel(); ok = y >= 0
    rr, cc = np.indices(dem.shape); grupos = ((rr // 100) * 100 + cc // 100).ravel()
    ha = res * res / 1e4; npos, nneg = int((y == 1).sum()), int((y == 0).sum())
    registro(f"zona: {npos * ha:,.0f} ha cultivadas observadas y {nneg * ha:,.0f} ha naturales para aprender")
    if npos < 300 or nneg < 300:
        st = dict(disponible=False, motivo=f"En 7,5 km a la redonda casi no hay {'potreros cultivados' if npos < 300 else 'terreno natural'} para comparar.")
        np.savez_compressed(f"{rd}/modelo.npz", io=io); json.dump(st, open(f"{rd}/modelo.json", "w"), ensure_ascii=False); pg(1.0); return {"io": io}, st
    rng = np.random.default_rng(0); idx = np.where(ok)[0]
    if len(idx) > 120000: idx = rng.choice(idx, 120000, replace=False)
    aucs, bas = [], []; mk = lambda: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=24, l2_regularization=1.0)
    for tr_i, te_i in GroupKFold(5).split(X[idx], y[idx], grupos[idx]):
        if len(np.unique(y[idx][te_i])) < 2: continue
        pr = mk().fit(X[idx][tr_i], y[idx][tr_i]).predict_proba(X[idx][te_i])[:, 1]; aucs.append(roc_auc_score(y[idx][te_i], pr)); bas.append(balanced_accuracy_score(y[idx][te_i], pr >= 0.5))
    prob = mk().fit(X[idx], y[idx]).predict_proba(X)[:, 1].reshape(dem.shape).astype("float32"); pg(0.97)
    registro(f"zona: modelo validado por bloques · AUC {np.mean(aucs):.2f} · acierto equilibrado {np.mean(bas)*100:.0f} %")
    sur = G["centro"][1] < 0; vec = {}
    for e in ("invierno-primavera", "verano", "otoño"):
        vec[e] = round(float((pos & np.isin(pico, [m for m in range(1, 13) if _estacion(m, sur) == e])).sum() * ha), 0)
    nombres_cdl = None
    if cdl is not None and (cdl > 0).any():
        v, c = np.unique(cdl[pos & (cdl > 0)], return_counts=True); o = np.argsort(c)[::-1][:6]
        nombres_cdl = [dict(cultivo=CDL.get(int(v[i]), f"código {int(v[i])}"), ha=round(float(c[i] * ha), 0)) for i in o if int(v[i]) in CDL]
    st = dict(disponible=True, npos=npos, nneg=nneg, auc=round(float(np.mean(aucs)), 3), acierto=round(float(np.mean(bas) * 100), 1),
              umbral_si=round(float(np.percentile(prob[pos], 10)), 3), umbral_no=round(float(np.percentile(prob[pos], 2)), 3),
              percentiles={v: [round(float(q), 2) for q in np.percentile(F[v][pos], [5, 25, 50, 75, 95])] for v in VARS},
              vecinos_estacion=vec, vecinos_cdl=nombres_cdl, meta=meta_r)
    arr = dict(prob=prob, io=io, **{f"f_{v}": F[v].astype("float32") for v in EXPLICA})
    np.savez_compressed(f"{rd}/modelo.npz", **arr); json.dump(st, open(f"{rd}/modelo.json", "w"), ensure_ascii=False); pg(1.0)
    return arr, st

def analizar_region(d, registro=print, radio=7500.0, anio_fin=2025, progreso=None, cancelado=None):
    """¿Dónde se puede cultivar dentro del terreno?  El sí/no sale de razones FÍSICAS del propio lugar (pendiente, cauces,
    árboles, agua, construcciones, caminos). La zona (potreros vecinos) y el mundo (lugares de clima y suelo parecidos)
    se usan como contexto, no como motivo para negar."""
    from . import mundo
    G = json.load(open(f"{d}/meta.json")); R = _grilla_region(G, radio); TR = Affine(*R["transform"]); res = R["res"]; ha = res * res / 1e4
    A, st = _zona(G, R, registro, progreso, anio_fin, cancelado)
    T = Affine(*G["transform"]); sh = (G["alto"], G["ancho"])
    def al_terreno(a, metodo=Resampling.bilinear):
        out = np.full(sh, np.nan, "float32")
        reproject(a.astype("float32"), out, src_transform=TR, src_crs=f"EPSG:{R['epsg']}", dst_transform=T, dst_crs=f"EPSG:{G['epsg']}", resampling=metodo, src_nodata=np.nan, dst_nodata=np.nan)
        return out
    zona_ok = bool(st.get("disponible"))
    pt = al_terreno(A["prob"]) if zona_ok else np.full(sh, np.nan, "float32")
    ft = {v: al_terreno(A[f"f_{v}"]) for v in EXPLICA} if zona_ok else {}
    t = np.load(f"{d}/terreno.npz"); masc = t["mascara"]; wct = rasterio.open(f"{d}/worldcover.tif").read(1); pend = t["pendiente_pct"]
    lenoso = np.isin(wct, [10, 20])
    if "io" in A: lenoso |= al_terreno(A["io"].astype("float32"), Resampling.nearest) == 2
    fh = f"{d}/hls_ndvi.npz"
    if os.path.exists(fh):                                     # con historial propio: leñoso = verde todo el año
        zz = np.load(fh)
        if len(zz["fechas"]) > 20:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore"); q10 = np.nanpercentile(zz["ndvi"].astype("float32"), 10, 0)
            lenoso = (lenoso | (q10 >= 0.45)) & ~((wct == 40) & (q10 < 0.35))
    it10 = max(1, int(round(10.0 / G["res"])))
    franja = binary_dilation(t["acumulacion"] * G["res"] ** 2 >= 5e4, iterations=it10)
    edif = binary_dilation(t["edificios"], iterations=it10) if "edificios" in t.files else np.zeros(sh, bool)
    cam = t["caminos"] if "caminos" in t.files else np.zeros(sh, bool)
    agua = np.isin(wct, [70, 80, 90, 95]); constr = (wct == 50) | edif
    cl = np.where(pend < 8, 1, np.where(pend < 15, 2, 3)).astype("uint8")
    cl[(cl <= 2) & lenoso] = 6
    plant, tipos_plant = plantado(d, G); cl[np.isin(cl, (1, 2, 6)) & plant] = 7        # una viña o un huerto no es bosque: es un cultivo que ya está
    cl[franja] = 4; cl[agua | constr | cam] = 5
    motivo = np.zeros(sh, "uint8"); motivo[agua] = 1; motivo[constr] = 2; motivo[cam] = 3
    hat = G["res"] ** 2 / 1e4
    try: mun = mundo.consultar(G["centro"][0], G["centro"][1]) if mundo.disponible() else dict(disponible=False, motivo="Falta la tabla mundial de lugares parecidos (se descarga una vez con «python -m prospector.obtener_datos»).")
    except Exception as e: mun = dict(disponible=False, motivo=f"No se pudo consultar la tabla mundial ({e}).")
    resumen = dict(disponible=True, ha={CLASES[k][0]: round(float((cl[masc] == k).sum() * hat), 2) for k in CLASES}, total_ha=round(float(masc.sum() * hat), 2),
                   criterios=dict(pendiente_si="< 8 %", pendiente_cuidado="8-15 %", pendiente_no="> 15 %", cauce="drena ≥ 5 ha, franja de 10 m", resguardo_construcciones="10 m"),
                   plantado=dict(ha=round(float((cl[masc] == 7).sum() * hat), 2), tipos=tipos_plant, fuente="Overture Maps, uso del suelo (OpenStreetMap)"),
                   mundo=mun, leyenda=[dict(clase=k, nombre=n, color=c) for k, (n, c) in CLASES.items()],
                   zona=(dict(disponible=True, radio_km=radio / 1000, cultivadas_cerca_ha=round(st["npos"] * ha), naturales_cerca_ha=round(st["nneg"] * ha), auc=st["auc"], acierto=st["acierto"],
                              tasa_base=round(st["npos"] / (st["npos"] + st["nneg"]), 3), percentiles=st["percentiles"], vecinos_estacion=st["vecinos_estacion"], vecinos_cdl=st["vecinos_cdl"],
                              fuentes=dict(worldcover="ESA WorldCover 2021", lulc=f"Impact Observatory LULC {st['meta'].get('anio_io')}", hls=f"NASA HLS, {st['meta'].get('escenas')} escenas",
                                           cdl=(f"USDA Cropland Data Layer {st['meta'].get('anio_cdl')}" if st["meta"].get("anio_cdl") else None)))
                         if zona_ok else dict(disponible=False, motivo=st.get("motivo"))))
    np.savez_compressed(f"{d}/cultivo.npz", clase=cl, prob=pt, motivo=motivo, **{f"f_{v}": ft[v] for v in ft})
    json.dump(resumen, open(f"{d}/cultivo.json", "w"), ensure_ascii=False, indent=1)
    return resumen

def explicar_punto(d, col, fila):
    """Explicación de un punto en dos lenguajes: `texto` (natural) y `tecnico` (con números y fuentes)."""
    r = json.load(open(f"{d}/cultivo.json")); z = np.load(f"{d}/cultivo.npz"); t = np.load(f"{d}/terreno.npz"); G = json.load(open(f"{d}/meta.json"))
    fila = int(np.clip(fila, 0, z["clase"].shape[0] - 1)); col = int(np.clip(col, 0, z["clase"].shape[1] - 1))
    k = int(z["clase"][fila, col]); p = float(t["pendiente_pct"][fila, col]); mot = int(z["motivo"][fila, col]) if "motivo" in z.files else 0
    dren = float(t["acumulacion"][fila, col]) * G["res"] ** 2 / 1e4
    plano = "es casi plano" if p < 2 else ("tiene una pendiente suave" if p < 5 else "tiene una pendiente moderada")
    if k == 1: tx = f"Aquí sí se puede cultivar. El terreno {plano} ({p:.0f} %), no corre agua por este punto y no hay árboles, construcciones ni caminos."
    elif k == 2: tx = (f"Aquí se puede cultivar, pero con cuidado. La pendiente es de {p:.0f} %: con esa inclinación la lluvia puede llevarse la tierra. "
                       "Conviene sembrar siguiendo el contorno de la ladera y no dejar el suelo desnudo.")
    elif k == 3: tx = f"Aquí no conviene cultivar. La pendiente es fuerte ({p:.0f} %): las máquinas trabajan mal y la lluvia se lleva el suelo. Sirve mejor para pradera o árboles."
    elif k == 4: tx = "Por aquí corre el agua cuando llueve. No se cultiva: se deja una franja con vegetación a cada lado para proteger el suelo y el agua."
    elif k == 5: tx = {1: "Aquí hay agua o un humedal.", 2: "Aquí hay una construcción (o está a menos de 10 metros de una).", 3: "Por aquí pasa un camino o una calle."}.get(mot, "Aquí hay agua, una construcción o un camino.")
    elif k == 7: tx = ("El mapa de uso del suelo marca aquí " + " o ".join(r.get("plantado", {}).get("tipos") or ["una plantación"]) + ". Ya es un cultivo plantado: no se propone despejarlo ni sembrar encima. "
                       "Esta herramienta no simula uvas ni frutales; esta parte se deja como está.")
    else: tx = f"El terreno en sí sirve para cultivar ({p:.0f} % de pendiente), pero hoy tiene árboles o matorral. Despejarlo puede requerir permiso."
    tec = [f"Clase {k}: {CLASES[k][0]}", f"Pendiente: {p:.1f} % (umbrales: <8 sí · 8-15 con cuidado · >15 no; relieve de 30 m suavizado)",
           f"Área que drena por este punto: {dren:.2f} ha (cauce si ≥ 5 ha; franja de 10 m)", f"Índice topográfico de humedad: {float(t['twi'][fila, col]):.1f}"]
    zo = r.get("zona", {})
    if zo.get("disponible") and np.isfinite(z["prob"][fila, col]):
        pz = float(z["prob"][fila, col]); tec.append(f"Zona ({zo['radio_km']:.1f} km): terrenos con este relieve y suelo están cultivados en {pz*100:.0f} % de los casos (tasa de la zona {zo['tasa_base']*100:.0f} %; modelo AUC {zo['auc']:.2f})")
        for v, (nom, uni, dec) in EXPLICA.items():
            if f"f_{v}" in z.files and v != "pendiente": q = zo["percentiles"][v]; tec.append(f"{nom[0].upper() + nom[1:]}: {float(z[f'f_{v}'][fila, col]):.{dec}f} {uni} (potreros cultivados de la zona, percentiles 5-95: {q[0]:.{dec}f}-{q[4]:.{dec}f})")
    return dict(clase=k, titulo=CLASES[k][0], color=CLASES[k][1], texto=tx, detalles=[], tecnico=tec)
