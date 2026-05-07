"""
Candidaturas Municipales - Listas electorales por municipio y convocatoria
Fuentes:
  tipo_04 -> candidatos (nombre, orden, elegido)
  tipo_06 -> votos y concejales por candidatura
  tipo_05 -> datos del municipio (censo, escanos, nombre)
  tipo_03 -> siglas y denominacion de la candidatura

Nota: tipo_04 codifica provincia_cod con codigo INE de 2 digitos (ej. "28")
      tipo_06 / tipo_05 usan el nombre de la provincia (ej. "Madrid").
      Se resuelve con el dict PROVINCIAS: codigo -> nombre.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from utils import (
    DATA_DIR, PROVINCIAS, PROV_NOMBRE_A_CCAA,
    party_color_map, normalize_partido,
)
from _mesa_view import render_election_map, PROV_NOMBRE_A_COD

TIPO = "Municipales"

st.set_page_config(
    page_title="Candidaturas Municipales",
    page_icon="U+1F5F3",
    layout="wide",
)


# =============================================================================
#  CARGA DE DATOS
# =============================================================================

@st.cache_resource(show_spinner="Cargando datos electorales...")
def _load_base():
    """Carga tipo_06 + tipo_05 + tipo_03 para Municipales (1a vuelta)."""
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

    # Agregar votos por municipio (colapsa multiples distritos en municipios grandes)
    t06 = (
        t06.groupby(["anio", "mes", "provincia_cod", "municipio_cod", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"),
             candidatos_obtenidos=("candidatos_obtenidos", "sum"))
    )
    t06["conv"] = t06.apply(lambda r: f"{r['anio']}/{r['mes']:02d}", axis=1)

    t05 = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "nombre_municipio",
            "num_escanos", "censo_ine", "votos_candidaturas",
        ],
    )
    t05 = t05[
        (t05["tipo_eleccion_cod"] == TIPO) &
        (t05["vuelta"].astype(int) == 1)
    ].copy()
    t05["anio"] = t05["anio"].astype(int)
    t05["mes"]  = t05["mes"].astype(int)

    t03 = pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes",
            "cod_candidatura", "siglas", "denominacion",
        ],
    )
    t03 = t03[t03["tipo_eleccion_cod"] == TIPO].copy()
    t03["anio"] = t03["anio"].astype(int)
    t03["mes"]  = t03["mes"].astype(int)
    t03 = t03.drop_duplicates(subset=["anio", "mes", "cod_candidatura"])
    t03["partido"] = t03["siglas"].where(
        t03["siglas"].notna() & (t03["siglas"].astype(str).str.strip() != ""),
        t03["denominacion"].astype(str).str[:28],
    )

    # df_votos: estructura para el mapa (= formato de 3_Municipales)
    df_votos = t06.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"],
        how="left",
    )
    df_votos["partido"] = df_votos["partido"].fillna(
        df_votos["cod_candidatura"].astype(str)
    )
    df_votos["partido"] = df_votos["partido"].map(normalize_partido)
    df_votos["ccaa_nombre"] = (
        df_votos["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    )

    # Anidir nombre_municipio y num_escanos desde t05
    # Ordenar por num_escanos desc para que la fila agregada (municipio total, con
    # num_escanos no nulo) se elija sobre las filas de distrito (num_escanos=NaN)
    mun_meta = (
        t05[["anio", "mes", "provincia_cod", "municipio_cod",
              "nombre_municipio", "num_escanos", "censo_ine", "votos_candidaturas"]]
        .sort_values("num_escanos", ascending=False, na_position="last")
        .drop_duplicates(subset=["anio", "mes", "provincia_cod", "municipio_cod"])
    )
    df_votos = df_votos.merge(
        mun_meta[["anio", "mes", "provincia_cod", "municipio_cod", "nombre_municipio", "num_escanos"]],
        on=["anio", "mes", "provincia_cod", "municipio_cod"], how="left"
    )

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
    t11 = t11.drop_duplicates(["anio", "mes", "provincia_cod", "municipio_cod"])
    t11["conv"] = t11.apply(lambda r: f"{r['anio']}/{r['mes']:02d}", axis=1)
    t11["total_votantes"] = (
        t11["votos_blanco"].fillna(0) +
        t11["votos_nulos"].fillna(0) +
        t11["votos_candidaturas"].fillna(0)
    ).astype(int)
    t11["nombre_municipio"] = t11["nombre_municipio"].str.title()

    # ── tipo_12: candidatos de municipios <250 hab ───────────────────────────
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
    t12 = t12.drop_duplicates(["_anio", "_mes", "provincia_cod", "municipio_cod",
                               "nombre", "primer_apellido", "segundo_apellido"])
    t12["nombre_completo"] = (
        t12["nombre"].str.strip() + " " +
        t12["primer_apellido"].str.strip() + " " +
        t12["segundo_apellido"].str.strip()
    ).str.strip()
    t12["conv"] = t12.apply(lambda r: f"{r['_anio']}/{r['_mes']:02d}", axis=1)

    return df_votos, t03, mun_meta, t11, t12


@st.cache_resource(show_spinner="Cargando candidatos (tipo_04)...")
def _load_candidatos():
    """Carga tipo_04 completo para Municipales, 1a vuelta."""
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
        (t04["tipo_candidato"] == "T")   # Solo titulares; excluir suplentes ('S')
    ].copy()
    t04["anio"] = t04["anio"].astype(int)
    t04["mes"]  = t04["mes"].astype(int)

    # provincia_cod en tipo_04 usa codigo INE -> mapear a nombre de provincia
    t04["provincia_nombre"] = t04["provincia_cod"].map(PROVINCIAS)

    # Nombre completo
    t04["nombre_completo"] = (
        t04["nombre"].fillna("") + " "
        + t04["primer_apellido"].fillna("") + " "
        + t04["segundo_apellido"].fillna("")
    ).str.strip()

    # Deduplicar (el mismo DAT puede indexarse varias veces en el repo)
    t04 = t04.drop_duplicates(
        subset=["anio", "mes", "provincia_cod", "municipio_cod", "cod_candidatura", "orden"],
        keep="first",
    )

    return t04


# =============================================================================
#  FUNCION DE RENDERIZADO DE UN MUNICIPIO
#  (definida ANTES de su llamada al final del archivo)
# =============================================================================

def _show_candidaturas(
    muni_name: str,
    munis_df: pd.DataFrame,
    anio_sel: int,
    mes_sel: int,
    sel_conv: str,
    sel_prov: str,
    df_all: pd.DataFrame,
    t03_base: pd.DataFrame,
    mun_meta_base: pd.DataFrame,
    t04_all: pd.DataFrame,
    t11_base: "pd.DataFrame | None" = None,
    t12_base: "pd.DataFrame | None" = None,
    solo: bool = False,
) -> None:
    """Muestra resumen de candidaturas + lista de candidatos para un municipio."""

    row_m = munis_df[munis_df["nombre_municipio"] == muni_name]
    if row_m.empty:
        st.warning(f"No se encontro codigo para '{muni_name}'.")
        return
    muni_cod = row_m["municipio_cod"].iloc[0]

    # Datos del municipio: intentar mun_meta (normales) o t11 (<250 hab)
    t05_row = mun_meta_base[
        (mun_meta_base["anio"] == anio_sel) &
        (mun_meta_base["mes"]  == mes_sel) &
        (mun_meta_base["provincia_cod"] == sel_prov) &
        (mun_meta_base["municipio_cod"] == muni_cod)
    ]
    is_small_muni = False
    t11_row = pd.DataFrame()
    if t05_row.empty and t11_base is not None:
        t11_row = t11_base[
            (t11_base["anio"] == anio_sel) &
            (t11_base["mes"]  == mes_sel) &
            (t11_base["provincia_cod"] == sel_prov) &
            (t11_base["municipio_cod"] == muni_cod)
        ]
        is_small_muni = not t11_row.empty

    if is_small_muni:
        num_escanos = int(t11_row["num_escanos"].iloc[0])                        if pd.notna(t11_row["num_escanos"].iloc[0]) else 0
        censo       = int(t11_row["censo_ine"].iloc[0])                          if pd.notna(t11_row["censo_ine"].iloc[0])   else 0
        votos_tot   = int(t11_row["votos_candidaturas"].fillna(0).iloc[0])
        st.caption("Municipio con sistema mayoritario de lista abierta (<250 hab)")
    else:
        num_escanos = int(t05_row["num_escanos"].iloc[0])                  if not t05_row.empty and pd.notna(t05_row["num_escanos"].iloc[0]) else 0
        censo       = int(t05_row["censo_ine"].iloc[0])                    if not t05_row.empty and pd.notna(t05_row["censo_ine"].iloc[0])   else 0
        _vc = t05_row["votos_candidaturas"].iloc[0] if not t05_row.empty else None
        votos_tot   = int(_vc) if pd.notna(_vc) else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Concejales a elegir", num_escanos)
    c2.metric("Censo electoral", f"{censo:,}")
    c3.metric("Votos a candidaturas", f"{votos_tot:,}")

    st.divider()

    # ─── Municipios pequenos (<250 hab): rama tipo_12 ─────────────────────────
    if is_small_muni:
        prov_cod_ine = PROV_NOMBRE_A_COD.get(sel_prov, "")
        if t12_base is not None and prov_cod_ine:
            t12_muni = t12_base[
                (t12_base["_anio"] == anio_sel) &
                (t12_base["_mes"]  == mes_sel) &
                (t12_base["provincia_cod"] == prov_cod_ine) &
                (t12_base["municipio_cod"] == muni_cod)
            ].copy()
        else:
            t12_muni = pd.DataFrame()

        if t12_muni.empty:
            st.info("Sin datos de candidatos para este municipio y convocatoria.")
            return

        total_cv = t12_muni.drop_duplicates("cod_candidatura")["votos_candidatura"].sum()

        st.subheader("Resultados por candidatura")
        cand_summ = (
            t12_muni.drop_duplicates("cod_candidatura")
            .assign(
                pct_votos=lambda d:
                    (d["votos_candidatura"] / total_cv * 100).round(1)
                    if total_cv > 0 else 0.0
            )
            [["partido", "denominacion", "votos_candidatura", "pct_votos", "num_candidatos_electos"]]
            .sort_values("votos_candidatura", ascending=False)
            .rename(columns={
                "partido":                "Candidatura",
                "denominacion":           "Denominacion",
                "votos_candidatura":      "Votos",
                "pct_votos":              "% Votos",
                "num_candidatos_electos": "Elegidos",
            })
            .reset_index(drop=True)
        )
        st.dataframe(
            cand_summ,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Votos":    st.column_config.NumberColumn(format="%,d"),
                "% Votos":  st.column_config.NumberColumn(format="%.1f%%"),
                "Elegidos": st.column_config.NumberColumn(format="%d"),
            },
        )
        csv_res = cand_summ.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar resultados (CSV)",
            data=csv_res,
            file_name=f"candidaturas_{muni_name}_{sel_conv.replace('/','_')}.csv",
            mime="text/csv",
            key=f"dl_res_{muni_cod}_{anio_sel}",
        )
        st.divider()

        st.subheader("Candidatos")
        st.caption("Lista abierta: los mas votados obtienen el acta independientemente de la candidatura.")
        n_cands_12 = t12_muni["cod_candidatura"].nunique()
        for _, cr in (
            t12_muni.drop_duplicates("cod_candidatura")
            .sort_values("votos_candidatura", ascending=False)
            .iterrows()
        ):
            cod_c  = cr["cod_candidatura"]
            sig_c  = str(cr.get("partido") or cod_c)
            den_c  = str(cr.get("denominacion") or sig_c)[:70]
            vot_c  = int(cr.get("votos_candidatura") or 0)
            ele_c  = int(cr.get("num_candidatos_electos") or 0)
            pct_c  = round(vot_c / total_cv * 100, 1) if total_cv > 0 else 0.0
            lista12 = (
                t12_muni[t12_muni["cod_candidatura"] == cod_c]
                .sort_values("votos_obtenidos", ascending=False)
            )
            if lista12.empty:
                continue
            ele_str = f"  |  {ele_c} elegido(s)" if ele_c > 0 else ""
            label   = f"{sig_c}  -  {vot_c:,} votos ({pct_c:.1f}%){ele_str}"
            with st.expander(label, expanded=(solo and n_cands_12 <= 3)):
                st.caption(den_c)
                l12_disp = lista12[["nombre_completo", "sexo", "votos_obtenidos", "elegido"]].copy()
                l12_disp["elegido"] = l12_disp["elegido"].map({"S": "S", "N": ""}).fillna("")
                l12_disp = l12_disp.rename(columns={
                    "nombre_completo":  "Candidato",
                    "sexo":             "Sexo",
                    "votos_obtenidos":  "Votos obtenidos",
                    "elegido":          "Elegido",
                })
                st.dataframe(
                    l12_disp.reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Votos obtenidos": st.column_config.NumberColumn(format="%,d"),
                        "Elegido":         st.column_config.TextColumn(width="small"),
                        "Sexo":            st.column_config.TextColumn(width="small"),
                    },
                )
                csv_l12 = l12_disp.to_csv(index=False).encode("utf-8")
                st.download_button(
                    f"Descargar candidatos {sig_c} (CSV)",
                    data=csv_l12,
                    file_name=f"lista_{muni_name}_{sig_c}_{sel_conv.replace('/','_')}.csv",
                    mime="text/csv",
                    key=f"dl_l12_{muni_cod}_{cod_c}_{anio_sel}",
                )
        return

    # ─── Municipios normales: datos de tipo_06 / tipo_04 ────────────────────
    # Votos por candidatura (ya agregados por municipio en _load_base, pero
    # se hace groupby de seguridad para municipios multi-distrito)
    t06_muni = (
        df_all[
            (df_all["anio"] == anio_sel) &
            (df_all["mes"]  == mes_sel) &
            (df_all["provincia_cod"] == sel_prov) &
            (df_all["municipio_cod"] == muni_cod)
        ]
        .groupby(["cod_candidatura", "partido"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"),
             candidatos_obtenidos=("candidatos_obtenidos", "sum"))
    )

    if t06_muni.empty:
        st.warning("Sin resultados electorales para este municipio y convocatoria.")
        return

    t06_muni["pct_votos"] = (
        t06_muni["votos_obtenidos"] / votos_tot * 100
    ).round(1) if votos_tot > 0 else 0.0

    # Anidir siglas y denominacion
    t03_conv = t03_base[
        (t03_base["anio"] == anio_sel) & (t03_base["mes"] == mes_sel)
    ][["cod_candidatura", "siglas", "denominacion"]]
    t06_muni = t06_muni.merge(t03_conv, on="cod_candidatura", how="left")
    t06_muni["siglas"]       = t06_muni["siglas"].fillna(t06_muni["partido"])
    t06_muni["denominacion"] = t06_muni["denominacion"].fillna(t06_muni["siglas"])
    t06_muni = t06_muni.sort_values("votos_obtenidos", ascending=False)

    # --- Tabla resumen ---
    st.subheader("Resultados por candidatura")

    resumen = (
        t06_muni[[
            "siglas", "denominacion", "votos_obtenidos",
            "pct_votos", "candidatos_obtenidos",
        ]]
        .rename(columns={
            "siglas":               "Candidatura",
            "denominacion":         "Denominacion",
            "votos_obtenidos":      "Votos",
            "pct_votos":            "% Votos",
            "candidatos_obtenidos": "Concejales",
        })
        .reset_index(drop=True)
    )

    st.dataframe(
        resumen,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Votos":      st.column_config.NumberColumn(format="%,d"),
            "% Votos":    st.column_config.NumberColumn(format="%.1f%%"),
            "Concejales": st.column_config.NumberColumn(format="%d"),
        },
    )

    csv_res = resumen.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar resultados (CSV)",
        data=csv_res,
        file_name=f"candidaturas_{muni_name}_{sel_conv.replace('/','_')}.csv",
        mime="text/csv",
        key=f"dl_res_{muni_cod}_{anio_sel}",
    )

    st.divider()

    # --- Listas de candidatos ---
    st.subheader("Listas de candidatos")

    t04_muni = t04_all[
        (t04_all["anio"] == anio_sel) &
        (t04_all["mes"]  == mes_sel) &
        (t04_all["provincia_nombre"] == sel_prov) &
        (t04_all["municipio_cod"] == muni_cod)
    ].copy()

    if t04_muni.empty:
        st.info(
            "No hay datos de candidatos individuales para esta convocatoria/municipio. "
            "(tipo_04 disponible a partir de 1987)"
        )
        return

    n_candidatos = len(t04_muni)
    n_cands      = t04_muni["cod_candidatura"].nunique()
    st.caption(
        f"{n_candidatos:,} candidatos en {n_cands} candidaturas. "
        "Los marcados con S fueron elegidos concejales."
    )

    for _, cand_row in t06_muni.iterrows():
        cod_c    = cand_row["cod_candidatura"]
        siglas_c = str(cand_row.get("siglas") or cand_row.get("partido") or cod_c)
        denom_c  = str(cand_row.get("denominacion") or siglas_c)[:70]
        votos_c  = int(cand_row.get("votos_obtenidos") or 0)
        conc_c   = int(cand_row.get("candidatos_obtenidos") or 0)
        pct_c    = float(cand_row.get("pct_votos") or 0)

        lista = t04_muni[t04_muni["cod_candidatura"] == cod_c].sort_values("orden")
        if lista.empty:
            continue

        elegidos_str = f"  |  {conc_c} elegido(s)" if conc_c > 0 else ""
        label = f"{siglas_c}  -  {votos_c:,} votos ({pct_c:.1f}%){elegidos_str}"

        auto_expand = solo and (n_cands <= 3)

        with st.expander(label, expanded=auto_expand):
            st.caption(denom_c)

            lista_disp = lista[["orden", "nombre_completo", "sexo", "elegido"]].copy()
            lista_disp["elegido"] = lista_disp["elegido"].map({"S": "S", "N": ""}).fillna("")
            lista_disp["orden"]   = lista_disp["orden"].fillna(0).astype(int)
            lista_disp = lista_disp.rename(columns={
                "orden":           "Pos",
                "nombre_completo": "Candidato",
                "sexo":            "Sexo",
                "elegido":         "Elegido",
            })

            st.dataframe(
                lista_disp.reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Pos":     st.column_config.NumberColumn(format="%d", width="small"),
                    "Elegido": st.column_config.TextColumn(width="small"),
                    "Sexo":    st.column_config.TextColumn(width="small"),
                },
            )

            csv_lista = lista_disp.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Descargar lista {siglas_c} (CSV)",
                data=csv_lista,
                file_name=f"lista_{muni_name}_{siglas_c}_{sel_conv.replace('/','_')}.csv",
                mime="text/csv",
                key=f"dl_lista_{muni_cod}_{cod_c}_{anio_sel}",
            )


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

df_all, t03_base, mun_meta_base, t11_all, t12_all = _load_base()
t04_all = _load_candidatos()

convs_ord = sorted(df_all["conv"].unique())

# -- Procesar click del mapa pendiente ANTES de renderizar sidebar ───────────
import re as _re
if st.session_state.get("_cand_pending_muni"):
    _pending = st.session_state.pop("_cand_pending_muni")
    _cur     = list(st.session_state.get("cand_munis") or [])
    if _pending not in _cur:
        st.session_state["cand_munis"] = _cur + [_pending]

st.title("Candidaturas Municipales")
st.caption(
    "Listas electorales, candidatos y resultados  1987-2023  "
    "Fuente: Ministerio del Interior"
)

# -- Sidebar ---
with st.sidebar:
    st.header("Filtros")

    sel_conv = st.selectbox(
        "Convocatoria",
        convs_ord,
        index=len(convs_ord) - 1,
        key="cand_conv",
    )
    anio_sel = int(sel_conv[:4])
    mes_sel  = int(sel_conv[5:])

    provs_conv = sorted(
        df_all[
            (df_all["anio"] == anio_sel) & (df_all["mes"] == mes_sel)
        ]["provincia_cod"].dropna().unique()
    )
    sel_prov = st.selectbox("Provincia", provs_conv, key="cand_prov")

    df_prov_conv = df_all[
        (df_all["anio"] == anio_sel) &
        (df_all["mes"]  == mes_sel) &
        (df_all["provincia_cod"] == sel_prov)
    ].copy()

    munis_df_t06 = (
        df_prov_conv[["municipio_cod", "nombre_municipio"]]
        .drop_duplicates("municipio_cod")
        .dropna(subset=["nombre_municipio"])
    )
    # Anadir municipios pequenos (<250 hab) desde t11
    t11_prov = t11_all[
        (t11_all["anio"] == anio_sel) &
        (t11_all["mes"]  == mes_sel) &
        (t11_all["provincia_cod"] == sel_prov)
    ][["municipio_cod", "nombre_municipio"]].drop_duplicates("municipio_cod")
    munis_df = (
        pd.concat([munis_df_t06, t11_prov], ignore_index=True)
        .drop_duplicates("municipio_cod")
        .dropna(subset=["nombre_municipio"])
        .sort_values("nombre_municipio")
    )
    muni_opts = munis_df["nombre_municipio"].tolist()

    sel_munis = st.multiselect(
        "Municipios",
        muni_opts,
        placeholder="Selecciona uno o mas...",
        key="cand_munis",
    )

    st.divider()
    if sel_munis:
        st.success(f"{len(sel_munis)} municipio(s) seleccionado(s)")
    else:
        st.info("Selecciona municipios en la lista.")
        st.caption(f"Hay {len(muni_opts):,} municipios en {sel_prov}.")

# -- Layout: mapa izq. + tablas dcha. ---
col_map, col_tabla = st.columns([42, 58])

with col_map:
    st.subheader(f"{sel_prov}  {sel_conv}")
    if df_prov_conv.empty:
        st.warning("Sin datos electorales para la seleccion.")
    else:
        _mapa_tooltip = render_election_map(
            nivel="Provincia",
            df_votos=df_prov_conv,
            df_t11=t11_all,
            df_t12=t12_all,
            color_fn=party_color_map,
            sel_conv=sel_conv,
            sel_prov=[sel_prov],
            prov_nombre_a_cod=PROV_NOMBRE_A_COD,
            return_click=True,
            key="cand_mapa_prov",
            height=480,
        )
        # Procesar click del mapa: el popup devuelve HTML con el nombre del municipio
        _last_popup = st.session_state.get("_cand_last_popup")
        if _mapa_tooltip and _mapa_tooltip != _last_popup:
            st.session_state["_cand_last_popup"] = _mapa_tooltip
            # Extraer texto limpio eliminando etiquetas HTML
            _clicked_raw = _re.sub(r'<[^>]+>', ' ', _mapa_tooltip)
            _clicked_raw = _re.sub(r'\s+', ' ', _clicked_raw).strip()
            if _clicked_raw:
                _upper_map = {n.upper(): n for n in muni_opts}
                _matched   = _upper_map.get(_clicked_raw.upper())
                if _matched and _matched not in (st.session_state.get("cand_munis") or []):
                    st.session_state["_cand_pending_muni"] = _matched
                    st.rerun()
    st.caption(
        "Municipios coloreados por partido ganador. "
        "Haz clic en un municipio para seleccionarlo."
    )

with col_tabla:
    if not sel_munis:
        st.info(
            "Selecciona uno o mas municipios en el panel lateral "
            "para ver las candidaturas y sus candidatos."
        )
        t05_prov = mun_meta_base[
            (mun_meta_base["anio"] == anio_sel) &
            (mun_meta_base["mes"]  == mes_sel) &
            (mun_meta_base["provincia_cod"] == sel_prov)
        ].sort_values("censo_ine", ascending=False).head(5)
        if not t05_prov.empty:
            st.caption(f"Los 5 municipios mas poblados de {sel_prov}:")
            for _, r in t05_prov.iterrows():
                n_esc  = int(r["num_escanos"]) if pd.notna(r["num_escanos"]) else 0
                censo  = int(r["censo_ine"])   if pd.notna(r["censo_ine"])   else 0
                st.caption(
                    f"- {r['nombre_municipio']}  |  {censo:,} hab.  |  {n_esc} concejales"
                )
    else:
        if len(sel_munis) > 1:
            tabs = st.tabs([f"{m}" for m in sel_munis])
            iter_munis = list(zip(tabs, sel_munis))
        else:
            iter_munis = [(st.container(), sel_munis[0])]

        for contenedor, muni_name in iter_munis:
            with contenedor:
                _show_candidaturas(
                    muni_name=muni_name,
                    munis_df=munis_df,
                    anio_sel=anio_sel,
                    mes_sel=mes_sel,
                    sel_conv=sel_conv,
                    sel_prov=sel_prov,
                    df_all=df_all,
                    t03_base=t03_base,
                    mun_meta_base=mun_meta_base,
                    t04_all=t04_all,
                    t11_base=t11_all,
                    t12_base=t12_all,
                    solo=(len(sel_munis) == 1),
                )
