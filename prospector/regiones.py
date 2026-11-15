"""Cultivos representativos de cada país y de cada región de primer nivel (estado, provincia, región) del mundo.

Dos fuentes, que se muestran por separado para poder contrastarlas:
  - CROPGRIDS v1.08 (Tang et al. 2024, CC-BY 4.0): superficie cosechada de 173 cultivos hacia 2020 en celdas de 5,6 km. Se suma dentro de cada
    región (límites de Natural Earth 1:10m, 4.596 regiones) y de cada país.
  - FAOSTAT (FAO, estadísticas oficiales que informa cada país): superficie cosechada por cultivo, promedio 2019-2021. Solo a nivel de país.
CROPGRIDS se construyó a partir de estadísticas nacionales y regionales, así que a nivel de país las dos fuentes no son independientes; a nivel de
región, CROPGRIDS es una estimación y hay que leerla como tal.

Uso (una vez):  python -m prospector.regiones <CROPGRIDS_NC.zip> <ne_10m_admin_1.shp> <fao_area_2019_2021.csv>
"""
import os, sys, json, functools
import numpy as np
from . import cultivado, cultivos

D = cultivado.D; F_GRILLA = os.path.join(D, "regiones.npz"); F_TABLA = os.path.join(D, "regiones.json")

# OJO: en CROPGRIDS «vegfor» son las otras hortalizas frescas y «vegetablenes» las hortalizas forrajeras (tabla CROPS_matching_v17 del propio conjunto de datos).
# nombres en español de las claves de CROPGRIDS que no están en la lista de «otros cultivos» ni en los cultivos simulados
MAS = dict(abaca="abacá", agave="agave", aniseetc="anís, comino y afines", areca="nuez de areca", bambara="bambara", beetfor="remolacha forrajera", berrynes="otras bayas", brazil="castaña de Brasil",
           cabbagefor="col forrajera", canaryseed="alpiste", carob="algarrobo", carrotfor="zanahoria forrajera", cashewapple="fruto del marañón", castor="ricino", cerealnes="otros cereales", chicory="achicoria",
           cinnamon="canela", clove="clavo de olor", fibrenes="otras fibras", fonio="fonio", fornes="otros forrajes", fruitnes="otras frutas", gooseberry="uva espina", grassnes="pastos sembrados",
           greenbroadbean="haba verde", greenonion="cebollín", hemp="cáñamo", hempseed="semilla de cáñamo", jutelikefiber="fibras tipo yute", kapokfiber="kapok", kapokseed="semilla de kapok", karite="karité",
           kolanut="nuez de cola", legumenes="otras leguminosas forrajeras", maizefor="maíz forrajero", melonseed="semilla de melón", mixedgrain="mezcla de granos", mixedgrass="praderas mixtas sembradas",
           mushroom="hongos", nutmeg="nuez moscada y cardamomo", nutnes="otros frutos secos", oilseedfor="oleaginosas forrajeras", oilseednes="otras oleaginosas", peppermint="menta", pimento="ají seco",
           popcorn="maíz para palomitas", poppy="amapola", pulsenes="otras legumbres", pyrethrum="piretro", ramie="ramio", rootnes="otras raíces y tubérculos", ryefor="centeno forrajero",
           sorghumfor="sorgo forrajero", spicenes="otras especias", stonefruitnes="otras frutas de carozo", stringbean="poroto verde (vaina)", sugarnes="otros cultivos azucareros", swedefor="colinabo forrajero",
           tropicalnes="otras frutas tropicales", tung="tung", turnipfor="nabo forrajero", vegetablenes="hortalizas y raíces forrajeras", vegfor="otras hortalizas", yautia="yautía")
NOMBRE = dict(MAS); NOMBRE.update(cultivado.OTROS); NOMBRE.update({v: cultivos.CULTIVOS[k]["nombre"].lower() for k, v in cultivado.CROPGRIDS.items()})

