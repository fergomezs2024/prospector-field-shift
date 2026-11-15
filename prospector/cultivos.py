"""Prospector · qué cultivar, dónde, cómo y en qué orden.

1. CULTIVOS POSIBLES. Cada cultivo de la biblioteca se simula día a día contra el clima REAL del lugar
   (NASA POWER 2001-hoy: temperatura, radiación, humedad, viento; lluvia GPM IMERG), probando una fecha de
   siembra cada 15 días. Para cada temporada se calcula:
     - duración del ciclo por suma térmica (grados-día),
     - agua: ETo Penman-Monteith FAO-56, ETc = Kc·ETo, balance de un depósito de suelo, ETa con estrés (Ks),
     - rendimiento relativo por agua: Y = 1 - Ky·(1 - ETa/ETc)   (FAO Riego y Drenaje 33),
     - daño por helada y por calor en floración, y ajuste por temperatura media fuera del rango óptimo.
   La mejor fecha de siembra es la de mayor rendimiento mediano en los años recientes.
2. ZONAS. El terreno cultivable se divide por relieve: plano, ladera suave, ladera, bajo húmedo.
3. ROTACIONES por zona: la actual + alternativas, comparadas en rendimiento, agua, erosión (RUSLE) y meses de suelo desnudo.
4. TÉCNICAS de siembra y protección, cada una con el dato que la justifica.

Parámetros de cultivo: valores típicos de FAO ECOCROP (rangos térmicos), FAO-56 (Kc, raíces, p) y FAO-33 (Ky).
Factores C de erosión por cultivo: Panagos et al. 2015 (Land Use Policy 48). Son valores generales, no de variedad local.
"""
import os, json, math, numpy as np, rasterio, requests
from affine import Affine

