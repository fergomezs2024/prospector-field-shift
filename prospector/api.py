"""Prospector · servidor local.  Uso: .venv/bin/python -m uvicorn prospector.api:app --port 8790"""
import os, io, json, base64, threading, time, traceback, numpy as np, rasterio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from PIL import Image
from matplotlib import colormaps
from affine import Affine
from . import datos, terreno, region, mundo, cultivos, loteo

AQUI = os.path.dirname(__file__); WEB = f"{AQUI}/web"
app = FastAPI(title="Prospector")
app.add_middleware(GZipMiddleware, minimum_size=2000)      # las respuestas JSON con rásteres en base64 bajan a una fracción
TRABAJOS = {}
F_EVENTOS = os.path.join(datos.RAIZ, "_eventos.log") if os.environ.get("PROSPECTOR_CACHE") else f"{AQUI}/eventos.log"

def _evento(tipo, i=None, **kw):
    """Historial para auditar: una línea JSON por acción (hora, tipo, terreno)."""
    try:
        with open(F_EVENTOS, "a") as f: f.write(json.dumps(dict(hora=time.strftime("%Y-%m-%d %H:%M:%S"), tipo=tipo, id=i, **kw), ensure_ascii=False) + "\n")
    except Exception: pass


class Pedido(BaseModel):
    geojson: dict
    nombre: str = "Terreno"
    anio_ini: int = 2021
    anio_fin: int = 2025

def _dir(i):
    d = os.path.join(datos.RAIZ, i)
    if not os.path.isdir(d): raise HTTPException(404, "área desconocida")
    return d

PASOS = [("terreno", "Relieve e imagen del terreno", 25), ("region", "Comparación con los potreros cultivados de la zona", 180),
         ("historial", "Historial de vegetación, suelo y clima del terreno", 300)]
F_TIEMPOS = os.path.join(datos.RAIZ, "_tiempos.json")

def _estimado(clave, defecto):
    try:
        v = json.load(open(F_TIEMPOS)).get(clave, [])[-5:]
        return float(np.median(v)) if v else defecto
    except Exception: return defecto

def _pasos(claves):
    return [dict(clave=c, nombre=n, estado="pendiente", seg=0, est=round(_estimado(c, e)), avance=None, t0=None) for c, n, e in PASOS if c in claves]

class _Paso:
    """Marca inicio y fin de un paso; guarda su duración real para estimar los siguientes."""
    def __init__(self, tr, clave): self.p = next(x for x in tr["pasos"] if x["clave"] == clave)
    def __enter__(self): self.p.update(estado="corriendo", t0=time.time()); return self
    def avance(self, f): self.p["avance"] = round(float(f), 3)
    def __exit__(self, tipo, *_):
        dur = time.time() - self.p["t0"]; self.p.update(estado="error" if tipo else "listo", seg=round(dur), t0=None, avance=1.0)
        if not tipo and dur > 5:
            try: t = json.load(open(F_TIEMPOS))
            except Exception: t = {}
            t.setdefault(self.p["clave"], []).append(round(dur)); os.makedirs(datos.RAIZ, exist_ok=True); json.dump(t, open(F_TIEMPOS, "w"))

def _activo():
    return next((k for k, v in TRABAJOS.items() if v["estado"] == "corriendo"), None)

