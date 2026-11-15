"""Prospector · dimensiones del terreno: superficie, alturas, desniveles, pendientes, orientación y hacia dónde va el agua."""
import os, json, math, numpy as np, rasterio
from affine import Affine
from rasterio.features import geometry_mask
if not hasattr(np, "in1d"): np.in1d = np.isin
from pysheds.grid import Grid

ORIENT = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
WC_NOMBRES = {10: "bosque", 20: "matorral", 30: "pradera", 40: "cultivo", 50: "construido", 60: "suelo desnudo", 70: "nieve/hielo",
              80: "agua", 90: "humedal", 95: "manglar", 100: "musgo/liquen"}

APTITUD = {   # clase: (nombre, color)
    1: ("Cultivable (pendiente < 8 %)", "#2e9e5b"),
    2: ("Cultivable con conservación de suelo (8-15 %)", "#c9d64a"),
    3: ("No cultivable: pendiente > 15 %", "#e07b39"),
    4: ("No cultivable: cauce y franja de protección (10 m)", "#3b8fd9"),
    5: ("No cultivable hoy: bosque o matorral", "#1f5d3a"),
    6: ("No cultivable: agua o humedal", "#1c4f8f"),
    7: ("No cultivable: construcciones y 10 m alrededor", "#8a8a8a"),
    8: ("No cultivable: caminos y calles", "#d9d2c0"),
}

