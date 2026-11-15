"""Marte y la Luna: relieve real de una zona y cómo quedaría nivelada para instalar una estación.

Relieve (se lee en línea, solo la ventana pedida):
  Marte  MOLA MEGDR, 463 m por celda (NASA Mars Global Surveyor; mosaico de USGS Astrogeology)
  Luna   LOLA LDEM, 118 m por celda (NASA Lunar Reconnaissance Orbiter; mosaico de USGS Astrogeology)

Lo que se calcula es geometría del terreno: desnivel, pendiente, el lugar más parejo para una plataforma y cuánta roca habría que mover para dejarla plana.
NO es un estudio de habitabilidad ni de terraformación: no considera radiación, temperatura, polvo, agua, hielo ni energía.
"""
import os, io, json, math, base64, hashlib
import numpy as np, rasterio
from rasterio.windows import Window
from . import datos

CUERPOS = {
    "marte": dict(nombre="Marte", radio=3396190.0, url="https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif", escala=1.0, max_km=400.0, lado_km=3.0,
                  fuente="MOLA MEGDR 463 m (NASA Mars Global Surveyor; USGS Astrogeology)", tinte=(196, 124, 86)),
    "luna": dict(nombre="la Luna", radio=1737400.0, url="https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif", escala=0.5, max_km=120.0, lado_km=1.0,
                 fuente="LOLA LDEM 118 m (NASA Lunar Reconnaissance Orbiter; USGS Astrogeology)", tinte=(176, 176, 172)),
}


def _png(rgb):
    from PIL import Image
    b = io.BytesIO(); Image.fromarray(rgb).save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()

def _sombra(z, res, tinte, marca=None):
    """Relieve sombreado con el color del cuerpo; `marca` pinta la plataforma más clara."""
    gy, gx = np.gradient(z, res); az, alt = math.radians(315), math.radians(40)
    pen = np.arctan(np.hypot(gx, gy) * 2.0); asp = np.arctan2(-gx, gy)
    s = np.clip(np.sin(alt) * np.cos(pen) + np.cos(alt) * np.sin(pen) * np.cos(az - asp), 0, 1)
    h = (z - z.min()) / max(float(np.ptp(z)), 1e-6); luz = (0.35 + 0.65 * s) * (0.8 + 0.3 * h)
    rgb = np.clip(luz[:, :, None] * np.array(tinte, "float32")[None, None, :] * 1.15, 0, 255)
    if marca is not None: rgb[marca] = rgb[marca] * 0.35 + np.array([238, 232, 214]) * 0.65
    return rgb.astype("uint8")


