"""
Participación histórica — Herramienta Pericles
Fuente: tipo_05.parquet
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unicodedata
import streamlit as st
import plotly.express as px
import pandas as pd
from utils import DATA_DIR, COLS_TIPO05, enrich_tipo05, etiqueta_conv, sort_conv


def _strip_accents(s: str) -> str:
    """Devuelve la cadena sin diacríticos (para comparación)."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def _title_es(s) -> str:
    """Title case que respeta ñ/Ñ: capitaliza solo tras espacios, no en límites Unicode."""
    if not isinstance(s, str):
        return s
    return ' '.join(w.capitalize() for w in s.strip().split())


def _muni_key(s) -> str:
    """Clave de comparación: sin tildes, sin ñ, sin '?' corruptos, minúsculas.
    Trata ñ → n y '?' → n (ambos son la misma corrupción en DAT históricos del MIR).
    """
    if not isinstance(s, str):
        return s
    return _strip_accents(s.replace('?', 'n').replace('Ñ', 'N').replace('ñ', 'n')).lower()

TIPOS_RELEVANTES = ["Congreso", "Senado", "Municipales", "Parlamento Europeo"]

st.set_page_config(page_title="Participación histórica", page_icon="📊", layout="wide")
st.title("📊 Participación histórica")


@st.cache_data(show_spinner="Cargando datos…")
def _load_t05():
    df = pd.read_parquet(str(DATA_DIR / "tipo_05.parquet"), columns=COLS_TIPO05)
    df = enrich_tipo05(df)
    df = df[df["tipo_eleccion_cod"].isin(TIPOS_RELEVANTES)]
    df = df[df["vuelta"].astype(str) == "1"]
    # Normalizar capitalización (usando _title_es para respetar ñ)
    df["nombre_municipio"] = df["nombre_municipio"].apply(_title_es)
    df["ccaa_nombre"]      = df["ccaa_nombre"].apply(_title_es)
    df["provincia_cod"]    = df["provincia_cod"].apply(_title_es)
    # Clave sin tildes/ñ/'?' para agrupar variantes históricas (BREÑA / BRENA / Bre?a → misma clave)
    df["_muni_key"] = df["nombre_municipio"].apply(_muni_key)
    # Nombre canónico: preferir variantes SIN '?' (datos corruptos); entre las buenas, la más frecuente
    def _best_name(x):
        good = x[~x.str.contains('?', regex=False, na=False)]
        pool = good if len(good) > 0 else x
        return pool.value_counts().index[0]
    canon = (
        df.groupby("_muni_key")["nombre_municipio"]
        .agg(_best_name)
        .rename("_muni_canon")
    )
    df = df.join(canon, on="_muni_key")
    return df


df_raw = _load_t05()

# ── Resumen global (siempre los 4 tipos, sin filtros) ─────────────────────────
resumen = (
    df_raw.groupby("tipo_eleccion_cod")[["anio", "mes"]]
    .apply(lambda x: x.drop_duplicates().shape[0], include_groups=False)
    .reset_index(name="convocatorias")
    .set_index("tipo_eleccion_cod")
    .reindex(TIPOS_RELEVANTES)
    .reset_index()
)
st.subheader("Convocatorias en el dataset")
cols_res = st.columns(len(TIPOS_RELEVANTES))
for i, row in enumerate(resumen.itertuples()):
    cols_res[i].metric(row.tipo_eleccion_cod, f"{int(row.convocatorias)} conv.")

st.divider()

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.header("Filtros")

sel_tipo = st.sidebar.multiselect(
    "Tipo de elección", TIPOS_RELEVANTES, default=["Congreso", "Senado"],
    key="part_tipo"
)

ccaa_opts = ["Todas"] + sorted(df_raw["ccaa_nombre"].dropna().unique())
sel_ccaa  = st.sidebar.selectbox("Comunidad Autónoma", ccaa_opts, key="part_ccaa")

_df_ccaa  = df_raw[df_raw["ccaa_nombre"] == sel_ccaa] if sel_ccaa != "Todas" else df_raw
prov_opts = ["Todas"] + sorted(_df_ccaa["provincia_cod"].dropna().unique())
sel_prov  = st.sidebar.selectbox("Provincia", prov_opts, key="part_prov")

_df_prov  = _df_ccaa[_df_ccaa["provincia_cod"] == sel_prov] if sel_prov != "Todas" else _df_ccaa
muni_opts = ["Todos"] + sorted(_df_prov["_muni_canon"].dropna().unique())
sel_muni  = st.sidebar.selectbox("Municipio", muni_opts, key="part_muni")

# ── Aplicar filtros ────────────────────────────────────────────────────────────
mask = pd.Series(True, index=df_raw.index)
if sel_tipo:
    mask &= df_raw["tipo_eleccion_cod"].isin(sel_tipo)
if sel_ccaa != "Todas":
    mask &= df_raw["ccaa_nombre"] == sel_ccaa
if sel_prov != "Todas":
    mask &= df_raw["provincia_cod"] == sel_prov
if sel_muni != "Todos":
    # Comparar usando clave normalizada para unir variantes históricas (BREÑA/BRENA/Bre?a)
    sel_key = _muni_key(sel_muni)
    mask &= df_raw["_muni_key"] == sel_key