def analizar(d):
    G = json.load(open(f"{d}/meta.json")); T = Affine(*G["transform"]); res = G["res"]
    dem = rasterio.open(f"{d}/dem.tif").read(1).astype(float); wc = rasterio.open(f"{d}/worldcover.tif").read(1)
    masc = ~geometry_mask([{"type": "Polygon", "coordinates": [G["poligono_utm"]]}], dem.shape, T)
    if masc.sum() == 0:                       # polígono más chico que una celda
        r, c = ~T * (np.mean([p[0] for p in G["poligono_utm"]]), np.mean([p[1] for p in G["poligono_utm"]])); masc[int(c), int(r)] = True
    P = np.array(G["poligono_utm"]); x, y = P[:, 0], P[:, 1]
    area = abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1])) / 2
    perim = float(np.hypot(np.diff(x), np.diff(y)).sum())
    # pendiente y orientación (Horn 1981)
    # NASADEM guarda metros enteros: se suaviza (gaussiana de 1 celda nativa, 30 m) antes de derivar para evitar pendientes escalonadas
    from scipy.ndimage import gaussian_filter
    dem_s = gaussian_filter(dem, sigma=max(30.0 / res, 1.0))
    gy, gx = np.gradient(dem_s, res, res)               # gy: hacia abajo de la matriz (sur)
    pend = np.hypot(gx, gy); pend_pct = pend * 100; pend_gr = np.degrees(np.arctan(pend))
    asp = (np.degrees(np.arctan2(-gx, gy)) + 360) % 360  # dirección hacia donde baja la ladera (0 = N)
    z = dem_s[masc]
    # desnivel a lo largo del eje más largo del polígono
    dmax, par = 0, (0, 1)
    for i in range(len(P) - 1):
        dd = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1]); j = int(dd.argmax())
        if dd[j] > dmax: dmax, par = float(dd[j]), (i, j)
    def alt(pt):
        c, r = ~T * (pt[0], pt[1]); r = int(np.clip(r, 0, dem.shape[0] - 1)); c = int(np.clip(c, 0, dem.shape[1] - 1)); return float(dem[r, c])
    # flujo (D8) en toda la ventana: el margen permite ver de dónde llega y hacia dónde sale el agua
    grid = Grid.from_raster(f"{d}/dem.tif"); dg = grid.read_raster(f"{d}/dem.tif")
    dg = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dg)))
    dirmap = (64, 128, 1, 2, 4, 8, 16, 32); fdir = grid.flowdir(dg, dirmap=dirmap); acc = np.asarray(grid.accumulation(fdir, dirmap=dirmap))
    fdir = np.asarray(fdir)
    area_dren = acc * res * res
    twi = np.log((acc * res) / np.maximum(pend, 0.001))
    # ---- edificaciones (huellas vectoriales) -> grilla, con 10 m de resguardo
    edif = np.zeros(dem.shape, bool); n_dentro = n_fuera = 0; m2_dentro = 0.0
    fe = f"{d}/edificios.geojson"
    if os.path.exists(fe):
        from rasterio.features import rasterize
        from rasterio.warp import transform_geom
        feats = json.load(open(fe))["features"]; geoms = []
        for f in feats:
            try: g = transform_geom("EPSG:4326", f"EPSG:{G['epsg']}", f["geometry"])
            except Exception: continue
            geoms.append(g); an = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]; a = np.array(an)
            c, r = ~T * (a[:, 0].mean(), a[:, 1].mean()); dentro = 0 <= int(r) < dem.shape[0] and 0 <= int(c) < dem.shape[1] and masc[int(r), int(c)]
            if dentro: n_dentro += 1; m2_dentro += abs(np.dot(a[:-1, 0], a[1:, 1]) - np.dot(a[1:, 0], a[:-1, 1])) / 2
            else: n_fuera += 1
        if geoms: edif = rasterize([(g, 1) for g in geoms], out_shape=dem.shape, transform=T, all_touched=True).astype(bool)
    # ---- caminos: líneas -> grilla, con ancho según su clase
    cam = np.zeros(dem.shape, bool); m_cam = 0.0
    fc = f"{d}/caminos.geojson"
    if os.path.exists(fc):
        from rasterio.features import rasterize
        from rasterio.warp import transform_geom
        from scipy.ndimage import binary_dilation as _dil
        ANCHO = dict(motorway=14, trunk=12, primary=10, secondary=8, tertiary=8, residential=6, unclassified=6, service=5, living_street=6)
        por_ancho = {}
        for f in json.load(open(fc))["features"]:
            try: g = transform_geom("EPSG:4326", f"EPSG:{G['epsg']}", f["geometry"])
            except Exception: continue
            w = 8 if f["properties"].get("tipo") == "rail" else ANCHO.get(f["properties"].get("clase"), 4)
            por_ancho.setdefault(w, []).append(g)
        for w, gs in por_ancho.items():
            linea = rasterize([(g, 1) for g in gs], out_shape=dem.shape, transform=T, all_touched=True).astype(bool)
            extra = int(round((w / 2) / res))                 # una celda ya cubre `res` metros
            cam |= _dil(linea, iterations=extra) if extra > 0 else linea
        m_cam = float((cam & masc).sum() * res)              # largo aproximado dentro del terreno
    # ---- aptitud: qué es cultivable y qué no (criterios explícitos, ver APTITUD)
    from scipy.ndimage import binary_dilation
    cauce = area_dren >= 5e4                                   # cauce: drena 5 ha o más
    franja = binary_dilation(cauce, iterations=max(1, int(round(10.0 / res))))   # franja de protección de 10 m
    apt = np.ones(dem.shape, np.uint8)
    apt[pend_pct >= 8] = 2; apt[pend_pct >= 15] = 3; apt[franja] = 4
    apt[np.isin(wc, [10, 20])] = 5; apt[np.isin(wc, [70, 80, 90, 95])] = 6; apt[wc == 50] = 7
    apt[binary_dilation(edif, iterations=max(1, int(round(10.0 / res))))] = 7; apt[cam] = 8
    ha_c = res * res / 1e4
    apt_ha = {APTITUD[k][0]: round(float((apt[masc] == k).sum() * ha_c), 2) for k in APTITUD}
    # punto por donde sale el agua del polígono: celda de mayor acumulación dentro
    rr, cc = np.where(masc); k = int(np.argmax(acc[masc])); rs, cs = int(rr[k]), int(cc[k])
    xs, ys = T * (cs + 0.5, rs + 0.5)
    from rasterio.warp import transform as trp
    lo, la = trp(f"EPSG:{G['epsg']}", "EPSG:4326", [xs], [ys])
    clases = {WC_NOMBRES.get(int(v), str(int(v))): round(float((wc[masc] == v).mean() * 100), 1) for v in np.unique(wc[masc])}
    alrededor = {WC_NOMBRES.get(int(v), str(int(v))): round(float((wc[~masc] == v).mean() * 100), 1) for v in np.unique(wc[~masc])}
    hist = np.histogram(asp[masc], bins=np.arange(-22.5, 360, 45))[0].astype(float); a2 = asp[masc]; hist[0] += (a2 >= 337.5).sum()
    cl_p = [0, 2, 5, 10, 15, 30, 1e9]; nom_p = ["0-2 % plano", "2-5 % suave", "5-10 % moderado", "10-15 % fuerte", "15-30 % muy fuerte", ">30 % escarpado"]
    pp = pend_pct[masc]
    out = dict(
        superficie_m2=round(area, 1), superficie_ha=round(area / 1e4, 3), perimetro_m=round(perim, 1),
        largo_maximo_m=round(dmax, 1), desnivel_eje_largo_m=round(abs(alt(P[par[0]]) - alt(P[par[1]])), 1),
        altitud_min_m=round(float(z.min()), 1), altitud_media_m=round(float(z.mean()), 1), altitud_max_m=round(float(z.max()), 1),
        desnivel_total_m=round(float(z.max() - z.min()), 1),
        pendiente_media_pct=round(float(pp.mean()), 1), pendiente_p90_pct=round(float(np.percentile(pp, 90)), 1), pendiente_max_pct=round(float(pp.max()), 1),
        pendiente_media_grados=round(float(pend_gr[masc].mean()), 1),
        clases_pendiente_pct={n: round(float(((pp >= a) & (pp < b)).mean() * 100), 1) for n, a, b in zip(nom_p, cl_p[:-1], cl_p[1:])},
        orientacion_dominante=ORIENT[int(hist.argmax())], orientacion_pct={o: round(float(v / hist.sum() * 100), 1) for o, v in zip(ORIENT, hist)},
        salida_agua=dict(lon=round(lo[0], 6), lat=round(la[0], 6), altitud_m=round(float(dem[rs, cs]), 1),
                         area_que_drena_por_ahi_ha=round(float(area_dren[rs, cs] / 1e4), 2)),
        agua_que_entra_desde_fuera_ha=round(float(max(area_dren[rs, cs] - masc.sum() * res * res, 0) / 1e4), 2),
        edificaciones=dict(dentro=n_dentro, superficie_m2=round(m2_dentro), alrededor=n_fuera), caminos_dentro_m=round(m_cam),
        relieve=(json.load(open(f"{d}/relieve.json")) if os.path.exists(f"{d}/relieve.json") else {}),
        margen_altura_m=(round(float(np.nanmedian(np.load(f"{d}/relieve_dif.npy")[masc])), 1) if os.path.exists(f"{d}/relieve_dif.npy") else None),
        aptitud_ha=apt_ha, cultivable_ha=round(float(np.isin(apt[masc], [1, 2]).sum() * ha_c), 2),
        cultivable_pct=round(float(np.isin(apt[masc], [1, 2]).mean() * 100), 1),
        cobertura_dentro_pct=clases, cobertura_alrededor_pct=alrededor,
        resolucion_grilla_m=res, celdas=int(masc.sum()), fuentes=G.get("fuentes", {}))
    np.savez_compressed(f"{d}/terreno.npz", mascara=masc, pendiente_pct=pend_pct.astype("float32"), orientacion=asp.astype("float32"),
                        acumulacion=acc.astype("float32"), aptitud=apt, edificios=edif, caminos=cam, agua=np.isin(wc, [70, 80, 90, 95]), direccion=fdir.astype("int16"), twi=twi.astype("float32"))
    json.dump(out, open(f"{d}/terreno.json", "w"), indent=1, ensure_ascii=False)
    return out