# cultivo de FAOSTAT -> clave de CROPGRIDS
FAO = {"Abaca, manila hemp, raw": "abaca", "Agave fibres, raw, n.e.c.": "agave", "Almonds, in shell": "almond", "Anise, badian, coriander, cumin, caraway, fennel and juniper berries, raw": "aniseetc", "Apples": "apple",
       "Apricots": "apricot", "Areca nuts": "areca", "Artichokes": "artichoke", "Asparagus": "asparagus", "Avocados": "avocado", "Bambara beans, dry": "bambara", "Bananas": "banana", "Barley": "barley",
       "Beans, dry": "bean", "Blueberries": "blueberry", "Broad beans and horse beans, dry": "broadbean", "Broad beans and horse beans, green": "greenbroadbean", "Buckwheat": "buckwheat", "Cabbages": "cabbage",
       "Canary seed": "canaryseed", "Cantaloupes and other melons": "melonetc", "Carrots and turnips": "carrot", "Cashew nuts, in shell": "cashew", "Cashewapple": "cashewapple", "Cassava, fresh": "cassava",
       "Castor oil seeds": "castor", "Cauliflowers and broccoli": "cauliflower", "Cereals n.e.c.": "cerealnes", "Cherries": "cherry", "Chestnuts, in shell": "chestnut", "Chick peas, dry": "chickpea",
       "Chicory roots": "chicory", "Chillies and peppers, dry (Capsicum spp., Pimenta spp.), raw": "pimento", "Chillies and peppers, green (Capsicum spp. and Pimenta spp.)": "chilleetc",
       "Cinnamon and cinnamon-tree flowers, raw": "cinnamon", "Cloves (whole stems), raw": "clove", "Cocoa beans": "cocoa", "Coconuts, in shell": "coconut", "Coffee, green": "coffee", "Cow peas, dry": "cowpea",
       "Cranberries": "cranberry", "Cucumbers and gherkins": "cucumberetc", "Currants": "currant", "Dates": "date", "Edible roots and tubers with high starch or inulin content, n.e.c., fresh": "rootnes",
       "Eggplants (aubergines)": "eggplant", "Figs": "fig", "Flax, raw or retted": "flax", "Fonio": "fonio", "Ginger, raw": "ginger", "Gooseberries": "gooseberry", "Grapes": "grape", "Green corn (maize)": "greencorn",
       "Green garlic": "garlic", "Groundnuts, excluding shelled": "groundnut", "Hazelnuts, in shell": "hazelnut", "Hempseed": "hempseed", "Hop cones": "hop", "Jute, raw or retted": "jute", "Kapok fruit": "kapokfiber",
       "Karite nuts (sheanuts)": "karite", "Kenaf, and other textile bast fibres, raw or retted": "jutelikefiber", "Kiwi fruit": "kiwi", "Kola nuts": "kolanut", "Lemons and limes": "lemonlime", "Lentils, dry": "lentil",
       "Lettuce and chicory": "lettuce", "Linseed": "linseed", "Locust beans (carobs)": "carob", "Lupins": "lupin", "Maize (corn)": "maize", "Mangoes, guavas and mangosteens": "mango", "Melonseed": "melonseed",
       "Millet": "millet", "Mixed grain": "mixedgrain", "Mustard seed": "mustard", "Natural rubber in primary forms": "rubber", "Nutmeg, mace, cardamoms, raw": "nutmeg", "Oats": "oats", "Oil palm fruit": "oilpalm",
       "Okra": "okra", "Olives": "olive", "Onions and shallots, dry (excluding dehydrated)": "onion", "Onions and shallots, green": "greenonion", "Oranges": "orange", "Other beans, green": "greenbean",
       "Other berries and fruits of the genus vaccinium n.e.c.": "berrynes", "Other citrus fruit, n.e.c.": "citrusnes", "Other fibre crops, raw, n.e.c.": "fibrenes", "Other fruits, n.e.c.": "fruitnes",
       "Other nuts (excluding wild edible nuts and groundnuts), in shell, n.e.c.": "nutnes", "Other oil seeds, n.e.c.": "oilseednes", "Other pulses n.e.c.": "pulsenes",
       "Other stimulant, spice and aromatic crops, n.e.c.": "spicenes", "Other stone fruits": "stonefruitnes", "Other sugar crops n.e.c.": "sugarnes", "Other tropical fruits, n.e.c.": "tropicalnes",
       "Other vegetables, fresh n.e.c.": "vegfor", "Papayas": "papaya", "Peaches and nectarines": "peachetc", "Pears": "pear", "Peas, dry": "pea", "Peas, green": "greenpea", "Pepper (Piper spp.), raw": "pepper",
       "Peppermint, spearmint": "peppermint", "Persimmons": "persimmon", "Pigeon peas, dry": "pigeonpea", "Pineapples": "pineapple", "Pistachios, in shell": "pistachio", "Plantains and cooking bananas": "plantain",
       "Plums and sloes": "plum", "Pomelos and grapefruits": "grapefruitetc", "Poppy seed": "poppy", "Potatoes": "potato", "Pumpkins, squash and gourds": "pumpkinetc", "Pyrethrum, dried flowers": "pyrethrum",
       "Quinces": "quince", "Quinoa": "quinoa", "Ramie, raw or retted": "ramie", "Rape or colza seed": "rapeseed", "Raspberries": "rasberry", "Rice": "rice", "Rye": "rye", "Safflower seed": "safflower",
       "Seed cotton, unginned": "cotton", "Sesame seed": "sesame", "Sisal, raw": "sisal", "Sorghum": "sorghum", "Sour cherries": "sourcherry", "Soya beans": "soybean", "Spinach": "spinach", "Strawberries": "strawberry",
       "String beans": "stringbean", "Sugar beet": "sugarbeet", "Sugar cane": "sugarcane", "Sunflower seed": "sunflower", "Sweet potatoes": "sweetpotato", "Tangerines, mandarins, clementines": "tangetc", "Taro": "taro",
       "Tea leaves": "tea", "Tomatoes": "tomato", "Triticale": "triticale", "True hemp, raw or retted": "hemp", "Tung nuts": "tung", "Unmanufactured tobacco": "tobacco", "Vanilla, raw": "vanilla", "Vetches": "vetch",
       "Walnuts, in shell": "walnut", "Watermelons": "watermelon", "Wheat": "wheat", "Yams": "yam", "Yautia": "yautia"}
