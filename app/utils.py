"""
Infoelectoral — utilidades compartidas entre páginas
"""
from pathlib import Path
import re
import numpy as np
import pandas as pd

ROOT       = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output"
DATA_DIR   = ROOT / "data"

# ── Catálogos territoriales ────────────────────────────────────────────────
AUTONOMIAS = {
    "01": "Andalucía", "02": "Aragón", "03": "Asturias", "04": "Baleares",
    "05": "Canarias", "06": "Cantabria", "07": "Castilla La Mancha",
    "08": "Castilla y León", "09": "Cataluña", "10": "Extremadura",
    "11": "Galicia", "12": "Madrid", "13": "Navarra", "14": "País Vasco",
    "15": "Murcia", "16": "La Rioja", "17": "Comunidad Valenciana",
    "18": "Ceuta", "19": "Melilla",
}

PROVINCIAS = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería",
    "05": "Ávila", "06": "Badajoz", "07": "Baleares", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña", "16": "Cuenca",
    "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Guipúzcoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid",
    "29": "Málaga", "30": "Murcia", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria",
    "40": "Segovia", "41": "Sevilla", "42": "Soria", "43": "Tarragona",
    "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid",
    "48": "Vizcaya", "49": "Zamora", "50": "Zaragoza",
    "51": "Ceuta", "52": "Melilla",
}


def ccaa_nombre(cod) -> str:
    """Convierte código CCAA (int o str, con o sin cero) a nombre."""
    return AUTONOMIAS.get(str(cod).zfill(2), str(cod))


def prov_nombre(cod) -> str:
    """Convierte código provincia (int o str) a nombre."""
    return PROVINCIAS.get(str(cod).zfill(2), str(cod))


# ── Constantes de columnas para cargadores ───────────────────────────────────
COLS_TIPO05 = [
    "tipo_eleccion_cod", "anio", "mes", "vuelta", "ccaa_cod",
    "provincia_cod", "municipio_cod", "nombre_municipio", "num_mesas",
    "censo_ine", "votos_blanco", "votos_nulos", "votos_candidaturas",
]

COLS_TIPO04 = [
    "tipo_eleccion_cod", "anio", "mes", "vuelta", "provincia_cod",
    "municipio_cod", "cod_candidatura", "orden",
    "nombre", "primer_apellido", "segundo_apellido",
    "sexo", "anio_nacimiento", "elegido",
]


def enrich_tipo05(df: pd.DataFrame) -> pd.DataFrame:
    """Añade columnas calculadas a un DataFrame de tipo_05."""
    df = df.copy()
    df["ccaa_nombre"] = df["ccaa_cod"].astype(str).str.zfill(2).map(AUTONOMIAS).fillna(df["ccaa_cod"].astype(str))
    df["votos_emitidos"] = df["votos_blanco"].fillna(0) + df["votos_nulos"].fillna(0) + df["votos_candidaturas"].fillna(0)
    df["participacion_pct"] = (df["votos_emitidos"] / df["censo_ine"].replace(0, np.nan) * 100).round(2)
    df["abstencion_pct"] = (100 - df["participacion_pct"]).round(2)
    return df


# ── Helpers de formato ────────────────────────────────────────────────────────

def etiqueta_conv(anio, mes):
    """Devuelve etiqueta 'YYYY/MM' dado anio y mes (float-safe)."""
    return f"{int(anio)}/{int(mes):02d}"


def sort_conv(df):
    """Ordena un DataFrame por anio, mes ascendente."""
    return df.sort_values(["anio", "mes"])


TIPO_COLORS = {
    "Congreso":            "#1f77b4",
    "Senado":              "#ff7f0e",
    "Municipales":         "#2ca02c",
    "Parlamento Europeo":  "#d62728",
    "Cabildos":            "#9467bd",
    "Referéndum":          "#8c564b",
}

# Mapping: código provincia (str 2-dig) → código CCAA (str 2-dig)
PROV_A_CCAA_COD: dict[str, str] = {
    "01": "14", "02": "07", "03": "17", "04": "01", "05": "08",
    "06": "10", "07": "04", "08": "09", "09": "08", "10": "10",
    "11": "01", "12": "17", "13": "07", "14": "01", "15": "11",
    "16": "07", "17": "09", "18": "01", "19": "07", "20": "14",
    "21": "01", "22": "02", "23": "01", "24": "08", "25": "09",
    "26": "16", "27": "11", "28": "12", "29": "01", "30": "15",
    "31": "13", "32": "11", "33": "03", "34": "08", "35": "05",
    "36": "11", "37": "08", "38": "05", "39": "06", "40": "08",
    "41": "01", "42": "08", "43": "09", "44": "02", "45": "07",
    "46": "17", "47": "08", "48": "14", "49": "08", "50": "02",
    "51": "18", "52": "19",
}