df = df_raw[mask].copy()

if df.empty:
    st.warning("Sin datos para los filtros seleccionados.")
    st.stop()

# ── Agregación por convocatoria ────────────────────────────────────────────────
grp = (
    df.groupby(["tipo_eleccion_cod", "anio", "mes"])
    .agg(
        censo=("censo_ine", "sum"),
        votos_emitidos=("votos_emitidos", "sum"),
        blancos=("votos_blanco", "sum"),
        nulos=("votos_nulos", "sum"),
        mesas=("num_mesas", "sum"),
    )
    .reset_index()
)
grp["participacion_pct"] = (grp["votos_emitidos"] / grp["censo"].replace(0, pd.NA) * 100).round(2)
grp["abstencion_pct"]    = (100 - grp["participacion_pct"]).round(2)
grp["blancos_pct"]       = (grp["blancos"] / grp["votos_emitidos"].replace(0, pd.NA) * 100).round(2)
grp["nulos_pct"]         = (grp["nulos"]   / grp["votos_emitidos"].replace(0, pd.NA) * 100).round(2)
grp["etiqueta"]          = grp.apply(lambda r: etiqueta_conv(r["anio"], r["mes"]), axis=1)
grp = sort_conv(grp)
_conv_order = list(dict.fromkeys(grp["etiqueta"]))

# ── KPIs del período filtrado (por tipo) ──────────────────────────────────────
st.subheader("Indicadores del período seleccionado")
kpi_tipo = (
    grp.groupby("tipo_eleccion_cod", as_index=False)
    .agg(convocatorias=("etiqueta", "nunique"), part_media=("participacion_pct", "mean"))
    .sort_values("convocatorias", ascending=False)
)
cols_k = st.columns(max(len(kpi_tipo), 1))
for i, row in enumerate(kpi_tipo.itertuples()):
    cols_k[i].metric(row.tipo_eleccion_cod, f"{row.part_media:.1f} % part.", f"{int(row.convocatorias)} conv.")

st.divider()

# ── Gráfico principal: evolución de participación ─────────────────────────────
st.subheader("Evolución de la participación")
fig1 = px.line(
    grp, x="etiqueta", y="participacion_pct",
    color="tipo_eleccion_cod", markers=True,
    labels={"etiqueta": "Convocatoria", "participacion_pct": "% participación", "tipo_eleccion_cod": "Tipo"},
    category_orders={"etiqueta": _conv_order},
    height=420,
)
fig1.update_layout(xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.35))
st.plotly_chart(fig1, use_container_width=True)

# ── Gráficos secundarios ───────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("Participación media por tipo")
    avg_tipo = (
        grp.groupby("tipo_eleccion_cod", as_index=False)
        .agg(part_media=("participacion_pct", "mean"), abs_media=("abstencion_pct", "mean"))
        .sort_values("part_media", ascending=True)
    )
    avg_melt = avg_tipo.melt(id_vars="tipo_eleccion_cod", var_name="variable", value_name="pct")
    avg_melt["variable"] = avg_melt["variable"].map({"part_media": "Participación", "abs_media": "Abstención"})
    fig2 = px.bar(
        avg_melt, x="pct", y="tipo_eleccion_cod", color="variable",
        barmode="stack", orientation="h", text_auto=".1f",
        labels={"pct": "% medio", "tipo_eleccion_cod": "", "variable": ""},
        color_discrete_map={"Participación": "#1f77b4", "Abstención": "#ef5350"},
        height=300,
    )
    fig2.update_layout(legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig2, use_container_width=True)

with col2:
    st.subheader("Voto en blanco y nulo")
    grp_melt = grp.melt(
        id_vars=["etiqueta", "tipo_eleccion_cod"],
        value_vars=["blancos_pct", "nulos_pct"],
        var_name="variable", value_name="pct"
    )
    grp_melt["serie"] = (
        grp_melt["tipo_eleccion_cod"] + " · "
        + grp_melt["variable"].map({"blancos_pct": "blanco", "nulos_pct": "nulo"})
    )
    fig3 = px.line(
        grp_melt, x="etiqueta", y="pct", color="serie", markers=True,
        labels={"etiqueta": "Convocatoria", "pct": "%", "serie": ""},
        category_orders={"etiqueta": _conv_order},
        height=300,
    )
    fig3.update_layout(xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.45))
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Tabla de datos ─────────────────────────────────────────────────────────────
st.subheader("Datos por convocatoria")
tabla = (
    grp[["etiqueta", "tipo_eleccion_cod", "mesas", "censo", "votos_emitidos",
         "participacion_pct", "abstencion_pct", "blancos_pct", "nulos_pct"]]
    .rename(columns={
        "etiqueta": "Convocatoria", "tipo_eleccion_cod": "Tipo",
        "mesas": "Mesas", "censo": "Censo", "votos_emitidos": "Votos emitidos",
        "participacion_pct": "Part. %", "abstencion_pct": "Abst. %",
        "blancos_pct": "Blancos %", "nulos_pct": "Nulos %",
    })
    .reset_index(drop=True)
)
st.dataframe(tabla, use_container_width=True)
