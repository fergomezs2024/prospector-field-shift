"""Marte y la Luna: dónde y cómo instalar una estación en una zona, con criterios publicados de ingeniería de sitios.

Relieve (se lee en línea, solo la ventana pedida):
  Marte  MOLA MEGDR, 463 m por celda (NASA Mars Global Surveyor; mosaico de USGS Astrogeology)
  Luna   LOLA LDEM, 118 m por celda (NASA Lunar Reconnaissance Orbiter; mosaico de USGS Astrogeology)

No se aplana la zona. Se hace lo que hacen los estudios de sitios:
  1. Se clasifica cada celda por su pendiente con los límites que usaron misiones reales.
  2. Se elige el lugar naturalmente más parejo para la plataforma de aterrizaje, del tamaño que proponen los estudios.
  3. Se calcula cuánto material habría que mover para dejar ESA plataforma a nivel, y cuánto tardaría un excavador robótico real.
  4. Se ubica la zona de la estación a la distancia que piden los estudios y se traza el acceso con la pendiente que admite la carga.
Cada límite lleva su fuente (ver CRITERIOS).

Es geometría del terreno a la escala del relieve disponible. NO evalúa radiación, temperatura, polvo, iluminación, agua, hielo ni energía,
y no ve rocas ni cráteres más chicos que una celda. Preparar un sitio no es terraformar: no cambia la atmósfera ni el clima.
"""
import os, io, json, math, base64, hashlib
import numpy as np, rasterio
from rasterio.windows import Window
from . import datos

VERSION = 4
NTRS = "https://ntrs.nasa.gov/api/citations/"
CUERPOS = {
    "marte": dict(nombre="Marte", radio=3396190.0, url="https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif", escala=1.0, max_km=400.0,
                  fuente="MOLA MEGDR 463 m (NASA Mars Global Surveyor; USGS Astrogeology)", tinte=(196, 124, 86),
                  foto="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{r}/{c}.jpg", foto_z=7, foto_nombre="mosaico en color Viking MDIM 2.1, 232 m (NASA / USGS, vía NASA Mars Trek)",
                  pend_ok=5.0, pend_tope=15.0, plataforma_m=100.0, densidad=1200.0, excav_kg_dia=2700.0, dist_estacion_m=1000.0, pend_acceso=5.0, altura_max=2000.0, lat_max=50.0),
    "luna": dict(nombre="la Luna", radio=1737400.0, url="https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif", escala=0.5, max_km=120.0,
                 fuente="LOLA LDEM 118 m (NASA Lunar Reconnaissance Orbiter; USGS Astrogeology)", tinte=(176, 176, 172),
                 foto="https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{r}/{c}.jpg", foto_z=8, foto_nombre="mosaico LRO WAC, 100 m (NASA / GSFC / ASU, vía NASA Moon Trek)",
                 pend_ok=6.0, pend_tope=10.0, plataforma_m=54.0, densidad=1500.0, excav_kg_dia=2700.0, dist_estacion_m=None, pend_acceso=5.0, altura_max=None, lat_max=None),
}
CRITERIOS = {
    "marte": [
        dict(que="Pendiente para aterrizar: hasta 5° medida en tramos de 200 a 500 m, que es la escala de este relieve", fuente="Guía de ingeniería de sitios de Mars Science Laboratory, JPL", url="https://marsoweb.nas.nasa.gov/landingsites/msl/memoranda/MSL_Eng_User_Guide_v2.pdf"),
        dict(que="Pendiente que descarta un sitio: 15° (límite de InSight a 84 m y de MSL a 20-40 m)", fuente="Golombek et al. 2017, selección del sitio de InSight", url="https://repository.si.edu/server/api/core/bitstreams/7ee1f701-fc36-44e6-8989-91f342ec00b5/content"),
        dict(que="Altura máxima +2 km y latitud entre 50° S y 50° N para una zona de exploración humana (criterios preliminares)", fuente="Bussey y Hoffman, NASA, taller de zonas de exploración humana en Marte", url=NTRS + "20160002370/downloads/20160002370.pdf"),
        dict(que="Plataforma de aterrizaje de 100 m de diámetro; la infraestructura queda a salvo de los escombros del motor a más de 1.000 m", fuente="Bussey y Hoffman, NASA", url=NTRS + "20160002370/downloads/20160002370.pdf"),
        dict(que="Un excavador robótico RASSOR 2.0 mueve al menos 2.700 kg de regolito por día", fuente="Mueller et al., NASA KSC, RASSOR 2.0", url=NTRS + "20210011366"),
        dict(que="Densidad del regolito marciano superficial: 1.100 a 1.300 kg/m³ (aquí se usa 1.200)", fuente="Morgan et al. 2018, Space Science Reviews", url="https://link.springer.com/article/10.1007/s11214-018-0537-y"),
        dict(que="Acceso para carga: hasta 5°. Es un valor de un estudio lunar, usado aquí también para Marte porque no se encontró uno propio", fuente="NASA KSC, Lunar Innovation Park, 2026", url=NTRS + "20260002816"),
    ],
    "luna": [
        dict(que="Pendiente para aterrizar con tripulación: menos de 10° medida en 100 m, que es la escala de este relieve", fuente="NASA, actualización del sistema de aterrizaje humano de Artemis, 2024", url=NTRS + "20240009596/downloads/ArtemisHLSUpdate_2024.pdf"),
        dict(que="Superficie de diseño del módulo lunar Apollo: pendiente media de hasta 6°", fuente="NASA TN D-6850", url=NTRS + "19720018253/downloads/19720018253.txt"),
        dict(que="Plataforma de aterrizaje de 27 m de radio (54 m de diámetro)", fuente="Metzger y Autry, estudio de costos de plataformas lunares", url="https://arxiv.org/pdf/2205.00378"),
        dict(que="Un terreno con 4° de pendiente obliga a levantar 2,6 veces más berma que uno a nivel; la NASA no ha definido una distancia segura sin berma", fuente="NASA KSC, Lunar Innovation Park, 2026", url=NTRS + "20260002816"),
        dict(que="Excavación: RASSOR 2.0, al menos 2.700 kg por día; el excavador IPEx, 10.000 kg en 11 días", fuente="NASA KSC (RASSOR 2.0; IPEx)", url=NTRS + "20240008162"),
        dict(que="Densidad del regolito lunar en los primeros 15 cm: 1.500 kg/m³", fuente="Lunar Sourcebook, capítulo 9", url="https://www.lpi.usra.edu/publications/books/lunar_sourcebook/pdf/Chapter09.pdf"),
        dict(que="Acceso para carga hasta una plataforma: hasta 5°", fuente="NASA KSC, Lunar Innovation Park, 2026", url=NTRS + "20260002816"),
    ],
}
es = lambda x, d=1: f"{x:.{d}f}".replace(".", ",")


