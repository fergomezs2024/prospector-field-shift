"""Prospector · lugares del mundo con condiciones parecidas (análogos de clima y suelo).

Pregunta: "¿en lugares del mundo con clima y suelo como este, se cultiva?"  No se analiza el mundo entero cada vez:
se construye UNA vez una tabla mundial (celdas de ~18 km) y cada consulta busca los vecinos más parecidos.
  Clima   WorldClim 2.1 (1970-2000), 10 minutos de arco: temperatura y lluvia anuales y estacionales (bio1,4,5,6,12,15,16,17,18,19)
  Suelo   SoilGrids 2.0 agregado a 5 km: arcilla, arena, pH, carbono orgánico (0-5 cm)
  Cultivo ESA CCI Land Cover 2020 (300 m): fracción de cada celda con cultivos (clases 10-30) y con riego (clase 20)
  Países  Natural Earth 1:110m
Método: distancia euclidiana en variables estandarizadas; los K vecinos más parecidos de todo el planeta.
Uso: python -m prospector.mundo   (construye la tabla, una sola vez)
"""
import os, io, json, zipfile, math, numpy as np, requests, rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin
D = os.environ.get("PROSPECTOR_DATOS") or os.path.join(os.path.dirname(__file__), "mundo_datos")
BIOS = [1, 4, 5, 6, 12, 15, 16, 17, 18, 19]; LOGS = {12, 16, 17, 18, 19}
VARS = [f"bio{b}" for b in BIOS] + ["arcilla", "arena", "ph", "carbono"]
EXCLUIR = {"carbono"}
NY, NX = 1080, 2160; T = from_origin(-180, 90, 1 / 6, 1 / 6)

def _bajar(url, dst, intentos=2, registro=None):
    """Descarga con reintentos. Si el servidor no responde no se queda colgado: corta a los 12 s sin conexión o a los 2 min sin datos.
    Lo ya bajado queda en «.part» y se retoma desde ahí la próxima vez. `url` puede ser una lista de servidores alternativos."""
    import time
    if os.path.exists(dst): return dst
    urls = [url] if isinstance(url, str) else list(url); ultimo = None
    for n in range(intentos):
        for u in urls:
            try:
                ya = os.path.getsize(dst + ".part") if os.path.exists(dst + ".part") else 0
                r = requests.get(u, timeout=(12, 120), stream=True, headers={"Range": f"bytes={ya}-"} if ya else {})
                if r.status_code == 416: os.replace(dst + ".part", dst); return dst          # ya estaba completo
                r.raise_for_status()
                with open(dst + ".part", "ab" if (ya and r.status_code == 206) else "wb") as f:
                    for ch in r.iter_content(1 << 20): f.write(ch)
                os.replace(dst + ".part", dst); return dst
            except Exception as e:
                ultimo = e
                if registro: registro(f"   no respondió {u.split('/')[2]} (intento {n + 1} de {intentos}): {str(e)[:90]}")
        time.sleep(5 * (n + 1))
    raise RuntimeError(f"no se pudo descargar desde {', '.join(x.split('/')[2] for x in urls)}: {str(ultimo)[:120]}")

