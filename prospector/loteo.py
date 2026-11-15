"""Distribución del terreno en lotes: no se ocupa todo, se descuenta lo que no conviene sembrar.

Parte de lo que ya se sabe del terreno (dónde se puede cultivar, árboles, caminos, construcciones, cauce) y de lo que
responde la persona (conservar o no los árboles, usar o no la ladera, qué franja dejar a caminos y bordes).
Devuelve los lotes sembrables, cuánto terreno se aprovecha y cuánto queda fuera con su motivo.
"""
import base64, json, os
import numpy as np
from affine import Affine
from rasterio.features import geometry_mask
from scipy.ndimage import distance_transform_edt, label

F = 4                      # la grilla del análisis se afina 4 veces para medir franjas de pocos metros
LOTE_MAX_HA = 6.0          # un lote más grande se parte en fajas, con un camino de servicio entre ellas
RETAZO_HA = 0.15           # pedazos más chicos no se pueden trabajar con maquinaria
MAX_LOTES = 12

def _arriba(a): return np.repeat(np.repeat(a, F, 0), F, 1)

# Clases de vía de OpenStreetMap/Overture: por cuáles pasa un vehículo, su ancho típico y cómo se les dice
VEHICULO = dict(motorway=(14, "una autopista"), trunk=(12, "una carretera principal"), primary=(10, "una carretera principal"), secondary=(8, "un camino público"), tertiary=(8, "un camino público"),
                residential=(6, "una calle"), living_street=(6, "una calle"), unclassified=(6, "un camino menor"), service=(5, "un camino de servicio"), track=(4, "una huella o camino de tierra"), unknown=(4, "un camino sin clasificar"))
PEATONAL = ("footway", "path", "steps", "pedestrian", "cycleway", "bridleway")
_ORDEN = list(VEHICULO); NOMBRE_CLASE = {i + 1: VEHICULO[k][1] for i, k in enumerate(_ORDEN)}

