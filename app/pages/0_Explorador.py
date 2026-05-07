"""
Explorador de resultados electorales — filtros en cascada con carga progresiva
Estrategia de carga:
  Arranque  → tipo_03 (catálogo) + tipo_06 (votos municipio) + tipo_05 (participación municipio)
  Al llegar a municipio → tipo_09 (participación por mesa) — carga bajo demanda
  Al elegir una mesa   → tipo_10 (votos por partido por mesa, 48M filas) — carga bajo demanda
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import urllib.parse
import urllib.request

import streamlit as st
import pandas as pd
from utils import DATA_DIR, PROVINCIAS

try:
    import folium
    from streamlit_folium import st_folium
    _FOLIUM_OK = True
except ImportError:
    _FOLIUM_OK = False

st.set_page_config(page_title="Explorador de resultados", page_icon="🔍", layout="wide")
st.title("🔍 Explorador de resultados electorales")
st.caption("Selecciona tipo de elección, fecha, provincia y municipio para ver los resultados por partido.")


# ── Carga base (siempre al arrancar) ──────────────────────────────────────────

@st.cache_data(show_spinner="Cargando catálogo de candidaturas…")
def _load_t03():
    return pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes",
                 "cod_candidatura", "siglas", "denominacion"],
    )


@st.cache_data(show_spinner="Cargando resultados electorales… (primera carga, un momento)")
def _load_t06():
    return pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "cod_candidatura", "votos_obtenidos", "candidatos_obtenidos"],
    )


@st.cache_data(show_spinner="Cargando participación municipal…")
def _load_t05():
    return pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod", "nombre_municipio",
                 "censo_ine", "votos_blanco", "votos_nulos", "votos_candidaturas",
                 "num_escanos", "num_mesas"],
    )


# ── Carga diferida (solo cuando el usuario la solicita) ───────────────────────

@st.cache_resource(show_spinner="Cargando datos de mesas…")
def _load_t09():
    """Participación por mesa. Se carga solo cuando el usuario activa el nivel mesa."""
    return pd.read_parquet(
        str(DATA_DIR / "tipo_09.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "distrito_num", "seccion", "mesa",
                 "censo_ine", "votos_blanco", "votos_nulos", "votos_candidaturas"],
    )


@st.cache_resource(show_spinner="Cargando resultados por mesa… (48 M filas, primera vez ~10 s)")
def _load_t10():
    """Votos por partido por mesa. Se carga solo cuando el usuario elige una mesa concreta."""
    df = pd.read_parquet(
        str(DATA_DIR / "tipo_10.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "distrito_num", "seccion", "mesa",
                 "cod_candidatura", "votos_obtenidos"],
    )
    # provincia_cod en tipo_10 es código numérico (ej. "35") → normalizar a 2 dígitos
    df["provincia_cod"] = df["provincia_cod"].astype(str).str.zfill(2)
    return df


# ── Nombres de distrito para capitales de provincia ─────────────────────────
# Clave: (provincia_cod, municipio_cod, distrito_num)  →  nombre del distrito
# Solo capitales con ≥ 8 distritos y nombres bien documentados.
_NOMBRES_DISTRITO: dict[tuple[str, str, str], str] = {
    # Madrid  (28-079)  — 21 distritos
    ("28", "079", "01"): "Centro",
    ("28", "079", "02"): "Arganzuela",
    ("28", "079", "03"): "Retiro",
    ("28", "079", "04"): "Salamanca",
    ("28", "079", "05"): "Chamartín",
    ("28", "079", "06"): "Tetuán",
    ("28", "079", "07"): "Chamberí",
    ("28", "079", "08"): "Fuencarral-El Pardo",
    ("28", "079", "09"): "Moncloa-Aravaca",
    ("28", "079", "10"): "Latina",
    ("28", "079", "11"): "Carabanchel",
    ("28", "079", "12"): "Usera",
    ("28", "079", "13"): "Puente de Vallecas",
    ("28", "079", "14"): "Moratalaz",
    ("28", "079", "15"): "Ciudad Lineal",
    ("28", "079", "16"): "Hortaleza",
    ("28", "079", "17"): "Villaverde",
    ("28", "079", "18"): "Villa de Vallecas",
    ("28", "079", "19"): "Vicálvaro",
    ("28", "079", "20"): "San Blas-Canillejas",
    ("28", "079", "21"): "Barajas",
    # Barcelona  (08-019)  — 10 distritos
    ("08", "019", "01"): "Ciutat Vella",
    ("08", "019", "02"): "Eixample",
    ("08", "019", "03"): "Sants-Montjuïc",
    ("08", "019", "04"): "Les Corts",
    ("08", "019", "05"): "Sarrià-Sant Gervasi",
    ("08", "019", "06"): "Gràcia",
    ("08", "019", "07"): "Horta-Guinardó",
    ("08", "019", "08"): "Nou Barris",
    ("08", "019", "09"): "Sant Andreu",
    ("08", "019", "10"): "Sant Martí",
    # Valencia  (46-250)  — 19 distritos
    ("46", "250", "01"): "Ciutat Vella",
    ("46", "250", "02"): "l'Eixample",
    ("46", "250", "03"): "Extramurs",
    ("46", "250", "04"): "Campanar",
    ("46", "250", "05"): "la Saïdia",
    ("46", "250", "06"): "el Pla del Real",
    ("46", "250", "07"): "l'Olivereta",
    ("46", "250", "08"): "Patraix",
    ("46", "250", "09"): "Jesús",
    ("46", "250", "10"): "Quatre Carreres",
    ("46", "250", "11"): "Poblats Marítims",
    ("46", "250", "12"): "Camins al Grau",
    ("46", "250", "13"): "Algirós",
    ("46", "250", "14"): "Benimaclet",
    ("46", "250", "15"): "Rascanya",
    ("46", "250", "16"): "Benicalap",
    ("46", "250", "17"): "Pobles del Nord",
    ("46", "250", "18"): "Pobles de l'Oest",
    ("46", "250", "19"): "Pobles del Sud",
    # Sevilla  (41-091)  — 11 distritos
    ("41", "091", "01"): "Casco Antiguo",
    ("41", "091", "02"): "Triana",
    ("41", "091", "03"): "Los Remedios",
    ("41", "091", "04"): "Nervión",
    ("41", "091", "05"): "Sur",
    ("41", "091", "06"): "Cerro-Amate",
    ("41", "091", "07"): "Macarena",
    ("41", "091", "08"): "San Pablo-Santa Justa",
    ("41", "091", "09"): "Este-Alcosa-Torreblanca",
    ("41", "091", "10"): "Bellavista-La Palmera",
    ("41", "091", "11"): "Valme",
    # Zaragoza  (50-297)  — 12 distritos
    ("50", "297", "01"): "Centro",
    ("50", "297", "02"): "Casco Histórico",
    ("50", "297", "03"): "Delicias",
    ("50", "297", "04"): "Universidad",
    ("50", "297", "05"): "Las Fuentes",
    ("50", "297", "06"): "La Almozara",
    ("50", "297", "07"): "Oliver-Valdefierro",
    ("50", "297", "08"): "Torrero-La Paz",
    ("50", "297", "09"): "Miralbueno-Garrapinillos",
    ("50", "297", "10"): "Actur-Rey Fernando",
    ("50", "297", "11"): "El Rabal",
    ("50", "297", "12"): "Periféricos",
    # Málaga  (29-067)  — 11 distritos
    ("29", "067", "01"): "Centro",
    ("29", "067", "02"): "Este",
    ("29", "067", "03"): "Ciudad Jardín",
    ("29", "067", "04"): "Bailén-Miraflores",
    ("29", "067", "05"): "Palma-Palmilla",
    ("29", "067", "06"): "Churriana",
    ("29", "067", "07"): "Carretera de Cádiz",
    ("29", "067", "08"): "Cruz de Humilladero",
    ("29", "067", "09"): "Campanillas",
    ("29", "067", "10"): "Puerto de la Torre",
    ("29", "067", "11"): "Teatinos-Universidad",
    # Valladolid  (47-186)  — 12 distritos
    ("47", "186", "01"): "Centro",
    ("47", "186", "02"): "Arturo Eyries",
    ("47", "186", "03"): "Caamaño-La Victoria",
    ("47", "186", "04"): "Delicias",
    ("47", "186", "05"): "Huerta del Rey-Covaresa",
    ("47", "186", "06"): "La Rubia",
    ("47", "186", "07"): "Pajarillos",
    ("47", "186", "08"): "Parquesol",
    ("47", "186", "09"): "Rondilla-Santa Clara",
    ("47", "186", "10"): "San Juan-Vadillos",
    ("47", "186", "11"): "Pilarica-Sta. Ana",
    ("47", "186", "12"): "Cuatro de Marzo",
}


# ── WFS del INE — geometrías de secciones censales (WGS-84) ──────────────────
# Usamos el WFS clásico (más estable que la OGC API Features que sufre timeouts).
_WFS_BASE = "https://www.ine.es/geoserver/WMS_INE_SECCIONES_G01/wfs"


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_district_geojson(cpro: str, cmun: str, cdis: str) -> dict:
    """GeoJSON de todas las secciones de un distrito (WFS INE, coordenadas WGS-84).
    Lanza excepción si la petición falla; el llamador decide cómo mostrar el error.
    """
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "WMS_INE_SECCIONES_G01:Secciones_2025",
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "CQL_FILTER": f"CPRO='{cpro}' AND CMUN='{cmun}' AND CDIS='{cdis}'",
        "COUNT": "100",
    }
    url = _WFS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    # Filtrar solo secciones (excluir el polígono del distrito completo CSEC=000)
    data["features"] = [
        f for f in data.get("features", [])
        if f.get("properties", {}).get("CSEC", "000") != "000"
    ]
    return data


@st.cache_data(show_spinner=False)
def _load_distritos() -> dict:
    """Dict (provincia_cod, municipio_cod) -> lista ordenada de distrito_num.
    Construido desde distritos_ine.parquet (descargado del WFS del INE).
    """
    df = pd.read_parquet(
        str(DATA_DIR / "distritos_ine.parquet"),
        columns=["provincia_cod", "municipio_cod", "distrito_num"],
    )
    lookup: dict = {}
    for prov, muni, dist in zip(df["provincia_cod"], df["municipio_cod"], df["distrito_num"]):
        key = (str(prov), str(muni))
        lookup.setdefault(key, []).append(str(dist).zfill(2))
    for k in lookup:
        lookup[k] = sorted(set(lookup[k]))
    return lookup


# Mapa inverso: nombre de provincia → código numérico (necesario para tipo_10)
PROV_NOMBRE_A_COD = {v: k for k, v in PROVINCIAS.items()}

# Carga base siempre
cat = _load_t03()
t06 = _load_t06()
t05 = _load_t05()
distritos_map = _load_distritos()


# ── Filtros en cascada ────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filtros")

    # ① Tipo de convocatoria
    tipos = sorted(t06["tipo_eleccion_cod"].dropna().unique())
    default_tipo = tipos.index("Congreso") if "Congreso" in tipos else 0
    sel_tipo = st.selectbox("① Tipo de convocatoria", tipos, index=default_tipo)

    df = t06[t06["tipo_eleccion_cod"] == sel_tipo]

    # ② Fecha
    convs = (
        df[["anio", "mes"]].drop_duplicates()
        .assign(anio=lambda x: x["anio"].astype(int), mes=lambda x: x["mes"].astype(int))
        .sort_values(["anio", "mes"])
    )
    convs["label"] = convs["anio"].astype(str) + "/" + convs["mes"].astype(str).str.zfill(2)
    labels = convs["label"].tolist()[::-1]   # más reciente primero
    sel_conv = st.selectbox("② Fecha", labels)
    sel_anio = int(sel_conv[:4])
    sel_mes  = int(sel_conv[5:])

    df = df[(df["anio"].astype(int) == sel_anio) & (df["mes"].astype(int) == sel_mes)]

    # Vuelta (solo visible si hay más de una)
    vueltas = sorted(df["vuelta"].dropna().unique().astype(int))
    if len(vueltas) > 1:
        sel_vuelta = st.selectbox("Vuelta", vueltas)
    else:
        sel_vuelta = vueltas[0] if vueltas else 1
    df = df[df["vuelta"].astype(int) == sel_vuelta]

    # ③ Provincia
    provs = sorted(df["provincia_cod"].dropna().unique())
    sel_prov = st.selectbox("③ Provincia", provs)
    df = df[df["provincia_cod"] == sel_prov]

    # ④ Municipio (nombre desde tipo_05)
    t05_provfil = t05[
        (t05["tipo_eleccion_cod"] == sel_tipo) &
        (t05["anio"].astype(int) == sel_anio) &
        (t05["mes"].astype(int) == sel_mes) &
        (t05["provincia_cod"] == sel_prov)
    ][["municipio_cod", "nombre_municipio"]].drop_duplicates()

    munis_en_t06 = df["municipio_cod"].dropna().unique()
    t05_provfil  = t05_provfil[t05_provfil["municipio_cod"].isin(munis_en_t06)]

    if t05_provfil.empty:
        muni_map = {cod: cod for cod in sorted(munis_en_t06)}
    else:
        t05_provfil = t05_provfil.sort_values("nombre_municipio")
        muni_map = dict(zip(t05_provfil["nombre_municipio"], t05_provfil["municipio_cod"]))

    sel_muni_name = st.selectbox("④ Municipio", list(muni_map.keys()))
    sel_muni_cod  = muni_map[sel_muni_name]
    df = df[df["municipio_cod"] == sel_muni_cod]

    # ⑤ Mesa — carga diferida: tipo_09 solo si el usuario activa el toggle
    st.divider()
    _mostrar_mesa = st.toggle("⑤ Desglosar por mesa", value=False,
                              help="Activa para ver el detalle por sección/mesa. Carga datos adicionales.")

sel_mesa_label    = None
sel_distrito      = None
sel_seccion       = None
sel_mesa_id       = None
t09_muni          = pd.DataFrame()
_sel_dist_filtro  = None   # filtro de distrito (solo municipios multi-distrito)

if _mostrar_mesa:
    t09 = _load_t09()   # lazy: se carga la primera vez que se activa el toggle
    t09_muni = t09[
        (t09["tipo_eleccion_cod"] == sel_tipo) &
        (t09["anio"].astype(int) == sel_anio) &
        (t09["mes"].astype(int) == sel_mes) &
        (t09["vuelta"].astype(int) == sel_vuelta) &
        (t09["provincia_cod"] == sel_prov) &
        (t09["municipio_cod"] == sel_muni_cod)
    ].copy()

    if not t09_muni.empty:
        # Selector de distrito (solo si el municipio tiene más de 1 distrito)
        muni_distritos = distritos_map.get((sel_prov, sel_muni_cod), [])
        # Fallback: inferir desde los datos reales si el parquet no lo tiene
        if not muni_distritos:
            muni_distritos = sorted(t09_muni["distrito_num"].astype(str).str.zfill(2).unique())
        if len(muni_distritos) > 1:
            with st.sidebar:
                dist_opts = ["— Todos los distritos —"] + [
                    f"D{d}  {_NOMBRES_DISTRITO.get((sel_prov, sel_muni_cod, d), '')}".strip()
                    for d in muni_distritos
                ]
                sel_dist_raw = st.selectbox(
                    "⑤ Distrito",
                    dist_opts,
                    help=f"{sel_muni_name} tiene {len(muni_distritos)} distritos municipales.",
                )
            if sel_dist_raw != "— Todos los distritos —":
                _sel_dist_filtro = sel_dist_raw[1:3]  # "D02  Nombre" → "02"
                t09_muni = t09_muni[
                    t09_muni["distrito_num"].astype(str).str.zfill(2) == _sel_dist_filtro
                ].copy()

        t09_muni["mesa_label"] = (
            "D" + t09_muni["distrito_num"].astype(str).str.zfill(2) +
            "  Sec. " + t09_muni["seccion"].astype(str).str.zfill(4) +
            "  Mesa " + t09_muni["mesa"].astype(str).str.upper()
        )
        mesa_opts = ["— Todas las mesas —"] + sorted(t09_muni["mesa_label"].unique())
        with st.sidebar:
            mesa_num = st.selectbox("Mesa", mesa_opts)
        sel_mesa_label = mesa_num
        if sel_mesa_label != "— Todas las mesas —":
            mesa_row_sb = t09_muni[t09_muni["mesa_label"] == sel_mesa_label].iloc[0]
            sel_distrito  = str(mesa_row_sb["distrito_num"]).zfill(2)
            sel_seccion   = str(mesa_row_sb["seccion"]).zfill(4)
            sel_mesa_id   = str(mesa_row_sb["mesa"]).upper()
    else:
        with st.sidebar:
            st.caption("Sin datos de mesa para esta selección.")


# ── Cabecera: contexto de la selección ───────────────────────────────────────

st.subheader(f"{sel_tipo}  ·  {sel_conv}  ·  {sel_muni_name}  ({sel_prov})")

# Participación municipal desde tipo_05
t05_sel = t05[
    (t05["tipo_eleccion_cod"] == sel_tipo) &
    (t05["anio"].astype(int) == sel_anio) &
    (t05["mes"].astype(int) == sel_mes) &
    (t05["vuelta"].astype(int) == sel_vuelta) &
    (t05["provincia_cod"] == sel_prov) &
    (t05["municipio_cod"] == sel_muni_cod)
]

esc = 0
if not t05_sel.empty:
    r = t05_sel.iloc[0]

    def _int(v):
        return int(v) if pd.notna(v) else 0

    censo = _int(r["censo_ine"])
    vb    = _int(r["votos_blanco"])
    vn    = _int(r["votos_nulos"])
    vc    = _int(r["votos_candidaturas"])
    vt    = vb + vn + vc
    pct   = vt / censo * 100 if censo > 0 else 0.0
    esc   = _int(r["num_escanos"])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Censo",              f"{censo:,}")
    c2.metric("Votos emitidos",     f"{vt:,}")
    c3.metric("Participación",      f"{pct:.1f}%")
    c4.metric("Blancos",            f"{vb:,}")
    c5.metric("Nulos",              f"{vn:,}")
    c6.metric("Escaños/Concejales", str(esc) if esc > 0 else "—")

st.divider()

# ── Catálogo de la convocatoria ───────────────────────────────────────────────

if df.empty:
    st.warning("Sin datos de resultados para esta selección.")
    st.stop()

cat_sel = (
    cat[
        (cat["tipo_eleccion_cod"] == sel_tipo) &
        (cat["anio"].astype(int) == sel_anio) &
        (cat["mes"].astype(int) == sel_mes)
    ][["cod_candidatura", "siglas", "denominacion"]]
    .drop_duplicates("cod_candidatura")
)

# ── Bloque de mesa (solo si toggle activo Y mesa seleccionada) ───────────────

if _mostrar_mesa and sel_mesa_label and sel_mesa_label != "— Todas las mesas —":
    mesa_row = t09_muni[t09_muni["mesa_label"] == sel_mesa_label]
    if not mesa_row.empty:
        mr = mesa_row.iloc[0]
        mc = int(mr["censo_ine"]) if pd.notna(mr["censo_ine"]) else 0

        # Cargar tipo_10 PRIMERO para obtener los totales de votos
        # (los campos votos_blanco/nulos/candidaturas de tipo_09 no son fiables a nivel mesa)
        t10_mesa     = pd.DataFrame()
        prov_cod_t10 = PROV_NOMBRE_A_COD.get(sel_prov)
        if prov_cod_t10 and sel_distrito and sel_seccion and sel_mesa_id:
            t10 = _load_t10()
            t10_mesa = t10[
                (t10["tipo_eleccion_cod"] == sel_tipo) &
                (t10["anio"].astype(int) == sel_anio) &
                (t10["mes"].astype(int) == sel_mes) &
                (t10["vuelta"].astype(int) == sel_vuelta) &
                (t10["provincia_cod"] == prov_cod_t10) &
                (t10["municipio_cod"] == sel_muni_cod) &
                (t10["distrito_num"].astype(str).str.zfill(2) == sel_distrito) &
                (t10["seccion"].astype(str).str.zfill(4) == sel_seccion) &
                (t10["mesa"].astype(str).str.upper() == sel_mesa_id)
            ].copy()

        with st.expander(f"📋 {sel_mesa_label}", expanded=True):
            if not t10_mesa.empty:
                total_m    = int(t10_mesa["votos_obtenidos"].sum())
                pct_cand_m = total_m / mc * 100 if mc > 0 else 0.0
                n_partidos = int((t10_mesa["votos_obtenidos"] > 0).sum())

                d1, d2, d3, d4 = st.columns(4)
                d1.metric("Censo mesa",            f"{mc:,}")
                d2.metric("Votos a candidaturas",  f"{total_m:,}")
                d3.metric("% votos / censo",       f"{pct_cand_m:.1f}%",
                          help="Cociente votos a candidaturas / censo. "
                               "No incluye votos en blanco ni nulos (no disponibles a nivel mesa).")
                d4.metric("Partidos con votos",    str(n_partidos))

                # Tabla de resultados por partido
                t10_mesa = t10_mesa.merge(cat_sel, on="cod_candidatura", how="left")
                t10_mesa["pct_votos"] = (
                    t10_mesa["votos_obtenidos"] / total_m * 100
                ).round(2) if total_m > 0 else 0.0
                t10_mesa = t10_mesa.sort_values("votos_obtenidos", ascending=False)

                st.markdown(f"**Resultados por partido** ({total_m:,} votos a candidaturas)")
                col_cfg_m = {
                    "Siglas":       st.column_config.TextColumn("Siglas", width="small"),
                    "Denominación": st.column_config.TextColumn("Denominación"),
                    "Votos":        st.column_config.NumberColumn("Votos", format="%d"),
                    "% votos":      st.column_config.NumberColumn("% votos", format="%.2f %%"),
                }
                tabla_m = t10_mesa[["siglas", "denominacion", "votos_obtenidos", "pct_votos"]].copy()
                tabla_m.columns = ["Siglas", "Denominación", "Votos", "% votos"]
                st.dataframe(tabla_m.reset_index(drop=True), use_container_width=True,
                             hide_index=True, column_config=col_cfg_m)
            else:
                d1, d2 = st.columns(2)
                d1.metric("Censo mesa", f"{mc:,}")
                d2.metric("Votos a candidaturas", "N/D")
                st.caption("⚠️ Sin datos de tipo_10 para esta mesa en la convocatoria seleccionada.")

        # ── Mapa de la sección ─────────────────────────────────────────────
        if _FOLIUM_OK and sel_distrito and sel_seccion:
            # Convertir sección 4-dígitos del padrón electoral → 3 dígitos INE
            _csec_3 = "".join(c for c in str(sel_seccion)[1:] if c.isdigit()).zfill(3)
            _nombre_dist = _NOMBRES_DISTRITO.get((sel_prov, sel_muni_cod, sel_distrito), "")
            _titulo_mapa = (
                f"🗺️ D{sel_distrito}"
                + (f" {_nombre_dist}" if _nombre_dist else "")
                + f"  ·  Sección {_csec_3}"
            )
            with st.expander(_titulo_mapa, expanded=True):
                _cpro = PROV_NOMBRE_A_COD.get(sel_prov)
                _cmun = str(sel_muni_cod).zfill(3)
                _cdis = str(sel_distrito).zfill(2)
                _gjson = None
                _map_error = None
                if not _cpro:
                    _map_error = (
                        f"Provincia '{sel_prov}' no encontrada en el catálogo "
                        f"de códigos INE. El mapa no puede cargarse."
                    )
                else:
                    with st.spinner("Cargando geometrías del INE…"):
                        try:
                            _gjson = _fetch_district_geojson(_cpro, _cmun, _cdis)
                        except Exception as _e:
                            _map_error = (
                                f"Error al consultar el WFS del INE "
                                f"(CPRO={_cpro}, CMUN={_cmun}, CDIS={_cdis}): "
                                f"{type(_e).__name__}: {_e}"
                            )
                if _gjson and _gjson.get("features"):
                    # Recoger bounding box
                    _lons, _lats = [], []
                    for _feat in _gjson["features"]:
                        _g = _feat["geometry"]
                        _rings = (
                            [_g["coordinates"][0]]
                            if _g["type"] == "Polygon"
                            else [_p[0] for _p in _g["coordinates"]]
                        )
                        for _ring in _rings:
                            for _xy in _ring:
                                _lons.append(_xy[0])
                                _lats.append(_xy[1])

                    def _sty(_f, _c=_csec_3):
                        if _f["properties"].get("CSEC") == _c:
                            return {"fillColor": "#e74c3c", "color": "#c0392b",
                                    "weight": 2.5, "fillOpacity": 0.6}
                        return {"fillColor": "#3498db", "color": "#1a6ea8",
                                "weight": 0.8, "fillOpacity": 0.15}

                    _m = folium.Map(tiles="CartoDB positron")
                    folium.GeoJson(
                        _gjson,
                        style_function=_sty,
                        tooltip=folium.GeoJsonTooltip(
                            fields=["CDIS", "CSEC", "NMUN"],
                            aliases=["Distrito:", "Sección:", "Municipio:"],
                            sticky=False,
                        ),
                    ).add_to(_m)
                    if _lons:
                        _m.fit_bounds(
                            [[min(_lats), min(_lons)], [max(_lats), max(_lons)]]
                        )
                    st_folium(_m, height=420, use_container_width=True,
                              returned_objects=[])
                    st.caption(
                        "Sección resaltada en rojo  ·  Fuente: INE Secciones Censales 2025"
                    )
                elif _map_error:
                    st.error(_map_error)
                else:
                    st.warning(
                        f"El WFS del INE no devolvió secciones para "
                        f"CPRO={_cpro}, CMUN={_cmun}, CDIS={_cdis}. "
                        f"Puede que este municipio no tenga datos de cartografía en Secciones_2025."
                    )


# ── Tabla de resultados por partido (nivel municipio) ────────────────────────

st.markdown(f"### Municipio: {sel_muni_name}")

res = (
    df.groupby("cod_candidatura", as_index=False)
    .agg(
        votos   = ("votos_obtenidos",      "sum"),
        escanos = ("candidatos_obtenidos", "sum"),
    )
    .merge(cat_sel, on="cod_candidatura", how="left")
)

total_votos = res["votos"].sum()
res["pct_votos"] = (res["votos"] / total_votos * 100).round(2) if total_votos > 0 else 0.0
res = res.sort_values("votos", ascending=False).reset_index(drop=True)

hay_escanos = (res["escanos"] > 0).any()

tabla = res[["siglas", "denominacion", "votos", "pct_votos"] +
            (["escanos"] if hay_escanos else [])].copy()
col_names = ["Siglas", "Denominación", "Votos", "% votos"] + \
            (["Escaños / Concejales"] if hay_escanos else [])
tabla.columns = col_names

if hay_escanos:
    tabla["Escaños / Concejales"] = tabla["Escaños / Concejales"].fillna(0).astype(int)

col_config = {
    "Siglas":       st.column_config.TextColumn("Siglas", width="small"),
    "Denominación": st.column_config.TextColumn("Denominación"),
    "Votos":        st.column_config.NumberColumn("Votos", format="%d"),
    "% votos":      st.column_config.NumberColumn("% votos", format="%.2f %%"),
}
if hay_escanos:
    col_config["Escaños / Concejales"] = st.column_config.NumberColumn(
        "Escaños / Concejales", format="%d"
    )

st.dataframe(
    tabla,
    use_container_width=True,
    hide_index=True,
    column_config=col_config,
)

st.caption(
    f"{len(res)} candidaturas  ·  {int(total_votos):,} votos a candidaturas"
    + (f"  ·  Escaños disponibles: {esc}" if esc > 0 else "")
)