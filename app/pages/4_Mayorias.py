"""
Mayorías Municipales — Análisis de partidos ganadores por municipio
Fuentes: tipo_06.parquet, tipo_05.parquet, tipo_03.parquet

Muestra qué partido ganó cada municipio (más concejales), el tipo de mayoría
(absoluta/relativa) y permite filtrar por CCAA, provincia y convocatoria.
Incluye evolución temporal del número de municipios ganados.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import DATA_DIR, PROVINCIAS, PROV_NOMBRE_A_CCAA, etiqueta_conv, party_color_map

TIPO = "Municipales"

st.set_page_config(page_title="Mayorías Municipales", page_icon="🏆", layout="wide")
st.title("🏆 Mayorías Municipales")
st.caption(
    "Partido ganador por municipio 1979–2023 · "
    "Mayoría absoluta = más de la mitad de los escaños · "
    "Fuente: Ministerio del Interior"
)


# ── Carga ──────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando datos de mayorías…")
def _load():
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "cod_candidatura", "candidatos_obtenidos"],
    )
    t06 = t06[
        (t06["tipo_eleccion_cod"] == TIPO) & (t06["vuelta"].astype(int) == 1)
    ].copy()

    t05 = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "nombre_municipio", "num_escanos"],
    )
    t05 = t05[
        (t05["tipo_eleccion_cod"] == TIPO) & (t05["vuelta"].astype(int) == 1)
    ].copy()

    t03 = pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes",
                 "cod_candidatura", "siglas", "denominacion"],
    )
    t03 = t03[t03["tipo_eleccion_cod"] == TIPO].copy()
    t03 = t03.drop_duplicates(subset=["anio", "mes", "cod_candidatura"])
    t03["partido"] = t03["siglas"].where(
        t03["siglas"].notna() & (t03["siglas"].astype(str).str.strip() != ""),
        t03["denominacion"].astype(str).str[:28],
    )

    df = t06.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    df["partido"] = df["partido"].fillna(df["cod_candidatura"].astype(str))

    # Nombre canónico (title case)
    nombre_canon = (
        t05[["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates(subset=["provincia_cod", "municipio_cod"])
        .set_index(["provincia_cod", "municipio_cod"])["nombre_municipio"]
        .str.title()
    )
    df["nombre_municipio"] = (
        df.set_index(["provincia_cod", "municipio_cod"])
        .index.map(nombre_canon).values
    )
    df["nombre_municipio"] = df["nombre_municipio"].fillna(df["municipio_cod"].astype(str))

    # Metadatos
    t05_slim = (
        t05[["anio", "mes", "provincia_cod", "municipio_cod", "num_escanos"]]
        .drop_duplicates(["anio", "mes", "provincia_cod", "municipio_cod"])
    )
    df = df.merge(t05_slim, on=["anio", "mes", "provincia_cod", "municipio_cod"], how="left")
    df["ccaa_nombre"] = df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    df["anio"] = df["anio"].astype(int)
    df["mes"]  = df["mes"].astype(int)
    df["conv"] = df.apply(lambda r: f"{r['anio']}/{r['mes']:02d}", axis=1)

    return df


df_all = _load()
convs_ord = (
    df_all[["anio", "mes", "conv"]].drop_duplicates()
    .sort_values(["anio", "mes"])["conv"].tolist()
)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    sel_convs = st.multiselect(
        "Convocatorias",
        convs_ord,
        default=[convs_ord[-1]],
        help="Una o varias convocatorias para comparar",
    )
    if not sel_convs:
        sel_convs = [convs_ord[-1]]

    ambito = st.radio(
        "Ámbito geográfico",
        ["Nacional", "CCAA", "Provincia"],
        horizontal=True,
    )

    sel_ccaa = sel_prov = None
    if ambito == "CCAA":
        ccaa_all = sorted(df_all["ccaa_nombre"].dropna().unique())
        sel_ccaa = st.multiselect("CCAA (opcional)", ccaa_all)
    elif ambito == "Provincia":
        prov_all = sorted(df_all["provincia_cod"].dropna().unique())
        sel_prov = st.multiselect("Provincia (opcional)", prov_all)

    top_n = st.slider("Top N partidos en gráfico", 5, 20, 15)


# ── Filtrado ───────────────────────────────────────────────────────────────────
df_f = df_all[df_all["conv"].isin(sel_convs)].copy()
if ambito == "CCAA" and sel_ccaa:
    df_f = df_f[df_f["ccaa_nombre"].isin(sel_ccaa)]
elif ambito == "Provincia" and sel_prov:
    df_f = df_f[df_f["provincia_cod"].isin(sel_prov)]

# ── Calcular ganadores por municipio ──────────────────────────────────────────
df_mp = df_f.groupby(
    ["conv", "anio", "mes", "ccaa_nombre", "provincia_cod", "municipio_cod",
     "nombre_municipio", "num_escanos", "partido"],
    as_index=False,
).agg(concejales=("candidatos_obtenidos", "sum"))

if df_mp.empty:
    st.warning("Sin datos para la selección actual.")
    st.stop()

idx_win = df_mp.groupby(["conv", "provincia_cod", "municipio_cod"])["concejales"].idxmax()
df_win  = df_mp.loc[idx_win].copy()

df_win["num_escanos"] = pd.to_numeric(df_win["num_escanos"], errors="coerce").fillna(0)
df_win["tipo_mayoria"] = df_win.apply(
    lambda r: "Mayoría absoluta"
    if r["num_escanos"] > 0 and r["concejales"] > r["num_escanos"] / 2
    else "Mayoría relativa",
    axis=1,
)

# ── KPIs ───────────────────────────────────────────────────────────────────────
n_total   = len(df_win)
n_abs     = (df_win["tipo_mayoria"] == "Mayoría absoluta").sum()
n_rel     = n_total - n_abs
pct_abs   = n_abs / n_total * 100 if n_total > 0 else 0.0
top_party = df_win["partido"].value_counts().index[0] if n_total > 0 else "—"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Municipios analizados",    f"{n_total:,}")
k2.metric("Mayorías absolutas",       f"{n_abs:,}")
k3.metric("Mayorías relativas",       f"{n_rel:,}")
k4.metric("% con mayoría absoluta",   f"{pct_abs:.1f}%")
k5.metric("Partido más victorioso",   top_party)

st.divider()

tab_dist, tab_evo, tab_tabla = st.tabs(
    ["📊 Distribución", "📈 Evolución temporal", "📋 Tabla detallada"]
)

# ─────────────────────────  TAB 1: DISTRIBUCIÓN  ──────────────────────────────
with tab_dist:
    df_win_agg = (
        df_win.groupby(["partido", "tipo_mayoria"])
        .size()
        .reset_index(name="municipios")
    )
    top_p = df_win_agg.groupby("partido")["municipios"].sum().nlargest(top_n).index
    df_chart = df_win_agg[df_win_agg["partido"].isin(top_p)].copy()

    # Ordenar por total de municipios ganados (absoluta + relativa)
    order = (
        df_chart.groupby("partido")["municipios"].sum()
        .sort_values(ascending=False).index.tolist()
    )

    fig = px.bar(
        df_chart,
        x="partido", y="municipios", color="tipo_mayoria",
        barmode="stack",
        category_orders={"partido": order},
        color_discrete_map={
            "Mayoría absoluta": "#2ca02c",
            "Mayoría relativa": "#ff7f0e",   # naranja visible
        },
        labels={
            "partido": "Partido",
            "municipios": "Municipios ganados",
            "tipo_mayoria": "Tipo de mayoría",
        },
        custom_data=["partido", "tipo_mayoria", "municipios"],
    )
    fig.update_traces(hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "Tipo: %{customdata[1]}<br>"
        "Municipios: %{customdata[2]:,}<extra></extra>"
    ))
    fig.update_layout(
        height=460,
        xaxis_tickangle=-40,
        legend=dict(orientation="h", yanchor="top", y=-0.30),
        margin=dict(b=100),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Top {top_n} partidos · Verde = Mayoría absoluta · Naranja = Mayoría relativa · "
        "Fuente: Ministerio del Interior"
    )

    # Resumen por partido (solo totales)
    df_resumen = (
        df_win.groupby("partido")["concejales"]
        .agg(municipios_ganados="count", concejales_totales="sum")
        .reset_index()
        .sort_values("municipios_ganados", ascending=False)
        .reset_index(drop=True)
    )
    df_abs_count = (
        df_win[df_win["tipo_mayoria"] == "Mayoría absoluta"]
        .groupby("partido").size().reset_index(name="absolutas")
    )
    df_resumen = df_resumen.merge(df_abs_count, on="partido", how="left")
    df_resumen["absolutas"] = df_resumen["absolutas"].fillna(0).astype(int)
    df_resumen["% absolutas"] = (
        df_resumen["absolutas"] / df_resumen["municipios_ganados"] * 100
    ).round(1)

    with st.expander("📋 Resumen por partido", expanded=False):
        st.dataframe(
            df_resumen,
            use_container_width=True,
            hide_index=True,
            column_config={
                "partido":             st.column_config.TextColumn("Partido"),
                "municipios_ganados":  st.column_config.NumberColumn("Municipios ganados", format="%d"),
                "absolutas":           st.column_config.NumberColumn("Con mayoría abs.", format="%d"),
                "% absolutas":         st.column_config.NumberColumn("% con abs.", format="%.1f %%"),
                "concejales_totales":  st.column_config.NumberColumn("Concejales totales", format="%d"),
            },
        )


# ─────────────────────────  TAB 2: EVOLUCIÓN TEMPORAL  ────────────────────────
with tab_evo:
    st.markdown(
        "Número de municipios ganados por convocatoria (todas las convocatorias históricas)."
    )

    # Recalcular para TODAS las convocatorias (sin filtro de sel_convs)
    df_all_f = df_all.copy()
    if ambito == "CCAA" and sel_ccaa:
        df_all_f = df_all_f[df_all_f["ccaa_nombre"].isin(sel_ccaa)]
    elif ambito == "Provincia" and sel_prov:
        df_all_f = df_all_f[df_all_f["provincia_cod"].isin(sel_prov)]

    df_mp_all = df_all_f.groupby(
        ["conv", "anio", "mes", "provincia_cod", "municipio_cod",
         "nombre_municipio", "num_escanos", "partido"],
        as_index=False,
    ).agg(concejales=("candidatos_obtenidos", "sum"))

    idx_all = df_mp_all.groupby(["conv", "provincia_cod", "municipio_cod"])["concejales"].idxmax()
    df_win_all = df_mp_all.loc[idx_all].copy()

    # Partidos a mostrar
    top_p_ev = df_win_all.groupby("partido").size().nlargest(top_n).index.tolist()
    candidates_ev = ["PP", "PSOE", "IU", "Cs", "VOX", "Podemos", "UP", "CDS", "AP", "PCE"]
    default_ev = [p for p in candidates_ev if p in top_p_ev][:8]

    sel_parties_ev = st.multiselect(
        "Selecciona partidos para el gráfico de evolución",
        sorted(df_win_all["partido"].unique()),
        default=default_ev,
        key="may_evo_parties",
    )

    if sel_parties_ev:
        df_evo = (
            df_win_all[df_win_all["partido"].isin(sel_parties_ev)]
            .groupby(["conv", "anio", "mes", "partido"])
            .size()
            .reset_index(name="municipios")
            .sort_values(["anio", "mes"])
        )
        fig_evo = px.line(
            df_evo,
            x="conv", y="municipios", color="partido",
            markers=True,
            labels={"conv": "Convocatoria", "municipios": "Municipios ganados",
                    "partido": "Partido"},
            category_orders={"conv": convs_ord},
            color_discrete_map=party_color_map(df_evo["partido"].unique()),
            custom_data=["partido", "conv", "municipios"],
        )
        fig_evo.update_traces(hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Convocatoria: %{customdata[1]}<br>"
            "Municipios: %{customdata[2]:,}<extra></extra>"
        ))
        fig_evo.update_layout(
            height=460,
            xaxis_tickangle=-40,
            legend=dict(orientation="h", yanchor="top", y=-0.30),
        )
        st.plotly_chart(fig_evo, use_container_width=True)

        st.markdown("**Tabla de evolución** (municipios ganados por convocatoria)")
        pivot_evo = (
            df_evo.pivot_table(
                index="partido", columns="conv", values="municipios", aggfunc="sum"
            ).fillna(0).astype(int)
            .reindex(columns=[c for c in convs_ord if c in df_evo["conv"].values])
        )
        st.dataframe(pivot_evo, use_container_width=True)
    else:
        st.info("Selecciona al menos un partido para ver su evolución histórica.")


# ─────────────────────────  TAB 3: TABLA DETALLADA  ───────────────────────────
with tab_tabla:
    # Filtros extra de la tabla
    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        fil_tipo = st.selectbox(
            "Tipo de mayoría",
            ["Todas", "Solo mayoría absoluta", "Solo mayoría relativa"],
            key="tab_tipo_may",
        )
    with col_t2:
        fil_partido = st.multiselect(
            "Filtrar por partido",
            sorted(df_win["partido"].unique()),
            key="tab_partido_may",
            help="Vacío = todos los partidos",
        )

    df_tabla = df_win.copy()
    if fil_tipo == "Solo mayoría absoluta":
        df_tabla = df_tabla[df_tabla["tipo_mayoria"] == "Mayoría absoluta"]
    elif fil_tipo == "Solo mayoría relativa":
        df_tabla = df_tabla[df_tabla["tipo_mayoria"] == "Mayoría relativa"]
    if fil_partido:
        df_tabla = df_tabla[df_tabla["partido"].isin(fil_partido)]

    df_tabla = df_tabla[
        ["conv", "ccaa_nombre", "provincia_cod", "nombre_municipio",
         "partido", "concejales", "num_escanos", "tipo_mayoria"]
    ].sort_values(
        ["conv", "provincia_cod", "nombre_municipio"]
    ).reset_index(drop=True)

    st.metric("Municipios mostrados", f"{len(df_tabla):,}")
    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "conv":             st.column_config.TextColumn("Convocatoria", width="small"),
            "ccaa_nombre":      st.column_config.TextColumn("CCAA"),
            "provincia_cod":    st.column_config.TextColumn("Provincia"),
            "nombre_municipio": st.column_config.TextColumn("Municipio"),
            "partido":          st.column_config.TextColumn("Partido ganador"),
            "concejales":       st.column_config.NumberColumn("Concejales", format="%d"),
            "num_escanos":      st.column_config.NumberColumn("Total escaños", format="%d"),
            "tipo_mayoria":     st.column_config.TextColumn("Tipo de mayoría"),
        },
    )
    st.caption(
        "Partido ganador = partido con más concejales en ese municipio. "
        "Mayoría absoluta: más de la mitad de los escaños. "
        "Fuente: Ministerio del Interior"
    )