# Mapping: nombre provincia → nombre CCAA
# Útil para tipo_06/09 donde provincia_cod es un nombre, no un código
PROV_NOMBRE_A_CCAA: dict[str, str] = {
    PROVINCIAS[k]: AUTONOMIAS[v]
    for k, v in PROV_A_CCAA_COD.items()
    if k in PROVINCIAS and v in AUTONOMIAS
}

# ── Sistema de colores estable por partido ────────────────────────────────────
PARTY_COLORS: dict[str, str] = {
    # PP y familia (azules oscuros / navys)
    "PP":               "#003087",
    "AP":               "#1565C0",
    "CD":               "#1976D2",
    "UPN":              "#2196F3",
    "PAR":              "#42A5F5",
    "PP-PAR":           "#42A5F5",
    "PP+Cs":            "#1976D2",
    "UCD":              "#64B5F6",
    "CDS":              "#B0BEC5",
    "NN.GG.":           "#90CAF9",
    "FAL":              "#90CAF9",
    # PSOE y familia (rojos)
    "PSOE":             "#C62828",
    "PSdG-PSOE":        "#D32F2F",
    "PSC-PSOE":         "#E53935",
    "PSC":              "#E53935",
    "PSA-PA":           "#EF5350",
    "PSM-PSOE":         "#EF9A9A",
    "PSE-EE(PSOE)":     "#E53935",
    "PSdeG-PSOE":       "#D32F2F",
    "PSM-EN":           "#EF9A9A",
    "PSOE-A":           "#C62828",
    # Podemos y coaliciones (morado)
    "Podemos":          "#7B1FA2",
    "UP":               "#6A1B9A",
    "En Comú Podem":    "#7B1FA2",
    "En Marea":         "#8E24AA",
    "Galicia en Común": "#8E24AA",
    "Compromís-Podem":  "#7B1FA2",
    "Ahora en Común":   "#9C27B0",
    # IU y coaliciones sin Podemos (rojo ladrillo)
    "IU":               "#BF360C",
    "IU-ICV":           "#BF360C",
    "ICV":              "#D84315",
    "IU-CA":            "#BF360C",
    "EU":               "#BF360C",
    "PCE":              "#B71C1C",
    "PCPE":             "#B71C1C",
    "EUiA":             "#D84315",
    # Sumar (magenta)
    "Sumar":            "#AD1457",
    "Yolanda Díaz":     "#AD1457",
    # ERC y coaliciones (amarillo)
    "ERC":              "#F9A825",
    "ERC-CATSÍ":        "#F9A825",
    "ERC-RI":           "#F9A825",
    "ERC-Sobiranistes": "#F9A825",
    "ERC-MES-MÉS":      "#F9A825",
    # Junts / CiU / PDeCat (azul celeste — distinto al PP)
    "CiU":              "#0277BD",
    "CDC":              "#0288D1",
    "Junts":            "#039BE5",
    "JxCat":            "#0288D1",
    "JxCat-Junts":      "#0288D1",
    "Junts per Cat.":   "#039BE5",
    "PDeCat":           "#0097A7",
    "DL":               "#0097A7",
    # UPYD (fucsia)
    "UPYD":             "#E91E63",
    "UPyD":             "#E91E63",
    # PNV (verde oscuro)
    "PNV":              "#33691E",
    "EAJ-PNV":          "#33691E",
    # Bildu y familia (verde claro)
    "Bildu":            "#8BC34A",
    "EH Bildu":         "#8BC34A",
    "EH-Bildu":         "#8BC34A",
    "EA":               "#AED581",
    "HB":               "#9CCC65",
    "Amaiur":           "#8BC34A",
    "Aralar":           "#AED581",
    # BNG (azul claro)
    "BNG":              "#29B6F6",
    "BNG-NÓS":          "#29B6F6",
    "BNG-NS":           "#29B6F6",
    # VOX (verde)
    "VOX":              "#2E7D32",
    # Ciudadanos / Cs (naranja)
    "Cs":               "#FF6D00",
    "Ciudadanos":       "#FF6D00",
    "C's":              "#FF6D00",
    # Coalición Canaria y familia (ámbar)
    "CC":               "#FFB300",
    "CC-NC-PNC":        "#FFB300",
    "CC-PNC":           "#FFB300",
    "NC":               "#FFD54F",
    "AHI":              "#FFD54F",
    # Partidos valencianos / otros regionales
    "Compromís":        "#FF8F00",
    "BM":               "#78909C",
    "CHA":              "#78909C",
    "ChA":              "#78909C",
    "NA+":              "#42A5F5",
    "Navarra Suma":     "#42A5F5",
    # Partidos históricos transición
    "PCE-PSUC":         "#B71C1C",
    "PSUC":             "#E53935",
    "AN-PNV":           "#33691E",
}