# país de FAOSTAT -> código de tres letras de Natural Earth, donde el nombre no coincide
PAIS_FAO = {"Bolivia (Plurinational State of)": "BOL", "Venezuela (Bolivarian Republic of)": "VEN", "United States of America": "USA", "Russian Federation": "RUS", "Iran (Islamic Republic of)": "IRN",
            "Republic of Korea": "KOR", "Democratic People's Republic of Korea": "PRK", "Viet Nam": "VNM", "Lao People's Democratic Republic": "LAO", "Syrian Arab Republic": "SYR", "Türkiye": "TUR",
            "United Republic of Tanzania": "TZA", "Côte d'Ivoire": "CIV", "Democratic Republic of the Congo": "COD", "Congo": "COG", "Czechia": "CZE", "Republic of Moldova": "MDA", "China, mainland": "CHN",
            "United Kingdom of Great Britain and Northern Ireland": "GBR", "Netherlands (Kingdom of the)": "NLD", "Brunei Darussalam": "BRN", "Cabo Verde": "CPV", "Eswatini": "SWZ", "North Macedonia": "MKD",
            "Serbia": "SRB", "South Sudan": "SDS", "Sudan": "SDN", "Timor-Leste": "TLS", "Bahamas": "BHS", "Gambia": "GMB", "Micronesia (Federated States of)": "FSM", "China, Taiwan Province of": "TWN",
            "Palestine": "PSX", "Somalia": "SOM", "Kosovo": "KOS", "France": "FRA", "Norway": "NOR"}


def resumir_fao(zip_fao, salida):
    """Del archivo completo de FAOSTAT (producción de cultivos) deja solo la superficie cosechada promedio 2019-2021 por país y cultivo."""
    import zipfile, csv, io
    suma = {}
    with zipfile.ZipFile(zip_fao) as z:
        nom = next(m for m in z.namelist() if "All_Data" in m)
        for f in csv.DictReader(io.TextIOWrapper(z.open(nom), encoding="latin-1")):
            if f["Element Code"] != "5312" or f["Year"] not in ("2019", "2020", "2021") or int(f["Item Code"]) >= 1000 or int(f["Area Code"]) >= 5000 or not f["Value"]: continue
            k = (f["Area"].encode("latin-1").decode("utf-8", "replace") if "Ã" in f["Area"] else f["Area"], f["Item"]); s = suma.setdefault(k, [0.0, 0]); s[0] += float(f["Value"]); s[1] += 1
    with open(salida, "w", encoding="utf-8", newline="") as g:
        w = csv.writer(g); w.writerow(["Area", "Item", "Value"]); [w.writerow([a, i, round(v / n, 1)]) for (a, i), (v, n) in sorted(suma.items())]
    return len(suma)