def _png(rgb):
    from PIL import Image
    b = io.BytesIO(); Image.fromarray(rgb).save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()

def _sombra(z, res, tinte):
    gy, gx = np.gradient(z, res); az, alt = math.radians(315), math.radians(40)
    pen = np.arctan(np.hypot(gx, gy) * 2.0); asp = np.arctan2(-gx, gy)
    s = np.clip(np.sin(alt) * np.cos(pen) + np.cos(alt) * np.sin(pen) * np.cos(az - asp), 0, 1)
    h = (z - z.min()) / max(float(np.ptp(z)), 1e-6); luz = (0.35 + 0.65 * s) * (0.8 + 0.3 * h)
    return np.clip(luz[:, :, None] * np.array(tinte, "float32")[None, None, :] * 1.15, 0, 255)

def _foto(C, lon0, lon1, lat0, lat1, alto, ancho):
    """Fotografía orbital real de la ventana (mosaico de NASA Trek, teselas equirrectangulares), remuestreada al tamaño pedido. None si no se pudo bajar."""
    import requests
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    z = C["foto_z"]; ppg = 2 ** (z + 1) * 256 / 360.0                          # píxeles por grado en ese nivel
    x0, x1 = (lon0 + 180) * ppg, (lon1 + 180) * ppg; y0, y1 = (90 - lat1) * ppg, (90 - lat0) * ppg
    c0, c1, r0, r1 = int(x0 // 256), int(x1 // 256), int(y0 // 256), int(y1 // 256)
    if (c1 - c0 + 1) * (r1 - r0 + 1) > 120: return None
    def una(rc):
        r, c = rc
        try:
            q = requests.get(C["foto"].format(z=z, r=r, c=c % (2 ** (z + 1))), timeout=(10, 30))
            if q.status_code == 200: return rc, Image.open(io.BytesIO(q.content)).convert("RGB")
        except Exception: pass
        return rc, None
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(una, [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]))
    if sum(1 for _, im in res if im is None) > len(res) * 0.2: return None
    lienzo = Image.new("RGB", ((c1 - c0 + 1) * 256, (r1 - r0 + 1) * 256), (90, 90, 90))
    for (r, c), im in res:
        if im is not None: lienzo.paste(im, ((c - c0) * 256, (r - r0) * 256))
    rec = lienzo.crop((int(x0 - c0 * 256), int(y0 - r0 * 256), int(math.ceil(x1 - c0 * 256)), int(math.ceil(y1 - r0 * 256))))
    return np.asarray(rec.resize((ancho, alto), Image.LANCZOS), "float32")