# clave: nombre, familia, grupo, Tbase, GDD del ciclo, Topt_min, Topt_max, Tabs_min, Tabs_max, helada (°C en floración), calor (°C en floración),
#        Kc ini/mid/fin, raíz m, p, Ky, C erosión, cobertura máx, residuo tras cosecha, tolera anegamiento, fija N, uso
_C = lambda *a: dict(zip(("nombre", "familia", "grupo", "tb", "gdd", "to1", "to2", "ta1", "ta2", "helada", "calor", "kc", "zr", "p", "ky", "cf", "fc", "res", "aneg", "fijan", "uso"), a))
CULTIVOS = {
    "trigo":    _C("Trigo", "gramíneas", "cereal de invierno", 0, 2000, 12, 23, 3, 32, -1, 32, (0.4, 1.15, 0.30), 1.3, 0.55, 1.05, 0.20, 0.90, 0.35, "media", False, "grano"),
    "cebada":   _C("Cebada", "gramíneas", "cereal de invierno", 0, 1750, 12, 22, 2, 32, -1, 32, (0.35, 1.15, 0.25), 1.2, 0.55, 1.00, 0.21, 0.90, 0.35, "baja", False, "grano"),
    "avena":    _C("Avena", "gramíneas", "cereal de invierno", 0, 1850, 12, 22, 3, 30, -1, 31, (0.35, 1.15, 0.25), 1.2, 0.55, 1.00, 0.20, 0.90, 0.35, "media", False, "grano y forraje"),
    "maiz":     _C("Maíz", "gramíneas", "cultivo de verano", 10, 1500, 18, 32, 10, 40, 0, 36, (0.35, 1.20, 0.45), 1.3, 0.55, 1.25, 0.38, 0.85, 0.30, "baja", False, "grano"),
    "sorgo":    _C("Sorgo", "gramíneas", "cultivo de verano", 10, 1450, 22, 34, 12, 42, 0, 39, (0.35, 1.05, 0.55), 1.5, 0.55, 0.90, 0.35, 0.80, 0.30, "media", False, "grano"),
    "lenteja":  _C("Lenteja", "leguminosas", "leguminosa de grano", 0, 1550, 12, 24, 4, 30, -2, 30, (0.4, 1.10, 0.30), 0.7, 0.50, 0.85, 0.32, 0.75, 0.10, "baja", True, "grano"),
    "garbanzo": _C("Garbanzo", "leguminosas", "leguminosa de grano", 0, 1750, 15, 28, 5, 34, -1, 33, (0.4, 1.00, 0.35), 0.9, 0.50, 0.85, 0.32, 0.70, 0.10, "baja", True, "grano"),
    "arveja":   _C("Arveja", "leguminosas", "leguminosa de grano", 3, 1400, 10, 22, 4, 28, -2, 28, (0.5, 1.15, 0.30), 0.8, 0.40, 1.15, 0.32, 0.80, 0.10, "baja", True, "grano"),
    "haba":     _C("Haba", "leguminosas", "leguminosa de grano", 0, 1750, 12, 23, 4, 30, -2, 29, (0.5, 1.15, 0.30), 0.7, 0.45, 1.15, 0.32, 0.80, 0.15, "media", True, "grano"),
    "poroto":   _C("Poroto (frijol)", "leguminosas", "cultivo de verano", 10, 1100, 17, 28, 10, 34, 1, 32, (0.4, 1.15, 0.35), 0.7, 0.45, 1.15, 0.32, 0.75, 0.10, "baja", True, "grano"),
    "soya":     _C("Soya", "leguminosas", "cultivo de verano", 10, 1300, 20, 32, 10, 38, 0, 36, (0.4, 1.15, 0.50), 1.0, 0.50, 0.85, 0.28, 0.85, 0.20, "media", True, "grano"),
    "raps":     _C("Raps (canola)", "crucíferas", "oleaginosa de invierno", 5, 1650, 12, 24, 4, 30, -2, 29, (0.35, 1.10, 0.35), 1.2, 0.60, 1.00, 0.30, 0.90, 0.20, "baja", False, "aceite"),
    "girasol":  _C("Girasol", "compuestas", "cultivo de verano", 6, 1650, 18, 30, 8, 38, 0, 36, (0.35, 1.10, 0.35), 1.3, 0.45, 0.95, 0.32, 0.80, 0.15, "baja", False, "aceite"),
    "papa":     _C("Papa", "solanáceas", "tubérculo", 5, 1250, 14, 22, 6, 30, -1, 30, (0.5, 1.15, 0.75), 0.5, 0.35, 1.10, 0.34, 0.80, 0.05, "baja", False, "alimento"),
    "quinoa":   _C("Quinoa", "amarantáceas", "grano andino", 3, 1500, 12, 24, 3, 32, -3, 33, (0.4, 1.00, 0.45), 0.9, 0.50, 0.90, 0.30, 0.75, 0.10, "baja", False, "grano"),
    "avena_vicia": _C("Avena con vicia (forraje)", "mezcla gramínea-leguminosa", "forraje y cobertura", 0, 1300, 10, 24, 2, 32, -4, 99, (0.5, 1.00, 0.85), 1.0, 0.55, 0.80, 0.08, 0.95, 0.45, "media", True, "forraje y cobertura del suelo"),
    "arroz":    _C("Arroz", "gramíneas", "cereal de verano (con mucha agua)", 10, 1900, 22, 32, 12, 40, 13, 36, (1.05, 1.20, 0.90), 0.6, 0.20, 1.10, 0.15, 0.90, 0.30, "alta", False, "grano"),
    "mijo":     _C("Mijo", "gramíneas", "cultivo de verano", 10, 1100, 20, 35, 10, 42, 2, 42, (0.30, 1.00, 0.30), 1.5, 0.55, 0.90, 0.30, 0.75, 0.25, "baja", False, "grano"),
    "centeno":  _C("Centeno", "gramíneas", "cereal de invierno", 0, 1900, 10, 22, 2, 30, -3, 31, (0.35, 1.15, 0.25), 1.3, 0.60, 1.00, 0.20, 0.90, 0.35, "baja", False, "grano"),
    "mani":     _C("Maní", "leguminosas", "cultivo de verano", 10, 1500, 22, 30, 14, 38, 2, 37, (0.40, 1.15, 0.60), 0.8, 0.50, 0.70, 0.32, 0.80, 0.10, "baja", True, "grano y aceite"),
    "algodon":  _C("Algodón", "malváceas", "cultivo de verano", 15, 1300, 25, 35, 16, 42, 2, 40, (0.35, 1.18, 0.60), 1.3, 0.65, 0.85, 0.50, 0.85, 0.20, "baja", False, "fibra"),
    "yuca":     _C("Yuca (mandioca)", "euforbiáceas", "raíz tropical", 13, 3200, 24, 32, 16, 38, 5, 99, (0.30, 0.80, 0.30), 0.7, 0.35, 0.70, 0.34, 0.80, 0.10, "baja", False, "alimento"),
    # hortalizas e industriales: Kc, raíz y p de FAO-56 (tablas 12, 17 y 22); Ky de FAO-33. Rangos térmicos generales. Sin calendario local (GGCMI no los trae).
    "tomate":   _C("Tomate", "solanáceas", "hortaliza de verano", 10, 1400, 18, 27, 10, 35, 1, 35, (0.60, 1.15, 0.80), 1.0, 0.40, 1.05, 0.34, 0.80, 0.05, "baja", False, "alimento"),
    "aji":      _C("Ají y pimiento", "solanáceas", "hortaliza de verano", 10, 1500, 18, 28, 10, 35, 1, 34, (0.60, 1.05, 0.90), 0.75, 0.30, 1.10, 0.34, 0.75, 0.05, "baja", False, "alimento"),
    "cebolla":  _C("Cebolla", "aliáceas", "hortaliza de estación fría", 5, 1500, 13, 24, 5, 30, -2, 32, (0.70, 1.05, 0.75), 0.45, 0.30, 1.10, 0.34, 0.60, 0.05, "baja", False, "alimento"),
    "repollo":  _C("Repollo", "crucíferas", "hortaliza de estación fría", 4, 1300, 13, 22, 4, 30, -3, 30, (0.70, 1.05, 0.95), 0.6, 0.45, 0.95, 0.34, 0.80, 0.05, "baja", False, "alimento"),
    "sandia":   _C("Sandía", "cucurbitáceas", "hortaliza de verano", 10, 1200, 22, 32, 12, 38, 1, 38, (0.40, 1.00, 0.75), 1.1, 0.40, 1.10, 0.34, 0.75, 0.05, "baja", False, "alimento"),
    "remolacha": _C("Remolacha azucarera", "amarantáceas", "raíz industrial", 3, 2400, 15, 25, 4, 35, -3, 99, (0.35, 1.20, 0.70), 1.0, 0.55, 1.00, 0.34, 0.90, 0.10, "baja", False, "azúcar"),
    "cartamo":  _C("Cártamo", "compuestas", "oleaginosa", 5, 1900, 15, 28, 5, 38, -2, 38, (0.35, 1.10, 0.25), 1.5, 0.60, 0.80, 0.28, 0.80, 0.15, "baja", False, "aceite"),
    "tabaco":   _C("Tabaco", "solanáceas", "cultivo industrial de verano", 10, 1300, 20, 30, 12, 36, 1, 38, (0.50, 1.15, 0.80), 0.6, 0.50, 0.90, 0.49, 0.80, 0.05, "baja", False, "hoja"),
    "alfalfa":  _C("Alfalfa", "leguminosas", "forraje permanente", 5, 99999, 15, 30, 3, 38, -8, 99, (0.4, 0.95, 0.90), 1.5, 0.55, 1.10, 0.05, 0.95, 0.80, "baja", True, "forraje"),
}
DEBILES = {"haba": 3, "aji": 3, "arveja": 2, "repollo": 2}      # de cada 10 lugares donde se siembra, cuántos no reconoce (validacion/INFORME_dirigida_53.md)
VERSION = 14            # subir cuando cambie el método: las copias guardadas con otra versión se recalculan
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def _clima(d, G):
    """Clima diario del terreno (NASA POWER). Si la descarga larga aún no terminó, se pide directo."""
    f = f"{d}/clima.json"
    if not os.path.exists(f):
        par = "T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR,IMERG_PRECTOT"
        import datetime
        fin = datetime.date.today().year - 1
        r = requests.get(f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={par}&community=AG&latitude={G['centro'][1]:.4f}&longitude={G['centro'][0]:.4f}"
                         f"&start=20010101&end={fin}1231&format=JSON&time-standard=UTC", timeout=600); r.raise_for_status()
        json.dump(r.json(), open(f, "w"))
    return leer_clima(f)

def leer_clima(f):
    """Series diarias de un archivo de NASA POWER: lluvia (IMERG, o MERRA-2 corregida donde falta), temperaturas, humedad, viento y radiación."""
    par = json.load(open(f))["properties"]["parameter"]; fechas = sorted(par["T2M"])
    g = lambda k: np.array([par[k][x] for x in fechas], float)
    P = g("IMERG_PRECTOT"); P2 = g("PRECTOTCORR"); P = np.where(P < -900, P2, P)
    out = dict(P=P, Tx=g("T2M_MAX"), Tn=g("T2M_MIN"), Tm=g("T2M"), RH=g("RH2M"), U2=g("WS2M"), Rs=g("ALLSKY_SFC_SW_DWN"))
    for k, v in out.items():
        bad = v < -900
        if bad.any() and (~bad).any(): v[bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], v[~bad])
    anio = np.array([int(x[:4]) for x in fechas]); mes = np.array([int(x[4:6]) for x in fechas])
    J = np.array([(np.datetime64(f"{x[:4]}-{x[4:6]}-{x[6:]}") - np.datetime64(f"{x[:4]}-01-01")).astype(int) + 1 for x in fechas])
    return out, anio, mes, J

