"""
Elecciones Municipales — Resultados por nivel, evolución temporal y tabla de mayorías
Fuentes: tipo_06.parquet, tipo_05.parquet, tipo_03.parquet

Niveles: Nacional · CCAA · Provincia · Municipio
Tabla especial: Mayorías absolutas y relativas por municipio
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import DATA_DIR, PROVINCIAS, PROV_NOMBRE_A_CCAA, etiqueta_conv, party_color_map, normalize_partido
from _mesa_view import (
    render_mesa_sidebar, render_mesa_tab4, render_mesa_map,
    get_t10_conv, get_t10_all, add_partido_label, ms_scope_label,
    render_election_map, render_sm_map,
    PROV_NOMBRE_A_COD,
)

TIPO = "Municipales"
# Lookup inverso: nombre de provincia → código 2 dígitos (para unir con t12 que usa códigos raw)
PROV_NOMBRE_TO_COD: dict[str, str] = {v: k for k, v in PROVINCIAS.items()}

st.set_page_config(page_title="Municipales", page_icon="🏙️", layout="wide")
st.title("🏙️ Elecciones Municipales")
st.caption("Resultados electorales 1979–2023 · Fuente: Ministerio del Interior")


# ── Carga ──────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando datos municipales…")
def _load():
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "cod_candidatura", "votos_obtenidos", "candidatos_obtenidos"],
    )
    t06 = t06[
        (t06["tipo_eleccion_cod"] == TIPO) & (t06["vuelta"].astype(int) == 1)
    ].copy()

    t05 = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod", "nombre_municipio", "num_escanos",
                 "censo_ine", "votos_candidaturas"],
    )
    t05 = t05[
        (t05["tipo_eleccion_cod"] == TIPO) & (t05["vuelta"].astype(int) == 1)
    ].copy()
    t05["anio"] = t05["anio"].astype(int)
    t05["mes"]  = t05["mes"].astype(int)

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
        on=["anio", "mes", "cod_candidatura"],
        how="left",
    )
    df["partido"] = df["partido"].fillna(df["cod_candidatura"].astype(str))
    df["partido"] = df["partido"].map(normalize_partido)
    df["ccaa_nombre"] = df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    df["anio"] = df["anio"].astype(int)
    df["mes"]  = df["mes"].astype(int)
    df["conv"] = df["anio"].astype(str) + "/" + df["mes"].astype(str).str.zfill(2)

    # Incorporar nombre municipio y total escaños desde tipo_05
    t05_slim = t05[["anio", "mes", "provincia_cod", "municipio_cod",
                    "nombre_municipio", "num_escanos"]].drop_duplicates(
        ["anio", "mes", "provincia_cod", "municipio_cod"]
    )
    df = df.merge(t05_slim, on=["anio", "mes", "provincia_cod", "municipio_cod"], how="left")

    # Nombre canónico: un único nombre por (provincia, municipio) en title case
    # para evitar duplicados por cambios de mayúsculas entre convocatorias
    nombre_canon = (
        t05[["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates(subset=["provincia_cod", "municipio_cod"])
        .assign(nombre_municipio=lambda d: d["nombre_municipio"].str.title())
    )
    df = df.drop(columns=["nombre_municipio"]).merge(
        nombre_canon, on=["provincia_cod", "municipio_cod"], how="left"
    )
    df["nombre_municipio"] = df["nombre_municipio"].fillna(df["municipio_cod"].astype(str))
    df["municipio_label"] = df["nombre_municipio"] + " (" + df["provincia_cod"] + ")"

    # ── tipo_11: municipios <250 hab (sistema mayoritario, lista abierta) ───
    t11 = pd.read_parquet(
        str(DATA_DIR / "tipo_11.parquet"),
        columns=["_proceso_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod", "nombre_municipio", "num_escanos",
                 "censo_ine", "votos_candidaturas", "votos_blanco", "votos_nulos"],
    )
    t11 = t11[
        (t11["_proceso_cod"] == "04") &
        (t11["vuelta"].fillna("1").astype(str) == "1")
    ].copy()
    t11["anio"] = pd.to_numeric(t11["anio"], errors="coerce")
    t11["mes"]  = pd.to_numeric(t11["mes"],  errors="coerce")
    t11 = t11.dropna(subset=["anio", "mes"])
    t11["anio"] = t11["anio"].astype(int)
    t11["mes"]  = t11["mes"].astype(int)
    # Deduplicar (el mismo DAT puede estar indexado dos veces en el repo)
    t11 = t11.drop_duplicates(["anio", "mes", "provincia_cod", "municipio_cod"])
    t11["conv"] = t11["anio"].astype(str) + "/" + t11["mes"].astype(str).str.zfill(2)
    t11["total_votantes"] = (
        t11["votos_blanco"].fillna(0) +
        t11["votos_nulos"].fillna(0) +
        t11["votos_candidaturas"].fillna(0)
    ).astype(int)
    t11["ccaa_nombre"]      = t11["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    t11["nombre_municipio"] = t11["nombre_municipio"].str.title()
    t11["municipio_label"]  = t11["nombre_municipio"] + " (" + t11["provincia_cod"] + ")"

    # ── Catálogo canónico de municipios (t05 + t11) ─────────────────────────
    t05_munis = (
        t05[["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates(["provincia_cod", "municipio_cod"])
        .copy()
    )
    t05_munis["is_small_muni"] = False

    t11_munis = (
        t11[["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates(["provincia_cod", "municipio_cod"])
        .copy()
    )
    t11_munis["is_small_muni"] = True

    muni_catalog = (
        pd.concat([t05_munis, t11_munis], ignore_index=True)
        .drop_duplicates(["provincia_cod", "municipio_cod"], keep="first")
    )
    muni_catalog["nombre_municipio"] = muni_catalog["nombre_municipio"].str.title()
    muni_catalog["ccaa_nombre"]      = muni_catalog["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    muni_catalog["municipio_label"]  = muni_catalog["nombre_municipio"] + " (" + muni_catalog["provincia_cod"] + ")"

    # ── tipo_12: candidatos de municipios <250 hab (sistema mayoritario) ────────
    t12 = pd.read_parquet(
        str(DATA_DIR / "tipo_12.parquet"),
        columns=["_proceso_cod", "_anio", "_mes",
                 "provincia_cod", "municipio_cod", "cod_candidatura",
                 "votos_candidatura", "num_candidatos_electos",
                 "nombre", "primer_apellido", "segundo_apellido",
                 "sexo", "votos_obtenidos", "elegido"],
    )
    t12 = t12[t12["_proceso_cod"] == "04"].copy()

    # Lookup de partidos para tipo_12 desde tipo_03
    t03_t12 = pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["_proceso_cod", "_anio", "_mes", "cod_candidatura", "siglas", "denominacion"],
    )
    t03_t12 = (
        t03_t12[t03_t12["_proceso_cod"] == "04"]
        .drop_duplicates(["_anio", "_mes", "cod_candidatura"])
    )
    t12 = t12.merge(
        t03_t12[["_anio", "_mes", "cod_candidatura", "siglas", "denominacion"]],
        on=["_anio", "_mes", "cod_candidatura"],
        how="left",
    )
    t12["partido"] = t12["siglas"].where(
        t12["siglas"].notna() & (t12["siglas"].astype(str).str.strip() != ""),
        t12["denominacion"].astype(str).str[:28],
    ).fillna("Independiente/Local")
    t12["partido"] = t12["partido"].map(normalize_partido)
    t12.loc[t12["cod_candidatura"] == "000000", "partido"] = "Independiente/Local"
    # Deduplicar (el mismo DAT puede estar indexado dos veces en el repo)
    t12 = t12.drop_duplicates(["_anio", "_mes", "provincia_cod", "municipio_cod",
                               "nombre", "primer_apellido", "segundo_apellido"])
    t12["nombre_completo"] = (
        t12["nombre"].str.strip() + " " +
        t12["primer_apellido"].str.strip() + " " +
        t12["segundo_apellido"].str.strip()
    ).str.strip()
    t12["conv"] = t12["_anio"].astype(str) + "/" + t12["_mes"].astype(str).str.zfill(2)

    return df, t05, t11, t12, muni_catalog


df_all, t05_all, t11_all, t12_all, muni_catalog = _load()
convs_ord = (
    pd.concat([
        df_all[["anio", "mes", "conv"]],
        t11_all[["anio", "mes", "conv"]],
    ])
    .drop_duplicates()
    .sort_values(["anio", "mes"])["conv"].tolist()
)

# ── Agrupación cacheada ───────────────────────────────────────────────────────
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
    """Agrega votos por partido y nivel geográfico. Cacheado por parámetros de filtro."""
    _GEO = {
        "Nacional":  [],
        "CCAA":      ["ccaa_nombre"],
        "Provincia": ["provincia_cod"],
        "Municipio": ["provincia_cod", "municipio_cod", "nombre_municipio"],
    }[nivel]
    mask = _df["conv"].isin(sel_convs)
    if nivel == "CCAA" and sel_ccaa:
        mask = mask & _df["ccaa_nombre"].isin(sel_ccaa)
    elif nivel == "Provincia" and sel_prov:
        mask = mask & _df["provincia_cod"].isin(sel_prov)
    elif nivel == "Municipio":
        if sel_prov:
            mask = mask & _df["provincia_cod"].isin(sel_prov)
        if sel_muni:
            mask = mask & _df["municipio_label"].isin(sel_muni)
    dfs = _df[mask]
    group_cols = ["conv", "anio", "mes"] + _GEO + ["partido"]
    agg = dfs.groupby(group_cols, as_index=False).agg(
        votos=("votos_obtenidos", "sum"),
        concejales=("candidatos_obtenidos", "sum"),
    )
    agg["votos_total"] = agg.groupby(["conv"] + _GEO)["votos"].transform("sum")
    agg["pct_voto"] = (agg["votos"] / agg["votos_total"] * 100).round(2)
    top = agg.groupby("partido")["votos"].sum().nlargest(top_n).index.tolist()
    return agg, top


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    NIVELES = ["Nacional", "CCAA", "Provincia", "Municipio"]
    nivel = st.radio("Nivel geográfico", NIVELES, index=2)   # default: Provincia

    sel_convs = st.multiselect(
        "Convocatorias",
        convs_ord,
        default=[convs_ord[-1]],
        help="Una o varias convocatorias para ver o comparar",
    )
    if not sel_convs:
        sel_convs = [convs_ord[-1]]

    sel_ccaa = sel_prov = sel_muni = None
    if nivel == "CCAA":
        ccaa_all = sorted(df_all["ccaa_nombre"].dropna().unique())
        sel_ccaa = st.multiselect("CCAA (opcional)", ccaa_all)
    elif nivel == "Provincia":
        prov_all = sorted(df_all["provincia_cod"].dropna().unique())
        sel_prov = st.multiselect("Provincia (opcional)", prov_all)
    elif nivel == "Municipio":
        prov_all = sorted(df_all["provincia_cod"].dropna().unique())
        sel_prov = st.multiselect(
            "Provincia (filtra municipios)", prov_all,
            help="Selecciona provincias para acotar el listado de municipios",
        )
        if sel_prov:
            muni_opts = sorted(
                muni_catalog[muni_catalog["provincia_cod"].isin(sel_prov)]["municipio_label"]
                .dropna().unique()
            )
        else:
            muni_opts = sorted(muni_catalog["municipio_label"].dropna().unique())
        sel_muni = st.multiselect(
            "Municipio (opcional)", muni_opts,
            help="Puedes mezclar municipios de distintas provincias",
        )

    top_n = st.slider("Top N partidos en gráfico", 5, 20, 10)


# ── Datos para la vista de resultados ─────────────────────────────────────────
GEO_DIM = {
    "Nacional":  [],
    "CCAA":      ["ccaa_nombre"],
    "Provincia": ["provincia_cod"],
    "Municipio": ["provincia_cod", "municipio_cod", "nombre_municipio"],
}[nivel]

df_agg, top_parties = _build_agg(
    df_all,
    tuple(sel_convs), nivel,
    tuple(sel_ccaa) if sel_ccaa else (),
    tuple(sel_prov) if sel_prov else (),
    tuple(sel_muni) if sel_muni else (),
    top_n,
)


# ── Desglose por mesa: calcular estado del sidebar ────────────────────────────
_ms: dict = {}
_ms_conv   = sel_convs[-1]   # convocatoria de referencia para el desglose
# ── Detectar municipio de sistema mayoritario (<250 hab) ─────────────────────
_is_sm  = False
_sm_row = None
if nivel == "Municipio" and sel_muni and len(sel_muni) == 1:
    _mc = muni_catalog[muni_catalog["municipio_label"] == sel_muni[0]]
    if len(_mc) > 0 and bool(_mc["is_small_muni"].iloc[0]):
        _is_sm  = True
        _sm_row = _mc.iloc[0]

if nivel == "Municipio" and sel_muni and len(sel_muni) == 1 and not _is_sm:
    _muni_row = (
        muni_catalog[muni_catalog["municipio_label"] == sel_muni[0]]
        [["provincia_cod", "municipio_cod", "nombre_municipio"]]
        .drop_duplicates().iloc[0]
    )
    _ms = render_mesa_sidebar(
        tipo=TIPO,
        anio=int(_ms_conv[:4]), mes=int(_ms_conv[5:]), vuelta=1,
        prov_nombre=_muni_row["provincia_cod"],
        muni_cod=_muni_row["municipio_cod"],
        muni_name=_muni_row["nombre_municipio"],
        key_prefix="municipales",
    )


# ── Tabs ──────────────────────────────────────────────────────────────────────────────
if nivel == "Municipio":
    tab_res, tab_evo, tab_mesa, tab_mapa = st.tabs(
        ["📊 Resultados", "📈 Evolución temporal", "🗳️ Por mesa", "🗺️ Mapa"]
    )
else:
    tab_res, tab_evo, tab_mapa = st.tabs(
        ["📊 Resultados", "📈 Evolución temporal", "🗺️ Mapa"]
    )
    tab_mesa = None


# ─────────────────────────────  TAB 1: RESULTADOS  ────────────────────────────
with tab_res:
    _mesa_drill = _ms.get("active") and (
        _ms.get("sel_distritos") or _ms.get("sel_mesas")
    )

    if _mesa_drill:
        # ── Resultados filtrados por distrito/mesa ───────────────────────────
        _scope = ms_scope_label(_ms)
        st.caption(f"📍 **{_scope}** · {_ms_conv}")
        df_t10_r = get_t10_conv(_ms)
        if df_t10_r.empty:
            st.warning("⚠️ Sin datos de mesa (tipo_10) para esta selección.")
        else:
            df_t10_r = add_partido_label(df_t10_r, TIPO)
            df_r_agg  = df_t10_r.groupby("partido", as_index=False)["votos_obtenidos"].sum()
            total_v_r = int(df_r_agg["votos_obtenidos"].sum())
            df_r_agg["pct_voto"] = (
                df_r_agg["votos_obtenidos"] / total_v_r * 100
            ).round(2)
            _t09_s    = _ms.get("df_t09_sel")
            _t09_m    = _ms.get("df_t09_muni")
            _t09_sel  = _t09_s if (_t09_s is not None and not _t09_s.empty) else _t09_m
            n_mesas_r = len(_t09_sel) if _t09_sel is not None else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Ámbito", _scope)
            c2.metric("Mesas incluidas", f"{n_mesas_r:,}")
            c3.metric("Votos a candidaturas", f"{total_v_r:,}")
            c4.metric("Partidos con votos",
                      str((df_r_agg["votos_obtenidos"] > 0).sum()))
            st.caption(
                "ℹ️ Datos de mesa (tipo_10). Concejales no disponibles a este nivel."
            )
            st.divider()

            top_p_r = df_r_agg.nlargest(top_n, "votos_obtenidos")["partido"].tolist()
            fig_r = px.bar(
                df_r_agg[df_r_agg["partido"].isin(top_p_r)]
                    .sort_values("pct_voto", ascending=False),
                x="partido", y="pct_voto", color="partido",
                labels={"partido": "Partido", "pct_voto": "% votos"},
                color_discrete_map=party_color_map(df_r_agg["partido"].unique()),
                custom_data=["partido", "pct_voto", "votos_obtenidos"],
            )
            fig_r.update_traces(hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "% Votos: %{customdata[1]:.2f}%<br>"
                "Votos: %{customdata[2]:,.0f}<extra></extra>"
            ))
            fig_r.update_layout(
                height=430, xaxis_tickangle=-40, showlegend=False, margin=dict(b=90),
            )
            st.plotly_chart(fig_r, use_container_width=True)
            st.dataframe(
                df_r_agg[["partido", "votos_obtenidos", "pct_voto"]]
                    .sort_values("votos_obtenidos", ascending=False)
                    .reset_index(drop=True),
                use_container_width=True, hide_index=True,
                column_config={
                    "partido":         st.column_config.TextColumn("Partido"),
                    "votos_obtenidos": st.column_config.NumberColumn("Votos", format="%d"),
                    "pct_voto":        st.column_config.NumberColumn("% votos", format="%.2f %%"),
                },
            )
            st.caption(
                f"Top {top_n} partidos en gráfico · Tabla completa · "
                "Fuente: Ministerio del Interior"
            )
            with st.expander("🗺️ Mapa de secciones", expanded=False):
                render_mesa_map(
                    _ms,
                    df_t10=df_t10_r,
                    color_fn=party_color_map,
                    key="municipales_map_res",
                )
    else:
        if _is_sm and _sm_row is not None:
            # ── Sistema mayoritario (<250 hab): participación + candidatos ────
            t11_sel = t11_all[
                (t11_all["provincia_cod"] == _sm_row["provincia_cod"]) &
                (t11_all["municipio_cod"] == _sm_row["municipio_cod"]) &
                (t11_all["conv"].isin(sel_convs))
            ]
            _prov_code = PROV_NOMBRE_TO_COD.get(_sm_row["provincia_cod"], _sm_row["provincia_cod"])
            t12_sel = t12_all[
                (t12_all["provincia_cod"] == _prov_code) &
                (t12_all["municipio_cod"] == _sm_row["municipio_cod"]) &
                (t12_all["conv"].isin(sel_convs))
            ]
            st.subheader(f"🗳️ {_sm_row['nombre_municipio']} — Municipio <250 hab (lista abierta)")
            if t11_sel.empty:
                st.warning("Sin datos disponibles para las convocatorias seleccionadas.")
            else:
                for _, row in t11_sel.sort_values("anio").iterrows():
                    censo   = int(row["censo_ine"])          if pd.notna(row["censo_ine"])          else 0
                    votanr  = int(row["total_votantes"])     if pd.notna(row["total_votantes"])     else 0
                    vcands  = int(row["votos_candidaturas"]) if pd.notna(row["votos_candidaturas"]) else 0
                    vblanco = int(row["votos_blanco"])       if pd.notna(row["votos_blanco"])       else 0
                    vnulos  = int(row["votos_nulos"])        if pd.notna(row["votos_nulos"])        else 0
                    partici = round(votanr / censo * 100, 1) if censo > 0 else 0.0
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Convocatoria", row["conv"])
                    c2.metric("Censo INE",    f"{censo:,}")
                    c3.metric("Votantes",     f"{votanr:,}")
                    c4.metric("Participación", f"{partici:.1f}%")
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("Votos a candidaturas", f"{vcands:,}")
                    cc2.metric("Votos en blanco",      f"{vblanco:,}")
                    cc3.metric("Votos nulos",           f"{vnulos:,}")

                    conv_key = row["conv"]
                    t12_conv = t12_sel[t12_sel["conv"] == conv_key]
                    if not t12_conv.empty:
                        # Tabla por candidatura (un row por partido)
                        cand_summary = (
                            t12_conv.drop_duplicates("cod_candidatura")
                            [["partido", "votos_candidatura", "num_candidatos_electos"]]
                            .sort_values("votos_candidatura", ascending=False)
                            .reset_index(drop=True)
                        )
                        st.markdown("**Resultados por partido**")
                        st.dataframe(
                            cand_summary,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "partido":               st.column_config.TextColumn("Partido"),
                                "votos_candidatura":     st.column_config.NumberColumn("Votos lista", format="%d"),
                                "num_candidatos_electos": st.column_config.NumberColumn("Concejales", format="%d"),
                            },
                        )
                        # Tabla de candidatos individuales
                        cands_table = (
                            t12_conv[["nombre_completo", "partido", "sexo", "votos_obtenidos", "elegido"]]
                            .sort_values(["elegido", "votos_obtenidos"], ascending=[False, False])
                            .reset_index(drop=True)
                        )
                        cands_table["elegido"] = cands_table["elegido"].map({"S": "✅ Sí", "N": "No"}).fillna(cands_table["elegido"])
                        st.markdown("**Candidatos individuales**")
                        st.dataframe(
                            cands_table,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "nombre_completo": st.column_config.TextColumn("Candidato"),
                                "partido":         st.column_config.TextColumn("Partido"),
                                "sexo":            st.column_config.TextColumn("Sexo"),
                                "votos_obtenidos": st.column_config.NumberColumn("Votos", format="%d"),
                                "elegido":         st.column_config.TextColumn("Elegido"),
                            },
                        )
                    st.divider()
        else:
            # ── Vista global (nivel geográfico seleccionado) ─────────────────
            total_votos = int(df_agg["votos"].sum())
            total_conc  = int(df_agg["concejales"].sum())
            n_con_conc  = int(df_agg[df_agg["concejales"] > 0]["partido"].nunique())

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Nivel", nivel)
            c2.metric("Votos a candidaturas", f"{total_votos:,}")
            c3.metric("Concejales asignados", f"{total_conc:,}" if total_conc > 0 else "—")
            c4.metric("Partidos con concejales", str(n_con_conc) if n_con_conc > 0 else "—")

            st.divider()

            if nivel == "Municipio" and not sel_prov and not sel_muni:
                st.info(
                    "💡 Selecciona una o varias **provincias** o **municipios** en el panel lateral "
                    "para explorar resultados a nivel de municipio."
                )
            else:
                x_col = {
                    "Nacional":  "conv",
                    "CCAA":      "ccaa_nombre",
                    "Provincia": "provincia_cod",
                    "Municipio": "nombre_municipio",
                }[nivel]

                df_chart = df_agg[df_agg["partido"].isin(top_parties)].sort_values(["anio", "mes"])

                fig = px.bar(
                    df_chart,
                    x=x_col, y="pct_voto", color="partido",
                    barmode="group",
                    labels={x_col: nivel, "pct_voto": "% votos", "partido": "Partido"},
                    color_discrete_map=party_color_map(df_agg["partido"].unique()),
                )
                fig.update_layout(
                    height=430,
                    xaxis_tickangle=-40,
                    legend=dict(orientation="h", yanchor="top", y=-0.30),
                    margin=dict(b=90),
                )
                st.plotly_chart(fig, use_container_width=True)

                disp_cols = ["conv"] + GEO_DIM + ["partido", "votos", "pct_voto", "concejales"]
                disp_cols = [c for c in disp_cols if c in df_agg.columns]
                sort_asc  = [True] * (1 + len(GEO_DIM)) + [False]
                df_tabla  = df_agg[disp_cols].sort_values(
                    ["conv"] + GEO_DIM + ["votos"], ascending=sort_asc
                ).reset_index(drop=True)

                cfg = {
                    "conv":             st.column_config.TextColumn("Convocatoria", width="small"),
                    "ccaa_nombre":      st.column_config.TextColumn("CCAA"),
                    "provincia_cod":    st.column_config.TextColumn("Provincia"),
                    "municipio_cod":    st.column_config.TextColumn("Cód. municipio"),
                    "nombre_municipio": st.column_config.TextColumn("Municipio"),
                    "partido":          st.column_config.TextColumn("Partido"),
                    "votos":            st.column_config.NumberColumn("Votos", format="%d"),
                    "pct_voto":         st.column_config.NumberColumn("% votos", format="%.2f %%"),
                    "concejales":       st.column_config.NumberColumn("Concejales", format="%d"),
                }
                st.dataframe(
                    df_tabla,
                    use_container_width=True,
                    hide_index=True,
                    column_config={k: v for k, v in cfg.items() if k in disp_cols},
                )
                st.caption(
                    f"Top {top_n} partidos en gráfico · Tabla completa · "
                    "Fuente: Ministerio del Interior"
                )


# ─────────────────────────────  TAB 2: EVOLUCIÓN  ─────────────────────────────
with tab_evo:
    _candidates = ["PP", "PSOE", "IU", "Cs", "VOX", "Podemos", "UP", "CDS", "AP", "PCE"]
    _mesa_evo   = _ms.get("active") and (
        _ms.get("sel_distritos") or _ms.get("sel_mesas")
    )

    if _mesa_evo:
        # ── Evolución histórica a nivel distrito/mesa ────────────────────────
        st.caption(
            f"📍 Evolución para: **{ms_scope_label(_ms)}** · {_ms['muni_name']}"
        )
        df_t10_ev = get_t10_all(_ms)
        if df_t10_ev.empty:
            st.warning("Sin datos históricos de mesa para esta selección.")
        else:
            df_t10_ev  = add_partido_label(df_t10_ev, TIPO)
            df_t10_ev["anio"] = df_t10_ev["anio"].astype(int)
            df_t10_ev["mes"]  = df_t10_ev["mes"].astype(int)
            df_t10_ev["conv"] = df_t10_ev.apply(
                lambda r: f"{r['anio']}/{r['mes']:02d}", axis=1
            )
            all_p_ev   = sorted(df_t10_ev["partido"].dropna().unique())
            def_ev     = [p for p in _candidates if p in all_p_ev][:6]
            sel_p_ev   = st.multiselect(
                "Selecciona partidos",
                all_p_ev,
                default=def_ev,
                key="evo_parties_mesa",
                help="Partidos presentes en este municipio/distrito/mesa",
            )
            convs_ev = sorted(
                df_t10_ev["conv"].unique(),
                key=lambda c: (int(c[:4]), int(c[5:])),
            )
            if sel_p_ev:
                df_ev = df_t10_ev.groupby(
                    ["conv", "anio", "mes", "partido"], as_index=False
                )["votos_obtenidos"].sum()
                ev_tot = df_ev.groupby("conv")["votos_obtenidos"].transform("sum")
                df_ev["pct"] = (df_ev["votos_obtenidos"] / ev_tot * 100).round(2)
                df_ev = df_ev[df_ev["partido"].isin(sel_p_ev)].sort_values(["anio", "mes"])

                if df_ev.empty:
                    st.warning("Sin datos para los partidos seleccionados.")
                else:
                    fig_ev_m = px.line(
                        df_ev,
                        x="conv", y="pct", color="partido",
                        markers=True,
                        labels={"conv": "Convocatoria", "pct": "% votos",
                                "partido": "Partido"},
                        category_orders={"conv": convs_ev},
                        color_discrete_map=party_color_map(df_ev["partido"].unique()),
                        custom_data=["partido", "conv", "pct", "votos_obtenidos"],
                    )
                    fig_ev_m.update_traces(hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Convocatoria: %{customdata[1]}<br>"
                        "% Votos: %{customdata[2]:.2f}%<br>"
                        "Votos: %{customdata[3]:,.0f}<extra></extra>"
                    ))
                    fig_ev_m.update_layout(
                        height=430, xaxis_tickangle=-40,
                        legend=dict(orientation="h", yanchor="top", y=-0.30),
                    )
                    st.plotly_chart(fig_ev_m, use_container_width=True)

                    st.markdown("**Tabla de evolución** (% voto por convocatoria)")
                    pivot_ev = (
                        df_ev.pivot_table(
                            index="partido", columns="conv",
                            values="pct", aggfunc="sum",
                        ).reindex(columns=[c for c in convs_ev if c in df_ev["conv"].values])
                    )
                    st.dataframe(
                        pivot_ev.style.format("{:.1f}%", na_rep="—"),
                        use_container_width=True,
                    )
            else:
                st.info("Selecciona al menos un partido para ver su evolución.")

            with st.expander("🗺️ Mapa de secciones", expanded=False):
                render_mesa_map(
                    _ms,
                    key="municipales_map_evo",
                )

    else:
        # ── Evolución global (nivel geográfico seleccionado) ─────────────────
        if _is_sm and _sm_row is not None:
            # ── Sistema mayoritario: evolución de participación + partidos ────
            st.subheader(f"📈 {_sm_row['nombre_municipio']} — Evolución histórica")
            t11_evo = t11_all[
                (t11_all["provincia_cod"] == _sm_row["provincia_cod"]) &
                (t11_all["municipio_cod"] == _sm_row["municipio_cod"])
            ].copy()
            _prov_code_evo = PROV_NOMBRE_TO_COD.get(_sm_row["provincia_cod"], _sm_row["provincia_cod"])
            t12_evo = t12_all[
                (t12_all["provincia_cod"] == _prov_code_evo) &
                (t12_all["municipio_cod"] == _sm_row["municipio_cod"])
            ].copy()
            if t11_evo.empty:
                st.warning("Sin datos históricos disponibles.")
            else:
                t11_evo["participacion_pct"] = (
                    t11_evo["total_votantes"] / t11_evo["censo_ine"] * 100
                ).round(1)
                t11_evo = t11_evo.sort_values(["anio", "mes"])
                fig_ca = px.line(
                    t11_evo,
                    x="conv", y="participacion_pct",
                    markers=True,
                    labels={"conv": "Convocatoria", "participacion_pct": "% Participación"},
                    custom_data=["conv", "participacion_pct", "censo_ine", "total_votantes"],
                )
                fig_ca.update_traces(hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Participación: %{customdata[1]:.1f}%<br>"
                    "Censo: %{customdata[2]:.0f}<br>"
                    "Votantes: %{customdata[3]:.0f}<extra></extra>"
                ))
                fig_ca.update_layout(height=380, xaxis_tickangle=-40)
                st.plotly_chart(fig_ca, use_container_width=True)
                st.dataframe(
                    t11_evo[["conv", "censo_ine", "total_votantes", "participacion_pct",
                              "votos_candidaturas", "votos_blanco", "votos_nulos"]]
                    .rename(columns={
                        "conv":               "Convocatoria",
                        "censo_ine":          "Censo INE",
                        "total_votantes":     "Votantes",
                        "participacion_pct":  "% Participación",
                        "votos_candidaturas": "Votos candidaturas",
                        "votos_blanco":       "Votos blanco",
                        "votos_nulos":        "Votos nulos",
                    })
                    .reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                )

                if not t12_evo.empty:
                    st.markdown("**Concejales por partido — histórico**")
                    evo_cand = (
                        t12_evo.drop_duplicates(["conv", "cod_candidatura"])
                        .groupby(["conv", "partido"], as_index=False)["num_candidatos_electos"].sum()
                        .query("num_candidatos_electos > 0")
                        .sort_values(["conv"])
                    )
                    if not evo_cand.empty:
                        fig_evo_p = px.bar(
                            evo_cand,
                            x="conv", y="num_candidatos_electos", color="partido",
                            barmode="stack",
                            labels={"conv": "Convocatoria", "num_candidatos_electos": "Concejales", "partido": "Partido"},
                            color_discrete_map=party_color_map(evo_cand["partido"].unique()),
                        )
                        fig_evo_p.update_layout(height=350, xaxis_tickangle=-40,
                                                legend=dict(orientation="h", yanchor="top", y=-0.30))
                        st.plotly_chart(fig_evo_p, use_container_width=True)
        else:
            all_parties_evo = sorted(df_all["partido"].dropna().unique())
            default_evo     = [p for p in _candidates if p in all_parties_evo][:6]

            sel_parties = st.multiselect(
                "Selecciona partidos",
                all_parties_evo,
                default=default_evo,
                help="Busca y añade cualquier partido del histórico",
                key="evo_parties_global",
            )

            scope_opts = ["Nacional"]
            if nivel == "CCAA" and sel_ccaa:
                scope_opts.append("CCAA seleccionadas")
            if sel_prov:
                scope_opts.append("Provincias seleccionadas")
            if sel_muni:
                scope_opts.append("Municipios seleccionados")
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
                elif scope == "Municipios seleccionados" and sel_muni:
                    df_evo_base = df_evo_base[df_evo_base["municipio_label"].isin(sel_muni)]
                    geo_dim_evo = ["nombre_municipio"]

                evo_grp = ["conv", "anio", "mes"] + geo_dim_evo + ["partido"]
                df_evo  = df_evo_base.groupby(evo_grp, as_index=False)["votos_obtenidos"].sum()
                evo_tot = df_evo.groupby(["conv"] + geo_dim_evo)["votos_obtenidos"].transform("sum")
                df_evo["pct"] = (df_evo["votos_obtenidos"] / evo_tot * 100).round(2)
                df_evo = df_evo[df_evo["partido"].isin(sel_parties)].sort_values(["anio", "mes"])

                if df_evo.empty:
                    st.warning("Sin datos para los partidos seleccionados en este ámbito.")
                else:
                    fig_evo = px.line(
                        df_evo,
                        x="conv", y="pct", color="partido",
                        markers=True,
                        labels={"conv": "Convocatoria", "pct": "% votos", "partido": "Partido"},
                        category_orders={"conv": convs_ord},
                        color_discrete_map=party_color_map(df_evo["partido"].unique()),
                        custom_data=["partido", "conv", "pct", "votos_obtenidos"],
                    )
                    fig_evo.update_traces(hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Convocatoria: %{customdata[1]}<br>"
                        "% Votos: %{customdata[2]:.2f}%<br>"
                        "Votos: %{customdata[3]:,.0f}<extra></extra>"
                    ))
                    fig_evo.update_layout(
                        height=430,
                        xaxis_tickangle=-40,
                        legend=dict(orientation="h", yanchor="top", y=-0.30),
                    )
                    st.plotly_chart(fig_evo, use_container_width=True)

                    st.markdown("**Tabla de evolución** (% voto por convocatoria)")
                    pivot = (
                        df_evo.pivot_table(
                            index="partido", columns="conv", values="pct", aggfunc="sum"
                        )
                        .reindex(columns=[c for c in convs_ord if c in df_evo["conv"].values])
                    )
                    st.dataframe(
                        pivot.style.format("{:.1f}%", na_rep="—"),
                        use_container_width=True,
                    )
            else:
                st.info("Selecciona al menos un partido para ver su evolución histórica.")


# ─────────────────────────────  TAB 3: POR MESA  ──────────────────────────────
if tab_mesa is not None:
    with tab_mesa:
        if _is_sm:
            st.info(
                "⚠️ Los municipios con **menos de 250 habitantes** usan sistema de lista abierta "
                "(LOREG art. 180). No existe desglose por mesa en los microdatos del Ministerio."
            )
        else:
            render_mesa_tab4(_ms, top_n=top_n, color_fn=party_color_map)


# ─────────────────────────────  TAB 4: MAPA  ──────────────────────────────────
with tab_mapa:
    st.markdown(
        f"### 🗺️ Mapa electoral · {nivel} · {_ms_conv}"
    )

    # Determinar la provincia de referencia para el mapa
    _map_prov = sel_prov if sel_prov else None

    # Convocatoria de referencia para el mapa
    _map_conv = sel_convs[-1] if sel_convs else (convs_ord[-1] if convs_ord else "")

    # Nivel efectivo del mapa
    _map_nivel = nivel

    # Para nivel Municipio con distrito activo → nivel Distrito
    _mesa_drill_map = _ms.get("active") and (
        _ms.get("sel_distritos") or _ms.get("sel_mesas")
    )
    if nivel == "Municipio" and _mesa_drill_map:
        _map_nivel = "Distrito"

    if _is_sm and _sm_row is not None:
        _prov_code_m = PROV_NOMBRE_TO_COD.get(_sm_row["provincia_cod"], _sm_row["provincia_cod"])
        _cpro_m = _prov_code_m.zfill(2)
        _cmun_m = str(_sm_row["municipio_cod"]).zfill(3)
        t12_map = t12_all[
            (t12_all["provincia_cod"] == _prov_code_m) &
            (t12_all["municipio_cod"] == _sm_row["municipio_cod"]) &
            (t12_all["conv"] == _map_conv)
        ]
        t11_map = t11_all[
            (t11_all["provincia_cod"] == _sm_row["provincia_cod"]) &
            (t11_all["municipio_cod"] == _sm_row["municipio_cod"]) &
            (t11_all["conv"] == _map_conv)
        ]
        t11_row_m = t11_map.iloc[0] if not t11_map.empty else None
        render_sm_map(
            cpro=_cpro_m,
            cmun=_cmun_m,
            muni_name=_sm_row["nombre_municipio"],
            sel_conv=_map_conv,
            t12_conv=t12_map,
            t11_row=t11_row_m,
            color_fn=party_color_map,
            key="sm_mapa_tab",
            height=460,
        )
    elif _map_nivel in ("CCAA",):
        st.info(
            "💡 El mapa está disponible para los niveles **Nacional**, **Provincia**, "
            "**Municipio** y **Distrito**. El nivel CCAA aún no está soportado."
        )
    else:
        # Para nivel Provincia con varias provincias: advertir que se muestra solo la primera
        if _map_nivel == "Provincia" and _map_prov and len(_map_prov) > 1:
            st.caption(
                f"ℹ️ Se muestra la provincia **{_map_prov[0]}**. "
                "El mapa soporta una provincia a la vez."
            )

        render_election_map(
            nivel=_map_nivel,
            df_votos=df_all,
            df_t11=t11_all,
            df_t12=t12_all,
            color_fn=party_color_map,
            sel_conv=_map_conv,
            sel_prov=_map_prov,
            sel_muni_label=sel_muni[0] if sel_muni and len(sel_muni) == 1 else None,
            prov_nombre_a_cod=PROV_NOMBRE_A_COD,
            mesa_state=_ms if _ms.get("active") else None,
            nacional_show_muni_wins=(_map_nivel == "Nacional"),
            key="municipales_mapa_tab",
            height=560,
        )