def _ejecutar(i, pedido):
    tr = TRABAJOS[i]; reg = lambda m: tr["log"].append(m); canc = lambda: tr.get("cancelar", False)
    try:
        with _Paso(tr, "terreno"):         # segundos: relieve + cobertura + imagen -> ya se puede ver el terreno 3D
            d, G = datos.preparar(pedido.geojson, pedido.anio_ini, pedido.anio_fin, registro=reg, solo_rapido=True, nombre=pedido.nombre)
            if not os.path.exists(f"{d}/terreno.json") or "caminos_dentro_m" not in json.load(open(f"{d}/terreno.json")): terreno.analizar(d)
        tr["terreno"] = True
        if canc(): raise datos.Cancelado()
        with _Paso(tr, "region") as ps:    # aprender de los terrenos cultivados alrededor (se guarda por zona)
            if not os.path.exists(f"{d}/cultivo.json") or "criterios" not in json.load(open(f"{d}/cultivo.json")): region.analizar_region(d, registro=reg, progreso=ps.avance, cancelado=canc)
        tr["region"] = True
        if canc(): raise datos.Cancelado()
        with _Paso(tr, "historial") as ps:   # minutos: HLS propio, suelo, clima
            nuevo = not os.path.exists(f"{d}/hls_ndvi.npz")
            d, G = datos.preparar(pedido.geojson, pedido.anio_ini, pedido.anio_fin, registro=reg, nombre=pedido.nombre, progreso=lambda f: ps.avance(0.9 * f), cancelado=canc)
            t = json.load(open(f"{d}/terreno.json")); t["fuentes"] = G.get("fuentes", {}); json.dump(t, open(f"{d}/terreno.json", "w"), indent=1, ensure_ascii=False)
            if nuevo: region.analizar_region(d, registro=lambda m: None)   # afina árboles/matorral con el historial propio
        reg("listo"); tr["estado"] = "listo"; _evento("analisis_listo", i, nombre=tr.get("nombre"), seg=round(time.time() - tr["t0"]))
    except datos.Cancelado:
        tr["estado"] = "pausado"; _evento("analisis_pausado", i, nombre=tr.get("nombre")); reg("análisis en pausa: se retoma al volver a abrir este terreno")
    except Exception as e:
        tr["estado"] = "error"; reg(f"ERROR: {e}"); traceback.print_exc(); _evento("analisis_error", i, nombre=tr.get("nombre"), error=str(e))

def _lanzar(i, pedido):
    """El terreno nuevo tiene prioridad: si hay otro análisis en curso se pausa (lo ya descargado se conserva)."""
    pausado = None
    for k, v in TRABAJOS.items():
        if k != i and v["estado"] == "corriendo": v["cancelar"] = True; pausado = v.get("nombre")
    for _ in range(100):
        if not any(k != i and v["estado"] == "corriendo" for k, v in TRABAJOS.items()): break
        time.sleep(0.2)
    os.makedirs(os.path.join(datos.RAIZ, i), exist_ok=True); json.dump(pedido.model_dump(), open(os.path.join(datos.RAIZ, i, "pedido.json"), "w"))   # para poder retomarlo
    TRABAJOS[i] = dict(estado="corriendo", terreno=False, region=False, log=[], t0=time.time(), pasos=_pasos(["terreno", "region", "historial"]), nombre=pedido.nombre)
    an = datos._anillo(pedido.geojson); _evento("analisis_inicio", i, nombre=pedido.nombre, centro=[round(sum(q[1] for q in an) / len(an), 5), round(sum(q[0] for q in an) / len(an), 5)], pauso_a=pausado)
    threading.Thread(target=_ejecutar, args=(i, pedido), daemon=True).start()
    return {"id": i, "pausado": pausado}

def _ocupado(i):
    o = _activo()
    if o and o != i:
        return JSONResponse(status_code=409, content=dict(ocupado=o, nombre=TRABAJOS[o].get("nombre", "otro terreno")))

@app.post("/api/pausar/{i}")
def pausar(i: str):
    if i in TRABAJOS and TRABAJOS[i]["estado"] == "corriendo": TRABAJOS[i]["cancelar"] = True; _evento("pausa_pedida", i)
    return {"id": i}

@app.get("/api/edificios/{i}")
def edificios(i: str):
    f = f"{_dir(i)}/edificios.geojson"
    return json.load(open(f)) if os.path.exists(f) else dict(type="FeatureCollection", features=[])