def _eto(c, J, lat_grados, z):
    """ETo de referencia, Penman-Monteith FAO-56 (ec. 6), mm/día."""
    lat = math.radians(lat_grados); Tx, Tn, Tm, RH, U2, Rs = c["Tx"], c["Tn"], c["Tm"], c["RH"], c["U2"], c["Rs"]
    Pa = 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26; gam = 0.000665 * Pa
    es = (0.6108 * np.exp(17.27 * Tx / (Tx + 237.3)) + 0.6108 * np.exp(17.27 * Tn / (Tn + 237.3))) / 2; ea = es * RH / 100
    delta = 4098 * (0.6108 * np.exp(17.27 * Tm / (Tm + 237.3))) / (Tm + 237.3) ** 2
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365); dec = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(lat) * np.tan(dec), -1, 1))
    Ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.sin(ws))
    Rso = np.maximum((0.75 + 2e-5 * z) * Ra, 0.1)
    Rn = 0.77 * Rs - 4.903e-9 * (((Tx + 273.16) ** 4 + (Tn + 273.16) ** 4) / 2) * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0))) * (1.35 * np.clip(Rs / Rso, 0.3, 1) - 0.35)
    return np.maximum((0.408 * delta * Rn + gam * 900 / (Tm + 273) * U2 * (es - ea)) / (delta + gam * (1 + 0.34 * U2)), 0)

def _temporada(cu, k0, L, awc, riego=False, diario=False):
    """Simula un cultivo sembrado el día k0. L: listas diarias (P, ETo, Tx, Tn, Tm). Devuelve dict o None si no completa el ciclo."""
    P, E, Tx, Tn, Tm = L; n = len(P); tb, gddT = cu["tb"], cu["gdd"]; kci, kcm, kcf = cu["kc"]; perenne = gddT > 90000
    # agua en el suelo al sembrar: 180 días de barbecho. La capa de arriba (30 cm) se seca por evaporación; lo que le sobra de lluvia
    # baja y se guarda en el suelo profundo. Así las raíces, al crecer, encuentran el agua que de verdad dejó la temporada anterior
    # (antes se suponía húmedo todo el suelo profundo, lo que regalaba agua en zonas secas).
    taw0 = awc * 0.3 * 1000; D = taw0 * 0.5; cap = max(awc * (cu["zr"] - 0.3) * 1000, 1e-6); hondo = 0.0
    for t in range(max(k0 - 180, 0), k0):
        D -= P[t] * 0.85
        if D < 0: hondo = min(hondo - D, cap); D = 0.0
        ks = 1.0 if D <= 0.5 * taw0 else max((taw0 - D) / (0.5 * taw0), 0.0); D = min(D + ks * 0.3 * E[t], taw0)
    seco_hondo = 1.0 - hondo / cap; zr_ant = 0.3
    humedo_al_sembrar = D <= 0.6 * taw0          # la capa de arriba guarda al menos 40 % de su agua útil (lluvia de la temporada anterior o deshielo)
    gdd = 0.0; etc = eta = lluvia = tsum = 0.0; nact = 0; helada = 0; calor = 0; dias = 0; serie = []; tflor = 0.0; nflor = 0
    lluvia_siembra = sum(P[max(k0 - 10, 0):min(k0 + 10, n)])      # para sembrar tiene que haber llovido (o regarse)
    maxd = 365 if perenne else cu.get("maxd", 250)
    for t in range(k0, min(k0 + maxd, n)):
        tm = Tm[t]; gdd += max(min(tm, cu["ta2"]) - tb, 0.0); f = min(dias / 365.0, 1.0) if perenne else gdd / gddT
        if perenne: kc = kcm; fr = 1.0; fc = cu["fc"]
        elif f < 0.15: kc = kci; fr = 0.25; fc = 0.10 + 0.15 * f / 0.15
        elif f < 0.45: x = (f - 0.15) / 0.30; kc = kci + (kcm - kci) * x; fr = 0.25 + 0.75 * x; fc = 0.25 + (cu["fc"] - 0.25) * x
        elif f < 0.80: kc = kcm; fr = 1.0; fc = cu["fc"]
        else: x = min((f - 0.80) / 0.20, 1.0); kc = kcm + (kcf - kcm) * x; fr = 1.0; fc = cu["fc"] * (1 - 0.35 * x)
        zr = max(0.3, cu["zr"] * fr); taw = awc * zr * 1000; raw = cu["p"] * taw
        if zr > zr_ant: D += (zr - zr_ant) * awc * 1000 * seco_hondo; zr_ant = zr         # la raíz entra a suelo nuevo, tan seco como lo dejó el barbecho
        D -= P[t] * 0.85
        if D < 0:                                           # la lluvia que sobra sigue bajando y moja el suelo que la raíz aún no alcanza
            hondo = min(hondo - D, cap); seco_hondo = 1.0 - hondo / cap; D = 0.0
        if riego and D > raw: D = 0.0
        ks = 1.0 if D <= raw else max((taw - D) / max(taw - raw, 1e-6), 0.0)
        e_c = kc * E[t]; e_a = ks * e_c; D = min(D + e_a, taw); etc += e_c; eta += e_a; lluvia += P[t]; dias += 1
        if tm > tb + 2: tsum += tm; nact += 1                    # la temperatura se juzga en los días en que la planta crece (no en el reposo de invierno), también en las praderas permanentes
        if not perenne and 0.40 <= f <= 0.78:
            tflor += tm; nflor += 1
            if Tn[t] < cu["helada"]: helada += 1
            if 0.50 <= f <= 0.65 and Tx[t] > cu["calor"]: calor += 1       # el calor daña en la floración misma (unas dos semanas), no en todo el llenado
        if diario: serie.append((t, fc, ks, f))
        if not perenne and f >= 1.0: break
    else:
        if not perenne: return None                       # no alcanzó a madurar (demasiado frío)
    if dias < 45 and not perenne: return None             # ciclo irreal (demasiado calor)
    yw = max(1 - cu["ky"] * (1 - eta / max(etc, 1e-6)), 0.0)
    tmed = tsum / max(nact, 1)
    yt = 1.0 if cu["to1"] <= tmed <= cu["to2"] else (max((tmed - cu["ta1"]) / max(cu["to1"] - cu["ta1"], 1e-6), 0.0) if tmed < cu["to1"] else max((cu["ta2"] - tmed) / max(cu["ta2"] - cu["to2"], 1e-6), 0.0))
    yh = (0.45 if helada >= 1 else 1.0) * (0.6 if helada >= 4 else 1.0); yc = max(1 - 0.03 * calor, 0.4)
    # la floración necesita temperatura: si cae en la época fría el cultivo no cuaja (aproxima el efecto de fotoperíodo y vernalización)
    yf = 1.0 if perenne or nflor == 0 else min(max((tflor / nflor - (cu["to1"] - 5)) / 5.0, 0.15), 1.0)
    ye = 1.0 if (riego or perenne or lluvia_siembra >= 20 or humedo_al_sembrar) else 0.55        # siembra en seco: mala emergencia
    return dict(y=yw * yt * yh * yc * yf * ye, yf=yf, ye=ye, yw=yw, yt=yt, yh=yh, yc=yc, etc=etc, eta=eta, lluvia=lluvia, dias=dias, helada=helada, calor=calor, fin=k0 + dias, serie=serie)

