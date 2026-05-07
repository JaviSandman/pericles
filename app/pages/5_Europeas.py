"""
Parlamento Europeo — Resultados por nivel geográfico y evolución temporal
Fuentes: tipo_06.parquet, tipo_03.parquet

Niveles: Nacional · CCAA · Provincia · Municipio
Nota: España vota como circunscripción única nacional.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import DATA_DIR, PROV_NOMBRE_A_CCAA, etiqueta_conv, party_color_map
from _mesa_view import (
    render_mesa_sidebar, render_mesa_tab4, render_mesa_map,
    get_t10_conv, get_t10_all, add_partido_label, ms_scope_label,
    render_election_map,
    PROV_NOMBRE_A_COD,
)

TIPO = "Parlamento Europeo"

st.set_page_config(page_title="Europeas", page_icon="🇪🇺", layout="wide")
st.title("🇪🇺 Parlamento Europeo")
st.caption("Resultados electorales 1987–2019 · Fuente: Ministerio del Interior")
st.info(
    "España vota como **circunscripción única nacional**: todos los eurodiputados "
    "se eligen en una sola vuelta nacional. El nivel Natural de análisis es Nacional.",
    icon="ℹ️",
)


@st.cache_resource(show_spinner="Cargando datos de Europeas…")
def _load():
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "cod_candidatura", "votos_obtenidos", "candidatos_obtenidos"],
    )
    t06 = t06[(t06["tipo_eleccion_cod"] == TIPO) & (t06["vuelta"].astype(int) == 1)].copy()

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
    df["ccaa_nombre"] = df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    df["anio"] = df["anio"].astype(int)
    df["mes"]  = df["mes"].astype(int)
    df["conv"] = df["anio"].astype(str) + "/" + df["mes"].astype(str).str.zfill(2)

    # ── tipo_05: nombres de municipio ──
    t05_muni = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=["tipo_eleccion_cod", "provincia_cod", "municipio_cod", "nombre_municipio"],
    )
    t05_muni = (
        t05_muni[t05_muni["tipo_eleccion_cod"] == TIPO]
        .drop_duplicates(subset=["provincia_cod", "municipio_cod"])
        [["provincia_cod", "municipio_cod", "nombre_municipio"]]
    )
    df = df.merge(t05_muni, on=["provincia_cod", "municipio_cod"], how="left")
    df["nombre_municipio"] = df["nombre_municipio"].fillna(df["municipio_cod"].astype(str))
    df["municipio_label"] = df["nombre_municipio"] + " (" + df["provincia_cod"] + ")"
    return df


df_all = _load()
convs_ord = (
    df_all[["anio", "mes", "conv"]].drop_duplicates()
    .sort_values(["anio", "mes"])["conv"].tolist()
)


# ── Agregación cacheada ──────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _build_agg(
    _df: "pd.DataFrame",
    sel_convs: tuple,
    nivel: str,
    sel_ccaa: tuple,
    sel_prov: tuple,
    sel_muni: tuple,
    top_n: int,
) -> "tuple[pd.DataFrame, list]":
    _GEO = {
        "Nacional":  [],
        "CCAA":      ["ccaa_nombre"],
        "Provincia": ["provincia_cod"],
        "Municipio": ["provincia_cod", "nombre_municipio"],
    }[nivel]
    mask = _df["conv"].isin(sel_convs)
    if nivel == "CCAA" and sel_ccaa:
        mask = mask & _df["ccaa_nombre"].isin(sel_ccaa)
    elif nivel in ("Provincia", "Municipio") and sel_prov:
        mask = mask & _df["provincia_cod"].isin(sel_prov)
    if nivel == "Municipio" and sel_muni:
        mask = mask & _df["municipio_label"].isin(sel_muni)
    dfs = _df[mask]
    group_cols = ["conv", "anio", "mes"] + _GEO + ["partido"]
    agg = dfs.groupby(group_cols, as_index=False).agg(votos=("votos_obtenidos", "sum"))
    agg["votos_total"] = agg.groupby(["conv"] + _GEO)["votos"].transform("sum")
    agg["pct_voto"] = (agg["votos"] / agg["votos_total"] * 100).round(2)
    top = agg.groupby("partido")["votos"].sum().nlargest(top_n).index.tolist()
    return agg, top


with st.sidebar:
    st.header("Filtros")
    NIVELES = ["Nacional", "CCAA", "Provincia", "Municipio"]
    nivel = st.radio("Nivel geográfico", NIVELES)

    sel_convs = st.multiselect("Convocatorias", convs_ord, default=[convs_ord[-1]])
    if not sel_convs:
        sel_convs = [convs_ord[-1]]

    sel_ccaa = sel_prov = sel_muni = None
    if nivel == "CCAA":
        sel_ccaa = st.multiselect("CCAA (opcional)", sorted(df_all["ccaa_nombre"].dropna().unique()))
    elif nivel in ("Provincia", "Municipio"):
        sel_prov = st.multiselect("Provincia (opcional)", sorted(df_all["provincia_cod"].dropna().unique()))
    if nivel == "Municipio":
        if sel_prov:
            muni_opts = sorted(
                df_all[df_all["provincia_cod"].isin(sel_prov)]["municipio_label"]
                .dropna().unique()
            )
        else:
            muni_opts = sorted(df_all["municipio_label"].dropna().unique())
        sel_muni = st.multiselect(
            "Municipio (opcional)", muni_opts,
            help="Selecciona un municipio para ver el desglose por mesa",
        )

    top_n = st.slider("Top N partidos en gráfico", 5, 20, 10)


GEO_DIM = {
    "Nacional":  [],
    "CCAA":      ["ccaa_nombre"],
    "Provincia": ["provincia_cod"],
    "Municipio": ["provincia_cod", "nombre_municipio"],
}[nivel]

df_agg, top_parties = _build_agg(
    df_all,
    tuple(sel_convs), nivel,
    tuple(sel_ccaa) if sel_ccaa else (),
    tuple(sel_prov) if sel_prov else (),
    tuple(sel_muni) if sel_muni else (),
    top_n,
)


# ── Mesa sidebar state ────────────────────────────────────────────────────────
_ms: dict = {}
_ms_conv = sel_convs[-1]
if nivel == "Municipio" and sel_muni and len(sel_muni) == 1:
    _muni_row = (
        df_all[df_all["municipio_label"] == sel_muni[0]]
        [["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates().iloc[0]
    )
    _ms = render_mesa_sidebar(
        tipo=TIPO,
        anio=int(_ms_conv[:4]), mes=int(_ms_conv[5:]), vuelta=1,
        prov_nombre=_muni_row["provincia_cod"],
        muni_cod=_muni_row["municipio_cod"],
        muni_name=_muni_row["nombre_municipio"],
        key_prefix="europeas",
    )


# ── Tabs ───────────────────────────────────────────────────────────────────────
if nivel == "Municipio" and sel_muni and len(sel_muni) == 1 and _ms.get("active"):
    tab_res, tab_evo, tab_mesa, tab_mapa = st.tabs(
        ["📊 Resultados", "📈 Evolución temporal", "🗳️ Por mesa", "🗺️ Mapa"]
    )
else:
    tab_res, tab_evo, tab_mapa = st.tabs(
        ["📊 Resultados", "📈 Evolución temporal", "🗺️ Mapa"]
    )
    tab_mesa = None

with tab_res:
    c1, c2, c3 = st.columns(3)
    c1.metric("Nivel", nivel)
    c2.metric("Votos a candidaturas", f"{int(df_agg['votos'].sum()):,}")
    c3.metric("Partidos con votos", str(int(df_agg['partido'].nunique())))
    st.divider()

    if nivel == "Municipio" and not sel_prov:
        st.info("💡 Selecciona una o varias **provincias** para explorar a nivel municipio.")
    else:
        x_col = {"Nacional": "conv", "CCAA": "ccaa_nombre",
                 "Provincia": "provincia_cod", "Municipio": "nombre_municipio"}[nivel]
        df_chart = df_agg[df_agg["partido"].isin(top_parties)].sort_values(["anio", "mes"])
        fig = px.bar(df_chart, x=x_col, y="pct_voto", color="partido", barmode="group",
                     labels={x_col: nivel, "pct_voto": "% votos", "partido": "Partido"},
                     color_discrete_map=party_color_map(df_agg["partido"].unique()))
        fig.update_layout(height=430, xaxis_tickangle=-40,
                          legend=dict(orientation="h", yanchor="top", y=-0.30), margin=dict(b=90))
        st.plotly_chart(fig, use_container_width=True)

        disp_cols = ["conv"] + GEO_DIM + ["partido", "votos", "pct_voto"]
        disp_cols = [c for c in disp_cols if c in df_agg.columns]
        df_tabla = df_agg[disp_cols].sort_values(
            ["conv"] + GEO_DIM + ["votos"],
            ascending=[True] * (1 + len(GEO_DIM)) + [False]
        ).reset_index(drop=True)
        cfg = {
            "conv": st.column_config.TextColumn("Convocatoria", width="small"),
            "ccaa_nombre": st.column_config.TextColumn("CCAA"),
            "provincia_cod": st.column_config.TextColumn("Provincia"),
            "nombre_municipio": st.column_config.TextColumn("Municipio"),
            "partido": st.column_config.TextColumn("Partido"),
            "votos": st.column_config.NumberColumn("Votos", format="%d"),
            "pct_voto": st.column_config.NumberColumn("% votos", format="%.2f %%"),
        }
        st.dataframe(df_tabla, use_container_width=True, hide_index=True,
                     column_config={k: v for k, v in cfg.items() if k in disp_cols})
        st.caption(f"Top {top_n} partidos en gráfico · Fuente: Ministerio del Interior")

with tab_evo:
    all_parties_evo = sorted(df_all["partido"].dropna().unique())
    candidates = ["PP", "PSOE", "Cs", "VOX", "IU", "Podemos", "UP",
                  "UPYD", "AP", "CDS", "Ciudadanos"]
    default_evo = [p for p in candidates if p in all_parties_evo][:6]
    sel_parties = st.multiselect("Selecciona partidos", all_parties_evo, default=default_evo)

    scope_opts = ["Nacional"]
    if nivel == "CCAA" and sel_ccaa:
        scope_opts.append("CCAA seleccionadas")
    if nivel in ("Provincia", "Municipio") and sel_prov:
        scope_opts.append("Provincias seleccionadas")
    scope = st.radio("Ámbito de la evolución", scope_opts, horizontal=True)

    if sel_parties:
        df_evo_base = df_all
        geo_dim_evo = []
        if scope == "CCAA seleccionadas" and sel_ccaa:
            df_evo_base = df_evo_base[df_evo_base["ccaa_nombre"].isin(sel_ccaa)]
            geo_dim_evo = ["ccaa_nombre"]
        elif scope == "Provincias seleccionadas" and sel_prov:
            df_evo_base = df_evo_base[df_evo_base["provincia_cod"].isin(sel_prov)]
            geo_dim_evo = ["provincia_cod"]

        evo_grp = ["conv", "anio", "mes"] + geo_dim_evo + ["partido"]
        df_evo = df_evo_base.groupby(evo_grp, as_index=False)["votos_obtenidos"].sum()
        evo_tot = df_evo.groupby(["conv"] + geo_dim_evo)["votos_obtenidos"].transform("sum")
        df_evo["pct"] = (df_evo["votos_obtenidos"] / evo_tot * 100).round(2)
        df_evo = df_evo[df_evo["partido"].isin(sel_parties)].sort_values(["anio", "mes"])

        if df_evo.empty:
            st.warning("Sin datos para los partidos seleccionados.")
        else:
            fig_evo = px.line(df_evo, x="conv", y="pct", color="partido", markers=True,
                              labels={"conv": "Convocatoria", "pct": "% votos"},
                              category_orders={"conv": convs_ord},
                              color_discrete_map=party_color_map(df_evo["partido"].unique()))
            fig_evo.update_layout(height=430, xaxis_tickangle=-40,
                                  legend=dict(orientation="h", yanchor="top", y=-0.30))
            st.plotly_chart(fig_evo, use_container_width=True)

            st.markdown("**Tabla de evolución** (% voto por convocatoria)")
            pivot = (
                df_evo.pivot_table(index="partido", columns="conv", values="pct", aggfunc="sum")
                .reindex(columns=[c for c in convs_ord if c in df_evo["conv"].values])
            )
            st.dataframe(pivot.style.format("{:.1f}%", na_rep="—"), use_container_width=True)
    else:
        st.info("Selecciona al menos un partido para ver su evolución histórica.")


# ─────────────────────────────  TAB 3: POR MESA  ──────────────────────────────
if tab_mesa is not None:
    with tab_mesa:
        render_mesa_tab4(_ms, top_n=top_n, color_fn=party_color_map)


# ─────────────────────────────  TAB 4: MAPA  ──────────────────────────────────
with tab_mapa:
    st.markdown(f"### 🗺️ Mapa electoral · {nivel} · {_ms_conv}")
    _map_prov = sel_prov if sel_prov else None
    _map_conv = sel_convs[-1] if sel_convs else (convs_ord[-1] if convs_ord else "")
    _map_nivel = nivel
    _mesa_drill_map = _ms.get("active") and (
        _ms.get("sel_distritos") or _ms.get("sel_mesas")
    )
    if nivel == "Municipio" and _mesa_drill_map:
        _map_nivel = "Distrito"
    if _map_nivel == "CCAA":
        st.info(
            "💡 El mapa está disponible para los niveles **Nacional**, **Provincia**, "
            "**Municipio** y **Distrito**. El nivel CCAA aún no está soportado."
        )
    else:
        if _map_nivel == "Provincia" and _map_prov and len(_map_prov) > 1:
            st.caption(
                f"ℹ️ Se muestra la provincia **{_map_prov[0]}**. "
                "El mapa soporta una provincia a la vez."
            )
        render_election_map(
            nivel=_map_nivel,
            df_votos=df_all,
            color_fn=party_color_map,
            sel_conv=_map_conv,
            sel_prov=_map_prov,
            sel_muni_label=sel_muni[0] if sel_muni and len(sel_muni) == 1 else None,
            prov_nombre_a_cod=PROV_NOMBRE_A_COD,
            mesa_state=_ms if _ms.get("active") else None,
            key="europeas_mapa_tab",
            height=560,
        )