@app.get("/api/caminos/{i}")
def caminos(i: str):
    f = f"{_dir(i)}/caminos.geojson"
    return json.load(open(f)) if os.path.exists(f) else dict(type="FeatureCollection", features=[])

def _cultivos(d, actual=None):
    f = f"{d}/cultivos.json"
    if os.path.exists(f):
        c = json.load(open(f))
        if c.get("version") == cultivos.VERSION and actual in (None, "", c.get("actual")): return c
        if not actual: actual = c.get("actual")
    return cultivos.analizar(d, actual=actual or None, registro=lambda m: None)

@app.get("/api/cultivos/{i}")
def get_cultivos(i: str, actual: str = ""):
    """Qué cultivar, dónde, cómo y en qué orden (se calcula en unos segundos y queda guardado)."""
    d = _dir(i)
    if not os.path.exists(f"{d}/cultivo.npz"): raise HTTPException(409, "Primero debe terminar el análisis de dónde se puede cultivar.")
    _evento("plan_cultivo", i, actual=actual or None)
    c = _cultivos(d, actual)
    # dónde va cada zona dentro del terreno (el punto más interior de la zona) y cuál de sus rotaciones rinde más
    from scipy.ndimage import distance_transform_edt
    zona = np.load(f"{d}/cultivos.npz")["zona"]
    from scipy.ndimage import gaussian_filter
    gf, gc = np.gradient(gaussian_filter(rasterio.open(f"{d}/dem.tif").read(1).astype(float), 2.0))
    c["zona_b64"] = base64.b64encode(np.ascontiguousarray(zona.astype("uint8")).tobytes()).decode(); c["zona_ancho"], c["zona_alto"] = int(zona.shape[1]), int(zona.shape[0])
    for z in c["zonas"]:
        m = zona == z["clave"]; z["mejor"] = _mejor(z)
        if m.any():      # dirección de los surcos: en ladera cruzan la pendiente (siguen la curva de nivel); en plano, el lado largo de la zona
            a, b = float(gc[m].mean()), float(gf[m].mean())
            if z.get("pendiente_media", 0) >= 3 and np.hypot(a, b) > 1e-6: v = np.array([-b, a]) / np.hypot(a, b); z["surco_texto"] = "surcos cruzando la pendiente, siguiendo la curva de nivel"
            else:
                fs, cs = np.nonzero(m); P = np.stack([cs - cs.mean(), fs - fs.mean()]); w, V = np.linalg.eigh(P @ P.T + np.eye(2) * 1e-6); v = V[:, 1]; z["surco_texto"] = "surcos rectos a lo largo de la zona"
            z["surco"] = [float(v[0]), float(v[1])]
        if m.any():      # punto bien adentro de la zona y lo más cerca posible de su centro
            dist = distance_transform_edt(m); fs, cs = np.nonzero(dist >= dist.max() * 0.6); f0, c0 = np.nonzero(m)[0].mean(), np.nonzero(m)[1].mean()
            k = int(np.argmin((fs - f0) ** 2 + (cs - c0) ** 2)); z["centro"] = [int(cs[k]), int(fs[k])]
    return c

@app.get("/api/entorno/{i}")
def get_entorno(i: str):
    """Lo que rodea al terreno, para la recreación 3D: dónde hay árboles (ESA WorldCover, 10 m) en toda la ventana."""
    d = _dir(i); wc = rasterio.open(f"{d}/worldcover.tif").read(1)
    veg = (wc == 10).astype("uint8")                                   # 1 = arbolado
    if os.path.exists(f"{d}/cultivo.npz") and os.path.exists(f"{d}/terreno.npz"):     # 2 = matorral o árboles dispersos dentro del terreno
        veg[(np.load(f"{d}/cultivo.npz")["clase"] == 6) & np.load(f"{d}/terreno.npz")["mascara"] & (veg == 0)] = 2
    return dict(ancho=int(wc.shape[1]), alto=int(wc.shape[0]), arboles=base64.b64encode(np.ascontiguousarray(veg).tobytes()).decode())