def _suelo(d):
    """Agua útil del suelo (Saxton & Rawls 2006) con la textura de SoilGrids del terreno; carbono fijado en 1,2 % (SoilGrids lo sobrestima)."""
    try:
        cl = np.nanmedian(rasterio.open(f"{d}/suelo_clay.tif").read(1)) / 10; sa = np.nanmedian(rasterio.open(f"{d}/suelo_sand.tif").read(1)) / 10
        if not (np.isfinite(cl) and np.isfinite(sa)): raise ValueError
        return dict(suelo_de(float(cl), float(sa)), supuesto=False)
    except Exception: return dict(suelo_de(25.0, 40.0), supuesto=True)        # sin dato de suelo: se usa un suelo medio y se avisa

def suelo_de(cl, sa):
    """Agua útil y erodabilidad a partir de arcilla y arena (%)."""
    S, C, O = sa / 100, cl / 100, 2.0
    t1500 = -0.024 * S + 0.487 * C + 0.006 * O + 0.005 * S * O - 0.013 * C * O + 0.068 * S * C + 0.031; wp = t1500 + (0.14 * t1500 - 0.02)
    t33 = -0.251 * S + 0.195 * C + 0.011 * O + 0.006 * S * O - 0.027 * C * O + 0.452 * S * C + 0.299; fcap = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    silt = max(100 - cl - sa, 0); soc = 1.2; SN = 1 - S
    kw = ((0.2 + 0.3 * math.exp(-0.0256 * sa * (1 - silt / 100))) * (silt / max(cl + silt, 1e-6)) ** 0.3 * (1 - 0.25 * soc / (soc + math.exp(3.72 - 2.95 * soc))) * (1 - 0.7 * SN / (SN + math.exp(-5.51 + 22.9 * SN))))
    tex = "arcilloso" if cl >= 40 else ("franco arcilloso" if cl >= 27 else ("arenoso" if sa >= 70 else ("franco arenoso" if sa >= 52 else "franco")))
    return dict(arcilla=round(float(cl)), arena=round(float(sa)), awc=float(np.clip(fcap - wp, 0.06, 0.24)), k_rusle=kw * 0.1317, textura=tex)

def _fase(f, perenne):
    if perenne: return "pradera establecida"
    return "recién sembrado" if f < 0.15 else ("creciendo" if f < 0.45 else ("en flor y llenando grano" if f < 0.80 else "madurando"))

def _prueba_fechas(cu, dias_j, idx0, recientes, L, n, awc):
    """Prueba cada fecha de siembra en cada año reciente, sin riego y con riego. Devuelve la mejor, la mejor con riego y todas."""
    mejor = None; mejor_r = None; por_j = {}
    for j0 in dias_j:
        ys, yr, det = [], [], []
        for a in recientes[:-1]:
            k0 = idx0[a] + j0 - 1
            if k0 + 200 >= n: continue
            s = _temporada(cu, k0, L, awc); ys.append(s["y"] if s else 0.0); det.append(s)
            s2 = _temporada(cu, k0, L, awc, riego=True); yr.append(s2["y"] if s2 else 0.0)
        if len(ys) < 6: continue
        m = float(np.median(ys)); por_j[j0] = dict(m=m, j0=j0, ys=ys, yr=yr, det=det)
        if mejor is None or m > mejor["m"]: mejor = por_j[j0]
        mr = float(np.median(yr))
        if mejor_r is None or mr > mejor_r[0]: mejor_r = (mr, j0)
    return mejor, mejor_r, por_j

