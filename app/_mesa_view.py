"""
Módulo compartido: desglose por mesa electoral.

Exporta `render_mesa_desglose(...)`, que añade el toggle + selectores de
distrito/mesa al sidebar y renderiza los resultados y el mapa de sección
en el área principal.

Usado por: 2_Congreso.py y 3_Municipales.py
"""
from __future__ import annotations

import json
import re as _re
import urllib.parse
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd

from utils import DATA_DIR, PROVINCIAS

try:
    import folium
    from streamlit_folium import st_folium
    _FOLIUM_OK = True
except ImportError:
    _FOLIUM_OK = False

# ── Constantes ────────────────────────────────────────────────────────────────

_WFS_BASE = "https://www.ine.es/geoserver/WMS_INE_SECCIONES_G01/wfs"

# Inverso de PROVINCIAS: nombre → código numérico de 2 dígitos
PROV_NOMBRE_A_COD: dict[str, str] = {v: k for k, v in PROVINCIAS.items()}

# Nombres de distrito para las principales capitales de provincia
_NOMBRES_DISTRITO: dict[tuple[str, str, str], str] = {
    # Madrid  (28-079)
    ("28", "079", "01"): "Centro",            ("28", "079", "02"): "Arganzuela",
    ("28", "079", "03"): "Retiro",            ("28", "079", "04"): "Salamanca",
    ("28", "079", "05"): "Chamartín",         ("28", "079", "06"): "Tetuán",
    ("28", "079", "07"): "Chamberí",          ("28", "079", "08"): "Fuencarral-El Pardo",
    ("28", "079", "09"): "Moncloa-Aravaca",   ("28", "079", "10"): "Latina",
    ("28", "079", "11"): "Carabanchel",       ("28", "079", "12"): "Usera",
    ("28", "079", "13"): "Puente de Vallecas",("28", "079", "14"): "Moratalaz",
    ("28", "079", "15"): "Ciudad Lineal",     ("28", "079", "16"): "Hortaleza",
    ("28", "079", "17"): "Villaverde",        ("28", "079", "18"): "Villa de Vallecas",
    ("28", "079", "19"): "Vicálvaro",         ("28", "079", "20"): "San Blas-Canillejas",
    ("28", "079", "21"): "Barajas",
    # Barcelona  (08-019)
    ("08", "019", "01"): "Ciutat Vella",      ("08", "019", "02"): "Eixample",
    ("08", "019", "03"): "Sants-Montjuïc",    ("08", "019", "04"): "Les Corts",
    ("08", "019", "05"): "Sarrià-Sant Gervasi",("08", "019", "06"): "Gràcia",
    ("08", "019", "07"): "Horta-Guinardó",    ("08", "019", "08"): "Nou Barris",
    ("08", "019", "09"): "Sant Andreu",       ("08", "019", "10"): "Sant Martí",
    # Valencia  (46-250)
    ("46", "250", "01"): "Ciutat Vella",      ("46", "250", "02"): "l'Eixample",
    ("46", "250", "03"): "Extramurs",         ("46", "250", "04"): "Campanar",
    ("46", "250", "05"): "la Saïdia",         ("46", "250", "06"): "el Pla del Real",
    ("46", "250", "07"): "l'Olivereta",       ("46", "250", "08"): "Patraix",
    ("46", "250", "09"): "Jesús",             ("46", "250", "10"): "Quatre Carreres",
    ("46", "250", "11"): "Poblats Marítims",  ("46", "250", "12"): "Camins al Grau",
    ("46", "250", "13"): "Algirós",           ("46", "250", "14"): "Benimaclet",
    ("46", "250", "15"): "Rascanya",          ("46", "250", "16"): "Benicalap",
    ("46", "250", "17"): "Pobles del Nord",   ("46", "250", "18"): "Pobles de l'Oest",
    ("46", "250", "19"): "Pobles del Sud",
    # Sevilla  (41-091)
    ("41", "091", "01"): "Casco Antiguo",     ("41", "091", "02"): "Triana",
    ("41", "091", "03"): "Los Remedios",      ("41", "091", "04"): "Nervión",
    ("41", "091", "05"): "Sur",               ("41", "091", "06"): "Cerro-Amate",
    ("41", "091", "07"): "Macarena",          ("41", "091", "08"): "San Pablo-Santa Justa",
    ("41", "091", "09"): "Este-Alcosa-Torreblanca",
    ("41", "091", "10"): "Bellavista-La Palmera",
    ("41", "091", "11"): "Valme",
    # Zaragoza  (50-297)
    ("50", "297", "01"): "Centro",            ("50", "297", "02"): "Casco Histórico",
    ("50", "297", "03"): "Delicias",          ("50", "297", "04"): "Universidad",
    ("50", "297", "05"): "Las Fuentes",       ("50", "297", "06"): "La Almozara",
    ("50", "297", "07"): "Oliver-Valdefierro",("50", "297", "08"): "Torrero-La Paz",
    ("50", "297", "09"): "Miralbueno-Garrapinillos",
    ("50", "297", "10"): "Actur-Rey Fernando",
    ("50", "297", "11"): "El Rabal",          ("50", "297", "12"): "Periféricos",
    # Málaga  (29-067)
    ("29", "067", "01"): "Centro",            ("29", "067", "02"): "Este",
    ("29", "067", "03"): "Ciudad Jardín",     ("29", "067", "04"): "Bailén-Miraflores",
    ("29", "067", "05"): "Palma-Palmilla",    ("29", "067", "06"): "Churriana",
    ("29", "067", "07"): "Carretera de Cádiz",("29", "067", "08"): "Cruz de Humilladero",
    ("29", "067", "09"): "Campanillas",       ("29", "067", "10"): "Puerto de la Torre",
    ("29", "067", "11"): "Teatinos-Universidad",
    # Valladolid  (47-186)
    ("47", "186", "01"): "Centro",            ("47", "186", "02"): "Arturo Eyries",
    ("47", "186", "03"): "Caamaño-La Victoria",("47", "186", "04"): "Delicias",
    ("47", "186", "05"): "Huerta del Rey-Covaresa",
    ("47", "186", "06"): "La Rubia",          ("47", "186", "07"): "Pajarillos",
    ("47", "186", "08"): "Parquesol",         ("47", "186", "09"): "Rondilla-Santa Clara",
    ("47", "186", "10"): "San Juan-Vadillos", ("47", "186", "11"): "Pilarica-Sta. Ana",
    ("47", "186", "12"): "Cuatro de Marzo",
}


# ── Cargadores diferidos (cached a nivel módulo) ──────────────────────────────

@st.cache_resource(show_spinner="Cargando participación por mesa…")
def _load_t09() -> pd.DataFrame:
    return pd.read_parquet(
        str(DATA_DIR / "tipo_09.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "distrito_num", "seccion", "mesa",
                 "censo_ine", "votos_blanco", "votos_nulos", "votos_candidaturas"],
    )


@st.cache_resource(show_spinner="Cargando resultados por mesa… (48 M filas, primera vez ~10 s)")
def _load_t10() -> pd.DataFrame:
    df = pd.read_parquet(
        str(DATA_DIR / "tipo_10.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "distrito_num", "seccion", "mesa",
                 "cod_candidatura", "votos_obtenidos"],
    )
    # tipo_10 usa código numérico de 2 dígitos para provincia_cod
    df["provincia_cod"] = df["provincia_cod"].astype(str).str.zfill(2)
    return df


@st.cache_data(show_spinner=False)
def _load_distritos() -> dict:
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


@st.cache_resource(show_spinner=False)
def _load_cat() -> pd.DataFrame:
    return pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes",
                 "cod_candidatura", "siglas", "denominacion"],
    )


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_district_geojson(cpro: str, cmun: str, cdis: str) -> dict:
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": "WMS_INE_SECCIONES_G01:Secciones_2025",
        "OUTPUTFORMAT": "application/json", "SRSNAME": "EPSG:4326",
        "CQL_FILTER": f"CPRO='{cpro}' AND CMUN='{cmun}' AND CDIS='{cdis}'",
        "COUNT": "100",
    }
    url = _WFS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    data["features"] = [
        f for f in data.get("features", [])
        if f.get("properties", {}).get("CSEC", "000") != "000"
    ]
    return data


# ── Función principal pública ─────────────────────────────────────────────────