@app.get("/api/loteo/{i}")
def get_loteo(i: str, bosque: str = "conservar", ladera: str = "incluir", camino: float = 5, construccion: float = 10, cabecera: float = 6, entrada: str = ""):
    """Reparte el terreno en lotes sembrables descontando caminos, construcciones, cauce, árboles y bordes, según lo que responda la persona."""
    d = _dir(i)
    if not os.path.exists(f"{d}/cultivo.npz"): raise HTTPException(409, "Primero debe terminar el análisis de dónde se puede cultivar.")
    ent = None
    try:
        if entrada: ent = [float(x) for x in entrada.split(",")][:2]
    except ValueError: ent = None
    return loteo.proponer(d, get_cultivos(i), bosque=bosque, ladera=ladera, camino=camino, construccion=construccion, cabecera=cabecera, entrada=ent)

def _mejor(z):
    """Rotación que más años sale bien; a igualdad, la de más rendimiento y menos suelo perdido."""
    e = z.get("estrategias") or []
    return max(range(len(e)), key=lambda k: (e[k]["buenos_de_10"], e[k]["rendimiento"], -e[k]["erosion_t_ha"])) if e else 0

SUELO_RGB, VERDE_RGB, SECO_RGB, RASTROJO_RGB = np.array([150, 116, 82.0]), np.array([52, 148, 58.0]), np.array([214, 186, 72.0]), np.array([196, 170, 112.0])

@app.get("/api/salud")
def salud():
    """Para el balanceador o el orquestador: el servicio responde y dice qué datos mundiales tiene cargados."""
    from . import calendario, cultivado
    return dict(ok=True, motor=cultivos.VERSION, cultivos=len(cultivos.CULTIVOS), tabla_mundial=mundo.disponible(), calendario=calendario.disponible(), observado=cultivado.disponible(), ocupado=_activo() is not None)

@app.get("/api/eventos")
def eventos(n: int = 80):
    try: return [json.loads(l) for l in open(F_EVENTOS).read().splitlines()[-n:]]
    except Exception: return []

@app.get("/api/activo")
def activo():
    o = _activo(); return dict(id=o, nombre=TRABAJOS[o].get("nombre")) if o else dict(id=None)

@app.post("/api/analizar/{i}")
def analizar(i: str):
    """Retoma o completa el análisis de un terreno guardado (lo ya descargado no se repite)."""
    d = _dir(i)
    if i in TRABAJOS and TRABAJOS[i]["estado"] == "corriendo": return {"id": i}
    if not os.path.exists(f"{d}/meta.json"):
        if os.path.exists(f"{d}/pedido.json"): return _lanzar(i, Pedido(**json.load(open(f"{d}/pedido.json"))))
        raise HTTPException(404, "Ese terreno no alcanzó a guardarse: hay que marcarlo de nuevo")
    G = json.load(open(f"{d}/meta.json"))
    return _lanzar(i, Pedido(geojson={"type": "Polygon", "coordinates": [G["poligono"]]}, nombre=G.get("nombre", i)))

