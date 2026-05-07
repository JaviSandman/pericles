"""
Candidaturas al Parlamento Europeo — listas electorales y resultados.

Fuentes:
  tipo_06 → votos y eurodiputados por candidatura/municipio (agregados a nacional)
  tipo_05 → participación por municipio (agregados a nacional y por provincia)
  tipo_03 → siglas y denominación de la candidatura
  tipo_04 → candidatos individuales (provincia_cod="99", circunscripción nacional única)

El Parlamento Europeo en España usa una **circunscripción nacional única**:
todos los candidatos compiten en una sola lista para toda España.

El mapa permite ver la distribución del voto por provincia; los candidatos
son nacionales (la misma lista para toda España).
"""
import sys, re as _re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from utils import (
    DATA_DIR, PROVINCIAS, PROV_NOMBRE_A_CCAA,
    party_color_map, normalize_partido,
)
from _mesa_view import render_election_map, PROV_NOMBRE_A_COD

TIPO        = "Parlamento Europeo"
ESCANOS_LBL = "Eurodiputados"

st.set_page_config(
    page_title="Candidaturas Europeas",
    page_icon="🇪🇺",
    layout="wide",
)


# =============================================================================
#  CARGA DE DATOS
# =============================================================================

@st.cache_resource(show_spinner="Cargando datos del Parlamento Europeo…")
def _load_base():
    """tipo_06 + tipo_05 + tipo_03, filtrados para Europeas y vuelta 1."""
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "cod_candidatura",
            "votos_obtenidos", "candidatos_obtenidos",
        ],
    )
    t06 = t06[
        (t06["tipo_eleccion_cod"] == TIPO) &
        (t06["vuelta"].astype(int) == 1)
    ].copy()
    t06["anio"] = t06["anio"].astype(int)
    t06["mes"]  = t06["mes"].astype(int)
    t06["conv"] = t06["anio"].astype(str) + "/" + t06["mes"].astype(str).str.zfill(2)

    # Agregado nacional (para tabla resumen)
    t06_nac = (
        t06.groupby(["anio", "mes", "conv", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"),
             candidatos_obtenidos=("candidatos_obtenidos", "sum"))
    )

    # Agregado provincial (para detalle de voto por provincia)
    t06_prov = (
        t06.groupby(["anio", "mes", "conv", "provincia_cod", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"),
             candidatos_obtenidos=("candidatos_obtenidos", "sum"))
    )

    t05 = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod",
            "num_escanos", "censo_ine", "votos_candidaturas",
        ],
    )
    t05 = t05[
        (t05["tipo_eleccion_cod"] == TIPO) &
        (t05["vuelta"].astype(int) == 1)
    ].copy()
    t05["anio"] = t05["anio"].astype(int)
    t05["mes"]  = t05["mes"].astype(int)
    # Nacional
    t05_nac = (
        t05.groupby(["anio", "mes"], as_index=False)
        .agg(censo_ine=("censo_ine", "sum"),
             votos_candidaturas=("votos_candidaturas", "sum"),
             num_escanos=("num_escanos", "max"))
    )
    # Por provincia
    t05_prov = (
        t05.groupby(["anio", "mes", "provincia_cod"], as_index=False)
        .agg(censo_ine=("censo_ine", "sum"),
             votos_candidaturas=("votos_candidaturas", "sum"))
    )

    t03 = pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "cod_candidatura", "siglas", "denominacion"],
    )
    t03 = t03[t03["tipo_eleccion_cod"] == TIPO].copy()
    t03["anio"] = t03["anio"].astype(int)
    t03["mes"]  = t03["mes"].astype(int)
    t03 = t03.drop_duplicates(subset=["anio", "mes", "cod_candidatura"])
    t03["partido"] = t03["siglas"].where(
        t03["siglas"].notna() & (t03["siglas"].astype(str).str.strip() != ""),
        t03["denominacion"].astype(str).str[:28],
    )

    # Escaños reales desde tipo_04 (candidatos_obtenidos en tipo_06 es siempre 0)
    t04_seats = pd.read_parquet(
        str(DATA_DIR / "tipo_04.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta", "cod_candidatura", "elegido"],
    )
    t04_seats = t04_seats[
        (t04_seats["tipo_eleccion_cod"] == TIPO) & (t04_seats["vuelta"] == "1")
    ].copy()
    t04_seats["anio"] = t04_seats["anio"].astype(int)
    t04_seats["mes"]  = t04_seats["mes"].astype(int)
    escanos_nac = (
        t04_seats.groupby(["anio", "mes", "cod_candidatura"])
        .apply(lambda x: (x["elegido"] == "S").sum(), include_groups=False)
        .reset_index(name="escanos_reales")
    )

    # Enriquecer t06_nac
    df_nac = t06_nac.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    df_nac["partido"] = df_nac["partido"].fillna(df_nac["cod_candidatura"].astype(str))
    df_nac["partido"] = df_nac["partido"].map(normalize_partido)
    # Añadir escaños reales
    df_nac = df_nac.merge(escanos_nac, on=["anio", "mes", "cod_candidatura"], how="left")
    df_nac["escanos_reales"] = df_nac["escanos_reales"].fillna(0).astype(int)
    df_nac["candidatos_obtenidos"] = df_nac["escanos_reales"]

    # Enriquecer t06_prov
    df_prov = t06_prov.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    df_prov["partido"] = df_prov["partido"].fillna(df_prov["cod_candidatura"].astype(str))
    df_prov["partido"] = df_prov["partido"].map(normalize_partido)
    df_prov["ccaa_nombre"] = df_prov["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")

    # t06 por municipio enriquecido (para el mapa)
    t06_muni_enrich = t06.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    t06_muni_enrich["partido"] = t06_muni_enrich["partido"].fillna(
        t06_muni_enrich["cod_candidatura"].astype(str)
    ).map(normalize_partido)
    t06_muni_enrich["ccaa_nombre"] = (
        t06_muni_enrich["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    )

    return df_nac, df_prov, t06_muni_enrich, t03, t05_nac, t05_prov


@st.cache_resource(show_spinner="Cargando candidatos…")
def _load_candidatos():
    """tipo_04 para Europeas, vuelta 1, titulares. Circunscripción nacional (provincia_cod="99")."""
    t04 = pd.read_parquet(
        str(DATA_DIR / "tipo_04.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "cod_candidatura",
            "orden", "tipo_candidato", "nombre", "primer_apellido", "segundo_apellido",
            "sexo", "elegido",
        ],
    )
    t04 = t04[
        (t04["tipo_eleccion_cod"] == TIPO) &
        (t04["vuelta"] == "1") &
        (t04["tipo_candidato"] == "T")
    ].copy()
    t04["anio"] = t04["anio"].astype(int)
    t04["mes"]  = t04["mes"].astype(int)
    t04["nombre_completo"] = (
        t04["nombre"].fillna("") + " " +
        t04["primer_apellido"].fillna("") + " " +
        t04["segundo_apellido"].fillna("")
    ).str.strip()
    t04 = t04.drop_duplicates(
        subset=["anio", "mes", "cod_candidatura", "orden"],
        keep="first",
    )
    return t04


# =============================================================================
#  RENDERIZADO DE RESULTADOS NACIONALES
# =============================================================================

def _show_resultados_nacionales(
    anio_sel: int,
    mes_sel: int,
    sel_conv: str,
    df_nac: pd.DataFrame,
    t03_base: pd.DataFrame,
    t05_nac: pd.DataFrame,
    t04_all: pd.DataFrame,
) -> None:
    """Muestra resultados nacionales + lista de candidatos."""

    t05_row = t05_nac[
        (t05_nac["anio"] == anio_sel) & (t05_nac["mes"] == mes_sel)
    ]
    num_escanos = int(t05_row["num_escanos"].iloc[0]) if not t05_row.empty and pd.notna(t05_row["num_escanos"].iloc[0]) else 0
    censo       = int(t05_row["censo_ine"].iloc[0])   if not t05_row.empty else 0
    votos_tot   = int(t05_row["votos_candidaturas"].iloc[0]) if not t05_row.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric(ESCANOS_LBL, num_escanos)
    c2.metric("Censo electoral", f"{censo:,}")
    c3.metric("Votos a candidaturas", f"{votos_tot:,}")
    st.caption("Circunscripción nacional única: todos los candidatos compiten para toda España.")

    st.divider()

    df_c = df_nac[
        (df_nac["anio"] == anio_sel) & (df_nac["mes"] == mes_sel)
    ].copy()

    if df_c.empty:
        st.warning("Sin resultados para esta convocatoria.")
        return

    df_c["pct_votos"] = (
        df_c["votos_obtenidos"] / votos_tot * 100
    ).round(2) if votos_tot > 0 else 0.0

    t03_conv = t03_base[
        (t03_base["anio"] == anio_sel) & (t03_base["mes"] == mes_sel)
    ][["cod_candidatura", "siglas", "denominacion"]]
    df_c = df_c.merge(t03_conv, on="cod_candidatura", how="left")
    df_c["siglas"]       = df_c["siglas"].fillna(df_c["partido"])
    df_c["denominacion"] = df_c["denominacion"].fillna(df_c["siglas"])
    df_c = df_c.sort_values("votos_obtenidos", ascending=False)

    st.subheader("Resultados nacionales")
    resumen = (
        df_c[["siglas", "denominacion", "votos_obtenidos", "pct_votos", "candidatos_obtenidos"]]
        .rename(columns={
            "siglas": "Candidatura",
            "denominacion": "Denominación",
            "votos_obtenidos": "Votos",
            "pct_votos": "% Votos",
            "candidatos_obtenidos": ESCANOS_LBL,
        })
        .reset_index(drop=True)
    )
    st.dataframe(
        resumen, use_container_width=True, hide_index=True,
        column_config={
            "Votos":     st.column_config.NumberColumn(format="%,d"),
            "% Votos":   st.column_config.NumberColumn(format="%.2f%%"),
            ESCANOS_LBL: st.column_config.NumberColumn(format="%d"),
        },
    )
    csv_res = resumen.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar resultados (CSV)", data=csv_res,
        file_name=f"europeas_{sel_conv.replace('/','_')}.csv",
        mime="text/csv", key=f"dl_res_eu_{anio_sel}",
    )

    st.divider()
    st.subheader("Listas de candidatos (circunscripción nacional)")

    t04_eu = t04_all[
        (t04_all["anio"] == anio_sel) & (t04_all["mes"] == mes_sel)
    ].copy()

    if t04_eu.empty:
        st.info("Sin datos de candidatos individuales para esta convocatoria.")
        return

    st.caption(
        f"{len(t04_eu):,} candidatos en {t04_eu['cod_candidatura'].nunique()} candidaturas. "
        "Los marcados con S fueron elegidos eurodiputados."
    )

    for _, cand_row in df_c.iterrows():
        cod_c = cand_row["cod_candidatura"]
        sig_c = str(cand_row.get("siglas") or cand_row.get("partido") or cod_c)
        den_c = str(cand_row.get("denominacion") or sig_c)[:70]
        vot_c = int(cand_row.get("votos_obtenidos") or 0)
        esc_c = int(cand_row.get("candidatos_obtenidos") or 0)
        pct_c = float(cand_row.get("pct_votos") or 0)

        lista = t04_eu[t04_eu["cod_candidatura"] == cod_c].sort_values("orden")
        if lista.empty:
            continue

        esc_str = f"  |  {esc_c} elegido(s)" if esc_c > 0 else ""
        label   = f"{sig_c}  -  {vot_c:,} votos ({pct_c:.2f}%){esc_str}"

        with st.expander(label):
            st.caption(den_c)
            lista_disp = lista[["orden", "nombre_completo", "sexo", "elegido"]].copy()
            lista_disp["elegido"] = lista_disp["elegido"].map({"S": "S", "N": ""}).fillna("")
            lista_disp["orden"]   = lista_disp["orden"].fillna(0).astype(int)
            lista_disp = lista_disp.rename(columns={
                "orden": "Pos", "nombre_completo": "Candidato",
                "sexo": "Sexo", "elegido": "Elegido",
            })
            st.dataframe(
                lista_disp.reset_index(drop=True),
                use_container_width=True, hide_index=True,
                column_config={
                    "Pos":     st.column_config.NumberColumn(format="%d", width="small"),
                    "Elegido": st.column_config.TextColumn(width="small"),
                    "Sexo":    st.column_config.TextColumn(width="small"),
                },
            )
            csv_l = lista_disp.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Descargar lista {sig_c} (CSV)", data=csv_l,
                file_name=f"europeas_{sig_c}_{sel_conv.replace('/','_')}.csv",
                mime="text/csv", key=f"dl_eu_{cod_c}_{anio_sel}",
            )