def render_mesa_desglose(
    tipo: str,
    anio: int,
    mes: int,
    vuelta: int,
    prov_nombre: str,   # nombre de provincia (como aparece en tipo_09/tipo_06)
    muni_cod: str,      # código de municipio, p.ej. "079"
    muni_name: str,     # nombre del municipio, p.ej. "Madrid"
    key_prefix: str = "",
) -> None:
    """
    Añade el toggle '🗳️ Desglosar por mesa' al sidebar.
    Cuando está activo muestra los selectores de distrito/mesa y, si el
    usuario elige una mesa concreta, renderiza los resultados de esa mesa
    más el mapa de la sección en el área principal de la página.

    Parámetros
    ----------
    tipo        : tipo de elección (ej. "Congreso", "Municipales")
    anio, mes   : año y mes de la convocatoria (int)
    vuelta      : número de vuelta (normalmente 1)
    prov_nombre : nombre de la provincia (str, como en tipo_09.provincia_cod)
    muni_cod    : código del municipio (str, sin zfill)
    muni_name   : nombre del municipio para mostrar en la UI
    key_prefix  : prefijo para las keys de los widgets de Streamlit
    """
    # ── Toggle en sidebar ────────────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        mostrar = st.toggle(
            "🗳️ Desglosar por mesa",
            value=False,
            key=f"{key_prefix}_toggle_mesa",
            help="Ver el detalle de resultados por sección/mesa. "
                 "Requiere cargar datos adicionales (primera activación ~10 s).",
        )

    if not mostrar:
        return

    # ── Cargar tipo_09 y filtrar al municipio ────────────────────────────────
    t09 = _load_t09()
    t09_muni = t09[
        (t09["tipo_eleccion_cod"] == tipo) &
        (t09["anio"].astype(int) == anio) &
        (t09["mes"].astype(int) == mes) &
        (t09["vuelta"].astype(int) == vuelta) &
        (t09["provincia_cod"] == prov_nombre) &
        (t09["municipio_cod"] == muni_cod)
    ].copy()

    if t09_muni.empty:
        with st.sidebar:
            st.caption("⚠️ Sin datos de mesa para esta convocatoria.")
        return

    # ── Código numérico de provincia (para tipo_10 y WFS) ───────────────────
    prov_cod = PROV_NOMBRE_A_COD.get(prov_nombre, "")

    # ── Selector de distrito (sidebar, solo si hay más de 1) ─────────────────
    distritos_map  = _load_distritos()
    muni_distritos = distritos_map.get((prov_cod, muni_cod), [])
    if not muni_distritos:
        muni_distritos = sorted(
            t09_muni["distrito_num"].astype(str).str.zfill(2).unique()
        )

    sel_dist_filtro = None
    if len(muni_distritos) > 1:
        with st.sidebar:
            dist_opts = ["— Todos los distritos —"] + [
                f"D{d}  {_NOMBRES_DISTRITO.get((prov_cod, muni_cod, d), '')}".strip()
                for d in muni_distritos
            ]
            sel_dist_raw = st.selectbox(
                "Distrito",
                dist_opts,
                key=f"{key_prefix}_distrito",
                help=f"{muni_name} tiene {len(muni_distritos)} distritos municipales.",
            )
        if sel_dist_raw != "— Todos los distritos —":
            sel_dist_filtro = sel_dist_raw[1:3]   # "D02  Nombre" → "02"
            t09_muni = t09_muni[
                t09_muni["distrito_num"].astype(str).str.zfill(2) == sel_dist_filtro
            ].copy()

    # ── Selector de mesa (sidebar) ───────────────────────────────────────────
    t09_muni["mesa_label"] = (
        "D" + t09_muni["distrito_num"].astype(str).str.zfill(2) +
        "  Sec. " + t09_muni["seccion"].astype(str).str.zfill(4) +
        "  Mesa " + t09_muni["mesa"].astype(str).str.upper()
    )
    mesa_opts = ["— Todas las mesas —"] + sorted(t09_muni["mesa_label"].unique())
    with st.sidebar:
        sel_mesa_label = st.selectbox(
            "Mesa",
            mesa_opts,
            key=f"{key_prefix}_mesa",
        )

    st.divider()
    st.subheader(f"🗳️ Desglose por mesa · {muni_name}")

    # ── Vista: todas las mesas ───────────────────────────────────────────────
    if sel_mesa_label == "— Todas las mesas —":
        df_part = t09_muni[["mesa_label", "censo_ine", "votos_candidaturas"]].copy()
        df_part["pct"] = (
            df_part["votos_candidaturas"]
            / df_part["censo_ine"].replace(0, pd.NA) * 100
        ).round(1)
        st.dataframe(
            df_part.rename(columns={
                "mesa_label":         "Mesa",
                "censo_ine":          "Censo",
                "votos_candidaturas": "Votos cand.",
                "pct":                "% participación",
            }).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Censo":           st.column_config.NumberColumn("Censo", format="%d"),
                "Votos cand.":     st.column_config.NumberColumn("Votos cand.", format="%d"),
                "% participación": st.column_config.NumberColumn("% participación", format="%.1f %%"),
            },
        )
        return

    # ── Vista: mesa concreta ─────────────────────────────────────────────────
    mesa_row  = t09_muni[t09_muni["mesa_label"] == sel_mesa_label].iloc[0]
    sel_dist  = str(mesa_row["distrito_num"]).zfill(2)
    sel_sec   = str(mesa_row["seccion"]).zfill(4)
    sel_mid   = str(mesa_row["mesa"]).upper()
    mc        = int(mesa_row["censo_ine"]) if pd.notna(mesa_row["censo_ine"]) else 0

    # Cargar tipo_10 y filtrar a esta mesa
    t10 = _load_t10()
    t10_mesa = t10[
        (t10["tipo_eleccion_cod"] == tipo) &
        (t10["anio"].astype(int) == anio) &
        (t10["mes"].astype(int) == mes) &
        (t10["vuelta"].astype(int) == vuelta) &
        (t10["provincia_cod"] == prov_cod) &
        (t10["municipio_cod"] == muni_cod) &
        (t10["distrito_num"].astype(str).str.zfill(2) == sel_dist) &
        (t10["seccion"].astype(str).str.zfill(4) == sel_sec) &
        (t10["mesa"].astype(str).str.upper() == sel_mid)
    ].copy()

    # Catálogo de partidos para esta convocatoria
    cat_all = _load_cat()
    cat_sel = (
        cat_all[
            (cat_all["tipo_eleccion_cod"] == tipo) &
            (cat_all["anio"].astype(int) == anio) &
            (cat_all["mes"].astype(int) == mes)
        ][["cod_candidatura", "siglas", "denominacion"]]
        .drop_duplicates("cod_candidatura")
    )

    with st.expander(f"📋 Resultados · {sel_mesa_label}", expanded=True):
        if not t10_mesa.empty:
            total_m    = int(t10_mesa["votos_obtenidos"].sum())
            pct_cand_m = total_m / mc * 100 if mc > 0 else 0.0
            n_partidos = int((t10_mesa["votos_obtenidos"] > 0).sum())

            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Censo mesa",           f"{mc:,}")
            d2.metric("Votos a candidaturas", f"{total_m:,}")
            d3.metric("% votos / censo",      f"{pct_cand_m:.1f}%",
                      help="Votos a candidaturas / censo. "
                           "No incluye blancos ni nulos (no disponibles a nivel mesa).")
            d4.metric("Partidos con votos",   str(n_partidos))

            t10_mesa = t10_mesa.merge(cat_sel, on="cod_candidatura", how="left")
            t10_mesa["pct_votos"] = (
                t10_mesa["votos_obtenidos"] / total_m * 100
            ).round(2) if total_m > 0 else 0.0
            t10_mesa = t10_mesa.sort_values("votos_obtenidos", ascending=False)

            tabla_m = t10_mesa[
                ["siglas", "denominacion", "votos_obtenidos", "pct_votos"]
            ].copy()
            tabla_m.columns = ["Siglas", "Denominación", "Votos", "% votos"]
            st.dataframe(
                tabla_m.reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Siglas":       st.column_config.TextColumn("Siglas", width="small"),
                    "Denominación": st.column_config.TextColumn("Denominación"),
                    "Votos":        st.column_config.NumberColumn("Votos", format="%d"),
                    "% votos":      st.column_config.NumberColumn("% votos", format="%.2f %%"),
                },
            )
        else:
            st.metric("Censo mesa", f"{mc:,}")
            st.caption("⚠️ Sin datos de tipo_10 para esta mesa.")

    # ── Mapa de la sección ───────────────────────────────────────────────────
    if not _FOLIUM_OK:
        return

    _csec_3      = "".join(c for c in str(sel_sec)[1:] if c.isdigit()).zfill(3)
    _nombre_dist = _NOMBRES_DISTRITO.get((prov_cod, muni_cod, sel_dist), "")
    _titulo_mapa = (
        f"🗺️ D{sel_dist}"
        + (f" {_nombre_dist}" if _nombre_dist else "")
        + f"  ·  Sección {_csec_3}"
    )
    with st.expander(_titulo_mapa, expanded=True):
        _cmun = str(muni_cod).zfill(3)
        _cdis = str(sel_dist).zfill(2)
        _gjson = None
        _map_error = None

        if not prov_cod:
            _map_error = (
                f"Provincia '{prov_nombre}' no encontrada en el catálogo INE. "
                "El mapa no puede cargarse."
            )
        else:
            with st.spinner("Cargando geometrías del INE…"):
                try:
                    _gjson = _fetch_district_geojson(prov_cod, _cmun, _cdis)
                except Exception as _e:
                    _map_error = (
                        f"Error al consultar el WFS del INE "
                        f"(CPRO={prov_cod}, CMUN={_cmun}, CDIS={_cdis}): "
                        f"{type(_e).__name__}: {_e}"
                    )

        if _gjson and _gjson.get("features"):
            _lons, _lats = [], []
            for _feat in _gjson["features"]:
                _g    = _feat["geometry"]
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
                _m.fit_bounds([[min(_lats), min(_lons)], [max(_lats), max(_lons)]])
            st_folium(_m, height=420, use_container_width=True, returned_objects=[])
            st.caption("Sección resaltada en rojo  ·  Fuente: INE Secciones Censales 2025")

        elif _map_error:
            st.error(_map_error)
        else:
            st.warning(
                f"El WFS del INE no devolvió secciones para "
                f"CPRO={prov_cod}, CMUN={_cmun}, CDIS={_cdis}. "
                "Puede que este municipio no tenga datos de cartografía en Secciones_2025."
            )


# ══════════════════════════════════════════════════════════════════════════════
# API v2 — render_mesa_sidebar / render_mesa_tab4 / helpers de datos
# Usada por 3_Municipales.py (y extensible a 2_Congreso.py)
# ══════════════════════════════════════════════════════════════════════════════

def ms_scope_label(state: dict) -> str:
    """Etiqueta corta del ámbito actualmente seleccionado."""
    prov_cod = state.get("prov_cod", "")
    muni_cod = state.get("muni_cod", "")
    sel_d    = state.get("sel_distritos", [])
    sel_m    = state.get("sel_mesas", [])
    if sel_m:
        return f"{len(sel_m)} mesa(s) seleccionada(s)"
    if sel_d:
        names = []
        for d in sel_d:
            nom = _NOMBRES_DISTRITO.get((prov_cod, muni_cod, d), "")
            names.append("D" + d + (" " + nom if nom else ""))
        return "Distrito(s): " + " · ".join(names)
    return "Todo el municipio"