def analizar(cuerpo, geo, lado_km=None):
    if cuerpo not in CUERPOS: raise ValueError("cuerpo desconocido")
    C = CUERPOS[cuerpo]; an = datos._anillo(geo); lon = np.array([p[0] for p in an]); lat = np.array([p[1] for p in an])
    lado_km = float(np.clip(lado_km or C["lado_km"], C["lado_km"] / 2, C["lado_km"] * 8))
    ident = hashlib.sha1(json.dumps([cuerpo, [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lon, lat)], lado_km]).encode()).hexdigest()[:12]
    d = os.path.join(datos.RAIZ, "_mundos"); os.makedirs(d, exist_ok=True); f = os.path.join(d, ident + ".json")
    if os.path.exists(f): return json.load(open(f))
    R = C["radio"]; mpg = math.pi * R / 180.0                                   # metros por grado (proyección equirrectangular del mosaico)
    x0, x1, y0, y1 = lon.min() * mpg, lon.max() * mpg, lat.min() * mpg, lat.max() * mpg
    ancho_km, alto_km = (x1 - x0) / 1000 * math.cos(math.radians(float(lat.mean()))), (y1 - y0) / 1000
    if max(ancho_km, alto_km) > C["max_km"]: raise ValueError(f"La zona es muy grande: marca menos de {C['max_km']:.0f} km de lado.")
    with rasterio.Env(GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="2", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with rasterio.open("/vsicurl/" + C["url"]) as s:
            res = s.res[0]; c0, r0 = ~s.transform * (x0, y1); c1, r1 = ~s.transform * (x1, y0)
            c0, r0 = int(max(math.floor(c0), 0)), int(max(math.floor(r0), 0)); c1, r1 = int(min(math.ceil(c1), s.width)), int(min(math.ceil(r1), s.height))
            if c1 - c0 < 12 or r1 - r0 < 12: raise ValueError(f"La zona es muy chica para el relieve disponible ({res:.0f} m por celda): marca al menos {12 * res / 1000:.0f} km de lado.")
            z = s.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype("float32") * C["escala"]; T = s.transform
    z[z < -30000] = np.nan
    if not np.isfinite(z).all(): z = np.where(np.isfinite(z), z, np.nanmedian(z))
    alto, ancho = z.shape; res_x = res * math.cos(math.radians(float(lat.mean())))      # en el terreno, una celda mide menos de este a oeste lejos del ecuador
    # dentro del polígono marcado
    from rasterio.features import geometry_mask
    from affine import Affine
    Tv = Affine(T.a, 0, T.c + c0 * T.a, 0, T.e, T.f + r0 * T.e)
    dentro = ~geometry_mask([{"type": "Polygon", "coordinates": [[(float(a) * mpg, float(b) * mpg) for a, b in zip(lon, lat)]]}], z.shape, Tv)
    if dentro.sum() < 16: dentro[:] = True
    gy, gx = np.gradient(z, res, res_x); pend = np.degrees(np.arctan(np.hypot(gx, gy)))
    # ---- la plataforma: el cuadrado de `lado_km` con menos desnivel dentro de la zona
    from scipy.ndimage import maximum_filter, minimum_filter, uniform_filter
    nf, nc = max(int(round(lado_km * 1000 / res)), 2), max(int(round(lado_km * 1000 / res_x)), 2)
    desn = maximum_filter(z, size=(nf, nc)) - minimum_filter(z, size=(nf, nc)); cubre = uniform_filter(dentro.astype("float32"), size=(nf, nc)) > 0.999
    cand = np.where(cubre, desn, np.inf)
    if not np.isfinite(cand).any(): cand = np.where(dentro, desn, np.inf)
    rc, cc = np.unravel_index(int(np.argmin(cand)), cand.shape)
    ra, rb = max(rc - nf // 2, 0), min(rc - nf // 2 + nf, alto); ca, cb = max(cc - nc // 2, 0), min(cc - nc // 2 + nc, ancho)
    plat = np.zeros(z.shape, bool); plat[ra:rb, ca:cb] = True
    nivel = float(z[plat].mean()); corte = float(np.clip(z[plat] - nivel, 0, None).sum() * res * res_x); relleno = float(np.clip(nivel - z[plat], 0, None).sum() * res * res_x)
    # terreno preparado: plataforma plana y un talud de transición de dos celdas alrededor
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(~plat); w = np.clip(1 - dist / 2.5, 0, 1); z2 = z * (1 - w) + nivel * w
    # ---- malla y texturas (se submuestrea si la ventana es grande)
    paso = max(1, int(math.ceil(max(alto, ancho) / 220))); zs, z2s, ps = z[::paso, ::paso], z2[::paso, ::paso], plat[::paso, ::paso]
    lon_c, lat_c = (ca + cb) / 2, (ra + rb) / 2
    plat_lon, plat_lat = (Tv * (lon_c, lat_c))[0] / mpg, (Tv * (lon_c, lat_c))[1] / mpg
    pp = pend[plat]; pz = pend[dentro]
    juicio = ("un terreno parejo" if np.ptp(z[plat]) < 0.03 * lado_km * 1000 else "un terreno con desnivel moderado" if np.ptp(z[plat]) < 0.10 * lado_km * 1000
              else "un terreno muy accidentado: en esta zona no hay un lugar parejo de ese tamaño")
    juicio += f" (desnivel de {float(np.ptp(z[plat])):.0f} m). Dejarlo plano significa mover en promedio {str(round(corte / max(float(plat.sum()) * res * res_x, 1), 1)).replace('.', ',')} m de material sobre toda la plataforma"
    out = dict(id=ident, cuerpo=cuerpo, nombre=C["nombre"], fuente=C["fuente"], res_m=round(res, 1), ancho_km=round(ancho_km, 1), alto_km=round(alto_km, 1),
               altura_min=round(float(z[dentro].min())), altura_max=round(float(z[dentro].max())), desnivel=round(float(np.ptp(z[dentro]))),
               pendiente_media=round(float(pz.mean()), 1), pct_menos_5=round(100 * float((pz < 5).mean())), pct_mas_15=round(100 * float((pz > 15).mean())),
               plataforma=dict(lado_km=lado_km, lon=round(float(plat_lon), 4), lat=round(float(plat_lat), 4), nivel=round(nivel), desnivel=round(float(np.ptp(z[plat])), 1), pendiente_media=round(float(pp.mean()), 1),
                               pendiente_max=round(float(pp.max()), 1), corte_m3=int(round(corte, -2)), relleno_m3=int(round(relleno, -2)), juicio=juicio),
               malla=dict(ancho=int(zs.shape[1]), alto=int(zs.shape[0]), res_x=round(res_x * paso, 1), res_y=round(res * paso, 1), zmin=float(min(zs.min(), z2s.min())),
                          z=base64.b64encode(np.ascontiguousarray(zs).tobytes()).decode(), z2=base64.b64encode(np.ascontiguousarray(z2s).tobytes()).decode()),
               textura=_png(_sombra(zs, res * paso, C["tinte"])), textura2=_png(_sombra(z2s, res * paso, C["tinte"], marca=ps)),
               limites=[f"El relieve tiene {res:.0f} m por celda: no muestra rocas, cráteres chicos ni grietas.",
                        "Solo se mide la forma del terreno. No se evalúa radiación, temperatura, polvo, agua, hielo, luz solar ni energía.",
                        "La tierra a mover supone cortar las partes altas y rellenar las bajas hasta un mismo nivel, sin compactación ni pérdidas.",
                        "Nivelar una plataforma no es terraformar: no cambia la atmósfera ni el clima del lugar."])
    json.dump(out, open(f, "w")); return out