def construir(registro=print):
    os.makedirs(D, exist_ok=True)
    registro("clima WorldClim (50 MB)…"); z = zipfile.ZipFile(_bajar(["https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip", "https://biogeo.ucdavis.edu/data/worldclim/v2.1/base/wc2.1_10m_bio.zip"], f"{D}/wc_bio.zip", registro=registro))
    cols = {}
    for b in BIOS:
        with rasterio.open(io.BytesIO(z.read(f"wc2.1_10m_bio_{b}.tif"))) as s: a = s.read(1).astype("float32"); a[a < -1e30] = np.nan; a[a == s.nodata] = np.nan
        cols[f"bio{b}"] = a
    registro("suelo SoilGrids 5 km…")
    for nom, var, esc in (("arcilla", "clay", 10), ("arena", "sand", 10), ("ph", "phh2o", 10), ("carbono", "soc", 10)):
        f = _bajar(f"https://files.isric.org/soilgrids/latest/data_aggregated/5000m/{var}/{var}_0-5cm_mean_5000.tif", f"{D}/sg_{var}.tif")
        with rasterio.open(f) as s:
            src = s.read(1).astype("float32"); src[(src <= 0) | (src == s.nodata)] = np.nan; out = np.full((NY, NX), np.nan, "float32")
            reproject(src, out, src_transform=s.transform, src_crs=s.crs, dst_transform=T, dst_crs="EPSG:4326", resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        cols[nom] = out / esc
    registro("cultivos ESA CCI 2020 (32 teselas)…")
    import planetary_computer as pc
    from pystac_client import Client
    from concurrent.futures import ThreadPoolExecutor
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    frac = np.full((NY, NX), np.nan, "float32"); riego = np.zeros((NY, NX), "float32")
    def tesela(it):
        with rasterio.open(it.assets["lccs_class"].href) as s:
            w, h = int(round((s.bounds.right - s.bounds.left) * 30)), int(round((s.bounds.top - s.bounds.bottom) * 30))     # 2 minutos de arco
            a = s.read(1, out_shape=(h, w), resampling=Resampling.nearest); return s.bounds, a
    its = list(cat.search(collections=["esa-cci-lc"], datetime="2020-01-01/2020-12-31").items())
    with ThreadPoolExecutor(8) as ex:
        for bnd, a in ex.map(tesela, its):
            h5, w5 = a.shape[0] // 5, a.shape[1] // 5; a = a[:h5 * 5, :w5 * 5].reshape(h5, 5, w5, 5)
            cult = np.isin(a, [10, 11, 12, 20, 30]).mean((1, 3)); irr = (a == 20).mean((1, 3)); agua = (a == 210).mean((1, 3))
            r0, c0 = int(round((90 - bnd.top) * 6)), int(round((bnd.left + 180) * 6))
            frac[r0:r0 + h5, c0:c0 + w5] = np.where(agua > 0.9, np.nan, cult); riego[r0:r0 + h5, c0:c0 + w5] = irr
    registro("países…")
    from rasterio.features import rasterize
    ne = json.loads(requests.get("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson", timeout=120).text)
    nombres = ["(sin país)"] + [f["properties"].get("NAME_ES") or f["properties"]["NAME"] for f in ne["features"]]
    pais = rasterize([(f["geometry"], k + 1) for k, f in enumerate(ne["features"])], out_shape=(NY, NX), transform=T, fill=0, all_touched=True, dtype="int16")
    ok = np.isfinite(frac) & np.all([np.isfinite(cols[v]) for v in VARS], 0)
    rr, cc = np.where(ok)
    X = np.stack([np.log1p(np.maximum(cols[v][ok], 0)) if (v.startswith("bio") and int(v[3:]) in LOGS) or v == "carbono" else cols[v][ok] for v in VARS], 1).astype("float32")
    mu, sd = X.mean(0), X.std(0)
    np.savez_compressed(f"{D}/mundo.npz", fila=rr.astype("int16"), col=cc.astype("int16"), X=X, mu=mu, sd=sd, frac=frac[ok], riego=riego[ok], pais=pais[ok],
                        crudo=np.stack([cols[v][ok] for v in VARS], 1).astype("float32"))
    json.dump(dict(nombres=nombres, vars=VARS, n=int(ok.sum()), cultivadas=int((frac[ok] >= 0.2).sum())), open(f"{D}/mundo.json", "w"), ensure_ascii=False)
    registro(f"tabla mundial: {ok.sum():,} celdas de tierra · {int((frac[ok] >= 0.2).sum()):,} con cultivos")
    # validación: ¿los vecinos parecidos (a más de 500 km) predicen si una celda se cultiva?
    from scipy.spatial import cKDTree
    from sklearn.metrics import roc_auc_score
    Z = (X - mu) / sd; arbol = cKDTree(Z); rng = np.random.default_rng(0); prueba = rng.choice(len(Z), 6000, replace=False)
    lat, lon = 90 - (rr + 0.5) / 6, -180 + (cc + 0.5) / 6; pred = []
    _, vec = arbol.query(Z[prueba], k=800)
    for i, v in zip(prueba, vec):
        lejos = v[_km(lat[i], lon[i], lat[v], lon[v]) > 500][:200]
        pred.append((frac[ok][lejos] >= 0.2).mean() if len(lejos) else np.nan)
    pred = np.array(pred); m = np.isfinite(pred); auc = roc_auc_score(frac[ok][prueba][m] >= 0.2, pred[m])
    meta = json.load(open(f"{D}/mundo.json")); meta["auc_analogos_lejanos"] = round(float(auc), 3); json.dump(meta, open(f"{D}/mundo.json", "w"), ensure_ascii=False)
    registro(f"validación: los 200 lugares más parecidos a más de 500 km predicen si se cultiva con AUC {auc:.2f}")

def _km(la1, lo1, la2, lo2):
    p = np.pi / 180; a = np.sin((la2 - la1) * p / 2) ** 2 + np.cos(la1 * p) * np.cos(la2 * p) * np.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))

