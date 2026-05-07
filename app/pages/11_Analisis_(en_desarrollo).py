"""
Análisis electoral — página unificada
Combina: Abstención · Blancos/Nulos · Volatilidad (Pedersen) ·
         Diferencial Congreso/Senado · Paridad de género

Fuentes de datos
────────────────
- tipo_05.parquet  → abstención y participación por municipio
- CSVs pre-calculados en output/  → blancos/nulos, Pedersen, diferencial, paridad

Correcciones aplicadas vs. páginas _old_*
─────────────────────────────────────────
1. provincia_cod en tipo_05 es NOMBRE (no código), no hay que mapear inverso
2. enrich_tipo05() ya calcula abstencion_pct = 100 - participacion_pct
3. % votos sobre votos_candidaturas, no sobre censo ni sobre emitidos
4. category_orders en todos los ejes X de convocatoria para orden cronológico
5. Uso de st.cache_resource para DataFrames grandes (tipo_05)
6. Vectorización: sin apply(lambda) para columnas de texto simples
7. num_escanos con pd.to_numeric(..., errors="coerce") siempre
8. provincia_cod del CSV de Pedersen es código numérico → mapear con PROVINCIAS
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils import OUTPUT_DIR, DATA_DIR, COLS_TIPO05, enrich_tipo05, PROVINCIAS

st.set_page_config(
    page_title="Análisis (en desarrollo)",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Análisis electoral (en desarrollo)")
st.caption(
    "Abstención · Blancos y nulos · Volatilidad Pedersen · "
    "Diferencial Congreso/Senado · Paridad de género · "
    "Fuente: Ministerio del Interior"
)


# ══════════════════════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Cargando datos de participación municipal…")
def _load_t05() -> pd.DataFrame:
    """tipo_05 enriquecido con participacion_pct, abstencion_pct, conv, etc."""
    df = pd.read_parquet(str(DATA_DIR / "tipo_05.parquet"), columns=COLS_TIPO05)
    df = enrich_tipo05(df)
    # Normalizar tipos para filtrado seguro
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["mes"]  = pd.to_numeric(df["mes"],  errors="coerce").astype("Int64")
    # enrich_tipo05 no añade 'conv' → construirlo de forma vectorizada
    df["conv"] = (
        df["anio"].astype(str) + "/" +
        df["mes"].astype(str).str.zfill(2)
    )
    return df


@st.cache_resource(show_spinner=False)
def _load_csv(fname: str) -> pd.DataFrame:
    path = OUTPUT_DIR / fname
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _conv_label(anio, mes) -> str:
    """YYYY + MM → 'YYYY/MM' limpio."""
    a = str(int(anio))
    m = str(int(float(str(mes).replace(".0", "")))).zfill(2)
    return f"{a}/{m}"


def _add_conv(df: pd.DataFrame) -> pd.DataFrame:
    """Añade columna 'conv' = 'YYYY/MM' a partir de anio + mes."""
    df = df.copy()
    df["conv"] = df["anio"].apply(lambda x: str(int(x))) + "/" + \
                 df["mes"].apply(lambda x: str(int(float(str(x).replace(".0", "")))).zfill(2))
    return df


def _prov_code_to_name(cod) -> str:
    """Código numérico 2-dig (int o str) → nombre de provincia."""
    return PROVINCIAS.get(str(int(cod)).zfill(2), str(cod))


def _sorted_convs(df: pd.DataFrame, col: str = "conv") -> list:
    return sorted(df[col].dropna().unique())


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab_abs, tab_bn, tab_ped, tab_dif, tab_par = st.tabs([
    "🚫 Abstención",
    "🗳️ Blancos y nulos",
    "📉 Volatilidad Pedersen",
    "↔️ Diferencial Cong/Sen",
    "⚖️ Paridad de género",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — ABSTENCIÓN POR MUNICIPIO
# ─────────────────────────────────────────────────────────────────────────────
with tab_abs:
    st.markdown(
        "**Abstención media** calculada por municipio a partir de tipo_05 "
        "(municipios con sistema proporcional, censo ≥ 250 hab). "
        "La abstención = 100 − participación. "
        "No incluye municipios de concejo abierto (<250 hab) ni el cómputo "
        "de la 2ª vuelta."
    )

    df05 = _load_t05()

    # ── Sidebar de filtros ───────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Filtros — Abstención")
        tipos_05 = sorted(df05["tipo_eleccion_cod"].dropna().unique())
        sel_tipo_abs = st.multiselect(
            "Tipo de elección", tipos_05,
            default=["Congreso"] if "Congreso" in tipos_05 else tipos_05[:1],
            key="abs_tipo",
        )
        # Provincia: usa nombres directos (provincia_cod = nombre en tipo_05)
        prov_opts_abs = ["Todas"] + sorted(df05["provincia_cod"].dropna().unique())
        sel_prov_abs  = st.selectbox("Provincia", prov_opts_abs, key="abs_prov")
        censo_min_abs = st.number_input(
            "Censo mínimo del municipio", 0, 100_000, 500, step=100,
            key="abs_censo",
            help="Filtra municipios muy pequeños cuya abstención puede ser estadísticamente inestable",
        )

    # ── Filtrado ─────────────────────────────────────────────────────────────
    mask = pd.Series(True, index=df05.index)
    if sel_tipo_abs:
        mask &= df05["tipo_eleccion_cod"].isin(sel_tipo_abs)
    if sel_prov_abs != "Todas":
        mask &= df05["provincia_cod"] == sel_prov_abs
    mask &= df05["censo_ine"].fillna(0) >= censo_min_abs
    # Solo primera vuelta para evitar doble cómputo en Congreso/Senado
    if "vuelta" in df05.columns:
        mask &= df05["vuelta"].fillna(1).astype(int) == 1

    df_f = df05[mask].copy()

    if df_f.empty:
        st.warning("Sin datos para los filtros seleccionados.")
    else:
        grp = (
            df_f.groupby(["provincia_cod", "nombre_municipio"], as_index=False)
            .agg(
                censo_medio=("censo_ine", "mean"),
                participacion_media=("participacion_pct", "mean"),
                abstencion_media=("abstencion_pct", "mean"),
                n_convocatorias=("conv", "nunique"),
            )
            .sort_values("abstencion_media", ascending=False)
        )

        col_sl, col_info = st.columns([1, 3])
        with col_sl:
            n_show = st.slider("Municipios a mostrar", 10, 100, 25, key="abs_n")
        with col_info:
            st.metric("Municipios en selección", f"{len(grp):,}")

        df_top = grp.head(n_show).copy()
        df_top["label"] = df_top["nombre_municipio"] + " (" + df_top["provincia_cod"] + ")"

        fig = px.bar(
            df_top.sort_values("abstencion_media"),
            x="abstencion_media", y="label", orientation="h",
            text_auto=".1f",
            labels={"abstencion_media": "% abstención media", "label": "Municipio"},
            color="abstencion_media", color_continuous_scale="Reds",
            title=f"Top {n_show} municipios por abstención media — {', '.join(sel_tipo_abs) if sel_tipo_abs else 'todos'}",
        )
        fig.update_layout(coloraxis_showscale=False, height=max(350, n_show * 22))
        st.plotly_chart(fig, use_container_width=True)

        # Evolución temporal de abstención media
        st.subheader("Evolución de la abstención media por convocatoria")
        evo = (
            df_f.groupby("conv", as_index=False)
            .agg(abstencion_media=("abstencion_pct", "mean"), n=("abstencion_pct", "count"))
        )
        conv_ord = _sorted_convs(evo)
        fig_evo = px.line(
            evo, x="conv", y="abstencion_media", markers=True,
            category_orders={"conv": conv_ord},
            labels={"conv": "Convocatoria", "abstencion_media": "% abstención media"},
        )
        fig_evo.update_layout(height=340, xaxis_tickangle=-40)
        st.plotly_chart(fig_evo, use_container_width=True)

        # Buscador
        st.subheader("Buscar municipio")
        query = st.text_input("Nombre (parcial)", key="abs_search")
        df_show = grp if not query else grp[
            grp["nombre_municipio"].str.contains(query, case=False, na=False)
        ]
        st.dataframe(
            df_show[["provincia_cod", "nombre_municipio",
                      "censo_medio", "n_convocatorias",
                      "participacion_media", "abstencion_media"]]
            .rename(columns={
                "provincia_cod": "Provincia",
                "nombre_municipio": "Municipio",
                "censo_medio": "Censo medio",
                "n_convocatorias": "Convocatorias",
                "participacion_media": "Participación % media",
                "abstencion_media": "Abstención % media",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "Censo medio":        st.column_config.NumberColumn(format="%d"),
                "Participación % media": st.column_config.NumberColumn(format="%.1f %%"),
                "Abstención % media": st.column_config.NumberColumn(format="%.1f %%"),
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — BLANCOS Y NULOS
# ─────────────────────────────────────────────────────────────────────────────
with tab_bn:
    st.markdown(
        "Porcentaje de **voto en blanco** y **nulo** sobre votos emitidos "
        "por convocatoria y tipo de elección. "
        "Voto en blanco = papeleta sin marcar candidatura. "
        "Voto nulo = papeleta inválida o en sobre erróneo."
    )

    bn_conv = _load_csv("a1_04_blancos_nulos_por_convocatoria.csv")
    bn_tipo = _load_csv("a1_04_blancos_nulos_por_tipo.csv")

    if bn_conv.empty:
        st.error("No se encontró el archivo a1_04_blancos_nulos_por_convocatoria.csv")
    else:
        bn_conv = _add_conv(bn_conv)
        # Solo primera vuelta
        if "vuelta" in bn_conv.columns:
            bn_conv = bn_conv[bn_conv["vuelta"].fillna(1).astype(int) == 1]

        tipos_bn = sorted(bn_conv["tipo_eleccion_cod"].unique())
        sel_tipos_bn = st.multiselect(
            "Tipos de elección", tipos_bn,
            default=["Congreso"] if "Congreso" in tipos_bn else tipos_bn[:2],
            key="bn_tipos",
        )
        df_bn = bn_conv[bn_conv["tipo_eleccion_cod"].isin(sel_tipos_bn)].copy()
        conv_ord_bn = _sorted_convs(df_bn)

        # KPIs de la selección
        if not df_bn.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Blancos medio (%)", f"{df_bn['blancos_pct_emitidos'].mean():.2f}")
            c2.metric("Nulos medio (%)",   f"{df_bn['nulos_pct_emitidos'].mean():.2f}")
            c3.metric("Blancos máx. (%)",  f"{df_bn['blancos_pct_emitidos'].max():.2f}")
            c4.metric("Nulos máx. (%)",    f"{df_bn['nulos_pct_emitidos'].max():.2f}")

        col1, col2 = st.columns(2)
        with col1:
            fig_b = px.line(
                df_bn, x="conv", y="blancos_pct_emitidos",
                color="tipo_eleccion_cod", markers=True,
                category_orders={"conv": conv_ord_bn},
                labels={
                    "conv": "Convocatoria",
                    "blancos_pct_emitidos": "% blanco",
                    "tipo_eleccion_cod": "Tipo",
                },
                title="Voto en blanco (% sobre emitidos)",
            )
            fig_b.update_layout(height=360, xaxis_tickangle=-40)
            st.plotly_chart(fig_b, use_container_width=True)

        with col2:
            fig_n = px.line(
                df_bn, x="conv", y="nulos_pct_emitidos",
                color="tipo_eleccion_cod", markers=True,
                category_orders={"conv": conv_ord_bn},
                labels={
                    "conv": "Convocatoria",
                    "nulos_pct_emitidos": "% nulo",
                    "tipo_eleccion_cod": "Tipo",
                },
                title="Voto nulo (% sobre emitidos)",
            )
            fig_n.update_layout(height=360, xaxis_tickangle=-40)
            st.plotly_chart(fig_n, use_container_width=True)

        # Comparativa por tipo (media histórica)
        if not bn_tipo.empty:
            st.subheader("Media histórica por tipo de elección")
            bn_tipo_m = bn_tipo.melt(
                id_vars="tipo_eleccion_cod",
                value_vars=[c for c in bn_tipo.columns if "pct" in c],
                var_name="categoría", value_name="porcentaje",
            )
            bn_tipo_m["categoría"] = bn_tipo_m["categoría"].map({
                "blancos_pct_media": "Blanco",
                "nulos_pct_media": "Nulo",
            }).fillna(bn_tipo_m["categoría"])
            fig_comp = px.bar(
                bn_tipo_m, x="tipo_eleccion_cod", y="porcentaje",
                color="categoría", barmode="group", text_auto=".2f",
                color_discrete_map={"Blanco": "#64B5F6", "Nulo": "#EF9A9A"},
                labels={"tipo_eleccion_cod": "Tipo", "porcentaje": "%", "categoría": ""},
            )
            fig_comp.update_layout(height=340)
            st.plotly_chart(fig_comp, use_container_width=True)

        with st.expander("Ver tabla completa"):
            st.dataframe(
                df_bn[["tipo_eleccion_cod", "conv", "participacion_pct",
                        "blancos_pct_emitidos", "nulos_pct_emitidos"]],
                use_container_width=True, hide_index=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — VOLATILIDAD PEDERSEN
# ─────────────────────────────────────────────────────────────────────────────
with tab_ped:
    st.markdown(
        """
        El **Índice de Pedersen** mide el cambio de voto entre dos elecciones
        consecutivas del mismo tipo: suma de variaciones absolutas de % voto por
        partido, dividida entre 2. **0% = estabilidad total · 100% = cambio absoluto**.
        Calculado a nivel provincial y promediado al nacional.
        """
    )

    ped_det  = _load_csv("a1_08_volatilidad_pedersen_detalle.csv")
    ped_prov = _load_csv("a1_08_volatilidad_pedersen_provincias.csv")

    if ped_det.empty:
        st.warning("No se encontró el archivo de Pedersen.")
    else:
        # provincia_cod en el CSV es código numérico → nombre
        ped_det["prov_nombre"] = ped_det["provincia_cod"].apply(_prov_code_to_name)

        # conv_posterior: entero YYYYMM → string YYYY/MM
        ped_det["conv"] = ped_det["conv_posterior"].apply(
            lambda x: f"{str(int(x))[:4]}/{str(int(x))[4:]}"
        )

        tipos_ped = sorted(ped_det["tipo_eleccion_cod"].dropna().unique())
        sel_tipo_ped = st.selectbox("Tipo de elección", tipos_ped, key="ped_tipo")

        df_ped = ped_det[ped_det["tipo_eleccion_cod"] == sel_tipo_ped].copy()
        conv_ord_ped = _sorted_convs(df_ped)

        # Pedersen nacional: media entre provincias por convocatoria posterior
        ped_nac = (
            df_ped.groupby("conv", as_index=False)
            .agg(pedersen_medio=("pedersen", "mean"), n_prov=("pedersen", "count"))
        )
        fig_nac = px.bar(
            ped_nac.assign(
                conv=pd.Categorical(ped_nac["conv"], categories=conv_ord_ped, ordered=True)
            ).sort_values("conv"),
            x="conv", y="pedersen_medio",
            color="pedersen_medio", color_continuous_scale="Oranges",
            text_auto=".1f",
            labels={"conv": "Convocatoria (posterior)", "pedersen_medio": "Pedersen medio (%)"},
            title=f"Volatilidad media entre convocatorias consecutivas — {sel_tipo_ped}",
        )
        fig_nac.update_layout(coloraxis_showscale=False, height=360, xaxis_tickangle=-40)
        st.plotly_chart(fig_nac, use_container_width=True)

        # Detalle por provincia en una convocatoria elegida
        st.subheader("Detalle por provincia")
        if conv_ord_ped:
            sel_conv_ped = st.selectbox(
                "Convocatoria (posterior)", conv_ord_ped,
                index=len(conv_ord_ped) - 1, key="ped_conv",
            )
            df_prov_sel = df_ped[df_ped["conv"] == sel_conv_ped].sort_values("pedersen")
            fig_prov = px.bar(
                df_prov_sel, x="pedersen", y="prov_nombre",
                orientation="h", text_auto=".1f",
                color="pedersen", color_continuous_scale="Oranges",
                labels={"pedersen": "Pedersen (%)", "prov_nombre": "Provincia"},
                title=f"Volatilidad por provincia — {sel_conv_ped}",
            )
            fig_prov.update_layout(coloraxis_showscale=False, height=520)
            st.plotly_chart(fig_prov, use_container_width=True)

        # Histórico por provincia
        if not ped_prov.empty:
            st.subheader("Histórico por provincia (media de todos los períodos)")
            ped_prov["prov_nombre"] = ped_prov["provincia_cod"].apply(_prov_code_to_name)
            fig_hist = px.bar(
                ped_prov.sort_values("pedersen_medio"),
                x="pedersen_medio", y="prov_nombre",
                orientation="h", text_auto=".1f",
                color="pedersen_medio", color_continuous_scale="Oranges",
                labels={"pedersen_medio": "Pedersen medio (%)", "prov_nombre": "Provincia"},
            )
            fig_hist.update_layout(coloraxis_showscale=False, height=600)
            st.plotly_chart(fig_hist, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — DIFERENCIAL CONGRESO / SENADO
# ─────────────────────────────────────────────────────────────────────────────
with tab_dif:
    st.markdown(
        """
        **Diferencial de participación Congreso − Senado** calculado a nivel municipal
        en cada convocatoria en que ambas elecciones se celebran simultáneamente.
        Valor positivo → más gente vota al Congreso que al Senado en ese municipio.
        """
    )

    dif_conv = _load_csv("a1_09_diferencial_por_convocatoria.csv")
    dif_muni = _load_csv("a1_09_diferencial_municipios.csv")

    if dif_conv.empty:
        st.warning("No se encontró el archivo de diferencial Congreso/Senado.")
    else:
        dif_conv = _add_conv(dif_conv)
        # Solo primera vuelta si existe columna
        if "vuelta" in dif_conv.columns:
            dif_conv = dif_conv[dif_conv["vuelta"].fillna(1).astype(int) == 1]

        conv_ord_dif = _sorted_convs(dif_conv)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Convocatorias", dif_conv["conv"].nunique())
        c2.metric("Diferencial medio global",
                  f"{dif_conv['diferencial_medio'].mean():.2f} pp")
        c3.metric("Máx. diferencial",
                  f"{dif_conv['diferencial_medio'].max():.2f} pp")
        c4.metric("Mín. diferencial",
                  f"{dif_conv['diferencial_medio'].min():.2f} pp")

        fig_dif = px.line(
            dif_conv, x="conv", y="diferencial_medio", markers=True,
            category_orders={"conv": conv_ord_dif},
            labels={"conv": "Convocatoria", "diferencial_medio": "Diferencial medio (pp)"},
            title="Diferencial medio de participación Congreso − Senado por convocatoria",
        )
        fig_dif.add_hline(y=0, line_dash="dash", line_color="#888888",
                          annotation_text="Sin diferencial")
        fig_dif.update_layout(height=360, xaxis_tickangle=-40)
        st.plotly_chart(fig_dif, use_container_width=True)

        # Detalle por municipio
        if not dif_muni.empty:
            dif_muni = _add_conv(dif_muni)
            if "vuelta" in dif_muni.columns:
                dif_muni = dif_muni[dif_muni["vuelta"].fillna(1).astype(int) == 1]

            st.subheader("Detalle por municipio")
            sel_conv_dif = st.selectbox(
                "Convocatoria", conv_ord_dif[::-1], key="dif_conv_sel",
            )
            df_m = dif_muni[dif_muni["conv"] == sel_conv_dif].copy()

            if df_m.empty:
                st.info("Sin datos municipales para esta convocatoria.")
            else:
                df_m_sorted = df_m.sort_values("diferencial_participacion", ascending=False)
                c1, c2 = st.columns(2)
                show_cols = ["provincia_cod", "nombre_municipio",
                             "participacion_cong", "participacion_sen",
                             "diferencial_participacion"]
                col_rename = {
                    "provincia_cod": "Provincia",
                    "nombre_municipio": "Municipio",
                    "participacion_cong": "Partic. Congreso %",
                    "participacion_sen": "Partic. Senado %",
                    "diferencial_participacion": "Diferencial pp",
                }
                with c1:
                    st.markdown("**Mayor participación en Congreso**")
                    st.dataframe(
                        df_m_sorted[show_cols].head(20).rename(columns=col_rename),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Partic. Congreso %": st.column_config.NumberColumn(format="%.1f %%"),
                            "Partic. Senado %":   st.column_config.NumberColumn(format="%.1f %%"),
                            "Diferencial pp":     st.column_config.NumberColumn(format="%.2f"),
                        },
                    )
                with c2:
                    st.markdown("**Mayor participación en Senado**")
                    st.dataframe(
                        df_m_sorted[show_cols].tail(20)
                        .sort_values("diferencial_participacion")
                        .rename(columns=col_rename),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Partic. Congreso %": st.column_config.NumberColumn(format="%.1f %%"),
                            "Partic. Senado %":   st.column_config.NumberColumn(format="%.1f %%"),
                            "Diferencial pp":     st.column_config.NumberColumn(format="%.2f"),
                        },
                    )

                # Distribución del diferencial
                fig_hist_dif = px.histogram(
                    df_m, x="diferencial_participacion", nbins=40,
                    labels={"diferencial_participacion": "Diferencial pp"},
                    title=f"Distribución del diferencial Congreso−Senado — {sel_conv_dif}",
                    color_discrete_sequence=["#1976D2"],
                )
                fig_hist_dif.add_vline(
                    x=0, line_dash="dash", line_color="#888888",
                )
                fig_hist_dif.update_layout(height=320)
                st.plotly_chart(fig_hist_dif, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — PARIDAD DE GÉNERO
# ─────────────────────────────────────────────────────────────────────────────
with tab_par:
    st.markdown(
        """
        Evolución de la **paridad de género** en las candidaturas y resultados
        del **Congreso de los Diputados** desde 2000.
        La Ley Orgánica de Igualdad (2007) introdujo el umbral del 40% mínimo por sexo.
        """
    )

    par_cand = _load_csv("b2_01_paridad_candidatos_conv.csv")
    par_eleg = _load_csv("b2_01_paridad_elegidos_conv.csv")
    renov    = _load_csv("b2_02_renovacion_listas.csv")

    if par_cand.empty and par_eleg.empty:
        st.warning("No se encontraron datos de paridad.")
    else:
        # Añadir conv string
        if not par_cand.empty:
            par_cand = _add_conv(par_cand).sort_values(["anio", "mes"])
        if not par_eleg.empty:
            par_eleg = _add_conv(par_eleg).sort_values(["anio", "mes"])

        # ── KPIs ────────────────────────────────────────────────────────────
        kp1, kp2, kp3, kp4 = st.columns(4)
        if not par_cand.empty:
            ult_c = par_cand.iloc[-1]
            kp1.metric("% candidatas — última conv.", f"{ult_c['pct_mujeres']:.1f} %")
            kp3.metric("Candidatas", f"{int(ult_c['mujeres']):,}")
        if not par_eleg.empty:
            ult_e = par_eleg.iloc[-1]
            kp2.metric("% elegidas — última conv.", f"{ult_e['pct_mujeres_eleg']:.1f} %")
            kp4.metric("Elegidas", f"{int(ult_e['eleg_mujeres']):,}")

        st.divider()
        col1, col2 = st.columns(2)

        # ── Gráfico candidatas ───────────────────────────────────────────────
        with col1:
            st.subheader("% mujeres candidatas")
            if not par_cand.empty:
                conv_ord_c = _sorted_convs(par_cand)
                fig_cand = go.Figure()
                fig_cand.add_trace(go.Bar(
                    x=par_cand["conv"], y=par_cand["pct_mujeres"],
                    name="% candidatas", marker_color="#E91E63",
                ))
                fig_cand.add_hline(y=40, line_dash="dot", line_color="#1565C0",
                                   annotation_text="Umbral 40% (Ley Igualdad 2007)",
                                   annotation_position="top right")
                fig_cand.add_hline(y=50, line_dash="dash", line_color="#888888",
                                   annotation_text="Paridad 50%")
                fig_cand.update_layout(
                    height=360, xaxis_tickangle=-40, yaxis_range=[0, 65],
                    yaxis_title="% mujeres",
                    xaxis=dict(categoryorder="array", categoryarray=conv_ord_c),
                )
                st.plotly_chart(fig_cand, use_container_width=True)

        # ── Gráfico elegidas ─────────────────────────────────────────────────
        with col2:
            st.subheader("% mujeres elegidas")
            if not par_eleg.empty:
                conv_ord_e = _sorted_convs(par_eleg)
                fig_eleg = go.Figure()
                fig_eleg.add_trace(go.Bar(
                    x=par_eleg["conv"], y=par_eleg["pct_mujeres_eleg"],
                    name="% elegidas", marker_color="#AD1457",
                ))
                fig_eleg.add_hline(y=40, line_dash="dot", line_color="#1565C0",
                                   annotation_text="Umbral 40%")
                fig_eleg.add_hline(y=50, line_dash="dash", line_color="#888888")
                fig_eleg.update_layout(
                    height=360, xaxis_tickangle=-40, yaxis_range=[0, 65],
                    yaxis_title="% mujeres",
                    xaxis=dict(categoryorder="array", categoryarray=conv_ord_e),
                )
                st.plotly_chart(fig_eleg, use_container_width=True)

        # ── Composición candidaturas ─────────────────────────────────────────
        if not par_cand.empty and {"mujeres", "hombres"}.issubset(par_cand.columns):
            conv_ord_c2 = _sorted_convs(par_cand)
            st.subheader("Composición total de candidaturas")
            fig_stack = go.Figure()
            fig_stack.add_trace(go.Bar(
                x=par_cand["conv"], y=par_cand["hombres"],
                name="Hombres", marker_color="#1565C0",
            ))
            fig_stack.add_trace(go.Bar(
                x=par_cand["conv"], y=par_cand["mujeres"],
                name="Mujeres", marker_color="#E91E63",
            ))
            fig_stack.update_layout(
                barmode="stack", height=300, xaxis_tickangle=-40,
                xaxis=dict(categoryorder="array", categoryarray=conv_ord_c2),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_stack, use_container_width=True)

        # ── Renovación de listas ─────────────────────────────────────────────
        st.divider()
        st.subheader("Renovación de listas electorales (Congreso)")
        st.markdown(
            "**Tasa de renovación** = % de candidatos que no aparecieron en "
            "la convocatoria anterior. 100% → lista completamente nueva."
        )

        if renov.empty:
            st.info("Sin datos de renovación disponibles.")
        else:
            kr1, kr2, kr3 = st.columns(3)
            kr1.metric("Pares de convocatorias",     len(renov))
            kr2.metric("Renovación media",  f"{renov['tasa_renovacion_pct'].mean():.1f} %")
            kr3.metric("Renovación máxima", f"{renov['tasa_renovacion_pct'].max():.1f} %")

            fig_renov = px.bar(
                renov, x="conv_posterior", y="tasa_renovacion_pct",
                text_auto=".1f",
                color="tasa_renovacion_pct", color_continuous_scale="Greens",
                labels={
                    "conv_posterior": "Convocatoria (posterior)",
                    "tasa_renovacion_pct": "% renovación",
                },
                title="Tasa de renovación de candidatos entre convocatorias al Congreso",
            )
            fig_renov.add_hline(y=50, line_dash="dash", line_color="#888888",
                                annotation_text="50%")
            fig_renov.update_layout(coloraxis_showscale=False, height=360, xaxis_tickangle=-40)
            st.plotly_chart(fig_renov, use_container_width=True)

            fig_desg = go.Figure()
            fig_desg.add_trace(go.Bar(
                x=renov["conv_posterior"], y=renov["nuevos"],
                name="Nuevos", marker_color="#43A047",
            ))
            fig_desg.add_trace(go.Bar(
                x=renov["conv_posterior"], y=renov["retirados"],
                name="Retirados", marker_color="#E53935",
            ))
            fig_desg.add_trace(go.Bar(
                x=renov["conv_posterior"], y=renov["repetidos"],
                name="Repetidos", marker_color="#1E88E5",
            ))
            fig_desg.update_layout(
                barmode="group", height=320, xaxis_tickangle=-40,
                legend=dict(orientation="h", y=1.1),
                title="Nuevos / Retirados / Repetidos por convocatoria",
            )
            st.plotly_chart(fig_desg, use_container_width=True)

            with st.expander("Ver tabla completa"):
                st.dataframe(renov, use_container_width=True, hide_index=True)