def get_t10_conv(state: dict) -> pd.DataFrame:
    """tipo_10 para la convocatoria activa, filtrado por la selección actual."""
    t10 = _load_t10()
    df  = t10[
        (t10["tipo_eleccion_cod"] == state["tipo"]) &
        (t10["anio"].astype(int)   == state["anio"]) &
        (t10["mes"].astype(int)    == state["mes"]) &
        (t10["vuelta"].astype(int) == state["vuelta"]) &
        (t10["provincia_cod"]      == state["prov_cod"]) &
        (t10["municipio_cod"]      == state["muni_cod"])
    ].copy()
    if state.get("sel_distritos"):
        df = df[df["distrito_num"].astype(str).str.zfill(2).isin(state["sel_distritos"])]
    if state.get("sel_mesas"):
        df["_lbl"] = (
            "D" + df["distrito_num"].astype(str).str.zfill(2)
            + "  S" + df["seccion"].astype(str).str.zfill(4)
            + "  M" + df["mesa"].astype(str).str.upper()
        )
        df = df[df["_lbl"].isin(state["sel_mesas"])].drop(columns=["_lbl"])
    return df


def get_t10_all(state: dict) -> pd.DataFrame:
    """tipo_10 para TODAS las convocatorias del municipio, filtrado por selección."""
    t10 = _load_t10()
    df  = t10[
        (t10["tipo_eleccion_cod"] == state["tipo"]) &
        (t10["vuelta"].astype(int) == 1) &
        (t10["provincia_cod"]      == state["prov_cod"]) &
        (t10["municipio_cod"]      == state["muni_cod"])
    ].copy()
    if state.get("sel_distritos"):
        df = df[df["distrito_num"].astype(str).str.zfill(2).isin(state["sel_distritos"])]
    if state.get("sel_mesas"):
        df["_lbl"] = (
            "D" + df["distrito_num"].astype(str).str.zfill(2)
            + "  S" + df["seccion"].astype(str).str.zfill(4)
            + "  M" + df["mesa"].astype(str).str.upper()
        )
        df = df[df["_lbl"].isin(state["sel_mesas"])].drop(columns=["_lbl"])
    return df