def _rotulos(rgb, res_px_m, intervalo, evitar=(0.5, 0.5)):
    """Barra de escala y leyenda de curvas de nivel dibujadas sobre la textura, para apreciar las dimensiones."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(rgb); d = ImageDraw.Draw(im, "RGBA"); H, W = rgb.shape[:2]
    km = next((k for k in (1, 2, 5, 10, 20, 50, 100) if k * 1000 / res_px_m >= W * 0.14), 100); largo = km * 1000 / res_px_m
    try: f = ImageFont.truetype("/usr/share/fonts/noto/NotoSans-Bold.ttf", max(int(H * 0.028), 11))
    except Exception: f = ImageFont.load_default()
    # la barra va en la esquina más lejana de la plataforma, para no taparla
    izq = evitar[0] > 0.5; arr = evitar[1] > 0.5; x = W * 0.04 if izq else W * 0.96 - largo; y = H * 0.09 if arr else H * 0.93; d.rectangle((x - 6, y - H * 0.05, x + largo + 6, y + 8), fill=(0, 0, 0, 120)); d.line((x, y, x + largo, y), fill=(255, 255, 255, 255), width=max(int(H * 0.006), 2))
    for xx in (x, x + largo): d.line((xx, y - H * 0.012, xx, y), fill=(255, 255, 255, 255), width=max(int(H * 0.004), 2))
    d.text((x, y - H * 0.047), f"{km} km · curvas cada {intervalo:g} m", font=f, fill=(255, 255, 255, 255))
    return np.asarray(im)

def _disco(shape, r, c, radio):
    yy, xx = np.ogrid[:shape[0], :shape[1]]; return (yy - r) ** 2 + (xx - c) ** 2 <= radio ** 2


def analizar(cuerpo, geo, lado_km=None):
    if cuerpo not in CUERPOS: raise ValueError("cuerpo desconocido")
    C = CUERPOS[cuerpo]; an = datos._anillo(geo); lon = np.array([p[0] for p in an]); lat = np.array([p[1] for p in an])
    ident = hashlib.sha1(json.dumps([VERSION, cuerpo, [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lon, lat)]]).encode()).hexdigest()[:12]
    d = os.path.join(datos.RAIZ, "_mundos"); os.makedirs(d, exist_ok=True); f = os.path.join(d, ident + ".json")
    if os.path.exists(f): return json.load(open(f))
    R = C["radio"]; mpg = math.pi * R / 180.0; latm = float(lat.mean())
    x0, x1, y0, y1 = lon.min() * mpg, lon.max() * mpg, lat.min() * mpg, lat.max() * mpg
    ancho_km, alto_km = (x1 - x0) / 1000 * math.cos(math.radians(latm)), (y1 - y0) / 1000
    if max(ancho_km, alto_km) > C["max_km"]: raise ValueError(f"La zona es muy grande: marca menos de {C['max_km']:.0f} km de lado.")
    import time
    ultimo = None
    for intento in range(3):                 # la lectura en línea puede fallar por un corte breve: se reintenta, sin guardar el error en la memoria de GDAL
        try:
            with rasterio.Env(GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", CPL_VSIL_CURL_NON_CACHED="/vsicurl/https://planetarymaps.usgs.gov", VSI_CACHE="FALSE"):
                with rasterio.open("/vsicurl/" + C["url"]) as s:
                    res = s.res[0]; c0, r0 = ~s.transform * (x0, y1); c1, r1 = ~s.transform * (x1, y0)
                    c0, r0 = int(max(math.floor(c0), 0)), int(max(math.floor(r0), 0)); c1, r1 = int(min(math.ceil(c1), s.width)), int(min(math.ceil(r1), s.height))
                    if c1 - c0 < 12 or r1 - r0 < 12: raise ValueError(f"La zona es muy chica para el relieve disponible ({res:.0f} m por celda): marca al menos {12 * res / 1000:.0f} km de lado.")
                    z = s.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype("float32") * C["escala"]; T = s.transform
            ultimo = None; break
        except ValueError: raise
        except Exception as e: ultimo = e; time.sleep(3 + 4 * intento)
    if ultimo is not None: raise ultimo
    z[z < -30000] = np.nan
    if not np.isfinite(z).all(): z = np.where(np.isfinite(z), z, np.nanmedian(z))
    alto, ancho = z.shape; res_x = res * math.cos(math.radians(latm))
    from rasterio.features import geometry_mask
    from affine import Affine
    from scipy.ndimage import maximum_filter, uniform_filter
    Tv = Affine(T.a, 0, T.c + c0 * T.a, 0, T.e, T.f + r0 * T.e)
    dentro = ~geometry_mask([{"type": "Polygon", "coordinates": [[(float(a) * mpg, float(b) * mpg) for a, b in zip(lon, lat)]]}], z.shape, Tv)
    if dentro.sum() < 16: dentro[:] = True
    gy, gx = np.gradient(z, res, res_x); pend = np.degrees(np.arctan(np.hypot(gx, gy)))
    lonlat = lambda r, c: ((Tv * (c + 0.5, r + 0.5))[0] / mpg, (Tv * (c + 0.5, r + 0.5))[1] / mpg)
    # ---- 1. clases de terreno por pendiente: 1 apto, 2 con reparos, 3 no
    clase = np.where(pend <= C["pend_ok"], 1, np.where(pend <= C["pend_tope"], 2, 3)).astype("uint8"); pz = pend[dentro]
    # ---- 2. plataforma de aterrizaje: la celda más pareja mirando también su vecindad (un sitio parejo rodeado de laderas no sirve)
    vecina = maximum_filter(pend, size=3); cubre = uniform_filter(dentro.astype("float32"), size=3) > 0.999
    cand = np.where(cubre, vecina, np.inf)
    if not np.isfinite(cand).any(): cand = np.where(dentro, vecina, np.inf)
    pr, pc = np.unravel_index(int(np.argmin(cand)), cand.shape); p_pend = float(pend[pr, pc]); p_vec = float(vecina[pr, pc])
    Rp = C["plataforma_m"] / 2; vol = 2.0 / 3.0 * Rp ** 3 * math.tan(math.radians(p_pend))      # cuña que se corta (y se rellena) para dejar a nivel un círculo sobre un plano inclinado
    masa = vol * C["densidad"]; dias = masa / C["excav_kg_dia"]
    if p_pend > C["pend_tope"]: cabe = "no"; frase = f"El lugar más parejo de la zona tiene {es(p_pend)}° de pendiente y supera el límite para aterrizar. En esta zona no conviene instalar una estación: busca otra."
    elif p_pend > C["pend_ok"]: cabe = "con reparos"; frase = f"El lugar más parejo de la zona tiene {es(p_pend)}° de pendiente, sobre el límite recomendado de {C['pend_ok']:g}°. Se puede considerar, pero hay zonas mejores."
    else: cabe = "sí"; frase = f"El lugar más parejo de la zona tiene {es(p_pend)}° de pendiente, bajo el límite de {C['pend_ok']:g}° para aterrizar."
    if vol < 1: vale = "A la escala de este relieve el lugar ya está a nivel: no haría falta mover material para la plataforma."
    elif dias <= 45: vale = f"Dejar a nivel la plataforma es una obra corta: cerca de {max(dias, 1):.0f} días de un excavador."
    elif dias <= 365: vale = f"Dejar a nivel la plataforma toma cerca de {max(round(dias / 30), 2)} meses de un excavador. Se puede hacer, pero conviene comparar con un sitio más parejo."
    else: vale = f"Dejar a nivel la plataforma tomaría cerca de {es(dias / 365)} años de un excavador. No vale la pena: es mejor elegir un sitio más parejo."
    plat = _disco(z.shape, pr, pc, max(Rp / res, 0.75)); p_lon, p_lat = lonlat(pr, pc)
    # ---- 3. zona de la estación: terreno apto, a la distancia que piden los estudios, lo más cerca posible de la plataforma
    dist_p = np.hypot((np.arange(alto)[:, None] - pr) * res, (np.arange(ancho)[None, :] - pc) * res_x); dmin = C["dist_estacion_m"] or 6 * res
    apta_e = dentro & (vecina <= C["pend_ok"]) & (dist_p >= dmin)
    est = None; ruta = np.zeros(z.shape, bool); acceso = None; er = ec = None
    if apta_e.any():
        er, ec = np.unravel_index(int(np.argmin(np.where(apta_e, dist_p + vecina * 200.0, np.inf))), z.shape); e_lon, e_lat = lonlat(er, ec)
        est = dict(lon=round(float(e_lon), 4), lat=round(float(e_lat), 4), distancia_m=int(round(float(dist_p[er, ec]), -1)), pendiente=round(float(pend[er, ec]), 1))
        # acceso: camino de menor esfuerzo entre plataforma y estación; el esfuerzo sube fuerte al pasar de la pendiente que admite la carga
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra
        n = alto * ancho; idx = np.arange(n).reshape(alto, ancho); zf = z.ravel(); fi, co, w = [], [], []
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            a = idx[max(-dr, 0):alto - max(dr, 0), max(-dc, 0):ancho - max(dc, 0)].ravel(); b = idx[max(dr, 0):alto - max(-dr, 0), max(dc, 0):ancho - max(-dc, 0)].ravel()
            dist = math.hypot(dr * res, dc * res_x); g = np.degrees(np.arctan(np.abs(zf[b] - zf[a]) / dist))
            fi.append(a); co.append(b); w.append(dist * (1 + 6 * (g / C["pend_acceso"]) ** 3))
        fi, co, w = np.concatenate(fi), np.concatenate(co), np.concatenate(w); gr = coo_matrix((np.r_[w, w], (np.r_[fi, co], np.r_[co, fi])), shape=(n, n)).tocsr()
        dd, pred = dijkstra(gr, indices=int(idx[pr, pc]), return_predecessors=True); cam = [int(idx[er, ec])]
        while pred[cam[-1]] >= 0: cam.append(int(pred[cam[-1]]))
        rr, cc = np.unravel_index(cam[::-1], z.shape); ruta[rr, cc] = True
        if len(cam) >= 2:
            tramo = np.hypot(np.diff(rr) * res, np.diff(cc) * res_x); gp = np.degrees(np.arctan(np.abs(np.diff(z[rr, cc])) / tramo))
            acceso = dict(largo_m=int(round(float(tramo.sum()), -1)), pendiente_media=round(float(np.average(gp, weights=tramo)), 1), pendiente_max=round(float(gp.max()), 1), cumple=bool(gp.max() <= C["pend_acceso"]))
    estm = _disco(z.shape, er, ec, 1.5) if est else np.zeros(z.shape, bool)
    # ---- condiciones generales del lugar
    cond = []
    if C["altura_max"] is not None:
        h = float(z[pr, pc]); cond.append(dict(que="Altura", valor=f"{h:,.0f} m".replace(",", "."), cumple=bool(h <= C["altura_max"]), nota=f"hasta +{C['altura_max'] / 1000:g} km para una misión humana; mientras más bajo, más atmósfera para frenar"))
    if C["lat_max"] is not None:
        cond.append(dict(que="Latitud", valor=f"{es(abs(p_lat))}° {'N' if p_lat >= 0 else 'S'}", cumple=bool(abs(p_lat) <= C["lat_max"]), nota=f"entre {C['lat_max']:g}° S y {C['lat_max']:g}° N"))
    # ---- malla y texturas: a la izquierda el relieve; a la derecha el mismo relieve con el plan del sitio pintado encima
    paso = max(1, int(math.ceil(max(alto, ancho) / 220))); zs = z[::paso, ::paso]
    # textura: la fotografía orbital real del lugar, con un sombreado suave del relieve y curvas de nivel; si no se pudo bajar, relieve sombreado
    from scipy.ndimage import zoom as _zoom
    k = max(1, int(round(1100 / max(alto, ancho)))); Ht, Wt = alto * k, ancho * k; zt = _zoom(z, k, order=1) if k > 1 else z
    lonA, latA = (Tv * (0, 0))[0] / mpg, (Tv * (0, 0))[1] / mpg; lonB, latB = (Tv * (ancho, alto))[0] / mpg, (Tv * (ancho, alto))[1] / mpg
    foto = None
    try: foto = _foto(C, lonA, lonB, latB, latA, Ht, Wt)
    except Exception: foto = None
    luz = _sombra(zt, res / k, (255, 255, 255)) / 255.0
    if foto is not None: foto = foto * min(150.0 / max(float(np.percentile(foto, 90)), 1.0), 2.2) if np.percentile(foto, 90) < 150 else foto      # los mosaicos lunares vienen muy oscuros: se aclaran sin cambiar el contraste
    base = np.clip(foto * (0.55 + 0.6 * luz), 0, 255) if foto is not None else _sombra(zt, res / k, C["tinte"])
    paso_c = next(v for v in (5, 10, 20, 50, 100, 200, 500, 1000) if float(np.ptp(z)) / v <= 14); niv = np.floor(zt / paso_c)
    curva = np.zeros(zt.shape, bool); curva[1:, :] |= niv[1:, :] != niv[:-1, :]; curva[:, 1:] |= niv[:, 1:] != niv[:, :-1]
    base[curva] = base[curva] * 0.72 + 255 * 0.28
    plan = base.copy(); arriba = lambda m: np.repeat(np.repeat(m, k, 0), k, 1)
    cs, ds = arriba(clase), arriba(dentro)
    for kk, col in ((1, (70, 190, 110)), (2, (236, 190, 70)), (3, (220, 80, 55))): m = (cs == kk) & ds; plan[m] = plan[m] * 0.68 + np.array(col) * 0.32
    grueso = lambda m, t=3: arriba(maximum_filter(m.astype("uint8"), size=t) > 0)
    plan[grueso(ruta)] = (250, 240, 205); plan[grueso(estm)] = (70, 140, 240); plan[grueso(plat | _disco(z.shape, pr, pc, 1.5))] = (255, 255, 255)
    ev = (pc / max(ancho - 1, 1), pr / max(alto - 1, 1)); base = _rotulos(base.astype("uint8"), res / k, paso_c, ev); plan = _rotulos(plan.astype("uint8"), res / k, paso_c, ev)
    out = dict(id=ident, cuerpo=cuerpo, nombre=C["nombre"], fuente=C["fuente"], res_m=round(res, 1), ancho_km=round(float(ancho_km), 1), alto_km=round(float(alto_km), 1),
               altura_min=round(float(z[dentro].min())), altura_max=round(float(z[dentro].max())), desnivel=round(float(np.ptp(z[dentro]))), pendiente_media=round(float(pz.mean()), 1),
               pct_apto=round(100 * float((pz <= C["pend_ok"]).mean())), pct_reparos=round(100 * float(((pz > C["pend_ok"]) & (pz <= C["pend_tope"])).mean())), pct_no=round(100 * float((pz > C["pend_tope"]).mean())),
               limite_ok=C["pend_ok"], limite_tope=C["pend_tope"],
               plataforma=dict(diametro_m=C["plataforma_m"], lon=round(float(p_lon), 4), lat=round(float(p_lat), 4), pendiente=round(p_pend, 1), pendiente_vecindad=round(p_vec, 1), cabe=cabe, frase=frase,
                               volumen_m3=int(round(vol)), masa_t=int(round(masa / 1000)), dias_excavador=int(round(dias)), vale=vale),
               estacion=est, distancia_pedida_m=C["dist_estacion_m"], acceso=acceso, limite_acceso=C["pend_acceso"], condiciones=cond, criterios=CRITERIOS[cuerpo],
               malla=dict(ancho=int(zs.shape[1]), alto=int(zs.shape[0]), res_x=round(res_x * paso, 1), res_y=round(res * paso, 1), zmin=float(zs.min()), z=base64.b64encode(np.ascontiguousarray(zs).tobytes()).decode()),
               textura=_png(base), textura2=_png(plan), foto=(C["foto_nombre"] if foto is not None else None), curvas_m=paso_c,
               limites=[f"El relieve tiene {res:.0f} m por celda: no ve rocas, cráteres chicos ni grietas, y la pendiente real en tramos de 5 a 20 m puede ser mayor que la medida aquí.",
                        "El material a mover supone que la plataforma es un círculo sobre un plano con la pendiente medida; el terreno real es más irregular.",
                        "El tiempo de excavación es el de un solo robot trabajando sin detenerse; no incluye compactar, levantar bermas ni fallas.",
                        "Solo se mira la forma del terreno. No se evalúa radiación, temperatura, polvo, luz solar, agua, hielo ni energía.",
                        "Preparar un sitio no es terraformar: no cambia la atmósfera ni el clima del lugar."])
    json.dump(out, open(f, "w")); return out