@app.get("/api/punto/{i}")
def punto(i: str, c: float, r: float):
    """Explicación de un punto. Solo dentro del terreno marcado: alrededor se muestra la imagen como contexto, sin análisis."""
    d = _dir(i); t = np.load(f"{d}/terreno.npz"); m = t["mascara"]
    fi, co = int(round(r)), int(round(c))
    if not (0 <= fi < m.shape[0] and 0 <= co < m.shape[1]) or not m[fi, co]:
        return dict(fuera=True, clase=0, titulo="Fuera de tu terreno", color="#7d7d7d", detalles=[], tecnico=[],
                    texto="Este punto está fuera de la zona que marcaste. El análisis se hace solo dentro de tu terreno; alrededor se muestra la imagen para dar contexto.")
    out = region.explicar_punto(d, c, r) if os.path.exists(f"{d}/cultivo.npz") else dict(clase=0, titulo="Punto de tu terreno", color="#3fbf7f", texto="El análisis de este terreno aún se está calculando.", detalles=[], tecnico=[])
    from scipy.ndimage import gaussian_filter
    G = json.load(open(f"{d}/meta.json")); dem = gaussian_filter(rasterio.open(f"{d}/dem.tif").read(1).astype(float), max(30.0 / G["res"], 1.0))
    z = float(dem[fi, co]); zmin = float(dem[m].min())
    out["detalles"] = [f"Altitud: {z:.0f} m sobre el nivel del mar ({z - zmin:.1f} m sobre el punto más bajo de tu terreno)"]
    out.setdefault("tecnico", [])
    return out

@app.post("/api/prospectar")
def prospectar(p: Pedido):
    import hashlib
    an = datos._anillo(p.geojson)
    i = hashlib.sha1(json.dumps([[round(c, 6) for c in q[:2]] for q in an]).encode()).hexdigest()[:12]
    if i in TRABAJOS and TRABAJOS[i]["estado"] == "corriendo": return {"id": i}
    return _lanzar(i, p)

@app.get("/api/estado/{i}")
def estado(i: str):
    if i in TRABAJOS:
        tr = TRABAJOS[i]; ahora = time.time()
        pasos = [dict(x, seg=round(ahora - x["t0"]) if x["t0"] else x["seg"]) for x in tr.get("pasos", [])]
        return dict({k: v for k, v in tr.items() if k != "cancelar"}, pasos=pasos, seg=round(ahora - tr["t0"]))
    if os.path.exists(os.path.join(datos.RAIZ, i, "terreno.json")):
        return dict(estado="listo", terreno=True, region=os.path.exists(os.path.join(datos.RAIZ, i, "cultivo.json")), log=["(en caché)"], seg=0, pasos=[])
    raise HTTPException(404)

@app.get("/api/areas")
def areas():
    """Historial de prospecciones, de la más reciente a la más antigua."""
    out = []
    if os.path.isdir(datos.RAIZ):
        for i in os.listdir(datos.RAIZ):
            b = os.path.join(datos.RAIZ, i); f = f"{b}/meta.json"
            if i.startswith("_") or not (os.path.exists(f) and os.path.exists(f"{b}/terreno.json")): continue
            G = json.load(open(f)); T = json.load(open(f"{b}/terreno.json")); cu = None
            if os.path.exists(f"{b}/cultivo.json"):
                c = json.load(open(f"{b}/cultivo.json")); cu = c["ha"].get("Sí se puede cultivar") if c.get("disponible") and "criterios" in c else None
            t0 = os.path.getmtime(f"{b}/dem.tif") if os.path.exists(f"{b}/dem.tif") else os.path.getmtime(f)
            out.append(dict(id=i, nombre=G.get("nombre") or "Terreno", centro=G["centro"], ha=T["superficie_ha"], poligono=G["poligono"], cultivable_ha=cu,
                            fecha=time.strftime("%Y-%m-%d %H:%M", time.localtime(t0)), t=t0, completo=os.path.exists(f"{b}/clima.json")))
    return sorted(out, key=lambda x: -x["t"])