def add_partido_label(df: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Une tipo_10 con el catálogo para añadir la columna 'partido'."""
    cat = _load_cat()
    cat_t = cat[cat["tipo_eleccion_cod"] == tipo].copy()
    cat_t["partido"] = cat_t["siglas"].where(
        cat_t["siglas"].notna() & (cat_t["siglas"].astype(str).str.strip() != ""),
        cat_t["denominacion"].astype(str).str[:28],
    )
    cat_t = cat_t.drop_duplicates(subset=["anio", "mes", "cod_candidatura"])
    df = df.merge(
        cat_t[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    df["partido"] = df["partido"].fillna(df["cod_candidatura"].astype(str))
    return df


def render_mesa_sidebar(
    tipo: str,
    anio: int,
    mes: int,
    vuelta: int,
    prov_nombre: str,
    muni_cod: str,
    muni_name: str,
    key_prefix: str = "",
    container=None,
    show_map_toggle: bool = True,
) -> dict:
    """
    Renderiza en el sidebar: toggle + multiselect de distritos + multiselect de mesas.
    Devuelve un dict con el estado completo de la selección.

    Claves del dict
    ────────────────
    active          bool
    tipo/anio/mes/vuelta  identidad de la convocatoria
    prov_nombre / prov_cod / muni_cod / muni_name
    key_prefix
    muni_distritos  list[str]  todos los distritos (zfill 2)
    sel_distritos   list[str]  distritos elegidos (vacío = todos)
    sel_mesas       list[str]  etiquetas de mesa elegidas (vacío = todas)
    df_t09_muni     DataFrame  tipo_09 completo para este municipio/conv
    df_t09_sel      DataFrame  tipo_09 filtrado por la selección
    """
    _ct = container if container is not None else st.sidebar
    prov_cod = PROV_NOMBRE_A_COD.get(prov_nombre, "")
    state: dict = {
        "active": False,
        "tipo": tipo, "anio": anio, "mes": mes, "vuelta": vuelta,
        "prov_nombre": prov_nombre, "prov_cod": prov_cod,
        "muni_cod": muni_cod, "muni_name": muni_name,
        "key_prefix": key_prefix,
        "muni_distritos": [], "sel_distritos": [], "sel_mesas": [],
        "df_t09_muni": None, "df_t09_sel": None,
    }

    with st.sidebar:
        st.divider()
        mostrar = st.toggle(
            "🗳️ Desglosar por mesa",
            value=False,
            key=f"{key_prefix}_toggle_mesa",
            help=(
                "Activa el desglose por distrito/sección/mesa. "
                "Los tabs de Resultados y Evolución se ajustan a la selección. "
                "Primera carga ~10 s."
            ),
        )
    state["active"] = mostrar
    if not mostrar:
        return state

    # ── Toggle mapa por sección ──────────────────────────────────────────────
    sec_detail = False
    if show_map_toggle:
        with _ct:
            sec_detail = st.toggle(
                "📍 Mapa por sección",
                value=False,
                key=f"{key_prefix}_sec_detail",
                help=(
                    "En el tab Mapa: colorea cada sección censal individualmente "
                    "por partido ganador, sin necesidad de seleccionar un distrito. "
                    "Más detalle, mayor tiempo de carga."
                ),
            )
    state["sec_detail"] = sec_detail

    # ── Cargar tipo_09 ───────────────────────────────────────────────────────
    t09 = _load_t09()
    df_muni = t09[
        (t09["tipo_eleccion_cod"] == tipo) &
        (t09["anio"].astype(int)   == anio) &
        (t09["mes"].astype(int)    == mes) &
        (t09["vuelta"].astype(int) == vuelta) &
        (t09["provincia_cod"]      == prov_nombre) &
        (t09["municipio_cod"]      == muni_cod)
    ].copy()

    if df_muni.empty:
        with _ct:
            st.caption("⚠️ Sin datos de mesa para esta convocatoria.")
        return state

    df_muni["mesa_label"] = (
        "D"  + df_muni["distrito_num"].astype(str).str.zfill(2)
        + "  S" + df_muni["seccion"].astype(str).str.zfill(4)
        + "  M" + df_muni["mesa"].astype(str).str.upper()
    )
    state["df_t09_muni"] = df_muni

    # ── Distritos ────────────────────────────────────────────────────────────
    distritos_map  = _load_distritos()
    muni_distritos = distritos_map.get((prov_cod, muni_cod), [])
    if not muni_distritos:
        muni_distritos = sorted(
            df_muni["distrito_num"].astype(str).str.zfill(2).unique()
        )
    state["muni_distritos"] = muni_distritos

    sel_distritos: list = []
    if len(muni_distritos) > 1:
        dist_opts = [
            ("D" + d + ("  " + _NOMBRES_DISTRITO.get((prov_cod, muni_cod, d), "")).rstrip()).rstrip()
            for d in muni_distritos
        ]
        with _ct:
            sel_dist_raw = st.multiselect(
                "Distritos  (vacío = todos)",
                dist_opts,
                key=f"{key_prefix}_distritos",
            )
        sel_distritos = [r[1:3] for r in sel_dist_raw]  # "D01  Centro" → "01"
    state["sel_distritos"] = sel_distritos

    # Filtrar t09 por distritos
    df_f = df_muni.copy()
    if sel_distritos:
        df_f = df_f[df_f["distrito_num"].astype(str).str.zfill(2).isin(sel_distritos)]

    # ── Mesas ────────────────────────────────────────────────────────────────
    mesa_opts = sorted(df_f["mesa_label"].unique())
    with _ct:
        sel_mesas = st.multiselect(
            "Mesas  (vacío = todas)",
            mesa_opts,
            key=f"{key_prefix}_mesas",
        )
    state["sel_mesas"] = sel_mesas

    if sel_mesas:
        df_f = df_f[df_f["mesa_label"].isin(sel_mesas)]
    state["df_t09_sel"] = df_f

    return state


def render_mesa_map(
    state: dict,
    df_t10: "pd.DataFrame | None" = None,
    color_fn=None,
    key: str = "mesa_map",
    height: int = 440,
) -> None:
    """
    Renderiza un mapa folium con las secciones censales de los distritos
    activos en *state*.

    Modos de color
    ──────────────
    • Si se pasa df_t10 (con columna 'partido'), cada sección se colorea
      con el color del partido que más votos obtuvo en ella.
    • Sin df_t10, las secciones seleccionadas se muestran en rojo y el
      resto del distrito en azul.

    Parámetros
    ──────────
    state     : dict de render_mesa_sidebar()
    df_t10    : DataFrame con columnas distrito_num, seccion, partido,
                votos_obtenidos (ya etiquetado con add_partido_label)
    color_fn  : callable(array_partidos) → dict {partido: hex_color}
    key       : clave única del widget st_folium
    height    : altura del mapa en px
    """
    if not _FOLIUM_OK:
        return

    prov_cod = state.get("prov_cod", "")
    muni_cod = state.get("muni_cod", "")
    if not prov_cod:
        return
    _cmun = str(muni_cod).zfill(3)

    # ── Distritos a cargar ────────────────────────────────────────────────────
    sel_distritos = state.get("sel_distritos", [])
    sel_mesas_lbl = state.get("sel_mesas", [])

    # Extraer distrito de etiquetas "D01  S0001  MA" → "01"
    mesa_dists = {
        lbl[1:3] for lbl in sel_mesas_lbl
        if len(lbl) >= 3 and lbl.startswith("D")
    }
    show_dists = sorted(set(sel_distritos) | mesa_dists)

    if not show_dists:
        show_dists = list(state.get("muni_distritos", []))
    if not show_dists:
        _t09b = state.get("df_t09_muni")
        if _t09b is not None and not _t09b.empty:
            show_dists = sorted(
                _t09b["distrito_num"].apply(lambda x: str(int(x)).zfill(2)).unique()
            )
    if not show_dists:
        return

    # ── Secciones "activas" → set (CDIS, CSEC) ───────────────────────────────
    _t09_s = state.get("df_t09_sel")
    _t09_m = state.get("df_t09_muni")
    df_t09 = _t09_s if (_t09_s is not None and not _t09_s.empty) else _t09_m

    highlighted: set = set()
    if df_t09 is not None and not df_t09.empty:
        for _, r in df_t09.iterrows():
            try:
                cdis = str(int(r["distrito_num"])).zfill(2)
                csec = str(int(r["seccion"])).zfill(4)[1:]   # últimos 3 dígitos
            except (ValueError, TypeError):
                cdis = str(r["distrito_num"]).zfill(2)
                csec = str(r["seccion"]).zfill(4)[1:]
            highlighted.add((cdis, csec))

    # ── Color por partido ganador por sección ─────────────────────────────────
    sec_color: dict = {}    # (CDIS, CSEC) → hex color
    sec_tooltip: dict = {}  # (CDIS, CSEC) → {_tip1, _tip2, _tip3}
    if df_t10 is not None and not df_t10.empty and color_fn is not None:
        try:
            df_c = df_t10.copy()
            df_c["CDIS"] = df_c["distrito_num"].apply(lambda x: str(int(x)).zfill(2))
            df_c["CSEC"] = df_c["seccion"].apply(lambda x: str(int(x)).zfill(4)[1:])
            df_grp = df_c.groupby(["CDIS", "CSEC", "partido"], as_index=False)[
                "votos_obtenidos"
            ].sum()
            idx_win = df_grp.groupby(["CDIS", "CSEC"])["votos_obtenidos"].idxmax()
            df_win  = df_grp.loc[idx_win]
            cmap    = color_fn(df_win["partido"].unique())
            for _, r in df_win.iterrows():
                sec_color[(r["CDIS"], r["CSEC"])] = cmap.get(r["partido"], "#aaaaaa")
            # ── Top-3 por sección para el tooltip ────────────────────────────
            for (cdis, csec), grp_s in df_grp.groupby(["CDIS", "CSEC"]):
                total_sec = grp_s["votos_obtenidos"].sum()
                top3 = grp_s.nlargest(3, "votos_obtenidos")
                tips: list[str] = []
                for _, row in top3.iterrows():
                    pct = row["votos_obtenidos"] / total_sec * 100 if total_sec > 0 else 0
                    tips.append(f"{row['partido']}  {pct:.1f}%")
                while len(tips) < 3:
                    tips.append("—")
                sec_tooltip[(cdis, csec)] = {
                    "_tip1": tips[0],
                    "_tip2": tips[1],
                    "_tip3": tips[2],
                }
        except Exception:
            sec_color = {}   # fallback silencioso a modo de selección
            sec_tooltip = {}

    # ── Descargar y fusionar GeoJSON ──────────────────────────────────────────
    all_features: list = []
    _map_err: str | None = None
    with st.spinner(f"Cargando geometrías · {len(show_dists)} distrito(s)…"):
        for _cdis in show_dists:
            try:
                _gjson = _fetch_district_geojson(prov_cod, _cmun, _cdis)
                if _gjson and _gjson.get("features"):
                    all_features.extend(_gjson["features"])
            except Exception as _e:
                _map_err = f"{type(_e).__name__}: {_e}"
                break

    if not all_features:
        if _map_err:
            st.error(f"Error WFS INE: {_map_err}")
        else:
            st.warning("El INE no devolvió geometrías para los distritos seleccionados.")
        return

    merged = {"type": "FeatureCollection", "features": all_features}

    # ── Inyectar resultados electorales en propiedades GeoJSON para tooltip ──
    if sec_tooltip:
        _empty_tip = {"_tip1": "—", "_tip2": "—", "_tip3": "—"}
        for _feat in all_features:
            _p = _feat.get("properties", {})
            _k = (_p.get("CDIS", ""), _p.get("CSEC", ""))
            _p.update(sec_tooltip.get(_k, _empty_tip))

    # ── Función de estilo (closure sobre sec_color / highlighted) ────────────
    def _sty_multi(_f, _hl=highlighted, _sc=sec_color):
        _props = _f.get("properties", {})
        _cdis  = _props.get("CDIS", "")
        _csec  = _props.get("CSEC", "")
        _k     = (_cdis, _csec)

        if _sc:   # modo partido ganador
            _col  = _sc.get(_k, "#cccccc")
            _bold = _k in _hl
            return {
                "fillColor":   _col,
                "color":       "#222222" if _bold else "#888888",
                "weight":      2.0       if _bold else 0.6,
                "fillOpacity": 0.80      if _bold else 0.40,
            }
        if _hl:   # modo selección → rojo/azul
            if _k in _hl:
                return {"fillColor": "#e74c3c", "color": "#c0392b",
                        "weight": 2.5, "fillOpacity": 0.65}
            return {"fillColor": "#3498db", "color": "#1a6ea8",
                    "weight": 0.8, "fillOpacity": 0.18}
        # todo el distrito sin selección concreta
        return {"fillColor": "#3498db", "color": "#1a6ea8",
                "weight": 0.8, "fillOpacity": 0.25}

    # ── Encuadre ──────────────────────────────────────────────────────────────
    _lons, _lats = [], []
    for _feat in all_features:
        _g     = _feat["geometry"]
        _rings = (
            [_g["coordinates"][0]] if _g["type"] == "Polygon"
            else [_p[0] for _p in _g["coordinates"]]
        )
        for _ring in _rings:
            for _xy in _ring:
                _lons.append(_xy[0]); _lats.append(_xy[1])

    # ── Renderizar ────────────────────────────────────────────────────────────
    _m = folium.Map(tiles="CartoDB positron")
    _tip_fields  = ["CDIS", "CSEC", "NMUN"]
    _tip_aliases = ["Distrito:", "Sección:", "Municipio:"]
    if sec_tooltip:
        _tip_fields  += ["_tip1", "_tip2", "_tip3"]
        _tip_aliases += ["🥇", "🥈", "🥉"]

    folium.GeoJson(
        merged,
        style_function=_sty_multi,
        tooltip=folium.GeoJsonTooltip(
            fields=_tip_fields,
            aliases=_tip_aliases,
            sticky=True,
        ),
    ).add_to(_m)
    if _lons:
        _m.fit_bounds([[min(_lats), min(_lons)], [max(_lats), max(_lons)]])
    st_folium(_m, height=height, use_container_width=True, returned_objects=[], key=key)

    n_sel = len(highlighted)
    if sec_color:
        st.caption(
            f"Cada sección coloreada por **partido ganador** · "
            f"{n_sel} sección(es) activa(s) · Fuente: INE Secciones Censales 2025"
        )
    elif highlighted:
        st.caption(
            f"🔴 {n_sel} sección(es) resaltada(s)  ·  "
            "🔵 Resto del distrito  ·  Fuente: INE Secciones Censales 2025"
        )
    else:
        st.caption(
            f"{len(all_features)} sección(es)  ·  Fuente: INE Secciones Censales 2025"
        )


def render_mesa_tab4(state: dict, top_n: int = 10, color_fn=None) -> None:
    """
    Renderiza el contenido del tab '🗳️ Por mesa'.

    Parámetros
    ----------
    state    : dict devuelto por render_mesa_sidebar()
    top_n    : top N partidos para el gráfico
    color_fn : callable(array_partidos) → dict  (party_color_map de utils)
    """
    import plotly.express as px

    if not state.get("active"):
        st.info(
            "💡 Activa el toggle **🗳️ Desglosar por mesa** en el panel lateral "
            "para ver este análisis. Selecciona primero exactamente 1 municipio."
        )
        return

    _t09_sel  = state.get("df_t09_sel")
    _t09_muni = state.get("df_t09_muni")
    df_t09 = _t09_sel if (_t09_sel is not None and not _t09_sel.empty) else _t09_muni
    if df_t09 is None or df_t09.empty:
        st.warning("⚠️ Sin datos de mesa para esta selección.")
        return

    muni_name = state["muni_name"]
    anio      = state["anio"]
    mes       = state["mes"]
    tipo      = state["tipo"]
    scope_lbl = ms_scope_label(state)

    st.subheader(f"🗳️ Por mesa · {muni_name} · {anio}/{mes:02d}")
    st.caption(f"Ámbito: **{scope_lbl}**")

    # ── KPIs participación ───────────────────────────────────────────────────
    n_mesas_v   = len(df_t09)
    total_censo = int(df_t09["censo_ine"].sum())
    total_cand  = int(df_t09["votos_candidaturas"].sum())
    vb = int(df_t09["votos_blanco"].sum())  if "votos_blanco" in df_t09.columns else 0
    vn = int(df_t09["votos_nulos"].sum())   if "votos_nulos"  in df_t09.columns else 0
    pct_p = total_cand / total_censo * 100  if total_censo > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Mesas",              f"{n_mesas_v:,}")
    k2.metric("Censo",              f"{total_censo:,}")
    k3.metric("Votos candidaturas", f"{total_cand:,}")
    k4.metric("% participación",    f"{pct_p:.1f}%")
    k5.metric("Blancos + nulos",    f"{vb + vn:,}")
    st.divider()

    # ── Tabla participación por mesa ─────────────────────────────────────────
    with st.expander("📋 Participación por mesa", expanded=False):
        cols_show = ["mesa_label", "censo_ine", "votos_candidaturas"]
        if "votos_blanco" in df_t09.columns:
            cols_show.append("votos_blanco")
        if "votos_nulos" in df_t09.columns:
            cols_show.append("votos_nulos")
        df_part = df_t09[cols_show].copy()
        df_part["pct_part"] = (
            df_part["votos_candidaturas"] / df_part["censo_ine"].replace(0, pd.NA) * 100
        ).round(1)
        rn = {"mesa_label": "Mesa", "censo_ine": "Censo",
              "votos_candidaturas": "Votos cand.",
              "votos_blanco": "Blancos", "votos_nulos": "Nulos",
              "pct_part": "% participación"}
        col_cfg_p = {
            "Censo":           st.column_config.NumberColumn("Censo", format="%d"),
            "Votos cand.":     st.column_config.NumberColumn("Votos cand.", format="%d"),
            "Blancos":         st.column_config.NumberColumn("Blancos", format="%d"),
            "Nulos":           st.column_config.NumberColumn("Nulos", format="%d"),
            "% participación": st.column_config.NumberColumn("% part.", format="%.1f %%"),
        }
        st.dataframe(
            df_part.rename(columns=rn).reset_index(drop=True),
            use_container_width=True, hide_index=True,
            column_config={k: v for k, v in col_cfg_p.items() if k in rn.values()},
        )

    # ── Resultados por partido por mesa (tipo_10) ────────────────────────────
    df_t10 = get_t10_conv(state)
    if df_t10.empty:
        st.info("ℹ️ No hay datos de votos por partido (tipo_10) para esta selección.")
        return

    df_t10 = add_partido_label(df_t10, tipo)
    df_t10["mesa_label"] = (
        "D"  + df_t10["distrito_num"].astype(str).str.zfill(2)
        + "  S" + df_t10["seccion"].astype(str).str.zfill(4)
        + "  M" + df_t10["mesa"].astype(str).str.upper()
    )

    df_ma = df_t10.groupby(["mesa_label", "partido"], as_index=False)["votos_obtenidos"].sum()
    df_ma["votos_total"] = df_ma.groupby("mesa_label")["votos_obtenidos"].transform("sum")
    df_ma["pct_voto"]    = (df_ma["votos_obtenidos"] / df_ma["votos_total"] * 100).round(2)

    top_p       = df_ma.groupby("partido")["votos_obtenidos"].sum().nlargest(top_n).index.tolist()
    df_chart    = df_ma[df_ma["partido"].isin(top_p)].sort_values("mesa_label")
    n_mc        = df_chart["mesa_label"].nunique()
    cmap        = color_fn(df_ma["partido"].unique()) if color_fn else {}

    if 0 < n_mc <= 150:
        fig = px.bar(
            df_chart,
            x="mesa_label", y="pct_voto", color="partido",
            barmode="stack",
            labels={"mesa_label": "Mesa", "pct_voto": "% votos", "partido": "Partido"},
            color_discrete_map=cmap,
            custom_data=["partido", "mesa_label", "pct_voto", "votos_obtenidos"],
        )
        fig.update_traces(hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Mesa: %{customdata[1]}<br>"
            "% Votos: %{customdata[2]:.2f}%<br>"
            "Votos: %{customdata[3]:,.0f}<extra></extra>"
        ))
        fig.update_layout(
            height=480,
            xaxis_tickangle=-50,
            legend=dict(orientation="h", yanchor="top", y=-0.38),
            margin=dict(b=150),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Top {top_n} partidos · {n_mc} mesas · "
            "D=Distrito  S=Sección  M=Mesa · Fuente: Min. del Interior"
        )
    elif n_mc > 150:
        st.info(
            f"⚠️ {n_mc} mesas en la selección — demasiadas para el gráfico. "
            "Selecciona distritos o mesas concretos en el panel lateral."
        )

    with st.expander("📋 Tabla completa por mesa", expanded=False):
        df_tabla = (
            df_ma[["mesa_label", "partido", "votos_obtenidos", "pct_voto"]]
            .sort_values(["mesa_label", "votos_obtenidos"], ascending=[True, False])
            .reset_index(drop=True)
        )
        st.dataframe(
            df_tabla, use_container_width=True, hide_index=True,
            column_config={
                "mesa_label":      st.column_config.TextColumn("Mesa"),
                "partido":         st.column_config.TextColumn("Partido"),
                "votos_obtenidos": st.column_config.NumberColumn("Votos", format="%d"),
                "pct_voto":        st.column_config.NumberColumn("% votos", format="%.2f %%"),
            },
        )

    # ── Detalle mesa única + mapa ────────────────────────────────────────────
    sel_mesas = state.get("sel_mesas", [])
    if len(sel_mesas) != 1:
        return

    sel_lbl = sel_mesas[0]
    t09_row = df_t09[df_t09["mesa_label"] == sel_lbl]
    if t09_row.empty:
        return
    row      = t09_row.iloc[0]
    sel_dist = str(row["distrito_num"]).zfill(2)
    sel_sec  = str(row["seccion"]).zfill(4)
    sel_mid  = str(row["mesa"]).upper()
    mc       = int(row["censo_ine"]) if pd.notna(row["censo_ine"]) else 0

    # Resultados de esta mesa exacta
    t10_mesa = df_t10[
        (df_t10["distrito_num"].astype(str).str.zfill(2) == sel_dist) &
        (df_t10["seccion"].astype(str).str.zfill(4)       == sel_sec) &
        (df_t10["mesa"].astype(str).str.upper()           == sel_mid)
    ].copy()

    with st.expander(f"📋 Resultados · {sel_lbl}", expanded=True):
        if not t10_mesa.empty:
            total_m    = int(t10_mesa["votos_obtenidos"].sum())
            n_part     = int((t10_mesa["votos_obtenidos"] > 0).sum())
            pct_m      = total_m / mc * 100 if mc > 0 else 0.0
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Censo mesa",           f"{mc:,}")
            d2.metric("Votos a candidaturas", f"{total_m:,}")
            d3.metric("% votos / censo",      f"{pct_m:.1f}%")
            d4.metric("Partidos con votos",   str(n_part))

            t10_mesa["pct"] = (
                t10_mesa["votos_obtenidos"] / total_m * 100
            ).round(2) if total_m > 0 else 0.0
            t10_mesa = t10_mesa.sort_values("votos_obtenidos", ascending=False)

            cat_conv = (
                _load_cat()[
                    (_load_cat()["tipo_eleccion_cod"] == tipo) &
                    (_load_cat()["anio"].astype(int)   == anio) &
                    (_load_cat()["mes"].astype(int)    == mes)
                ][["cod_candidatura", "siglas", "denominacion"]]
                .drop_duplicates("cod_candidatura")
            )
            t10_mesa = t10_mesa.merge(cat_conv, on="cod_candidatura", how="left")
            tabla_m  = t10_mesa[["siglas", "denominacion", "votos_obtenidos", "pct"]].copy()
            tabla_m.columns = ["Siglas", "Denominación", "Votos", "% votos"]
            st.dataframe(
                tabla_m.reset_index(drop=True), use_container_width=True, hide_index=True,
                column_config={
                    "Siglas":       st.column_config.TextColumn("Siglas", width="small"),
                    "Denominación": st.column_config.TextColumn("Denominación"),
                    "Votos":        st.column_config.NumberColumn("Votos", format="%d"),
                    "% votos":      st.column_config.NumberColumn("% votos", format="%.2f %%"),
                },
            )
        else:
            st.metric("Censo mesa", f"{mc:,}")
            st.caption("⚠️ Sin datos de tipo_10 para esta mesa.")

    # ── Mapa ─────────────────────────────────────────────────────────────────
    # ── Mapa de secciones ─────────────────────────────────────────────────────
    _nombre_dist = _NOMBRES_DISTRITO.get(
        (state["prov_cod"], state["muni_cod"], sel_dist), ""
    )
    _titulo_mapa = (
        f"🗺️ D{sel_dist}"
        + (f" {_nombre_dist}" if _nombre_dist else "")
        + f"  ·  Sección {sel_sec}"
    )
    with st.expander(_titulo_mapa, expanded=True):
        render_mesa_map(
            state,
            df_t10=df_t10,
            color_fn=color_fn,
            key="tab4_map_single",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  render_election_map  —  Mapa choropleth multinivel
#  Nacional → provincias  |  Provincia → municipios  |  Municipio → distritos
#  Distrito/Sección ya cubiertos por render_mesa_map
# ══════════════════════════════════════════════════════════════════════════════

_PROV_GEOJSON_URL = (
    "https://raw.githubusercontent.com/codeforgermany/click_that_hood/"
    "main/public/data/spain-provinces.geojson"
)

# Tabla de normalización: nombre de provincia en click_that_hood → código INE 2-dig
_CTHOOD_TO_PROV_COD: dict[str, str] = {
    "Álava": "01", "Alava": "01", "Araba/Álava": "01",
    "Albacete": "02",
    "Alicante": "03", "Alacant": "03", "Alacant/Alicante": "03",
    "Almería": "04", "Almeria": "04",
    "Ávila": "05", "Avila": "05",
    "Badajoz": "06",
    "Baleares": "07", "Illes Balears": "07", "Islas Baleares": "07",
    "Barcelona": "08",
    "Burgos": "09",
    "Cáceres": "10", "Caceres": "10",
    "Cádiz": "11", "Cadiz": "11",
    "Castellón": "12", "Castellon": "12", "Castelló": "12", "Castelló/Castellón": "12",
    "Ciudad Real": "13",
    "Córdoba": "14", "Cordoba": "14",
    "A Coruña": "15", "La Coruña": "15", "Coruña": "15",
    "Cuenca": "16",
    "Girona": "17", "Gerona": "17",
    "Granada": "18",
    "Guadalajara": "19",
    "Guipúzcoa": "20", "Gipuzkoa": "20", "Guipuzcoa": "20", "Gipuzkoa/Guipúzcoa": "20",
    "Huelva": "21",
    "Huesca": "22",
    "Jaén": "23", "Jaen": "23",
    "León": "24", "Leon": "24",
    "Lleida": "25", "Lérida": "25", "Lerida": "25",
    "La Rioja": "26",
    "Lugo": "27",
    "Madrid": "28",
    "Málaga": "29", "Malaga": "29",
    "Murcia": "30",
    "Navarra": "31", "Navarre": "31",
    "Ourense": "32", "Orense": "32",
    "Asturias": "33",
    "Palencia": "34",
    "Las Palmas": "35",
    "Pontevedra": "36",
    "Salamanca": "37",
    "Santa Cruz de Tenerife": "38", "Santa Cruz De Tenerife": "38", "Tenerife": "38",
    "Cantabria": "39",
    "Segovia": "40",
    "Sevilla": "41",
    "Soria": "42",
    "Tarragona": "43",
    "Teruel": "44",
    "Toledo": "45",
    "Valencia": "46", "València": "46", "València/Valencia": "46",
    "Valladolid": "47",
    "Vizcaya": "48", "Bizkaia": "48", "Bizkaia/Vizcaya": "48",
    "Zamora": "49",
    "Zaragoza": "50",
    "Ceuta": "51",
    "Melilla": "52",
}


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_prov_geojson() -> dict:
    """Descarga el GeoJSON de provincias de España (CDN estático, ~400 KB)."""
    req = urllib.request.Request(
        _PROV_GEOJSON_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_province_secciones(cpro: str) -> dict:
    """Descarga todas las secciones de una provincia (WFS, ~500–3000 features)."""
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": "WMS_INE_SECCIONES_G01:Secciones_2025",
        "OUTPUTFORMAT": "application/json", "SRSNAME": "EPSG:4326",
        "CQL_FILTER": f"CPRO='{cpro}'",
        "COUNT": "10000",
    }
    url = _WFS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    # Excluir secciones fantasma (CSEC=000 son distritos/municipio entero)
    data["features"] = [
        f for f in data.get("features", [])
        if f.get("properties", {}).get("CSEC", "000") != "000"
    ]
    return data


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_municipality_secciones(cpro: str, cmun: str) -> dict:
    """Descarga todas las secciones de un municipio (WFS)."""
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": "WMS_INE_SECCIONES_G01:Secciones_2025",
        "OUTPUTFORMAT": "application/json", "SRSNAME": "EPSG:4326",
        "CQL_FILTER": f"CPRO='{cpro}' AND CMUN='{cmun}'",
        "COUNT": "5000",
    }
    url = _WFS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    data["features"] = [
        f for f in data.get("features", [])
        if f.get("properties", {}).get("CSEC", "000") != "000"
    ]
    return data


def _top5_tooltip(
    df_agg: pd.DataFrame,
    color_fn,
    mun_name: str = "",
    extra_col: str | None = None,
    extra_label: str | None = None,
    show_votes: bool = False,
) -> str:
    """
    Dado un DataFrame con columnas [partido, votos_obtenidos, pct_voto]
    y opcionalmente [candidatos_obtenidos], devuelve HTML con los 5
    partidos más votados. Si mun_name se indica, lo incluye como cabecera.
    """
    top = df_agg.nlargest(5, "votos_obtenidos")
    cmap = color_fn(top["partido"].values) if color_fn else {}
    has_conc  = "candidatos_obtenidos" in top.columns
    has_extra = extra_col is not None and extra_col in top.columns
    lines = []
    if mun_name:
        lines.append(f"<b>{mun_name}</b>")
    for _, r in top.iterrows():
        col = cmap.get(r["partido"], "#888888")
        line = f'<span style="color:{col};font-weight:bold">{r["partido"]}</span>'
        if show_votes:
            line += f" \u2014 {int(r['votos_obtenidos']):,} votos ({r['pct_voto']:.1f}%)"
        else:
            line += f" \u2014 {r['pct_voto']:.1f}%"
        if has_conc and pd.notna(r.get("candidatos_obtenidos")):
            line += f" \u2014 {int(r['candidatos_obtenidos'])} conc."
        if has_extra:
            v = r.get(extra_col)
            if pd.notna(v) and v != 0:
                lbl = extra_label or extra_col
                line += f" \u2014 {int(v)} {lbl}"
        lines.append(line)
    return "<br>".join(lines)


def _fit_bounds_from_geojson(m: "folium.Map", features: list) -> None:
    """Ajusta el encuadre del mapa a los features dados."""
    lons, lats = [], []
    for feat in features:
        g = feat.get("geometry", {})
        if not g:
            continue
        rings = (
            [g["coordinates"][0]] if g["type"] == "Polygon"
            else [p[0] for p in g["coordinates"]]
        )
        for ring in rings:
            for xy in ring:
                lons.append(xy[0]); lats.append(xy[1])
    if lons:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])


def render_sm_map(
    cpro: str,
    cmun: str,
    muni_name: str,
    sel_conv: str,
    t12_conv: "pd.DataFrame",
    t11_row: "pd.Series | None",
    color_fn,
    key: str = "sm_map",
    height: int = 420,
) -> None:
    """
    Mapa de un municipio <250 hab usando el GeoJSON del INE.

    Colorea el polígono con el partido ganador y muestra un popup/tooltip
    con los resultados completos (participación + votos por partido).

    Parámetros
    ----------
    cpro      : código INE de provincia (2 dígitos, zfill), p.ej. "34"
    cmun      : código INE de municipio (3 dígitos, zfill), p.ej. "025"
    muni_name : nombre legible del municipio
    sel_conv  : convocatoria p.ej. "2023/05"
    t12_conv  : DataFrame filtrado de tipo_12 para este municipio y convocatoria
    t11_row   : Serie de tipo_11 con censo/votos, o None si no hay datos
    color_fn  : callable → dict{partido: hex}
    key       : clave única del widget st_folium
    height    : altura del mapa en px
    """
    if not _FOLIUM_OK:
        st.warning("📦 Instala `folium` y `streamlit-folium` para ver el mapa.")
        return

    with st.spinner(f"Cargando geometría de {muni_name}…"):
        try:
            gjson = _fetch_municipality_secciones(cpro, cmun)
        except Exception as e:
            st.error(f"Error al obtener el polígono del municipio: {e}")
            return

    if not gjson.get("features"):
        st.info(
            "ℹ️ El INE no devolvió secciones censales para este municipio. "
            "Es posible que con <100 habitantes no aparezca en el WFS."
        )
        return

    # Partido ganador (t12)
    if not t12_conv.empty:
        by_party = (
            t12_conv.drop_duplicates("cod_candidatura")
            [["partido", "votos_candidatura", "num_candidatos_electos"]]
            .sort_values("votos_candidatura", ascending=False)
            .reset_index(drop=True)
        )
        total_cv = by_party["votos_candidatura"].sum()
        by_party["pct_votos"] = (
            by_party["votos_candidatura"] / total_cv * 100
        ).round(1) if total_cv > 0 else 0.0
        winner = by_party.iloc[0]["partido"]
    else:
        by_party = pd.DataFrame()
        winner = "—"

    cmap = color_fn([winner]) if winner != "—" else {}
    fill_color = cmap.get(winner, "#b0c4de")

    # Construir HTML del popup
    lines_html = [
        f"<b style='font-size:14px'>{muni_name}</b><br>",
        f"<span style='color:#555'>Convocatoria: {sel_conv}</span><br><br>",
    ]
    if t11_row is not None:
        censo  = int(t11_row["censo_ine"])      if pd.notna(t11_row.get("censo_ine"))      else 0
        totv   = int(t11_row["total_votantes"]) if pd.notna(t11_row.get("total_votantes")) else 0
        partici = round(totv / censo * 100, 1) if censo > 0 else 0.0
        lines_html.append(
            f"<b>Censo:</b> {censo:,} &nbsp;|&nbsp; "
            f"<b>Votantes:</b> {totv:,} &nbsp;|&nbsp; "
            f"<b>Participación:</b> {partici:.1f}%<br><br>"
        )
    if not by_party.empty:
        lines_html.append("<b>Resultados:</b><br>")
        cmap_all = color_fn(by_party["partido"].values)
        for _, r in by_party.iterrows():
            col = cmap_all.get(r["partido"], "#888888")
            conc = int(r["num_candidatos_electos"])
            lines_html.append(
                f'<span style="color:{col};font-weight:bold">{r["partido"]}</span> '
                f'— {int(r["votos_candidatura"])} votos ({r["pct_votos"]:.1f}%)'
                + (f', <b>{conc} concejal{"es" if conc != 1 else ""}</b>' if conc > 0 else "")
                + "<br>"
            )
    popup_html = "".join(lines_html)

    # Tooltip breve
    tooltip_txt = (
        f"{muni_name} · {winner}"
        + (f" ({by_party.iloc[0]['pct_votos']:.1f}%)" if not by_party.empty else "")
    )

    m = folium.Map(tiles="CartoDB positron")
    folium.GeoJson(
        gjson,
        style_function=lambda _: {
            "fillColor": fill_color,
            "color": "#444444",
            "weight": 1.5,
            "fillOpacity": 0.75,
        },
        tooltip=folium.Tooltip(tooltip_txt, sticky=True),
        popup=folium.Popup(popup_html, max_width=340),
    ).add_to(m)
    _fit_bounds_from_geojson(m, gjson["features"])
    st_folium(m, height=height, use_container_width=True, returned_objects=[], key=key)
    st.caption(
        f"Fuente: INE (cartografía 2025) + Ministerio del Interior · {sel_conv}"
    )


def render_election_map(
    nivel: str,
    df_votos: pd.DataFrame,
    color_fn,
    sel_conv: str,
    sel_prov: list | None = None,
    sel_muni_label: str | None = None,
    sel_distrito: str | None = None,
    prov_nombre_a_cod: dict | None = None,
    mesa_state: dict | None = None,
    df_t11: "pd.DataFrame | None" = None,
    df_t12: "pd.DataFrame | None" = None,
    nacional_seat_df: "pd.DataFrame | None" = None,
    nacional_seat_col: str | None = None,
    nacional_seat_label: str | None = None,
    nacional_show_muni_wins: bool = False,
    nacional_prov_totals: "dict | None" = None,
    return_click: bool = False,
    key: str = "election_map",
    height: int = 520,
) -> "str | None":
    """
    Renderiza un mapa choropleth electoral interactivo según el nivel geográfico.

    Niveles
    -------
    Nacional   → polígonos de provincias, coloreados por partido ganador.
    Provincia  → secciones coloreadas por municipio ganador (1 provincia).
    Municipio  → secciones coloreadas por distrito (1 municipio).
    Distrito   → secciones coloreadas por partido ganador (delega a render_mesa_map).

    Parámetros
    ----------
    nivel           : "Nacional" | "Provincia" | "Municipio" | "Distrito"
    df_votos        : DataFrame agregado tipo_06 para la(s) convocatoria(s).
                      Columnas necesarias: provincia_cod, municipio_cod (opt),
                      partido, votos_obtenidos.
    color_fn        : callable(array_partidos) → dict{partido: hex}
    sel_conv        : convocatoria de referencia (ej. "2019/05")
    sel_prov        : lista de nombres de provincia (cuando nivel == Provincia)
    sel_muni_label  : etiqueta municipio "Nombre (prov)" (cuando nivel == Municipio)
    sel_distrito    : código distrito "01" … (cuando nivel == Distrito)
    prov_nombre_a_cod: dict nombre_prov → cod_2dig (de utils.PROV_NOMBRE_A_COD o similar)
    mesa_state      : dict de render_mesa_sidebar (para nivel Distrito)
    key             : clave única Streamlit
    height          : altura del mapa en px
    """
    if not _FOLIUM_OK:
        st.warning("📦 Instala `folium` y `streamlit-folium` para ver el mapa.")
        return

    anio_ref = int(sel_conv[:4])
    mes_ref  = int(sel_conv[5:])
    pnc = prov_nombre_a_cod or {}

    # ── Filtrar df_votos a la convocatoria de referencia ─────────────────────
    if "anio" in df_votos.columns and "mes" in df_votos.columns:
        df_conv = df_votos[
            (df_votos["anio"].astype(int) == anio_ref) &
            (df_votos["mes"].astype(int)  == mes_ref)
        ].copy()
    else:
        df_conv = df_votos.copy()

    # ════════════════════════════════════════════════════════════════
    #  NIVEL NACIONAL — polígonos de las 52 provincias
    # ════════════════════════════════════════════════════════════════
    if nivel == "Nacional":
        # ── Votos por provincia+partido ───────────────────────────────────
        df_pv = (
            df_conv.groupby(["provincia_cod", "partido"], as_index=False)
            ["votos_obtenidos"].sum()
        )
        if nacional_prov_totals:
            df_pv["votos_total"] = df_pv["provincia_cod"].map(nacional_prov_totals)
            df_pv["votos_total"] = df_pv["votos_total"].fillna(
                df_pv.groupby("provincia_cod")["votos_obtenidos"].transform("sum")
            )
        else:
            df_pv["votos_total"] = df_pv.groupby("provincia_cod")["votos_obtenidos"].transform("sum")
        df_pv["pct_voto"]    = (df_pv["votos_obtenidos"] / df_pv["votos_total"] * 100).round(1)

        # ── Extra: escaños / senadores (Congreso / Senado) ────────────────
        _extra_col_name: str | None  = None
        _extra_col_label: str | None = None
        if nacional_seat_df is not None and nacional_seat_col:
            _extra_col_name  = nacional_seat_col
            _extra_col_label = nacional_seat_label or nacional_seat_col
            _seat_slim = (
                nacional_seat_df[["provincia_cod", "partido", nacional_seat_col]]
                .copy()
            )
            df_pv = df_pv.merge(_seat_slim, on=["provincia_cod", "partido"], how="left")
            df_pv[nacional_seat_col] = df_pv[nacional_seat_col].fillna(0)

        # ── Extra: municipios ganados (Municipales) ───────────────────────
        if nacional_show_muni_wins and "municipio_cod" in df_conv.columns:
            _extra_col_name  = "_muni_wins"
            _extra_col_label = "municipios"
            _df_mw = df_conv.groupby(
                ["provincia_cod", "municipio_cod", "partido"], as_index=False
            )["votos_obtenidos"].sum()
            _mw_idx = _df_mw.groupby(
                ["provincia_cod", "municipio_cod"]
            )["votos_obtenidos"].idxmax()
            _df_mw_win = _df_mw.loc[_mw_idx][["provincia_cod", "partido"]]
            _df_mw_cnt = (
                _df_mw_win.groupby(["provincia_cod", "partido"], as_index=False)
                .size()
                .rename(columns={"size": "_muni_wins"})
            )
            df_pv = df_pv.merge(_df_mw_cnt, on=["provincia_cod", "partido"], how="left")
            df_pv["_muni_wins"] = df_pv["_muni_wins"].fillna(0).astype(int)

        # ── Winner y top-5 indexados por nombre de provincia ─────────────
        idx_win  = df_pv.groupby("provincia_cod")["votos_obtenidos"].idxmax()
        df_win   = df_pv.loc[idx_win].set_index("provincia_cod")

        top5_html: dict[str, str] = {}
        for prov_name, grp in df_pv.groupby("provincia_cod"):
            top5_html[prov_name] = _top5_tooltip(
                grp, color_fn,
                extra_col=_extra_col_name,
                extra_label=_extra_col_label,
                show_votes=True,
            )

        all_parties = df_win["partido"].unique()
        cmap        = color_fn(all_parties)

        # ── GeoJSON de provincias ─────────────────────────────────────────
        with st.spinner("Cargando geometrías de provincias…"):
            try:
                gjson = _fetch_prov_geojson()
            except Exception as e:
                st.error(f"No se pudo descargar el GeoJSON de provincias: {e}")
                return

        # Enriquecer features: resolver nombre GeoJSON → nombre en datos
        enriched = []
        for feat in gjson.get("features", []):
            props = feat.get("properties", {})
            pname = (
                props.get("name")
                or props.get("NAME_1")
                or props.get("provincia")
                or props.get("PROVINCIA")
                or ""
            )
            cod = _CTHOOD_TO_PROV_COD.get(pname, "")
            if not cod:
                for k, v in PROVINCIAS.items():
                    if v.lower() == pname.lower():
                        cod = k
                        break
            # Fallback genérico para nombres bilingües tipo "X/Y": probar cada parte
            if not cod and "/" in pname:
                for part in pname.split("/"):
                    part = part.strip()
                    cod = _CTHOOD_TO_PROV_COD.get(part, "")
                    if not cod:
                        for k, v in PROVINCIAS.items():
                            if v.lower() == part.lower():
                                cod = k
                                break
                    if cod:
                        break

            # Código INE → nombre de provincia tal como está en los datos
            prov_name_in_data = PROVINCIAS.get(cod, "")
            winner  = df_win.loc[prov_name_in_data, "partido"]  if prov_name_in_data in df_win.index  else "—"
            pct_win = df_win.loc[prov_name_in_data, "pct_voto"] if prov_name_in_data in df_win.index  else 0.0
            tooltip = top5_html.get(prov_name_in_data, "Sin datos")
            prov_name_es = PROVINCIAS.get(cod, pname)

            feat["properties"]["_cod_prov"]  = cod
            feat["properties"]["_winner"]    = winner
            feat["properties"]["_pct"]       = pct_win
            feat["properties"]["_top5"]      = tooltip
            feat["properties"]["_prov_name"] = prov_name_es
            enriched.append(feat)

        gjson_enriched = {"type": "FeatureCollection", "features": enriched}

        def _sty_nacional(f):
            winner = f["properties"].get("_winner", "")
            col    = cmap.get(winner, "#cccccc")
            return {"fillColor": col, "color": "#444444",
                    "weight": 1.0, "fillOpacity": 0.72}

        m = folium.Map(tiles="CartoDB positron", location=[40.4, -3.7], zoom_start=6)
        folium.GeoJson(
            gjson_enriched,
            style_function=_sty_nacional,
            tooltip=folium.GeoJsonTooltip(
                fields=["_prov_name", "_winner", "_pct", "_top5"],
                aliases=["Provincia:", "Ganador:", "% votos:", "Top 5:"],
                sticky=True,
                parse_html=True,
            ),
            popup=folium.GeoJsonPopup(
                fields=["_prov_name"],
                aliases=[""],
                parse_html=False,
            ) if return_click else None,
        ).add_to(m)
        _map_data = st_folium(
            m, height=height, use_container_width=True,
            returned_objects=["last_object_clicked_popup"] if return_click else [],
            key=key,
        )
        st.caption(
            f"Partido ganador por provincia · {sel_conv} · "
            "Fuente: Min. del Interior + INE"
        )
        if return_click:
            _popup = (_map_data or {}).get("last_object_clicked_popup") or ""
            if _popup:
                _plain = _re.sub(r'<[^>]+>', ' ', str(_popup))
                _plain = _re.sub(r'\s+', ' ', _plain).strip()
                return _plain
        return None

    # ════════════════════════════════════════════════════════════════
    #  NIVEL PROVINCIA — secciones coloreadas por municipio ganador
    # ════════════════════════════════════════════════════════════════
    if nivel == "Provincia":
        if not sel_prov:
            st.info("Selecciona al menos una provincia en el panel lateral para ver el mapa.")
            return
        # Usar la primera provincia seleccionada (el mapa es por provincia)
        prov_n  = sel_prov[0]
        cpro    = pnc.get(prov_n, "")
        if not cpro:
            st.warning(f"Código INE no encontrado para provincia '{prov_n}'.")
            return

        # Resultados por municipio
        df_pm = df_conv[df_conv["provincia_cod"] == prov_n].copy()
        if df_pm.empty:
            st.warning("Sin datos electorales para esta provincia en la convocatoria seleccionada.")
            return

        # Agregado por municipio+partido (incluyendo concejales de tipo_06)
        _agg_cols: dict
        if "candidatos_obtenidos" in df_pm.columns:
            _agg_cols = {"votos_obtenidos": ("votos_obtenidos", "sum"),
                         "candidatos_obtenidos": ("candidatos_obtenidos", "sum")}
        else:
            _agg_cols = {"votos_obtenidos": ("votos_obtenidos", "sum")}
        df_pm_agg = df_pm.groupby(["municipio_cod", "partido"], as_index=False).agg(**_agg_cols)
        df_pm_agg["votos_total"] = df_pm_agg.groupby("municipio_cod")["votos_obtenidos"].transform("sum")
        df_pm_agg["pct_voto"]    = (df_pm_agg["votos_obtenidos"] / df_pm_agg["votos_total"] * 100).round(1)

        idx_win = df_pm_agg.groupby("municipio_cod")["votos_obtenidos"].idxmax()
        df_mwi  = df_pm_agg.loc[idx_win].set_index("municipio_cod")

        # Nombre de municipio para tooltip
        mun_names: dict[str, str] = {}
        if "nombre_municipio" in df_conv.columns:
            for _, r in (
                df_conv[df_conv["provincia_cod"] == prov_n]
                [["municipio_cod", "nombre_municipio"]]
                .drop_duplicates("municipio_cod").iterrows()
            ):
                mun_names[r["municipio_cod"]] = str(r["nombre_municipio"])

        # Datos de participación para municipios <250 hab (sistema mayoritario, tipo_11)
        t11_by_cmun: dict = {}
        if df_t11 is not None and not df_t11.empty:
            df_t11_prov = df_t11[
                (df_t11["provincia_cod"] == prov_n) &
                (df_t11["anio"].astype(int) == anio_ref) &
                (df_t11["mes"].astype(int) == mes_ref)
            ]
            for _, r in df_t11_prov.iterrows():
                cmun_t11 = str(r["municipio_cod"])
                t11_by_cmun[cmun_t11] = r
                if cmun_t11 not in mun_names and pd.notna(r.get("nombre_municipio")):
                    mun_names[cmun_t11] = str(r["nombre_municipio"]).title()

        # Candidaturas de municipios <250 hab desde tipo_12
        t12_muni_map: dict[str, pd.DataFrame] = {}
        if df_t12 is not None and not df_t12.empty:
            _t12_prov = df_t12[
                (df_t12["provincia_cod"] == cpro) &
                (df_t12["conv"] == sel_conv)
            ]
            for _cmun_t12, _grp in _t12_prov.groupby("municipio_cod"):
                _by_p = (
                    _grp.drop_duplicates("cod_candidatura")
                    [["partido", "votos_candidatura", "num_candidatos_electos"]]
                    .sort_values("votos_candidatura", ascending=False)
                    .reset_index(drop=True)
                )
                _total_cv = _by_p["votos_candidatura"].sum()
                _by_p["pct_voto"] = (
                    _by_p["votos_candidatura"] / _total_cv * 100
                ).round(1) if _total_cv > 0 else 0.0
                _by_p = _by_p.rename(columns={
                    "votos_candidatura": "votos_obtenidos",
                    "num_candidatos_electos": "candidatos_obtenidos",
                })
                _cmun_key = str(_cmun_t12).zfill(3)
                t12_muni_map[_cmun_key] = _by_p

        # Cmap: incluir ganadores de tipo_06 + tipo_12
        _all_p_list = list(df_mwi["partido"].unique())
        for _by_p in t12_muni_map.values():
            if not _by_p.empty:
                _w = _by_p.iloc[0]["partido"]
                if _w not in _all_p_list:
                    _all_p_list.append(_w)
        cmap = color_fn(_all_p_list)

        # GeoJSON secciones de la provincia
        with st.spinner(f"Cargando secciones de {prov_n}… (primera vez puede tardar)"):
            try:
                gjson = _fetch_province_secciones(cpro)
            except Exception as e:
                st.error(f"Error WFS INE: {e}")
                return
        if not gjson.get("features"):
            st.warning("El INE no devolvió secciones para esta provincia.")
            return

        # Enriquecer features con datos electorales del municipio
        for feat in gjson["features"]:
            props    = feat["properties"]
            cmun     = props.get("CMUN", "")
            mun_name = mun_names.get(cmun) or props.get("NMUN", cmun)
            if cmun in df_mwi.index:
                winner  = df_mwi.loc[cmun, "partido"]
                _bp     = df_pm_agg[df_pm_agg["municipio_cod"] == cmun]
                tooltip = _top5_tooltip(_bp, color_fn, mun_name=mun_name)
            elif cmun in t12_muni_map:
                _by_p   = t12_muni_map[cmun]
                winner  = _by_p.iloc[0]["partido"] if not _by_p.empty else "—"
                tooltip = _top5_tooltip(_by_p, color_fn, mun_name=mun_name)
            elif cmun in t11_by_cmun:
                t11r    = t11_by_cmun[cmun]
                censo   = int(t11r["censo_ine"])      if pd.notna(t11r.get("censo_ine"))      else 0
                totv    = int(t11r["total_votantes"]) if pd.notna(t11r.get("total_votantes")) else 0
                partici = round(totv / censo * 100, 1) if censo > 0 else 0.0
                winner  = "—"
                tooltip = (
                    f"<b>{mun_name}</b><br>"
                    f"<i>Sin candidaturas &lt;250 hab</i><br>"
                    f"Participaci\u00f3n: {partici:.1f}%"
                )
            else:
                winner  = "—"
                tooltip = f"<b>{mun_name}</b><br><i>Sin datos</i>"
            props["_winner"]       = winner
            props["_tooltip_html"] = tooltip
            props["_mun_name"]     = mun_name

        def _sty_prov(f):
            winner = f["properties"].get("_winner", "")
            col    = cmap.get(winner, "#cccccc")
            return {"fillColor": col, "color": "#666666",
                    "weight": 0.4, "fillOpacity": 0.70}

        m = folium.Map(tiles="CartoDB positron")
        folium.GeoJson(
            gjson,
            style_function=_sty_prov,
            tooltip=folium.GeoJsonTooltip(
                fields=["_tooltip_html"],
                aliases=[""],
                sticky=True,
                parse_html=True,
            ),
            popup=folium.GeoJsonPopup(
                fields=["_mun_name"],
                aliases=[""],
                parse_html=False,
            ) if return_click else None,
        ).add_to(m)
        _fit_bounds_from_geojson(m, gjson["features"])
        _sfdata = st_folium(
            m, height=height, use_container_width=True,
            returned_objects=["last_object_clicked_popup"] if return_click else [],
            key=key,
        )
        st.caption(
            f"Partido ganador por municipio · {prov_n} · {sel_conv} · "
            "Fuente: Min. del Interior + INE"
        )
        if return_click:
            return (_sfdata or {}).get("last_object_clicked_popup")
        return

    # ════════════════════════════════════════════════════════════════
    #  NIVEL MUNICIPIO — secciones coloreadas por distrito ganador
    # ════════════════════════════════════════════════════════════════
    if nivel == "Municipio":
        # Necesitamos los datos a nivel de mesa (tipo_10) para el nivel de distrito.
        # Si no hay mesa_state activo, mostramos aviso.
        if not mesa_state or not mesa_state.get("active"):
            st.info(
                "💡 Activa **🗳️ Desglosar por mesa** en el panel lateral "
                "para ver el mapa a nivel de distrito / sección."
            )
            return

        prov_cod = mesa_state.get("prov_cod", "")
        muni_cod = mesa_state.get("muni_cod", "")
        muni_name = mesa_state.get("muni_name", "")
        cpro  = prov_cod.zfill(2) if prov_cod else ""
        cmun  = str(muni_cod).zfill(3)

        if not cpro or not cmun:
            st.warning("Datos de municipio no disponibles.")
            return

        # Cargar votos por distrito desde tipo_10
        tipo  = mesa_state.get("tipo", "Municipales")
        df_t10_m = get_t10_conv(mesa_state)
        if df_t10_m.empty:
            st.warning("Sin datos de mesa para este municipio.")
            return
        df_t10_m = add_partido_label(df_t10_m, tipo)

        # ── Mapa por sección (toggle sec_detail) ─────────────────────────────
        if mesa_state.get("sec_detail", False):
            render_mesa_map(
                mesa_state,
                df_t10=df_t10_m if not df_t10_m.empty else None,
                color_fn=color_fn,
                key=key,
                height=height,
            )
            st.caption(
                f"Partido ganador por sección · {muni_name} · {sel_conv} · "
                "Fuente: Min. del Interior + INE"
            )
            return

        # Agrupar por distrito
        df_dm = df_t10_m.copy()
        df_dm["CDIS"] = df_dm["distrito_num"].apply(lambda x: str(int(x)).zfill(2))
        df_dist = df_dm.groupby(["CDIS", "partido"], as_index=False)["votos_obtenidos"].sum()
        df_dist["votos_total"] = df_dist.groupby("CDIS")["votos_obtenidos"].transform("sum")
        df_dist["pct_voto"]    = (df_dist["votos_obtenidos"] / df_dist["votos_total"] * 100).round(1)

        idx_win  = df_dist.groupby("CDIS")["votos_obtenidos"].idxmax()
        df_dwi   = df_dist.loc[idx_win].set_index("CDIS")
        top5_dist = {
            cdis: _top5_tooltip(grp, color_fn)
            for cdis, grp in df_dist.groupby("CDIS")
        }
        all_p  = df_dwi["partido"].unique()
        cmap   = color_fn(all_p)

        # Nombres de distrito
        dist_names: dict[str, str] = {}
        for cdis in df_dwi.index:
            nom = _NOMBRES_DISTRITO.get((prov_cod, muni_cod, cdis), "")
            dist_names[cdis] = f"D{cdis}" + (f" {nom}" if nom else "")

        # GeoJSON secciones del municipio
        with st.spinner(f"Cargando secciones de {muni_name}…"):
            try:
                gjson = _fetch_municipality_secciones(cpro, cmun)
            except Exception as e:
                st.error(f"Error WFS INE: {e}")
                return
        if not gjson.get("features"):
            st.warning("El INE no devolvió secciones para este municipio.")
            return

        # Enriquecer features
        for feat in gjson["features"]:
            props = feat["properties"]
            cdis  = props.get("CDIS", "")
            winner = df_dwi.loc[cdis, "partido"]  if cdis in df_dwi.index else "—"
            pct_w  = df_dwi.loc[cdis, "pct_voto"] if cdis in df_dwi.index else 0.0
            props["_winner"]    = winner
            props["_pct"]       = pct_w
            props["_top5"]      = top5_dist.get(cdis, "Sin datos")
            props["_dist_name"] = dist_names.get(cdis, f"D{cdis}")

        def _sty_muni(f):
            winner = f["properties"].get("_winner", "")
            col    = cmap.get(winner, "#cccccc")
            return {"fillColor": col, "color": "#555555",
                    "weight": 0.5, "fillOpacity": 0.72}

        m = folium.Map(tiles="CartoDB positron")
        folium.GeoJson(
            gjson,
            style_function=_sty_muni,
            tooltip=folium.GeoJsonTooltip(
                fields=["_dist_name", "_winner", "_pct", "_top5"],
                aliases=["Distrito:", "Ganador:", "% votos:", "Top 5:"],
                sticky=True,
                parse_html=True,
            ),
        ).add_to(m)
        _fit_bounds_from_geojson(m, gjson["features"])
        st_folium(m, height=height, use_container_width=True,
                  returned_objects=[], key=key)
        st.caption(
            f"Partido ganador por distrito · {muni_name} · {sel_conv} · "
            "Fuente: Min. del Interior + INE"
        )
        return

    # ════════════════════════════════════════════════════════════════
    #  NIVEL DISTRITO — delegar a render_mesa_map
    # ════════════════════════════════════════════════════════════════
    if nivel == "Distrito" and mesa_state:
        df_t10_d = get_t10_conv(mesa_state)
        if not df_t10_d.empty:
            df_t10_d = add_partido_label(df_t10_d, mesa_state.get("tipo", "Municipales"))
        render_mesa_map(
            mesa_state,
            df_t10=df_t10_d if not df_t10_d.empty else None,
            color_fn=color_fn,
            key=key,
            height=height,
        )