# =============================================================================
#  RENDERIZADO DE DETALLE POR PROVINCIA
# =============================================================================

def _show_provincia(
    prov_nombre: str,
    anio_sel: int,
    mes_sel: int,
    sel_conv: str,
    df_prov: pd.DataFrame,
    t03_base: pd.DataFrame,
    t05_prov: pd.DataFrame,
) -> None:
    """Resultados de esa provincia para las Europeas (solo votos, no candidatos — son nacionales)."""
    t05_row = t05_prov[
        (t05_prov["anio"] == anio_sel) &
        (t05_prov["mes"]  == mes_sel) &
        (t05_prov["provincia_cod"] == prov_nombre)
    ]
    censo     = int(t05_row["censo_ine"].iloc[0])         if not t05_row.empty else 0
    votos_tot = int(t05_row["votos_candidaturas"].iloc[0]) if not t05_row.empty else 0

    c1, c2 = st.columns(2)
    c1.metric("Censo electoral", f"{censo:,}")
    c2.metric("Votos a candidaturas", f"{votos_tot:,}")
    st.caption("Detalle de voto en esta provincia. Los candidatos son los mismos para toda España.")

    df_p = df_prov[
        (df_prov["anio"] == anio_sel) &
        (df_prov["mes"]  == mes_sel) &
        (df_prov["provincia_cod"] == prov_nombre)
    ].copy()

    if df_p.empty:
        st.warning("Sin resultados para esta provincia y convocatoria.")
        return

    df_p["pct_votos"] = (
        df_p["votos_obtenidos"] / votos_tot * 100
    ).round(2) if votos_tot > 0 else 0.0

    t03_conv = t03_base[
        (t03_base["anio"] == anio_sel) & (t03_base["mes"] == mes_sel)
    ][["cod_candidatura", "siglas"]]
    df_p = df_p.merge(t03_conv, on="cod_candidatura", how="left")
    df_p["siglas"] = df_p["siglas"].fillna(df_p["partido"])
    df_p = df_p.sort_values("votos_obtenidos", ascending=False)

    st.dataframe(
        df_p[["siglas", "votos_obtenidos", "pct_votos"]]
        .rename(columns={"siglas": "Partido", "votos_obtenidos": "Votos", "pct_votos": "% Votos"})
        .reset_index(drop=True),
        use_container_width=True, hide_index=True,
        column_config={
            "Votos":   st.column_config.NumberColumn(format="%,d"),
            "% Votos": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

df_nac, df_prov_data, df_muni, t03_base, t05_nac, t05_prov = _load_base()
t04_all = _load_candidatos()

convs_ord = sorted(df_nac["conv"].unique())

if st.session_state.get("_eu_pending_prov"):
    _pending = st.session_state.pop("_eu_pending_prov")
    _cur = list(st.session_state.get("eu_provs") or [])
    if _pending not in _cur:
        st.session_state["eu_provs"] = _cur + [_pending]

st.title("🇪🇺 Candidaturas al Parlamento Europeo")
st.caption(
    "Listas electorales, candidatos y resultados · 1987-2024 · "
    "Circunscripción nacional única · Fuente: Ministerio del Interior"
)

with st.sidebar:
    st.header("Filtros")
    sel_conv = st.selectbox(
        "Convocatoria", convs_ord, index=len(convs_ord) - 1, key="eu_conv",
    )
    anio_sel = int(sel_conv[:4])
    mes_sel  = int(sel_conv[5:])

    provs_conv = sorted(
        df_prov_data[
            (df_prov_data["anio"] == anio_sel) & (df_prov_data["mes"] == mes_sel)
        ]["provincia_cod"].dropna().unique()
    )

    st.divider()
    st.markdown("**Vista de provincia**")
    st.caption("Selecciona en el mapa o en la lista para ver el desglose provincial del voto.")
    sel_provs = st.multiselect(
        "Provincias", provs_conv,
        placeholder="Opcional: desglose por provincia",
        key="eu_provs",
    )
    st.divider()
    if sel_provs:
        st.info(f"{len(sel_provs)} provincia(s) para desglose regional.")
    else:
        st.info("Sin provincia seleccionada: se muestran resultados nacionales.")

# ── Layout: mapa izq. + contenido dcha. ──────────────────────────────────────
df_conv_all = df_muni[
    (df_muni["anio"] == anio_sel) & (df_muni["mes"] == mes_sel)
].copy()

col_map, col_tabla = st.columns([42, 58])

with col_map:
    st.subheader(f"España · {sel_conv}")
    if df_conv_all.empty:
        st.warning("Sin datos para la convocatoria seleccionada.")
    else:
        # Totales de votos a candidaturas por provincia para normalizar %
        _t05_conv = t05_prov[
            (t05_prov["anio"] == anio_sel) & (t05_prov["mes"] == mes_sel)
        ]
        _prov_totals = dict(
            zip(_t05_conv["provincia_cod"], _t05_conv["votos_candidaturas"])
        )
        _tooltip = render_election_map(
            nivel="Nacional",
            df_votos=df_conv_all,
            df_t11=None,
            df_t12=None,
            color_fn=party_color_map,
            sel_conv=sel_conv,
            sel_prov=provs_conv,
            prov_nombre_a_cod=PROV_NOMBRE_A_COD,
            nacional_prov_totals=_prov_totals,
            return_click=True,
            key="eu_mapa_nac",
            height=500,
        )
        _last_popup = st.session_state.get("_eu_last_popup")
        if _tooltip and _tooltip != _last_popup:
            st.session_state["_eu_last_popup"] = _tooltip
            _clicked_raw = _re.sub(r'<[^>]+>', ' ', _tooltip)
            _clicked_raw = _re.sub(r'\s+', ' ', _clicked_raw).strip()
            if _clicked_raw:
                _upper_map = {n.upper(): n for n in provs_conv}
                _matched   = _upper_map.get(_clicked_raw.upper())
                if _matched and _matched not in (st.session_state.get("eu_provs") or []):
                    st.session_state["_eu_pending_prov"] = _matched
                    st.rerun()
    st.caption("Provincias coloreadas por partido con más votos. Clic para ver desglose provincial.")

with col_tabla:
    if not sel_provs:
        # Vista principal: resultados nacionales + candidatos
        _show_resultados_nacionales(
            anio_sel=anio_sel,
            mes_sel=mes_sel,
            sel_conv=sel_conv,
            df_nac=df_nac,
            t03_base=t03_base,
            t05_nac=t05_nac,
            t04_all=t04_all,
        )
    else:
        # Vista provincial: desglose del voto en las provincias seleccionadas
        # + acceso a la lista nacional de candidatos
        if len(sel_provs) > 1:
            tab_names = [f"{p}" for p in sel_provs] + ["🇪🇸 Lista nacional"]
            tabs = st.tabs(tab_names)
            for tab, prov_nombre in zip(tabs[:-1], sel_provs):
                with tab:
                    _show_provincia(
                        prov_nombre=prov_nombre,
                        anio_sel=anio_sel,
                        mes_sel=mes_sel,
                        sel_conv=sel_conv,
                        df_prov=df_prov_data,
                        t03_base=t03_base,
                        t05_prov=t05_prov,
                    )
            with tabs[-1]:
                _show_resultados_nacionales(
                    anio_sel=anio_sel,
                    mes_sel=mes_sel,
                    sel_conv=sel_conv,
                    df_nac=df_nac,
                    t03_base=t03_base,
                    t05_nac=t05_nac,
                    t04_all=t04_all,
                )
        else:
            prov_nombre = sel_provs[0]
            c_prov, c_nac = st.columns([1, 1])
            with c_prov:
                st.subheader(f"Voto en {prov_nombre}")
                _show_provincia(
                    prov_nombre=prov_nombre,
                    anio_sel=anio_sel,
                    mes_sel=mes_sel,
                    sel_conv=sel_conv,
                    df_prov=df_prov_data,
                    t03_base=t03_base,
                    t05_prov=t05_prov,
                )
            with c_nac:
                st.subheader("Lista nacional de candidatos")
                _show_resultados_nacionales(
                    anio_sel=anio_sel,
                    mes_sel=mes_sel,
                    sel_conv=sel_conv,
                    df_nac=df_nac,
                    t03_base=t03_base,
                    t05_nac=t05_nac,
                    t04_all=t04_all,
                )