# Reglas de familia por substring (orden importa — se evalúan de arriba a abajo)
# Si el nombre exacto no está en PARTY_COLORS, se prueba cada regla.
_FAMILY_RULES: list[tuple[str, str]] = [
    # Podemos primero (puede aparecer en coaliciones con IU)
    ("Podemos",  "#7B1FA2"),
    ("Podem",    "#7B1FA2"),
    ("Sumar",    "#AD1457"),
    # ERC (cualquier variante con subtítulo)
    ("ERC",      "#F9A825"),
    # Junts / JxCat (cualquier variante con subtítulo)
    ("JxCat",    "#0288D1"),
    ("Junts",    "#039BE5"),
    # PSOE (cualquier federación autonómica)
    ("PSOE",     "#C62828"),
    ("PSE-EE",   "#E53935"),
    # IU (si no lleva Podemos)
    ("IU",       "#BF360C"),
    # Bildu
    ("Bildu",    "#8BC34A"),
    # PNV / EAJ
    ("EAJ",      "#33691E"),
    ("PNV",      "#33691E"),
    # BNG
    ("BNG",      "#29B6F6"),
    # VOX
    ("VOX",      "#2E7D32"),
    # PP (al final para no capturar UPYD, etc.)
    ("PP",       "#003087"),
    # Ciudadanos
    ("Ciudadanos", "#FF6D00"),
]

_GRAY_PALETTE = [
    "#9E9E9E", "#757575", "#BDBDBD", "#616161", "#E0E0E0",
    "#546E7A", "#90A4AE", "#78909C", "#B0BEC5", "#455A64",
    "#37474F", "#CFD8DC", "#263238", "#ECEFF1", "#607D8B",
]


def _resolve_color(name: str, gray_counters: list[int]) -> str:
    """Resuelve el color para un partido: exacto → familia → gris rotativo."""
    if name in PARTY_COLORS:
        return PARTY_COLORS[name]
    name_upper = name.upper()
    for substring, color in _FAMILY_RULES:
        if substring.upper() in name_upper:
            return color
    color = _GRAY_PALETTE[gray_counters[0] % len(_GRAY_PALETTE)]
    gray_counters[0] += 1
    return color


# Patrón: acrónimo con puntos del tipo 'P.P.', 'P.S.O.E.', 'I.U.', 'U.C.D.'
_DOTTED_ACRONYM = re.compile(r'^([A-ZÁÉÍÓÚÜÑ]{1,3}\.){2,}$')


def normalize_partido(name: str) -> str:
    """Normaliza siglas con puntos intermedios: 'P.P.' → 'PP', 'P.S.O.E.' → 'PSOE'.

    Solo actúa sobre cadenas que sigan el patrón LETRA(S).LETRA(S).... No modifica
    nombres con guiones, espacios ni cadenas normales.
    """
    if not isinstance(name, str):
        return name
    stripped = name.strip()
    if _DOTTED_ACRONYM.match(stripped):
        return stripped.replace('.', '')
    return stripped


def party_color_map(parties) -> dict[str, str]:
    """Devuelve {partido: color} para color_discrete_map de Plotly.

    Prioridad: coincidencia exacta → regla de familia (substring) → gris rotativo.
    Los grises son únicos por partido y no se solapan con colores de familias.
    """
    gray_counters = [0]
    return {p: _resolve_color(str(p), gray_counters) for p in parties}