_CACHE = {}
def _cargar():
    if not _CACHE:
        from scipy.spatial import cKDTree
        z = np.load(f"{D}/mundo.npz"); _CACHE.update({k: z[k] for k in z.files}); _CACHE["meta"] = json.load(open(f"{D}/mundo.json"))
        usar = [k for k, v in enumerate(VARS) if v not in EXCLUIR]      # el carbono de SoilGrids es poco fiable en varias zonas: no se usa para comparar
        _CACHE["Z"] = ((_CACHE["X"] - _CACHE["mu"]) / _CACHE["sd"])[:, usar]; _CACHE["arbol"] = cKDTree(_CACHE["Z"])
        _CACHE["lat"] = 90 - (_CACHE["fila"] + 0.5) / 6; _CACHE["lon"] = -180 + (_CACHE["col"] + 0.5) / 6
    return _CACHE

def disponible(): return os.path.exists(f"{D}/mundo.npz")

def validar(n=6000):
    """¿Los lugares parecidos a más de 500 km predicen si una celda se cultiva?  Devuelve el AUC y lo guarda."""
    from sklearn.metrics import roc_auc_score
    M = _cargar(); rng = np.random.default_rng(0); prueba = rng.choice(len(M["Z"]), n, replace=False); pred = []
    _, vec = M["arbol"].query(M["Z"][prueba], k=800)
    for i, v in zip(prueba, vec):
        lejos = v[_km(M["lat"][i], M["lon"][i], M["lat"][v], M["lon"][v]) > 500][:200]; pred.append((M["frac"][lejos] >= 0.2).mean() if len(lejos) else np.nan)
    pred = np.array(pred); m = np.isfinite(pred); auc = float(roc_auc_score(M["frac"][prueba][m] >= 0.2, pred[m]))
    meta = json.load(open(f"{D}/mundo.json")); meta["auc_analogos_lejanos"] = round(auc, 3); meta["variables_usadas"] = [v for v in VARS if v not in EXCLUIR]
    json.dump(meta, open(f"{D}/mundo.json", "w"), ensure_ascii=False); M["meta"] = meta; return auc

def consultar(lon, lat, k=300):
    """Los k lugares del mundo con clima y suelo más parecidos a (lon, lat) y qué pasa en ellos."""
    M = _cargar(); d0 = _km(lat, lon, M["lat"], M["lon"]); i0 = int(np.argmin(d0))
    if d0[i0] > 60: return dict(disponible=False, motivo="No hay datos de clima y suelo para este punto (mar, hielo o isla pequeña).")
    dist, vec = M["arbol"].query(M["Z"][i0], k=k * 4)
    km = _km(lat, lon, M["lat"][vec], M["lon"][vec]); sel = vec[km > 100][:k]; ds = dist[km > 100][:k]     # se excluye solo el entorno inmediato (100 km)
    cult = M["frac"][sel] >= 0.2; n10 = int(round(cult.mean() * 10)); nom = M["meta"]["nombres"]
    paises = {}
    for j in sel[cult]:
        p = nom[int(M["pais"][j])]; paises.setdefault(p, []).append(j)
    top = sorted(((p, len(v)) for p, v in paises.items() if p != "(sin país)"), key=lambda x: -x[1])[:5]
    ej = []
    for p, _ in top:
        j = paises[p][0]; ej.append(dict(pais=p, lugares=len(paises[p]), lat=round(float(M["lat"][j]), 2), lon=round(float(M["lon"][j]), 2)))
    c = dict(zip(VARS, M["crudo"][i0].tolist())); med = float(np.median(ds))
    parecido = "muy parecidos" if med < 0.9 else ("parecidos" if med < 1.6 else "solo algo parecidos")
    riego = float(M["riego"][sel][cult].mean() / max(M["frac"][sel][cult].mean(), 1e-6)) if cult.any() else 0.0
    return dict(disponible=True, k=int(len(sel)), cultivados=int(cult.sum()), de_cada_10=n10, parecido=parecido, distancia_mediana=round(med, 2),
                paises=ej, fraccion_riego=round(riego, 2), aqui_cultivo=round(float(M["frac"][i0]), 2),
                clima=dict(temp_media=round(c["bio1"], 1), temp_max_mes_calido=round(c["bio5"], 1), temp_min_mes_frio=round(c["bio6"], 1), lluvia_anual=round(c["bio12"]),
                           lluvia_trimestre_seco=round(c["bio17"]), lluvia_trimestre_calido=round(c["bio18"]), lluvia_trimestre_frio=round(c["bio19"])),
                suelo=dict(arcilla=round(c["arcilla"]), arena=round(c["arena"]), ph=round(c["ph"], 1), carbono_g_kg=round(c["carbono"], 1)),
                auc=M["meta"].get("auc_analogos_lejanos"), n_mundo=M["meta"]["n"])

if __name__ == "__main__":
    construir(); print(json.dumps(consultar(-72.123, -36.273), ensure_ascii=False, indent=1))