@app.get("/api/terreno/{i}")
def get_terreno(i: str, motivo: str = "abrir"):
    d = _dir(i); G = json.load(open(f"{d}/meta.json")); _evento("ver_terreno", i, nombre=G.get("nombre"), motivo=motivo)
    if "caminos_dentro_m" not in json.load(open(f"{d}/terreno.json")): terreno.analizar(d)
    fc = f"{d}/cultivo.json"
    if os.path.exists(fc):
        c = json.load(open(fc))
        if "criterios" not in c:                       # formato anterior: se rehace con lo ya descargado si la zona está en caché
            try: region.analizar_region(d, registro=lambda m: None)
            except Exception: pass
        elif not c.get("mundo", {}).get("disponible") and mundo.disponible():      # la tabla mundial se construyó después
            try: c["mundo"] = mundo.consultar(G["centro"][0], G["centro"][1]); json.dump(c, open(fc, "w"), ensure_ascii=False, indent=1)
            except Exception: pass
    from rasterio.warp import transform as trp
    T = Affine(*G["transform"]); W, H = G["ancho"], G["alto"]
    ex, ey = zip(*[T * (c, r) for c, r in ((0, 0), (W, 0), (0, H), (W, H))])
    lo, la = trp(f"EPSG:{G['epsg']}", "EPSG:4326", list(ex), list(ey))
    return dict(meta={k: G[k] for k in ("id", "epsg", "res", "ancho", "alto", "bbox", "centro", "poligono")} | {"nombre": G.get("nombre", i), "esquinas": [[a, b] for a, b in zip(lo, la)]},
                aptitud_leyenda=[dict(nombre=n, color=c) for n, c in terreno.APTITUD.values()],
                terreno=json.load(open(f"{d}/terreno.json")), vegetacion=os.path.exists(f"{d}/hls_ndvi.npz"), completo=os.path.exists(f"{d}/clima.json"),
                cultivo=json.load(open(f"{d}/cultivo.json")) if os.path.exists(f"{d}/cultivo.json") else None)

@app.get("/api/malla/{i}")
def malla(i: str):
    d = _dir(i); G = json.load(open(f"{d}/meta.json")); T = Affine(*G["transform"])
    dem = rasterio.open(f"{d}/dem.tif").read(1).astype("float32")
    from scipy.ndimage import gaussian_filter
    dem = gaussian_filter(dem, sigma=max(30.0 / G["res"], 1.0) * 0.7)
    paso = max(1, int(np.ceil(np.sqrt(dem.size / 160000))))
    z = np.ascontiguousarray(dem[::paso, ::paso])
    pol = [[(~T * (x, y))[0], (~T * (x, y))[1]] for x, y in G["poligono_utm"]]     # en celdas (col, fila)
    dens = []                                                  # borde densificado: sigue el relieve celda a celda
    for (c0, r0), (c1, r1) in zip(pol[:-1], pol[1:]):
        n = max(1, int(np.ceil(np.hypot(c1 - c0, r1 - r0) / paso)))
        dens += [[c0 + (c1 - c0) * k / n, r0 + (r1 - r0) * k / n] for k in range(n)]
    dens.append(pol[-1])
    return dict(ancho=int(z.shape[1]), alto=int(z.shape[0]), res=G["res"] * paso, zmin=float(z.min()), zmax=float(z.max()),
                z=base64.b64encode(z.tobytes()).decode(), poligono=[[c / paso, r / paso] for c, r in dens])

def _con_edif(d, out, edif):
    """Pinta las huellas de edificaciones (naranja) sobre cualquier capa."""
    if edif:
        try:
            z = np.load(f"{d}/terreno.npz"); out = out.copy()
            if "caminos" in z.files: out[z["caminos"]] = (238, 226, 180)
            out[z["edificios"]] = (255, 138, 0)
        except Exception: pass
    return out

def _png(rgba):
    b = io.BytesIO(); Image.fromarray(rgba).save(b, "PNG"); return Response(b.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})

def _textura(d):
    f = f"{d}/textura.tif"
    if not os.path.exists(f): return None
    a = rasterio.open(f).read().astype("float32")
    lo, hi = np.percentile(a[a > 0], [1, 99.5]) if (a > 0).any() else (0, 255)
    return np.clip((a - lo) / max(hi - lo, 1) * 255, 0, 255).astype("uint8").transpose(1, 2, 0)