def construir(zip_nc, shp, fao_csv, registro=print):
    import zipfile, tempfile, csv, shapefile, rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    r = shapefile.Reader(shp, encoding="utf-8"); regs = [None]; formas = []
    for i, sr in enumerate(r.iterShapeRecords()):
        a = sr.record.as_dict()
        if not sr.shape.points: continue
        regs.append(dict(nombre=a.get("name_es") or a.get("name") or "", local=a.get("name") or "", tipo=a.get("type_en") or "", pais=a.get("admin") or "", iso3=a.get("adm0_a3") or "")); formas.append((sr.shape.__geo_interface__, len(regs) - 1))
    registro(f"{len(regs) - 1} regiones; rasterizando…")
    ids = rasterize(formas, out_shape=(3600, 7200), transform=from_origin(-180, 90, 0.05, 0.05), fill=0, dtype="uint16", all_touched=False)
    N = len(regs); area = {}
    with zipfile.ZipFile(zip_nc) as z, tempfile.TemporaryDirectory() as tmp:
        for m in z.namelist():
            nom = os.path.basename(m).replace("CROPGRIDSv1.08_", "").replace(".nc", "")
            if not m.endswith(".nc") or nom not in NOMBRE: continue
            f = os.path.join(tmp, "x.nc"); open(f, "wb").write(z.read(m))
            try:
                with rasterio.open(f'netcdf:"{f}":harvarea') as s: a = s.read(1).astype("float64")
            except Exception as e: registro(f"{nom}: no se pudo leer ({str(e)[:60]})"); continue
            a[(a < 0) | (a > 1e6)] = 0.0; area[nom] = np.bincount(ids.ravel(), weights=a.ravel(), minlength=N)
    registro(f"{len(area)} cultivos sumados por región")
    claves = sorted(area); A = np.stack([area[k] for k in claves], 1)                       # [región, cultivo] en hectáreas
    def top(v, n):
        t = float(v.sum()); o = np.argsort(-v)[:n]
        return [[claves[j], int(round(v[j])), round(100 * float(v[j]) / t, 1)] for j in o if v[j] >= 50 and t > 0], int(round(t))
    for i in range(1, N): regs[i]["top"], regs[i]["ha"] = top(A[i], 12)
    paises = {}
    for iso in sorted({x["iso3"] for x in regs[1:]}):
        sel = [i for i in range(1, N) if regs[i]["iso3"] == iso]; t, ha = top(A[sel].sum(0), 15)
        paises[iso] = dict(nombre=regs[sel[0]]["pais"], top=t, ha=ha, fao=None)
    # ---- FAOSTAT: superficie cosechada oficial por país, promedio 2019-2021
    por_nombre = {v["nombre"]: k for k, v in paises.items()}; fao = {}
    for fila in csv.DictReader(open(fao_csv, encoding="utf-8")):
        iso = PAIS_FAO.get(fila["Area"]) or por_nombre.get(fila["Area"]); k = FAO.get(fila["Item"])
        if not iso or not k or iso not in paises: continue
        try: fao.setdefault(iso, {}); fao[iso][k] = fao[iso].get(k, 0.0) + float(fila["Value"])
        except ValueError: pass
    for iso, d in fao.items():
        t = sum(d.values()); o = sorted(d.items(), key=lambda x: -x[1])[:15]
        paises[iso]["fao"] = dict(top=[[k, int(round(v)), round(100 * v / t, 1)] for k, v in o if v >= 50], ha=int(round(t)))
    np.savez_compressed(F_GRILLA, ids=ids); json.dump(dict(regiones=regs, paises=paises, fuente_regiones="CROPGRIDS v1.08 (hacia 2020) sumado en regiones de Natural Earth 1:10m", fuente_fao="FAOSTAT, superficie cosechada, promedio 2019-2021"),
                                                      open(F_TABLA, "w"), ensure_ascii=False)
    registro(f"listo: {N - 1} regiones, {len(paises)} países, {sum(1 for p in paises.values() if p['fao'])} con FAOSTAT"); return N - 1


def disponible(): return os.path.exists(F_GRILLA) and os.path.exists(F_TABLA)

@functools.lru_cache(maxsize=1)
def _cargar(): return np.load(F_GRILLA)["ids"], json.load(open(F_TABLA))

def _lista(t, n): return [dict(clave=k, nombre=NOMBRE.get(k, k), ha=ha, pct=p) for k, ha, p in (t or [])[:n]]

def consultar(lon, lat, n=6):
    """Cultivos principales de la región y del país del punto: {region, pais, top_region, top_pais, fao_pais, coincidencia}. None si no hay dato."""
    if not disponible(): return None
    ids, T = _cargar(); fi, co = int((90 - lat) / 0.05), int((lon + 180) / 0.05)
    if not (0 <= fi < 3600 and 0 <= co < 7200) or not ids[fi, co]: return None
    r = T["regiones"][int(ids[fi, co])]; p = T["paises"].get(r["iso3"], {})
    out = dict(region=r["nombre"] or r["local"], tipo=r["tipo"], pais=r["pais"], iso3=r["iso3"], ha_region=r.get("ha", 0), top_region=_lista(r.get("top"), n), top_pais=_lista(p.get("top"), n),
               fao_pais=_lista((p.get("fao") or {}).get("top"), n), fuente_regiones=T["fuente_regiones"], fuente_fao=T["fuente_fao"])
    a, b = [x["clave"] for x in out["top_pais"]], [x["clave"] for x in out["fao_pais"]]
    out["coincidencia"] = dict(comunes=len(set(a) & set(b)), de=len(b)) if b else None
    return out

if __name__ == "__main__":
    construir(*sys.argv[1:4])