def evaluar(c, anio, mes, J, lat, z, awc, lon=None, usar_calendario=True, solo=None):
    """Qué cultivos se dan con este clima y este suelo. Si hay calendario mundial para la zona, el ciclo de cada cultivo
    se ajusta a la variedad que se usa ahí (grados-día acumulados entre la siembra y la cosecha locales)."""
    from . import calendario
    ETo = _eto(c, J, lat, z)
    L = [x.tolist() for x in (c["P"], ETo, c["Tx"], c["Tn"], c["Tm"])]; n = len(L[0]); anios = sorted(set(anio.tolist()))
    recientes = [a for a in anios if a >= anios[-1] - 14]; antes = [a for a in anios if a < recientes[0]]
    Pan = {a: float(c["P"][anio == a].sum()) for a in anios}
    # años tipo reales (sin el último: su temporada no cabe completa en los datos)
    ordenados = sorted(recientes[:-1], key=lambda a: Pan[a]); tipo = dict(seco=ordenados[max(1, len(ordenados) // 10)], normal=ordenados[len(ordenados) // 2], lluvioso=ordenados[-max(2, len(ordenados) // 10)])
    idx0 = {a: int(np.where(anio == a)[0][0]) for a in anios}
    heladas = {a: int(((c["Tn"] < 0) & (anio == a)).sum()) for a in anios}
    clima = dict(lluvia_reciente=round(np.mean([Pan[a] for a in recientes])), lluvia_antes=round(np.mean([Pan[a] for a in antes])) if antes else None,
                 periodo_reciente=[recientes[0], recientes[-1]], periodo_antes=[antes[0], antes[-1]] if antes else None, eto_anual=round(float(ETo.sum() / len(anios))),
                 temp_media=round(float(c["Tm"].mean()), 1), heladas_por_anio=round(float(np.mean([heladas[a] for a in recientes])), 1),
                 dias_calor_35=round(float(np.mean([((c["Tx"] >= 35) & (anio == a)).sum() for a in recientes])), 1), anios_tipo=tipo, lluvia_por_anio={str(a): round(Pan[a]) for a in anios})
    cal = calendario.consultar(lon, lat) if (usar_calendario and lon is not None and calendario.disponible()) else {}
    dia_mes = lambda j: int(mes[idx0[recientes[0]] + (j - 1) % 365])
    # ---------- cada cultivo, cada fecha de siembra, cada año
    res_c = []
    for clave, cu0 in CULTIVOS.items():
        if solo and clave not in solo: continue
        cu = cu0; local = None; mejor = None
        for cod, etiqueta, ref in calendario.CODIGOS.get(clave, []):                    # variantes locales del cultivo
            k = (cal.get(cod) or {}).get("rf")
            if not k: continue
            gl = [sum(max(min(L[4][t], cu0["ta2"]) - cu0["tb"], 0.0) for t in range(idx0[a] + k["siembra"] - 1, min(idx0[a] + k["siembra"] - 1 + k["dias"], n))) for a in recientes[:-2]]
            g = float(np.median(gl)) if gl else 0.0
            if g < 250: continue                                                        # el calendario de la celda no calza con este clima (montaña, costa)
            g = float(np.clip(g, 0.75 * cu0["gdd"], 1.30 * cu0["gdd"]))                     # el calendario es grueso (55 km, por meses): ajusta el ciclo, pero sin salirse de lo que el cultivo puede dar
            cu_l = dict(cu0, gdd=g, maxd=max(250, min(k["dias"] + 60, 365)))
            mj, mr, por_j = _prueba_fechas(cu_l, sorted(set(list(range(1, 366, 15)) + [k["siembra"]])), idx0, recientes, L, n, awc)
            if mj is None: continue
            obs = por_j.get(k["siembra"])
            if obs and obs["m"] >= 0.85 * mj["m"]: mj = obs                             # si la fecha de la zona rinde casi lo mismo, manda la práctica local
            if mejor is None or mj["m"] > mejor["m"]: mejor, mejor_r, cu, local = mj, mr, cu_l, dict(k, etiqueta=etiqueta, referencia=ref, grados_dia=round(g))
        if mejor is None: mejor, mejor_r, _ = _prueba_fechas(cu0, range(1, 366, 15), idx0, recientes, L, n, awc)
        if mejor is None: continue
        ok = [x for x in mejor["det"] if x]; nb = sum(1 for y in mejor["ys"] if y >= 0.6)
        calend = None
        if local:
            dif = abs((mejor["j0"] - local["siembra"] + 182) % 365 - 182)
            calend = dict(fuente=f"Calendario mundial de cultivos GGCMI ({local['fuente']})", variante=local["etiqueta"], referencia=local["referencia"], siembra_mes=dia_mes(local["siembra"]), cosecha_mes=dia_mes(local["cosecha"]),
                          ciclo_dias=local["dias"], grados_dia_local=local["grados_dia"], grados_dia_general=cu0["gdd"], diferencia_dias=int(dif), coincide=bool(dif <= 31))
        if not ok:
            res_c.append(dict(clave=clave, nombre=cu["nombre"], familia=cu["familia"], grupo=cu["grupo"], apto=0.0, buenos_de_10=0, veredicto="no se da", fijan=cu["fijan"], uso=cu["uso"], cf=cu["cf"], riego_mm=0, agua_mm=0, meses_cubierto=0,
                              porque="No alcanza a completar su ciclo con las temperaturas de este lugar.", riesgos=[], mensual={}, calendario=calend)); continue
        med = lambda k: float(np.median([x[k] for x in ok])); dias = med("dias"); etc = med("etc"); eta = med("eta")
        mes_s = dia_mes(mejor["j0"]); mes_c = dia_mes(mejor["j0"] + int(dias))
        ph = sum(1 for x in ok if x["helada"] >= 1) / len(ok); pc = sum(1 for x in ok if x["calor"] >= 5) / len(ok); psq = sum(1 for x in ok if x["yw"] < 0.6) / len(ok)
        y_riego = mejor_r[0]; mes_riego = dia_mes(mejor_r[1]); b10 = int(round(nb / len(mejor["ys"]) * 10)); riesgos = []
        if psq >= 0.2: riesgos.append(dict(tipo="sequía", de_10=int(round(psq * 10)), texto=f"le falta agua en {int(round(psq * 10))} de cada 10 años"))
        if ph >= 0.15: riesgos.append(dict(tipo="helada", de_10=int(round(ph * 10)), texto=f"hiela en plena floración en {int(round(ph * 10))} de cada 10 años"))
        if pc >= 0.2: riesgos.append(dict(tipo="calor", de_10=int(round(pc * 10)), texto=f"hace demasiado calor en la floración en {int(round(pc * 10))} de cada 10 años"))
        yt = med("yt"); fallos = int(round(sum(1 for y in mejor["ys"] if y < 0.25) / len(mejor["ys"]) * 10))
        if b10 >= 7: ver = "se da bien"
        elif b10 >= 4: ver = "se da, con riesgo"
        elif mejor["m"] >= 0.35 and fallos <= 2 and 1 - (1 - med("yw")) / max(cu["ky"], 1e-6) >= 0.5: ver = "se da, con cosecha baja"      # secano de bajo rendimiento: rinde poco, pero casi nunca se pierde; la lluvia tiene que cubrir al menos la mitad del agua que el cultivo necesita
        elif y_riego >= 0.4 and psq >= 0.3: ver = "solo con riego"               # con riego se da; si rinde menos de 70 % el texto dice que es con cosecha limitada
        else: ver = "no se recomienda"
        if yt < 0.6 and ver != "se da bien": ver = "no se recomienda"
        por = (f"Sembrado en {MESES[mes_s - 1]}, sale bien {b10} de cada 10 años sin riego." if ver in ("se da bien", "se da, con riesgo") else
               f"Sembrado en {MESES[mes_s - 1]}, se cosecha casi todos los años, pero poco: cerca de {int(round(mejor['m'] * 100))} % de lo que daría con agua suficiente." if ver == "se da, con cosecha baja" else
               (f"Sin riego solo sale bien {b10} de cada 10 años; con riego sí se da, sembrando en {MESES[mes_riego - 1]}." + ("" if y_riego >= 0.7 else f" Aun con riego rinde cerca de {int(round(y_riego * 100))} % de lo normal, por la temperatura.") if ver == "solo con riego" else
                ("La temperatura de este lugar no le acomoda." if yt < 0.6 else f"Sale bien solo {b10} de cada 10 años.")))
        if riesgos and ver != "no se recomienda": por += " Ojo: " + "; ".join(r["texto"] for r in riesgos) + "."
        if calend and ver != "no se recomienda":
            fem = calend["variante"].split()[0] in ("cebada", "avena", "arveja", "lenteja", "haba", "soya", "papa", "yuca")
            quien = f"{'la' if fem else 'el'} {calend['variante']}" if not calend["referencia"] else f"las {calend['referencia']}" if calend["referencia"].startswith("legumbres") else f"la {calend['referencia']}"
            por += (f" En esta zona {quien} se siembra normalmente en {MESES[calend['siembra_mes'] - 1]}" + (": coincide." if calend["coincide"] else f"; la simulación prefiere {MESES[mes_s - 1]}, conviene consultarlo con alguien del lugar."))
        mensual = {}
        if solo is None:                                    # series mensuales para la simulación (año seco, normal y lluvioso reales)
            for nom, a in tipo.items():
                k0 = idx0[a] + mejor["j0"] - 1; s = _temporada(cu, k0, L, awc, diario=True) if k0 + 200 < n else None
                m12 = [dict(fc=0.0, ks=1.0, fase="suelo sin cultivo") for _ in range(12)]
                if s:
                    acum = {}
                    for tt, fc, ks, f in s["serie"]: acum.setdefault(int(mes[tt]), []).append((fc, ks, f))
                    for mm, v in acum.items(): m12[mm - 1] = dict(fc=round(float(np.mean([x[0] for x in v])), 2), ks=round(float(np.mean([x[1] for x in v])), 2), fase=_fase(float(np.mean([x[2] for x in v])), cu["gdd"] > 90000))
                    fin_m = int(mes[min(s["fin"], n - 1)])
                    for q in range(1, 4):                                   # rastrojo los 3 meses siguientes a la cosecha
                        mm = (fin_m - 1 + q) % 12
                        if m12[mm]["fase"] == "suelo sin cultivo": m12[mm] = dict(fc=round(cu["res"], 2), ks=1.0, fase="rastrojo")
                mensual[nom] = m12
        res_c.append(dict(clave=clave, nombre=cu["nombre"], familia=cu["familia"], grupo=cu["grupo"], fijan=cu["fijan"], uso=cu["uso"], apto=round(mejor["m"], 2), con_riego=round(y_riego, 2), siembra_mes_riego=mes_riego,
                          buenos_de_10=b10, fallos_de_10=fallos, veredicto=ver, porque=por, riesgos=riesgos, siembra_mes=mes_s, cosecha_mes=mes_c, ciclo_dias=int(round(dias)), calendario=calend,
                          agua_mm=int(round(etc)), lluvia_cubre_pct=int(round(eta / max(etc, 1e-6) * 100)), riego_mm=int(round(max(etc - eta, 0))),
                          meses_cubierto=sum(1 for x in mensual.get("normal", []) if x["fc"] >= 0.3), mensual=mensual, cf=cu["cf"],
                          tecnico=dict(rend_relativo_mediano=round(mejor["m"], 2), factor_agua=round(med("yw"), 2), factor_temperatura=round(yt, 2), factor_floracion=round(med("yf"), 2), factor_emergencia=round(med("ye"), 2), dia_siembra=mejor["j0"],
                                       prob_helada_floracion=round(ph, 2), prob_calor_floracion=round(pc, 2), prob_deficit_hidrico=round(psq, 2), rend_por_anio=[round(y, 2) for y in mejor["ys"]],
                                       parametros=dict(Tbase=cu["tb"], grados_dia=round(cu["gdd"]) if cu["gdd"] < 90000 else None, Kc=cu["kc"], raiz_m=cu["zr"], p=cu["p"], Ky=cu["ky"], C_erosion=cu["cf"]))))
    # ---------- lo que se cultiva de verdad en la zona (dato observado; no cambia el veredicto, lo acompaña)
    if solo is None and lon is not None:
        from . import cultivado
        if cultivado.disponible():
            try: sup, ren = cultivado.superficie(lon, lat), cultivado.rendimiento(lon, lat)
            except Exception: sup, ren = {}, {}
            for x in res_c:
                o = sup.get(x["clave"])
                if o is None: continue
                x["observado"] = dict(pct_zona=o["pct_zona"], pct_celda=o["pct_celda"], rendimiento=ren.get(x["clave"]))
                r = ren.get(x["clave"]); frase = (f" En esta zona sí se siembra: ocupa cerca de {o['pct_zona']:.0f} % de la tierra." if o["pct_zona"] >= 1 else (" En esta zona se siembra poco." if o["pct_zona"] >= 0.05 else " No figura sembrado en esta zona."))
                if r and o["pct_zona"] >= 0.05: frase += f" Rendimiento medido en la zona: {r['t_ha']:.1f} toneladas por hectárea (entre {r['minimo']:.1f} y {r['maximo']:.1f} según el año)."
                x["porque"] += frase
    return dict(cultivos=res_c, clima=clima, tipo=tipo, recientes=recientes, Pan=Pan)

def analizar(d, actual=None, registro=print):
    G = json.load(open(f"{d}/meta.json")); T = json.load(open(f"{d}/terreno.json")); t = np.load(f"{d}/terreno.npz"); masc = t["mascara"]
    cl = np.load(f"{d}/cultivo.npz")["clase"] if os.path.exists(f"{d}/cultivo.npz") else None
    c, anio, mes, J = _clima(d, G); lat = G["centro"][1]; z = T["altitud_media_m"]; su = _suelo(d)
    ev = evaluar(c, anio, mes, J, lat, z, su["awc"], lon=G["centro"][0]); res_c, clima, recientes, Pan = ev["cultivos"], ev["clima"], ev["recientes"], ev["Pan"]
    orden = {"se da bien": 0, "se da, con riesgo": 1, "se da, con cosecha baja": 1.5, "solo con riego": 2, "no se recomienda": 3, "no se da": 4}
    res_c.sort(key=lambda x: (orden[x["veredicto"]], -x["apto"])); por_clave = {x["clave"]: x for x in res_c}
    aptos = [x for x in res_c if x["veredicto"] in ("se da bien", "se da, con riesgo", "se da, con cosecha baja")]
    # ---------- 2. zonas del terreno cultivable
    pend = t["pendiente_pct"]; twi = t["twi"]; acc_ha = t["acumulacion"] * G["res"] ** 2 / 1e4
    cult = masc & (np.isin(cl, [1, 2]) if cl is not None else np.ones_like(masc))        # solo lo cultivable hoy: lo que tiene árboles o matorral queda fuera del plan
    from scipy.ndimage import distance_transform_edt
    cerca = distance_transform_edt(~(acc_ha >= 5)) * G["res"] <= 60
    zona = np.zeros(masc.shape, "uint8")
    zona[cult & (pend < 5)] = 1; zona[cult & (pend >= 5) & (pend < 8)] = 2; zona[cult & (pend >= 8)] = 3
    zona[cult & (pend < 3) & cerca & (twi >= np.nanpercentile(twi[masc], 75))] = 4
    ha_c = G["res"] ** 2 / 1e4; gy_s = np.sin(np.arctan(pend / 100)); As = np.minimum(t["acumulacion"] * G["res"], 300)
    LS = (As / 22.13) ** 0.4 * (np.maximum(gy_s, 0.001) / 0.0896) ** 1.3
    Rr = float(np.mean([0.0483 * Pan[a] ** 1.61 if Pan[a] < 850 else 587.8 - 1.219 * Pan[a] + 0.004105 * Pan[a] ** 2 for a in recientes]))
    NOMZ = {1: ("Plano", "Lo más fácil de trabajar: casi sin pendiente."), 2: ("Ladera suave", "Pendiente de 5 a 8 %: se puede sembrar, cuidando que la lluvia no arrastre tierra."),
            3: ("Ladera", "Pendiente de 8 a 15 %: el suelo se pierde con facilidad si queda desnudo."), 4: ("Bajo húmedo", "Parte baja junto al cauce: recibe agua de arriba y puede encharcarse en la época de lluvias.")}
    hileras = {"maiz", "girasol", "papa", "poroto", "soya", "sorgo", "algodon", "mani", "yuca", "mijo"}
    if actual not in por_clave: actual = next((x["clave"] for x in aptos if x["grupo"].startswith("cereal")), aptos[0]["clave"] if aptos else res_c[0]["clave"])
    zonas = []
    for k in (1, 2, 3, 4):
        mz = zona == k
        if mz.sum() * ha_c < 0.05: continue
        ls = float(np.nanmean(LS[mz])); pm = float(pend[mz].mean())
        def nota(x):
            v = x["apto"]
            if k in (2, 3) and x["clave"] in hileras: v *= 0.7 if k == 2 else 0.5
            if k == 4 and CULTIVOS[x["clave"]]["aneg"] == "baja": v *= 0.55
            if k == 3 and x["cf"] <= 0.1: v *= 1.15
            return v
        cand = sorted(aptos, key=nota, reverse=True); evitar = []
        if k in (2, 3): evitar = [x["nombre"] for x in aptos if x["clave"] in hileras]
        if k == 4: evitar = [x["nombre"] for x in aptos if CULTIVOS[x["clave"]]["aneg"] == "baja"]
        usable = [x for x in cand if x["nombre"] not in evitar] or cand
        prin = next((x for x in usable if not x["fijan"] and x["cf"] > 0.1), usable[0] if usable else None)
        leg = next((x for x in usable if x["fijan"] and x["cf"] > 0.1 and x["familia"] != (prin or {}).get("familia")), None)
        ter = next((x for x in usable if prin and x["familia"] not in (prin["familia"], (leg or {}).get("familia")) and x["cf"] > 0.1), None)
        cob = next((x for x in usable if x["cf"] <= 0.1), None)
        def estrategia(nombre, seq, nota_s):
            cs = [por_clave[q] for q in seq if q in por_clave]
            if not cs: return None
            ero = float(np.mean([Rr * su["k_rusle"] * ls * x["cf"] for x in cs])); fam_rep = any(cs[i]["familia"] == cs[(i + 1) % len(cs)]["familia"] for i in range(len(cs))) and len(cs) > 0
            return dict(nombre=nombre, secuencia=[x["clave"] for x in cs], nombres=[x["nombre"] for x in cs], rendimiento=round(float(np.mean([x["apto"] for x in cs])), 2),
                        buenos_de_10=int(round(np.mean([x["buenos_de_10"] for x in cs]))), agua_mm=int(round(np.mean([x["agua_mm"] for x in cs]))), riego_mm=int(round(np.mean([x["riego_mm"] for x in cs]))),
                        erosion_t_ha=round(ero, 1), meses_desnudo=round(float(np.mean([12 - x["meses_cubierto"] for x in cs])), 1), anios_con_leguminosa=sum(1 for x in cs if x["fijan"]),
                        repite_familia=bool(fam_rep), nota=nota_s)
        ests = [estrategia(f"Como hoy: {por_clave[actual]['nombre'].lower()} todos los años", [actual], "Mismo cultivo cada año: las plagas y malezas de ese cultivo se acumulan y el suelo pierde siempre lo mismo.")]
        if prin and leg: ests.append(estrategia(f"{prin['nombre']} y {leg['nombre'].lower()}, año por medio", [prin["clave"], leg["clave"]], f"La {leg['nombre'].lower()} deja nitrógeno en el suelo para el cultivo siguiente y corta el ciclo de plagas del {prin['nombre'].lower()}."))
        if prin and leg and (cob or ter):
            x3 = cob if (k in (2, 3) or not ter) and cob else ter
            ests.append(estrategia(f"Tres años: {prin['nombre'].lower()}, {leg['nombre'].lower()} y {x3['nombre'].lower()}", [prin["clave"], leg["clave"], x3["clave"]],
                                   ("Suma un año de forraje que cubre el suelo casi todo el año y frena la erosión." if x3["cf"] <= 0.1 else "Tres familias distintas: más difícil para plagas y enfermedades.")))
        if k == 3 and cob and cob["clave"] == "alfalfa" or (k == 3 and "alfalfa" in por_clave and por_clave["alfalfa"]["veredicto"] in ("se da bien", "se da, con riesgo")):
            ests.append(estrategia("Pradera permanente de alfalfa", ["alfalfa"], "En ladera, tener el suelo cubierto todo el año es lo que más lo protege."))
        ests = [e for e in ests if e]
        # técnicas, cada una con el dato que la justifica
        tec = []
        if k == 2: tec.append(dict(titulo="Sembrar siguiendo el contorno de la ladera", porque=f"La pendiente media es {pm:.0f} %: las hileras atravesadas frenan el agua en vez de encauzarla cuesta abajo."))
        if k == 3: tec += [dict(titulo="Sembrar en contorno y en franjas alternadas", porque=f"Con {pm:.0f} % de pendiente, alternar franjas de cultivo y de pasto corta el recorrido del agua."),
                           dict(titulo="No dejar el suelo desnudo", porque="En ladera, un cultivo que deja el suelo descubierto pierde varias veces más tierra que uno con cobertura.")]
        if k == 4: tec += [dict(titulo="Dejar una franja con vegetación junto al cauce", porque="Filtra la tierra y los productos que bajan del resto del terreno antes de que lleguen al agua."),
                           dict(titulo="Sembrar después de las lluvias fuertes o hacer surcos de drenaje", porque="Esta parte recibe agua de las zonas altas y se encharca.")]
        if ests and ests[0]["erosion_t_ha"] > 5: tec.append(dict(titulo="Dejar el rastrojo sobre el suelo y labrar lo mínimo", porque=f"Con el manejo actual se estima una pérdida de {ests[0]['erosion_t_ha']} toneladas de suelo por hectárea al año."))
        if prin and prin["riego_mm"] > 80: tec.append(dict(titulo="Sembrar temprano, apenas llueva lo suficiente", porque=f"Al {prin['nombre'].lower()} le faltan unos {prin['riego_mm']} mm de agua al final del ciclo: adelantar la siembra aprovecha mejor la lluvia."))
        if prin and any(r["tipo"] == "helada" for r in prin["riesgos"]): tec.append(dict(titulo="Elegir una variedad que florezca más tarde", porque=f"El {prin['nombre'].lower()}: {next(r['texto'] for r in prin['riesgos'] if r['tipo'] == 'helada')}."))
        if prin and any(r["tipo"] == "calor" for r in prin["riesgos"]): tec.append(dict(titulo="Elegir una variedad de ciclo corto", porque=f"El {prin['nombre'].lower()}: {next(r['texto'] for r in prin['riesgos'] if r['tipo'] == 'calor')}."))
        if float(c["U2"].mean()) >= 3.0: tec.append(dict(titulo="Plantar una cortina de árboles contra el viento", porque=f"El viento medio es de {float(c['U2'].mean()):.1f} m/s: seca el suelo y tumba los cultivos altos."))
        zonas.append(dict(clave=k, nombre=NOMZ[k][0], descripcion=NOMZ[k][1], ha=round(float(mz.sum() * ha_c), 2), pendiente_media=round(pm, 1), factor_ls=round(ls, 2),
                          recomendados=[x["nombre"] for x in usable[:5]], recomendados_claves=[x["clave"] for x in usable[:5]], evitar=evitar, tecnicas=tec, estrategias=ests))
    np.savez_compressed(f"{d}/cultivos.npz", zona=zona)
    out = dict(version=VERSION, clima=clima, suelo=dict(textura=su["textura"], supuesto=su.get("supuesto", False), arcilla=su["arcilla"], arena=su["arena"], agua_util_mm_m=round(su["awc"] * 1000)), cultivos=res_c, zonas=zonas, actual=actual,
               fuentes=dict(clima="NASA POWER diario (MERRA-2, CERES) y lluvia GPM IMERG", metodo="FAO-56 (agua), FAO-33 (rendimiento por agua), suma térmica, RUSLE (erosión)",
                            observado="Superficie sembrada: CROPGRIDS v1.08 (Tang et al. 2024). Rendimiento medido: GDHY (Iizumi y Sakai 2020), 2007-2016", parametros="FAO ECOCROP, FAO-56, FAO-33; factores C de Panagos et al. 2015; largo de ciclo y fecha de siembra de la zona según el calendario mundial GGCMI (Jägermeyr et al. 2021)"))
    from . import cultivado, calendario, mundo
    for x in res_c:                        # cultivos que la validación dirigida mostró débiles: se dice en la propia ficha
        if x["clave"] in DEBILES and x.get("porque"): x["porque"] += f" Ojo: en la validación mundial el motor no reconoció este cultivo en cerca de {DEBILES[x['clave']]} de cada 10 lugares donde sí se siembra; si aquí sale mal, no lo descartes solo por eso."
    try:
        from . import regiones
        out["region"] = regiones.consultar(G["centro"][0], lat)      # cultivos principales de la región y del país (observado y oficial)
    except Exception: out["region"] = None
    try: out["otros_zona"] = cultivado.otros(G["centro"][0], lat)      # cultivos que este motor no simula pero que sí se siembran en la zona (dato observado)
    except Exception: out["otros_zona"] = []
    # ---------- qué dato faltó en este análisis y qué resultado afecta: se dice, no se disimula
    F = []
    if su.get("supuesto"): F.append(dict(dato="Suelo del terreno (SoilGrids)", efecto="No se pudo leer. Se usó un suelo medio supuesto (25 % de arcilla, 40 % de arena): el agua que guarda el suelo, y por eso el veredicto de cada cultivo, puede cambiar."))
    if not calendario.disponible(): F.append(dict(dato="Calendario local de cultivos (GGCMI)", efecto="Las fechas y el largo del ciclo salen de valores generales, sin ajuste a lo que se acostumbra en la zona."))
    if not cultivado.disponible(): F.append(dict(dato="Superficie sembrada y rendimiento medido (CROPGRIDS, GDHY)", efecto="No se muestra si cada cultivo se siembra de verdad en la zona ni su rendimiento medido."))
    if not os.path.exists(cultivado.F_OTROS): F.append(dict(dato="Otros cultivos de la zona (CROPGRIDS)", efecto="No se informa qué frutales, viñas u hortalizas se cultivan alrededor."))
    if out["region"] is None: F.append(dict(dato="Cultivos principales por país y región (CROPGRIDS, FAOSTAT)", efecto="No se informa qué se cultiva en la región ni en el país del terreno."))
    if not mundo.disponible(): F.append(dict(dato="Tabla mundial de clima y suelo", efecto="No se compara este lugar con otros lugares parecidos del mundo."))
    for arch, dato, efecto in (("uso.geojson", "Viñas y huertos mapeados (Overture, OpenStreetMap)", "Una viña o un huerto de frutales puede aparecer como «árboles»."),
                               ("caminos.geojson", "Caminos mapeados (Overture, OpenStreetMap)", "No se conoce el camino más cercano: el acceso y las franjas junto a caminos no se calculan bien."),
                               ("edificios.geojson", "Construcciones mapeadas (Overture)", "No se descuentan las construcciones ni su resguardo.")):
        if not os.path.exists(f"{d}/{arch}"): F.append(dict(dato=dato, efecto=efecto))
    out["faltan"] = F
    json.dump(out, open(f"{d}/cultivos.json", "w"), ensure_ascii=False)
    return out