def _ndvi_clim(d):
    f = f"{d}/ndvi_clim.npy"
    if os.path.exists(f): return np.load(f)
    z = np.load(f"{d}/hls_ndvi.npz"); nd = z["ndvi"].astype("float32"); mes = np.array([int(x[5:7]) for x in z["fechas"]])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = np.stack([np.nanmedian(nd[mes == m], axis=0) if (mes == m).any() else np.full(nd.shape[1:], np.nan) for m in range(1, 13)])
    np.save(f, c); return c

CAPAS = {"pendiente": ("Pendiente (%)", "YlOrRd", 0, 30), "flujo": ("Hacia dónde va el agua (área que drena, ha)", "Blues", None, None),
         "altitud": ("Altitud (m)", "terrain", None, None), "humedad": ("Índice topográfico de humedad", "YlGnBu", 2, 14)}

@app.get("/api/capa/{i}/{nombre}.png")
def capa(i: str, nombre: str, mes: int = 1, mezcla: float = 0.75, edif: int = 1, est_: int = 0, anio_: int = 0, tipo: str = "normal", solo: int = 0):
    d = _dir(i); base = _textura(d)
    G = json.load(open(f"{d}/meta.json"))
    if base is None: base = np.full((G["alto"], G["ancho"], 3), 128, "uint8")
    if not os.path.exists(f"{d}/terreno.npz") or "caminos" not in np.load(f"{d}/terreno.npz").files: terreno.analizar(d)
    t = np.load(f"{d}/terreno.npz"); fuera = np.where(t["mascara"], 1.0, 0.72)[:, :, None]      # fuera del terreno se atenúa
    if nombre == "imagen": return _png(np.dstack([_con_edif(d, (base * fuera).astype("uint8"), edif), np.full(base.shape[:2], 255, "uint8")]))
    if nombre == "plan":
        # simulación: cada zona con el cultivo que le toca ese año de la rotación, en ese mes y ese tipo de año (seco/normal/lluvioso reales)
        est: int = int(est_); anio_r = int(anio_)
        c = _cultivos(d); zona = np.load(f"{d}/cultivos.npz")["zona"]; por = {x["clave"]: x for x in c["cultivos"]}
        out = (base * 0.72).astype("float32"); alfa = np.zeros(out.shape[:2], "uint8") if solo else np.full(out.shape[:2], 255, "uint8")   # solo=1: transparente fuera de lo pintado
        if os.path.exists(f"{d}/cultivo.npz") and not solo:
            cl = np.load(f"{d}/cultivo.npz")["clase"]
            for k, (_, hx) in region.CLASES.items():
                if k in (4, 5, 6): m_ = (cl == k) & t["mascara"]; out[m_] = base[m_] * 0.45 + np.array([int(hx[j:j + 2], 16) for j in (1, 3, 5)]) * 0.55
        for z in c["zonas"]:
            if not z["estrategias"]: continue
            e = z["estrategias"][_mejor(z) if est < 0 else min(est, len(z["estrategias"]) - 1)]; cu = por[e["secuencia"][anio_r % len(e["secuencia"])]]
            m12 = cu.get("mensual", {}).get(tipo) or cu.get("mensual", {}).get("normal")
            if not m12: continue
            x = m12[mes - 1]; col = RASTROJO_RGB * 0.6 + SUELO_RGB * 0.4 if x["fase"] == "rastrojo" else SUELO_RGB + (VERDE_RGB - SUELO_RGB) * min(x["fc"] / 0.9, 1.0)
            if x["fase"] not in ("rastrojo", "suelo sin cultivo") and x["ks"] < 0.6: col = col + (SECO_RGB - col) * min((0.6 - x["ks"]) / 0.5, 1.0)
            if solo == 2: col = RASTROJO_RGB * 0.5 + SUELO_RGB * 0.5 if x["fase"] == "rastrojo" else SUELO_RGB      # solo el suelo: las plantas se dibujan en 3D
            mz = zona == z["clave"]; out[mz] = col if solo else base[mz] * 0.18 + col * 0.82; alfa[mz] = (150 if solo == 2 else 190) if solo else 255
        return _png(np.dstack([out.astype("uint8") if solo else _con_edif(d, out.astype("uint8"), edif), alfa]))
    if nombre == "cultivo":
        if not os.path.exists(f"{d}/cultivo.npz"): raise HTTPException(404, "comparación con la zona aún no disponible")
        cl = np.load(f"{d}/cultivo.npz")["clase"]; col = np.zeros(cl.shape + (3,), "float32")
        for k, (_, hx) in region.CLASES.items(): col[cl == k] = [int(hx[j:j + 2], 16) for j in (1, 3, 5)]
        dentro = t["mascara"][:, :, None]
        if solo: return _png(np.dstack([col.astype("uint8"), np.where(t["mascara"] & (cl > 0), 185, 0).astype("uint8")]))
        out = _con_edif(d, np.where(dentro, base * 0.25 + col * 0.75, base * 0.72).astype("uint8"), edif)       # el color solo dentro del terreno
        return _png(np.dstack([out, np.full(out.shape[:2], 255, "uint8")]))
    if nombre == "aptitud":
        apt = t["aptitud"]; col = np.zeros(apt.shape + (3,), "float32")
        for k, (_, hx) in terreno.APTITUD.items(): col[apt == k] = [int(hx[j:j + 2], 16) for j in (1, 3, 5)]
        if solo: return _png(np.dstack([col.astype("uint8"), np.where(apt > 0, 175, 0).astype("uint8")]))
        out = _con_edif(d, np.where(t["mascara"][:, :, None], base * 0.2 + col * 0.8, base * 0.72).astype("uint8"), edif)
        return _png(np.dstack([out, np.full(out.shape[:2], 255, "uint8")]))
    if nombre == "pendiente": v = t["pendiente_pct"]; cm, lo, hi = "YlOrRd", 0, max(8.0, float(np.percentile(v, 98)))
    elif nombre == "flujo":
        v = np.log10(np.maximum(t["acumulacion"] * G["res"] ** 2 / 1e4, 1e-3)); cm, lo, hi = "Blues", -1.5, float(np.nanmax(v))
    elif nombre == "humedad": v, (cm, lo, hi) = t["twi"], ("YlGnBu", 2, 14)
    elif nombre == "altitud":
        v = rasterio.open(f"{d}/dem.tif").read(1).astype("float32"); cm, lo, hi = "terrain", float(v.min()), float(v.max())
    elif nombre == "ndvi":
        if not os.path.exists(f"{d}/hls_ndvi.npz"): raise HTTPException(404, "historial de vegetación aún descargando")
        v, (cm, lo, hi) = _ndvi_clim(d)[mes - 1], ("RdYlGn", 0.1, 0.8)
    else: raise HTTPException(404)
    n = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1); col = (colormaps[cm](np.nan_to_num(n))[:, :, :3] * 255)
    if solo:                                                          # mapa de toda la vista, transparente, para ir sobre la imagen de alta resolución
        al = np.isfinite(v) * 185.0
        if nombre == "flujo": al = al * np.clip((n - 0.25) / 0.5, 0, 1)
        return _png(np.dstack([col.astype("uint8"), al.astype("uint8")]))
    a = mezcla * (np.isfinite(v) & t["mascara"])[:, :, None]            # el análisis solo dentro del terreno marcado
    if nombre == "flujo": a = a * np.clip((n - 0.25) / 0.5, 0, 1)[:, :, None]      # solo se pinta donde se concentra el agua
    out = _con_edif(d, ((base * (1 - a) + col * a) * fuera).astype("uint8"), edif)
    return _png(np.dstack([out, np.full(out.shape[:2], 255, "uint8")]))

@app.get("/")
def raiz(): return FileResponse(f"{WEB}/index.html")
app.mount("/", StaticFiles(directory=WEB), name="web")
