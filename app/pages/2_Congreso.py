"""
Congreso de los Diputados — Resultados por nivel geográfico y evolución temporal
Fuentes: tipo_06.parquet (votos/municipio), tipo_03.parquet (catálogo candidaturas),
         tipo_07.parquet (escaños por circunscripción)

Niveles disponibles: Nacional · CCAA · Provincia · Municipio
Escaños: calculados por método D'Hondt con umbral del 3% por circunscripción.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import DATA_DIR, PROVINCIAS, PROV_NOMBRE_A_CCAA, etiqueta_conv, party_color_map
from _mesa_view import (
    render_mesa_sidebar, render_mesa_tab4, render_mesa_map,
    get_t10_conv, get_t10_all, add_partido_label, ms_scope_label,
    render_election_map, render_sm_map,
    PROV_NOMBRE_A_COD,
)

TIPO = "Congreso"

st.set_page_config(page_title="Congreso", page_icon="🏛️", layout="wide")
st.title("🏛️ Congreso de los Diputados")
st.caption("Resultados electorales 1979–2023 · Fuente: Ministerio del Interior")


# ── D'Hondt ────────────────────────────────────────────────────────────────────
def _dhondt(vote_series: pd.Series, n_seats: int, threshold: float = 0.03) -> pd.Series:
    """Allocate n_seats by D'Hondt method applying Spain's 3% per-constituency threshold."""
    seats = pd.Series(0, index=vote_series.index, dtype=int)
    total = vote_series.sum()
    if n_seats == 0 or total == 0:
        return seats
    eligible_mask = vote_series >= threshold * total
    if not eligible_mask.any():
        return seats
    q = vote_series.where(eligible_mask, 0.0).copy().astype(float)
    for _ in range(int(n_seats)):
        if q.max() == 0:
            break
        winner = q.idxmax()
        seats[winner] += 1
        q[winner] = vote_series[winner] / (seats[winner] + 1)
    return seats


# ── Carga ──────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando datos del Congreso…")
def _load():
    # ── tipo_06: votos a nivel municipal ──
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta",
                 "provincia_cod", "municipio_cod",
                 "cod_candidatura", "votos_obtenidos", "candidatos_obtenidos"],
    )
    t06 = t06[
        (t06["tipo_eleccion_cod"] == TIPO) & (t06["vuelta"].astype(int) == 1)
    ].copy()

    # ── tipo_03: catálogo partidos ──
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

    # ── Merge votos + partido ──
    df = t06.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"],
        how="left",
    )
    df["partido"] = df["partido"].fillna(df["cod_candidatura"].astype(str))
    df["ccaa_nombre"] = df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")

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
    # Label único para filtros: «Nombre (Provincia)» permite cruzar provincias
    df["municipio_label"] = df["nombre_municipio"] + " (" + df["provincia_cod"] + ")"

    # ── D'Hondt: votos agregados a nivel provincia (antes de convertir tipos) ──
    votos_prov = (
        t06.groupby(["anio", "mes", "provincia_cod", "cod_candidatura"], as_index=False)
        ["votos_obtenidos"].sum()
    )

    # tipo_07: escaños por circunscripción (provincia) por convocatoria
    t07 = pd.read_parquet(
        str(DATA_DIR / "tipo_07.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "provincia_cod", "num_escanos"],
    )
    t07 = t07[
        (t07["tipo_eleccion_cod"] == TIPO) &
        (~t07["provincia_cod"].isin(["99", "00"]))
    ].copy()
    # Eliminar duplicados (el fichero repite cada provincia ~3 veces)
    t07 = t07.drop_duplicates(subset=["anio", "mes", "provincia_cod"])
    # Mapear código numérico de provincia → nombre (igual que tipo_06.provincia_cod)
    t07["provincia_nombre"] = t07["provincia_cod"].map(PROVINCIAS)
    seat_map = (
        t07.dropna(subset=["provincia_nombre"])
        .set_index(["anio", "mes", "provincia_nombre"])["num_escanos"]
        .to_dict()
    )

    # Aplicar D'Hondt por (convocatoria, provincia)
    escanos_records = []
    for (anio_s, mes_f, prov_name), grp in votos_prov.groupby(
        ["anio", "mes", "provincia_cod"]
    ):
        n = int(seat_map.get((anio_s, mes_f, prov_name), 0))
        if n == 0:
            continue
        vote_s = grp.set_index("cod_candidatura")["votos_obtenidos"].fillna(0)
        seat_s = _dhondt(vote_s, n)
        for cand, esc in seat_s.items():
            if esc > 0:
                escanos_records.append({
                    "anio": anio_s, "mes": mes_f,
                    "provincia_cod": prov_name,
                    "cod_candidatura": cand,
                    "escanos": int(esc),
                })

    # Construir escanos_df con partido y ccaa_nombre
    if escanos_records:
        escanos_df = pd.DataFrame(escanos_records)
        escanos_df["anio"] = escanos_df["anio"].astype(int)
        escanos_df["mes"] = escanos_df["mes"].astype(float).astype(int)
        escanos_df["conv"] = escanos_df.apply(
            lambda r: f"{r['anio']}/{r['mes']:02d}", axis=1
        )
        t03_int = t03.copy()
        t03_int["anio"] = t03_int["anio"].astype(int)
        t03_int["mes"] = t03_int["mes"].astype(float).astype(int)
        escanos_df = escanos_df.merge(
            t03_int[["anio", "mes", "cod_candidatura", "partido"]],
            on=["anio", "mes", "cod_candidatura"],
            how="left",
        )
        escanos_df["partido"] = escanos_df["partido"].fillna(
            escanos_df["cod_candidatura"].astype(str)
        )
        escanos_df["ccaa_nombre"] = (
            escanos_df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
        )
    else:
        escanos_df = pd.DataFrame(
            columns=["conv", "anio", "mes", "provincia_cod", "ccaa_nombre",
                     "cod_candidatura", "partido", "escanos"]
        )

    # ── Conversión de tipos en df principal ──
    df["anio"] = df["anio"].astype(int)
    df["mes"] = df["mes"].astype(int)
    df["conv"] = df["anio"].astype(str) + "/" + df["mes"].astype(str).str.zfill(2)
    return df, escanos_df


df_all, escanos_all = _load()
convs_ord = (
    df_all[["anio", "mes", "conv"]].drop_duplicates()
    .sort_values(["anio", "mes"])["conv"].tolist()
)


# ── Agregación cacheada ──────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _build_agg(
    _df: "pd.DataFrame",
    _escanos: "pd.DataFrame",
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
    elif nivel == "Provincia" and sel_prov:
        mask = mask & _df["provincia_cod"].isin(sel_prov)
    elif nivel == "Municipio":
        if sel_prov:
            mask = mask & _df["provincia_cod"].isin(sel_prov)
        if sel_muni:
            mask = mask & _df["municipio_label"].isin(sel_muni)
    dfs = _df[mask]
    group_cols = ["conv", "anio", "mes"] + _GEO + ["partido"]
    agg = dfs.groupby(group_cols, as_index=False).agg(votos=("votos_obtenidos", "sum"))
    agg["votos_total"] = agg.groupby(["conv"] + _GEO)["votos"].transform("sum")
    agg["pct_voto"] = (agg["votos"] / agg["votos_total"] * 100).round(2)
    # Escaños D'Hondt (no aplica a nivel Municipio)
    if nivel != "Municipio" and not _escanos.empty:
        esc_filt = _escanos[_escanos["conv"].isin(sel_convs)]
        if nivel == "CCAA" and sel_ccaa:
            esc_filt = esc_filt[esc_filt["ccaa_nombre"].isin(sel_ccaa)]
        elif nivel == "Provincia" and sel_prov:
            esc_filt = esc_filt[esc_filt["provincia_cod"].isin(sel_prov)]
        esc_agg = esc_filt.groupby(["conv"] + _GEO + ["partido"], as_index=False).agg(
            escanos=("escanos", "sum")
        )
        agg = agg.merge(esc_agg, on=["conv"] + _GEO + ["partido"], how="left")
        agg["escanos"] = agg["escanos"].fillna(0).astype(int)
    else:
        agg["escanos"] = 0
    top = agg.groupby("partido")["votos"].sum().nlargest(top_n).index.tolist()
    return agg, top


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    NIVELES = ["Nacional", "CCAA", "Provincia", "Municipio"]
    nivel = st.radio("Nivel geográfico", NIVELES)

    sel_convs = st.multiselect(
        "Convocatorias",
        convs_ord,
        default=[convs_ord[-1]],
        help="Selecciona una o varias convocatorias para ver o comparar",
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
                df_all[df_all["provincia_cod"].isin(sel_prov)]["municipio_label"]
                .dropna().unique()
            )
        else:
            muni_opts = sorted(df_all["municipio_label"].dropna().unique())
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
    "Municipio": ["provincia_cod", "nombre_municipio"],
}[nivel]

df_agg, top_parties = _build_agg(
    df_all, escanos_all,
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
        key_prefix="congreso",
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


# ─────────────────────────────  TAB 1: RESULTADOS  ────────────────────────────
with tab_res:
    total_votos   = int(df_agg["votos"].sum())
    total_escanos = int(df_agg["escanos"].sum()) if nivel != "Municipio" else 0
    n_partidos    = int(df_agg["partido"].nunique())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nivel", nivel)
    c2.metric("Votos a candidaturas", f"{total_votos:,}")
    c3.metric("Escaños (D'Hondt)", str(total_escanos) if nivel != "Municipio" else "—")
    c4.metric("Partidos con votos", str(n_partidos))

    # ── Nota sobre la fuente de los escaños ──────────────────────────────────
    if nivel != "Municipio":
        anios_sel = {int(c.split("/")[0]) for c in sel_convs}
        tiene_post86 = any(a > 1986 for a in anios_sel)
        tiene_pre87  = any(a <= 1986 for a in anios_sel)
        if tiene_post86 and tiene_pre87:
            st.info(
                "ℹ️ **Fuente de los escaños:** Para las convocatorias **hasta 1986** se conservan "
                "registros parciales en el dataset del Ministerio del Interior. "
                "Para las convocatorias **posteriores a 1986** el Ministerio no incluyó ese campo "
                "en los ficheros de resultados, por lo que los escaños se **calculan aquí "
                "mediante el método D'Hondt** con el umbral del 3% por circunscripción, "
                "tal como establece la LOREG."
            )
        elif tiene_post86:
            st.caption(
                "ℹ️ Escaños calculados mediante D'Hondt (umbral 3% por circunscripción · LOREG) · "
                "El dataset del Ministerio del Interior no incluye este dato para elecciones posteriores a 1986."
            )

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

        df_chart = df_agg[df_agg["partido"].isin(top_parties)].sort_values(["anio", "mes", x_col])

        geo_label = {
            "Nacional":  "Convocatoria",
            "CCAA":      "CCAA",
            "Provincia": "Provincia",
            "Municipio": "Municipio",
        }[nivel]

        fig = px.bar(
            df_chart,
            x=x_col, y="pct_voto", color="partido",
            barmode="group",
            custom_data=["partido", x_col, "pct_voto", "votos"],
            labels={x_col: nivel, "pct_voto": "% votos", "partido": "Partido"},
            color_discrete_map=party_color_map(df_agg["partido"].unique()),
        )
        fig.update_traces(
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"{geo_label}: %{{customdata[1]}}<br>"
                "% Votos: %{customdata[2]:.2f}%<br>"
                "Votos: %{customdata[3]:,.0f}<extra></extra>"
            )
        )
        fig.update_layout(
            height=430,
            xaxis_tickangle=-40,
            legend=dict(orientation="h", yanchor="top", y=-0.30),
            margin=dict(b=90),
        )
        st.plotly_chart(fig, use_container_width=True)

        disp_cols = ["conv"] + GEO_DIM + ["partido", "votos", "pct_voto"]
        if nivel != "Municipio":
            disp_cols.append("escanos")
        disp_cols = [c for c in disp_cols if c in df_agg.columns]
        sort_asc  = [True] * (1 + len(GEO_DIM)) + [False]
        df_tabla  = df_agg[disp_cols].sort_values(
            ["conv"] + GEO_DIM + ["votos"], ascending=sort_asc
        ).reset_index(drop=True)

        cfg = {
            "conv":             st.column_config.TextColumn("Convocatoria", width="small"),
            "ccaa_nombre":      st.column_config.TextColumn("CCAA"),
            "provincia_cod":    st.column_config.TextColumn("Provincia"),
            "nombre_municipio": st.column_config.TextColumn("Municipio"),
            "partido":          st.column_config.TextColumn("Partido"),
            "votos":            st.column_config.NumberColumn("Votos", format="%d"),
            "pct_voto":         st.column_config.NumberColumn("% votos", format="%.2f %%"),
            "escanos":          st.column_config.NumberColumn("Escaños", format="%d"),
        }
        st.dataframe(
            df_tabla,
            use_container_width=True,
            hide_index=True,
            column_config={k: v for k, v in cfg.items() if k in disp_cols},
        )
        st.caption(
            f"Top {top_n} partidos en gráfico · Tabla completa · Fuente: Ministerio del Interior"
        )


# ─────────────────────────────  TAB 2: EVOLUCIÓN  ─────────────────────────────
with tab_evo:
    all_parties_evo = sorted(df_all["partido"].dropna().unique())
    candidates = ["PP", "PSOE", "Cs", "VOX", "IU", "Podemos", "UP",
                  "UPYD", "UCD", "AP", "CD", "CDS"]
    default_evo = [p for p in candidates if p in all_parties_evo][:6]

    sel_parties = st.multiselect(
        "Selecciona partidos",
        all_parties_evo,
        default=default_evo,
        help="Busca y añade cualquier partido del histórico 1979–2023",
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
                custom_data=["partido", "conv", "pct", "votos_obtenidos"],
                labels={"conv": "Convocatoria", "pct": "% votos", "partido": "Partido"},
                category_orders={"conv": convs_ord},
                color_discrete_map=party_color_map(df_evo["partido"].unique()),
            )
            fig_evo.update_traces(
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Convocatoria: %{customdata[1]}<br>"
                    "% Votos: %{customdata[2]:.2f}%<br>"
                    "Votos: %{customdata[3]:,.0f}<extra></extra>"
                )
            )
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
            nacional_seat_df=(
                escanos_all[escanos_all["conv"] == _map_conv][["provincia_cod", "partido", "escanos"]]
                if _map_nivel == "Nacional" and not escanos_all.empty else None
            ),
            nacional_seat_col="escanos",
            nacional_seat_label="diputados",
            key="congreso_mapa_tab",
            height=560,
        )