def _red(d, G, forma, T2):
    """Red de caminos reconocida: se separa lo que sirve para vehículos, lo peatonal y el tren, con su ancho real, en la grilla fina.
    Si no hay camino para vehículos en la vista, busca el más cercano en la ventana ampliada."""
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom
    from shapely.geometry import shape, Polygon
    from . import datos
    vacio = dict(veh=np.zeros(forma, bool), riel=np.zeros(forma, bool), peat=np.zeros(forma, bool), clase_g=np.zeros((forma[0] // F, forma[1] // F), "uint8"), vehiculos_m=0, peatonales_m=0, tren_m=0, clases={}, cercano=None, fuente="sin datos de caminos")
    f = f"{d}/caminos.geojson"
    try:
        if not os.path.exists(f) or not json.load(open(f)).get("ampliado"): datos.descargar_caminos(d, G)
    except Exception: pass
    if not os.path.exists(f): return vacio
    pol = Polygon(G["poligono_utm"]); x0, y0 = T2 * (0, 0); x1, y1 = T2 * (forma[1], forma[0]); vista = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    veh, riel, peat, por_clase, lejos, largo = [], [], [], [], [], dict(veh=0.0, peat=0.0, riel=0.0); clases = {}
    for ft in json.load(open(f))["features"]:
        try: g = shape(transform_geom("EPSG:4326", f"EPSG:{G['epsg']}", ft["geometry"]))
        except Exception: continue
        k = ft["properties"].get("clase") or "unknown"; en_vista = g.intersection(vista)
        if ft["properties"].get("tipo") == "rail":
            if not en_vista.is_empty: riel.append(g.buffer(4)); largo["riel"] += en_vista.length
        elif k in PEATONAL:
            if not en_vista.is_empty: peat.append(g.buffer(1.5)); largo["peat"] += en_vista.length
        else:
            k = k if k in VEHICULO else "unknown"
            if not en_vista.is_empty: veh.append(g.buffer(VEHICULO[k][0] / 2)); por_clase.append((g.buffer(G["res"]), _ORDEN.index(k) + 1)); largo["veh"] += en_vista.length; clases[VEHICULO[k][1]] = clases.get(VEHICULO[k][1], 0) + en_vista.length
            lejos.append((pol.distance(g), g, k))
    ras = lambda gs: rasterize([(g, 1) for g in gs], out_shape=forma, transform=T2, all_touched=True).astype(bool) if gs else np.zeros(forma, bool)
    out = dict(veh=ras(veh), riel=ras(riel), peat=ras(peat), vehiculos_m=int(largo["veh"]), peatonales_m=int(largo["peat"]), tren_m=int(largo["riel"]),
               clases={k: int(v) for k, v in sorted(clases.items(), key=lambda x: -x[1])}, cercano=None, fuente="Overture Maps (OpenStreetMap y otros), hasta 1,2 km alrededor")
    Tg = T2 * Affine.scale(F)
    out["clase_g"] = rasterize(sorted(por_clase, key=lambda x: -x[1]), out_shape=(forma[0] // F, forma[1] // F), transform=Tg, all_touched=True).astype("uint8") if por_clase else vacio["clase_g"]
    if lejos:
        dist, g, k = min(lejos, key=lambda x: x[0]); p = g.interpolate(g.project(pol.centroid)); dx, dy = p.x - pol.centroid.x, p.y - pol.centroid.y
        rumbo = ["este", "noreste", "norte", "noroeste", "oeste", "suroeste", "sur", "sureste"][int(round(np.degrees(np.arctan2(dy, dx)) / 45)) % 8]
        out["cercano"] = dict(m=int(round(dist)), clase=VEHICULO[k][1], rumbo=rumbo, en_vista=bool(out["veh"].any()))
    return out

def proponer(d, plan, bosque="conservar", ladera="incluir", camino=5.0, construccion=10.0, cabecera=6.0, entrada=None):
    G = json.load(open(f"{d}/meta.json")); t = np.load(f"{d}/terreno.npz"); res = G["res"] / F; ha_c = res * res / 1e4
    cl = _arriba(np.load(f"{d}/cultivo.npz")["clase"]); zona = _arriba(np.load(f"{d}/cultivos.npz")["zona"]); pend = _arriba(t["pendiente_pct"])
    T2 = Affine(*G["transform"]) * Affine.scale(1.0 / F)
    dentro = ~geometry_mask([{"type": "Polygon", "coordinates": [G["poligono_utm"]]}], cl.shape, T2)
    red = _red(d, G, cl.shape, T2); cam, edi = red["veh"] | red["riel"], _arriba(t["edificios"])
    d_cam = distance_transform_edt(~cam) * res if cam.any() else np.full(cl.shape, 1e9)
    d_edi = distance_transform_edt(~edi) * res if edi.any() else np.full(cl.shape, 1e9)
    ha = lambda m: round(float(m.sum() * ha_c), 2)

    # ---- lo que se encontró dentro del terreno y hay que decidir
    arboles = dentro & (cl == 6); lad = dentro & (cl == 2); cam_cerca = dentro & (d_cam < 30); edi_cerca = dentro & (d_edi < 30)
    hallazgos = []
    if arboles.any(): hallazgos.append(dict(clave="bosque", valor=bosque, pregunta=f"Hay {ha(arboles):.1f} ha con árboles o matorral en terreno que sirve para cultivo. ¿Qué hacemos con ellas?".replace(".", ",", 1),
                                           opciones=[["conservar", "Conservarlas (no se siembra ahí)"], ["habilitar", "Habilitarlas para cultivo"]]))
    if lad.any(): hallazgos.append(dict(clave="ladera", valor=ladera, pregunta=f"Hay {ha(lad):.1f} ha de ladera moderada (8 a 15 %). ¿Se siembra?".replace(".", ",", 1),
                                       opciones=[["incluir", "Sí, con surcos en curva de nivel"], ["dejar", "No, se deja con pasto"]]))
    if cam_cerca.any(): hallazgos.append(dict(clave="camino", valor=str(int(camino)), pregunta="Hay un camino dentro o al borde del terreno. ¿Cuánta franja libre se deja a cada lado?",
                                             opciones=[["0", "Ninguna"], ["5", "5 metros"], ["10", "10 metros"]]))
    if edi_cerca.any(): hallazgos.append(dict(clave="construccion", valor=str(int(construccion)), pregunta="Hay construcciones dentro o pegadas al terreno. ¿Cuánta distancia se deja?",
                                             opciones=[["5", "5 metros"], ["10", "10 metros"], ["20", "20 metros"]]))
    hallazgos.append(dict(clave="cabecera", valor=str(int(cabecera)), pregunta="¿Cuánto espacio se deja en los bordes de cada lote para girar con la maquinaria y entrar?",
                          opciones=[["0", "Nada (trabajo a mano)"], ["4", "4 metros"], ["6", "6 metros"], ["10", "10 metros"]]))

    # ---- qué queda fuera y por qué (cada superficie se cuenta una sola vez, en este orden)
    fuera, resto = [], dentro.copy()
    def quitar(m, motivo):
        q = resto & m
        if q.any(): fuera.append(dict(motivo=motivo, ha=ha(q)))
        resto[q] = False
    quitar(cl == 5, "Agua, construcciones o caminos"); quitar(cl == 4, "Cauce y su franja de protección"); quitar(cl == 3, "Pendiente fuerte (más de 15 %)")
    if bosque == "conservar": quitar(cl == 6, "Árboles y matorral que se conservan")
    if ladera == "dejar": quitar(cl == 2, "Ladera que se deja con pasto")
    quitar(~np.isin(cl, (1, 2, 6)), "Sin datos suficientes")
    if camino > 0: quitar(d_cam < camino, f"Franja libre junto a caminos ({int(camino)} m)")
    quitar(d_edi < construccion, f"Distancia a construcciones ({int(construccion)} m)")
    if cabecera > 0: quitar(distance_transform_edt(resto) * res < cabecera, f"Bordes para girar y entrar ({int(cabecera)} m)")

    # ---- lotes: cada pedazo continuo, separado por tipo de terreno; los grandes se parten en fajas
    por_zona = {z["clave"]: z for z in plan["zonas"] if z.get("estrategias") and z.get("surco")}
    if not por_zona:                                               # nada cultivable hoy: respuesta completa pero vacía, con el motivo
        quitar(resto, "Sin cultivos que se den aquí sin riego, o sin superficie cultivable")
        return dict(lotes=[], hallazgos=hallazgos, fuera=fuera, total_ha=ha(dentro), usado_ha=0.0, pct=0, ancho=int(cl.shape[1]), alto=int(cl.shape[0]), factor=F, raster="", caminos_nuevos=[], sin_camino_cerca=False,
                    red={k: v for k, v in red.items() if k not in ("veh", "riel", "peat", "clase_g")}, entrada=entrada, etapas=[], proyeccion=None)
    grande = max(por_zona.values(), key=lambda z: z["ha"])["clave"]
    zf = zona.copy(); sin = resto & ~np.isin(zf, list(por_zona))
    zf[sin] = np.where(pend[sin] < 5, 1, np.where(pend[sin] < 8, 2, 3)); zf[resto & ~np.isin(zf, list(por_zona))] = grande
    piezas = []
    for k, z in por_zona.items():
        et, n = label(resto & (zf == k))
        for j in range(1, n + 1):
            m = et == j
            if m.sum() * ha_c < RETAZO_HA: continue
            partes = int(np.ceil(m.sum() * ha_c / LOTE_MAX_HA))
            if partes > 1:                                         # fajas a lo largo de los surcos, con camino de servicio de 4 m entre ellas
                fs, cs = np.nonzero(m); v = -z["surco"][1] * cs + z["surco"][0] * fs; cortes = np.quantile(v, np.linspace(0, 1, partes + 1))
                for p in range(partes):
                    sel = (v >= cortes[p] + (2.0 / res if p else -1)) & (v <= cortes[p + 1] - (2.0 / res if p < partes - 1 else -1))
                    mm = np.zeros_like(m); mm[fs[sel], cs[sel]] = True; piezas.append((k, mm))
            else: piezas.append((k, m))
    piezas = [(k, m) for k, m in piezas if m.sum() * ha_c >= RETAZO_HA]; piezas.sort(key=lambda x: -x[1].sum()); piezas = piezas[:MAX_LOTES]
    raster = np.zeros(cl.shape, "uint8"); lotes = []
    for n, (k, m) in enumerate(piezas, 1):
        raster[m] = n; dist = distance_transform_edt(m); fs, cs = np.nonzero(dist >= dist.max() * 0.6); f0, c0 = np.nonzero(m)[0].mean(), np.nonzero(m)[1].mean()
        q = int(np.argmin((fs - f0) ** 2 + (cs - c0) ** 2)); z = por_zona[k]
        lotes.append(dict(id=n, zona=int(k), zona_nombre=z["nombre"], ha=ha(m), centro=[float(cs[q]) / F, float(fs[q]) / F], surco=z["surco"], surco_texto=z.get("surco_texto", ""),
                          pendiente=round(float(pend[m].mean()), 1)))
    quitar(resto & (raster == 0), "Retazos chicos y caminos de servicio entre lotes")
    usado = ha(raster > 0)
    nuevos, sin_camino = _accesos(d, G, t, raster[F // 2::F, F // 2::F], bosque == "habilitar", red, entrada)
    origen = next((c.get("desde") for c in nuevos if c["tipo"] == "acceso" and c.get("desde")), None)
    por_id = {l["id"]: l for l in lotes}
    despeje = ha((cl == 6) & (raster > 0)) if bosque == "habilitar" else 0.0
    acc = [c for c in nuevos if c["tipo"] == "acceso"]; ser = [c for c in nuevos if c["tipo"] == "servicio"]
    etapas = []
    if acc: etapas.append(dict(clave="acceso", titulo="Abrir el camino de entrada", detalle=f"{int(sum(c['largo_m'] for c in acc))} m desde {'la entrada que marcaste' if entrada else (origen or 'el camino más cercano')} hasta el primer lote" +
                               (f"; cruza la vía del tren en {sum(c.get('cruces_riel', 0) for c in acc)} punto(s) y necesita un cruce autorizado" if sum(c.get("cruces_riel", 0) for c in acc) else "") +
                               (f"; {int(sum(c['fuera_m'] for c in acc))} m pasan por terreno vecino y necesitan permiso de paso" if sum(c["fuera_m"] for c in acc) >= 10 else "") +
                               (f"; cruza el cauce en {sum(c['cruces_cauce'] for c in acc)} punto(s) y necesita alcantarilla o badén" if sum(c["cruces_cauce"] for c in acc) else "") + "."))
    elif sin_camino: etapas.append(dict(clave="acceso", titulo="Resolver la entrada", detalle=(f"El camino para vehículos más cercano ({red['cercano']['clase']}) está a {red['cercano']['m']} m hacia el {red['cercano']['rumbo']}, fuera de la vista: marca la entrada a mano para trazar el acceso." if red.get("cercano") else "No hay ningún camino para vehículos registrado en 1,2 km a la redonda: marca la entrada a mano. Puede existir una huella que el mapa no tiene.")))
    if not acc and not sin_camino and not entrada and red.get("cercano"):
        etapas.append(dict(clave="entrada", titulo="La entrada ya existe", detalle=f"Los lotes quedan pegados a {red['cercano']['clase']}: se entra directo, sin abrir camino nuevo."))
    if ser: etapas.append(dict(clave="servicio", titulo="Trazar caminos de servicio entre lotes", detalle=f"{int(sum(c['largo_m'] for c in ser))} m en {len(ser)} tramos" +
                               (f"; {int(sum(c['por_arboles_m'] for c in ser))} m pasan entre árboles" if sum(c["por_arboles_m"] for c in ser) >= 10 else "") +
                               (f"; cruzan el cauce en {sum(c['cruces_cauce'] for c in ser)} punto(s) y necesitan alcantarilla o badén" if sum(c["cruces_cauce"] for c in ser) else "") + "."))
    if despeje > 0: etapas.append(dict(clave="despeje", titulo="Despejar árboles y matorral", detalle=f"{despeje:.1f} ha dentro de los lotes. Revisa antes si la ley local permite cortarlos y deja la franja del cauce intacta.".replace(".", ",", 1)))
    etapas.append(dict(clave="suelo", titulo="Preparar el suelo y marcar los lotes", detalle=f"{usado:.1f} ha en {len(lotes)} lotes, dejando libres los bordes y las franjas.".replace(".", ",", 1)))
    etapas.append(dict(clave="siembra", titulo="Primera siembra", detalle="Cada lote con el cultivo que más años sale bien en su tipo de terreno."))
    hoy = ha(dentro & np.isin(cl, (1, 2)))
    agua = sum(l["ha"] * por_zona[l["zona"]]["estrategias"][por_zona[l["zona"]].get("mejor", 0)]["agua_mm"] * 10 for l in lotes)
    buenos = sum(l["ha"] * por_zona[l["zona"]]["estrategias"][por_zona[l["zona"]].get("mejor", 0)]["buenos_de_10"] for l in lotes) / max(usado, 1e-6)
    proy = dict(hoy_ha=hoy, plan_ha=usado, despeje_ha=despeje, camino_m=int(sum(c["largo_m"] for c in nuevos)), agua_m3_anio=int(round(agua, -2)), buenos_de_10=round(buenos, 1))
    return dict(red={k: v for k, v in red.items() if k not in ('veh', 'riel', 'peat', 'clase_g')}, entrada=entrada, caminos_nuevos=nuevos, sin_camino_cerca=bool(sin_camino), etapas=etapas, proyeccion=proy, lotes=lotes, hallazgos=hallazgos, fuera=fuera, total_ha=ha(dentro), usado_ha=usado, pct=round(100 * usado / max(ha(dentro), 1e-6)),
                ancho=int(cl.shape[1]), alto=int(cl.shape[0]), factor=F, raster=base64.b64encode(raster.tobytes()).decode())


def _accesos(d, G, t, lot, talar, red, entrada=None):
    """Por dónde entrar y cómo unir los lotes: ruta de menor esfuerzo desde el camino existente más cercano.
    El esfuerzo sube con la pendiente, al cruzar el cauce, al pasar entre árboles, por terreno vecino o por dentro de un lote."""
    import rasterio
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    res = G["res"]; alto, ancho = lot.shape; N = alto * ancho
    cl = np.load(f"{d}/cultivo.npz")["clase"]; pend = t["pendiente_pct"]; arb = rasterio.open(f"{d}/worldcover.tif").read(1) == 10
    costo = 1 + (np.minimum(pend, 60) / 8.0) ** 2
    costo = costo * np.where(cl == 4, 25, 1) * np.where(arb & ~(talar & (lot > 0)), 3, 1) * np.where(lot > 0, 4, 1) * np.where(t["mascara"], 1, 2)
    costo[t["edificios"] | t["agua"]] = 1e6
    costo = costo * np.where(red["riel"].reshape(alto, F, ancho, F).any((1, 3)), 30, 1)
    idx = np.arange(N).reshape(alto, ancho); fil, col, val = [], [], []
    for df, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = idx[max(0, -df):alto - max(0, df), max(0, -dc):ancho - max(0, dc)]; b = idx[max(0, df):alto - max(0, -df), max(0, dc):ancho - max(0, -dc)]
        fil.append(a.ravel()); col.append(b.ravel()); val.append((costo.ravel()[a.ravel()] + costo.ravel()[b.ravel()]) / 2 * res * np.hypot(df, dc))
    fil, col, val = np.concatenate(fil), np.concatenate(col), np.concatenate(val)
    riel = red["riel"].reshape(alto, F, ancho, F).any((1, 3)); veh = red["veh"].reshape(alto, F, ancho, F).any((1, 3))
    if entrada:                                                      # la persona marcó por dónde se entra: todo parte de ahí
        unido = np.zeros(lot.shape, bool); unido[int(np.clip(entrada[1], 0, alto - 1)), int(np.clip(entrada[0], 0, ancho - 1))] = True
    else: unido = veh.copy()                                         # solo caminos por los que pasa un vehículo (no senderos ni escaleras)
    sin_camino = not unido.any(); pendientes = [int(k) for k in np.unique(lot) if k > 0]; salida = []
    if sin_camino and pendientes:                                   # sin camino a la vista: se parte del lote más grande
        k0 = max(pendientes, key=lambda k: (lot == k).sum()); unido |= lot == k0; pendientes.remove(k0)
    primero = not sin_camino; costo_riel = riel
    while pendientes:
        fu = np.flatnonzero(unido.ravel())
        g = coo_matrix((np.concatenate([val, np.full(len(fu), 1e-9)]), (np.concatenate([fil, np.full(len(fu), N)]), np.concatenate([col, fu]))), shape=(N + 1, N + 1)).tocsr()
        dist, pre = dijkstra(g, directed=False, indices=N, return_predecessors=True)
        dl = np.where(np.isin(lot, pendientes), dist[:N].reshape(alto, ancho), np.inf); fin = int(np.argmin(dl))
        if not np.isfinite(dl.ravel()[fin]): break
        k = int(lot.ravel()[fin]); ruta = [fin]
        while pre[ruta[-1]] != N and pre[ruta[-1]] >= 0: ruta.append(int(pre[ruta[-1]]))
        ruta = ruta[::-1]; fs, cs = np.divmod(np.array(ruta), ancho)
        largo = float(np.hypot(np.diff(fs), np.diff(cs)).sum() * res) if len(ruta) > 1 else 0.0
        if largo >= 15:
            en4 = cl[fs, cs] == 4
            salida.append(dict(tipo="acceso" if primero else "servicio", lote=k, puntos=[[int(c), int(f)] for f, c in zip(fs, cs)], largo_m=round(largo),
                               por_arboles_m=int(arb[fs, cs].sum() * res), cruces_cauce=int((en4[1:] & ~en4[:-1]).sum() + int(en4[0])), fuera_m=int((~t["mascara"][fs, cs]).sum() * res),
                               pendiente_max=round(float(pend[fs, cs].max()), 1),
                               cruces_riel=int((costo_riel[fs, cs][1:] & ~costo_riel[fs, cs][:-1]).sum()), desde=(None if entrada else NOMBRE_CLASE.get(int(red["clase_g"][fs[0], cs[0]])))))
        unido[fs, cs] = True; unido |= lot == k; pendientes.remove(k); primero = False
    return salida, sin_camino
