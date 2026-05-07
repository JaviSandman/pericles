"""
Candidaturas al Congreso de los Diputados — listas electorales por provincia y convocatoria.

Fuentes:
  tipo_06 → votos y diputados por candidatura/municipio (agregados a provincia)
  tipo_05 → datos de participación por municipio (agregados a provincia)
  tipo_03 → siglas y denominación de la candidatura
  tipo_04 → candidatos individuales (municipio_cod="999", provincia_cod = código INE 2 dig.)

Nota: tipo_04 usa provincia_cod como código INE de 2 dígitos (ej. "28").
      tipo_06 / tipo_05 usan el nombre de la provincia (ej. "Madrid").
      Se resuelve con el dict PROVINCIAS: código → nombre.
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

TIPO       = "Congreso"
ESCANOS_LBL = "Diputados"

st.set_page_config(
    page_title="Candidaturas Congreso",
    page_icon="🏛️",
    layout="wide",
)


# ─── Mapa invertido: nombre → código INE ─────────────────────────────────────
_PROV_NOMBRE_A_COD_INE: dict[str, str] = {v: k for k, v in PROVINCIAS.items()}


# =============================================================================
#  CARGA DE DATOS
# =============================================================================

@st.cache_resource(show_spinner="Cargando datos del Congreso…")
def _load_base():
    """tipo_06 + tipo_05 + tipo_03, filtrados para TIPO y vuelta 1."""
    # ── tipo_06: votos por municipio ─────────────────────────────────────────
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

    # Agregación por provincia (necesaria para el mapa nacional y la vista de provincia)
    t06_prov = (
        t06.groupby(["anio", "mes", "conv", "provincia_cod", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"),
             candidatos_obtenidos=("candidatos_obtenidos", "sum"))
    )

    # ── tipo_05: totales por municipio → agregarlos a provincia ──────────────
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
    # num_escanos por provincia = valor fijo por fila de municipio con datos → max/sum?
    # Para Congreso, num_escanos en tipo_05 es el nº de diputados de la provincia
    t05_prov = (
        t05.groupby(["anio", "mes", "provincia_cod"], as_index=False)
        .agg(
            censo_ine=("censo_ine", "sum"),
            votos_candidaturas=("votos_candidaturas", "sum"),
            num_escanos=("num_escanos", "max"),   # todos los municipios de la prov tienen el mismo valor
        )
    )

    # ── tipo_03: siglas y denominación de candidaturas ───────────────────────
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
        columns=["tipo_eleccion_cod", "anio", "mes", "vuelta", "provincia_cod", "cod_candidatura", "elegido"],
    )
    t04_seats = t04_seats[
        (t04_seats["tipo_eleccion_cod"] == TIPO) & (t04_seats["vuelta"] == "1")
    ].copy()
    t04_seats["anio"] = t04_seats["anio"].astype(int)
    t04_seats["mes"]  = t04_seats["mes"].astype(int)
    # provincia_cod en tipo_04 = código INE → convertir a nombre para hacer join
    t04_seats["provincia_nombre"] = t04_seats["provincia_cod"].map(PROVINCIAS)
    escanos_prov = (
        t04_seats.groupby(["anio", "mes", "provincia_nombre", "cod_candidatura"])
        .apply(lambda x: (x["elegido"] == "S").sum(), include_groups=False)
        .reset_index(name="escanos_reales")
    )

    # Enriquecer t06_prov con partido
    df_votos = t06_prov.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"],
        how="left",
    )
    df_votos["partido"] = df_votos["partido"].fillna(df_votos["cod_candidatura"].astype(str))
    df_votos["partido"] = df_votos["partido"].map(normalize_partido)
    df_votos["ccaa_nombre"] = df_votos["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    # Añadir escaños reales
    df_votos = df_votos.merge(
        escanos_prov,
        left_on=["anio", "mes", "provincia_cod", "cod_candidatura"],
        right_on=["anio", "mes", "provincia_nombre", "cod_candidatura"],
        how="left",
    ).drop(columns=["provincia_nombre"], errors="ignore")
    df_votos["escanos_reales"] = df_votos["escanos_reales"].fillna(0).astype(int)
    df_votos["candidatos_obtenidos"] = df_votos["escanos_reales"]

    # También necesitamos t06 original (por municipio) para el mapa
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

    return df_votos, t06_muni_enrich, t03, t05_prov


@st.cache_resource(show_spinner="Cargando candidatos…")
def _load_candidatos():
    """tipo_04 para Congreso, vuelta 1, solo titulares."""
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
    # provincia_cod en tipo_04 = código INE 2 dígitos → nombre
    t04["provincia_nombre"] = t04["provincia_cod"].map(PROVINCIAS)
    t04["nombre_completo"] = (
        t04["nombre"].fillna("") + " " +
        t04["primer_apellido"].fillna("") + " " +
        t04["segundo_apellido"].fillna("")
    ).str.strip()
    t04 = t04.drop_duplicates(
        subset=["anio", "mes", "provincia_cod", "cod_candidatura", "orden"],
        keep="first",
    )
    return t04


# =============================================================================
#  RENDERIZADO DE UNA PROVINCIA
# =============================================================================

def _show_provincia(
    prov_nombre: str,
    anio_sel: int,
    mes_sel: int,
    sel_conv: str,
    df_prov_conv: pd.DataFrame,
    t03_base: pd.DataFrame,
    t05_prov: pd.DataFrame,
    t04_all: pd.DataFrame,
    solo: bool = False,
) -> None:
    """Muestra resumen de candidaturas + listas de candidatos para una provincia."""

    # Totales de la provincia
    t05_row = t05_prov[
        (t05_prov["anio"] == anio_sel) &
        (t05_prov["mes"]  == mes_sel) &
        (t05_prov["provincia_cod"] == prov_nombre)
    ]
    # Escaños: sumar candidatos_obtenidos (= escanos_reales desde tipo_04)
    # t05_prov["num_escanos"] no es fiable para Congreso (contiene 0 en algunos registros)
    num_escanos = int(
        df_prov_conv.loc[df_prov_conv["provincia_cod"] == prov_nombre, "candidatos_obtenidos"].sum()
    )
    censo       = int(t05_row["censo_ine"].iloc[0])   if not t05_row.empty else 0
    votos_tot   = int(t05_row["votos_candidaturas"].iloc[0]) if not t05_row.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric(ESCANOS_LBL, num_escanos)
    c2.metric("Censo electoral", f"{censo:,}")
    c3.metric("Votos a candidaturas", f"{votos_tot:,}")

    st.divider()

    # Votos por candidatura en la provincia
    df_p = df_prov_conv[df_prov_conv["provincia_cod"] == prov_nombre].copy()
    if df_p.empty:
        st.warning("Sin resultados para esta provincia y convocatoria.")
        return

    df_p["pct_votos"] = (
        df_p["votos_obtenidos"] / votos_tot * 100
    ).round(1) if votos_tot > 0 else 0.0

    t03_conv = t03_base[
        (t03_base["anio"] == anio_sel) & (t03_base["mes"] == mes_sel)
    ][["cod_candidatura", "siglas", "denominacion"]]
    df_p = df_p.merge(t03_conv, on="cod_candidatura", how="left")
    df_p["siglas"]       = df_p["siglas"].fillna(df_p["partido"])
    df_p["denominacion"] = df_p["denominacion"].fillna(df_p["siglas"])
    df_p = df_p.sort_values("votos_obtenidos", ascending=False)

    st.subheader("Resultados por candidatura")
    resumen = (
        df_p[["siglas", "denominacion", "votos_obtenidos", "pct_votos", "candidatos_obtenidos"]]
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
            "Votos":        st.column_config.NumberColumn(format="%,d"),
            "% Votos":      st.column_config.NumberColumn(format="%.1f%%"),
            ESCANOS_LBL:    st.column_config.NumberColumn(format="%d"),
        },
    )
    csv_res = resumen.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar resultados (CSV)", data=csv_res,
        file_name=f"candidaturas_{prov_nombre}_{sel_conv.replace('/','_')}.csv",
        mime="text/csv", key=f"dl_res_{prov_nombre}_{anio_sel}",
    )

    st.divider()
    st.subheader("Listas de candidatos")

    # tipo_04 filtrado: provincia_nombre ya viene mapeada desde PROVINCIAS
    t04_prov = t04_all[
        (t04_all["anio"] == anio_sel) &
        (t04_all["mes"]  == mes_sel) &
        (t04_all["provincia_nombre"] == prov_nombre)
    ].copy()

    if t04_prov.empty:
        st.info("Sin datos de candidatos individuales para esta convocatoria. (tipo_04 disponible desde 1987)")
        return

    st.caption(
        f"{len(t04_prov):,} candidatos en {t04_prov['cod_candidatura'].nunique()} candidaturas. "
        "Los marcados con S fueron elegidos diputados."
    )

    for _, cand_row in df_p.iterrows():
        cod_c   = cand_row["cod_candidatura"]
        sig_c   = str(cand_row.get("siglas") or cand_row.get("partido") or cod_c)
        den_c   = str(cand_row.get("denominacion") or sig_c)[:70]
        vot_c   = int(cand_row.get("votos_obtenidos") or 0)
        esc_c   = int(cand_row.get("candidatos_obtenidos") or 0)
        pct_c   = float(cand_row.get("pct_votos") or 0)

        lista = t04_prov[t04_prov["cod_candidatura"] == cod_c].sort_values("orden")
        if lista.empty:
            continue

        esc_str = f"  |  {esc_c} elegido(s)" if esc_c > 0 else ""
        label   = f"{sig_c}  -  {vot_c:,} votos ({pct_c:.1f}%){esc_str}"

        with st.expander(label, expanded=(solo and df_p["cod_candidatura"].nunique() <= 3)):
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
                file_name=f"lista_{prov_nombre}_{sig_c}_{sel_conv.replace('/','_')}.csv",
                mime="text/csv", key=f"dl_l_{prov_nombre}_{cod_c}_{anio_sel}",
            )


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

df_prov, df_muni, t03_base, t05_prov = _load_base()
t04_all = _load_candidatos()

convs_ord = sorted(df_prov["conv"].unique())

# Procesar click pendiente del mapa (provincia) antes de renderizar sidebar
if st.session_state.get("_cong_pending_prov"):
    _pending = st.session_state.pop("_cong_pending_prov")
    _cur = list(st.session_state.get("cong_provs") or [])
    if _pending not in _cur:
        st.session_state["cong_provs"] = _cur + [_pending]

st.title("🏛️ Candidaturas al Congreso de los Diputados")
st.caption("Listas electorales, candidatos y resultados por provincia · 1979-2023 · Fuente: Ministerio del Interior")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    sel_conv = st.selectbox(
        "Convocatoria", convs_ord, index=len(convs_ord) - 1, key="cong_conv",
    )
    anio_sel = int(sel_conv[:4])
    mes_sel  = int(sel_conv[5:])

    # Provincias disponibles para esta convocatoria
    provs_conv = sorted(
        df_prov[
            (df_prov["anio"] == anio_sel) & (df_prov["mes"] == mes_sel)
        ]["provincia_cod"].dropna().unique()
    )

    sel_provs = st.multiselect(
        "Provincias", provs_conv,
        placeholder="Selecciona una o más...",
        key="cong_provs",
    )

    st.divider()
    if sel_provs:
        st.success(f"{len(sel_provs)} provincia(s) seleccionada(s)")
    else:
        st.info("Selecciona provincias en el mapa o en la lista.")
        st.caption(f"{len(provs_conv)} provincias disponibles.")

# ── Layout: mapa izq. + tablas dcha. ─────────────────────────────────────────
df_conv_all = df_muni[
    (df_muni["anio"] == anio_sel) & (df_muni["mes"] == mes_sel)
].copy()

col_map, col_tabla = st.columns([42, 58])

with col_map:
    st.subheader(f"España · {sel_conv}")
    if df_conv_all.empty:
        st.warning("Sin datos electorales para la convocatoria seleccionada.")
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
            key="cong_mapa_nac",
            height=500,
        )
        # Procesar click: mapa devuelve nombre de provincia
        _last_popup = st.session_state.get("_cong_last_popup")
        if _tooltip and _tooltip != _last_popup:
            st.session_state["_cong_last_popup"] = _tooltip
            _clicked_raw = _re.sub(r'<[^>]+>', ' ', _tooltip)
            _clicked_raw = _re.sub(r'\s+', ' ', _clicked_raw).strip()
            if _clicked_raw:
                _upper_map = {n.upper(): n for n in provs_conv}
                _matched   = _upper_map.get(_clicked_raw.upper())
                if _matched and _matched not in (st.session_state.get("cong_provs") or []):
                    st.session_state["_cong_pending_prov"] = _matched
                    st.rerun()
    st.caption("Provincias coloreadas por partido con más votos. Haz clic para seleccionar.")

# ── Panel derecho: candidaturas ───────────────────────────────────────────────
with col_tabla:
    df_prov_conv = df_prov[
        (df_prov["anio"] == anio_sel) & (df_prov["mes"] == mes_sel)
    ].copy()

    if not sel_provs:
        st.info("Selecciona una o más provincias en el mapa o en el panel lateral para ver las candidaturas.")
        # Resumen nacional
        if not df_prov_conv.empty:
            nac = (
                df_prov_conv.groupby("partido", as_index=False)
                .agg(votos=("votos_obtenidos", "sum"), escanos=("candidatos_obtenidos", "sum"))
                .sort_values("votos", ascending=False)
                .head(10)
            )
            st.caption(f"Resumen nacional {sel_conv} — top 10 partidos:")
            st.dataframe(
                nac.rename(columns={"partido": "Partido", "votos": "Votos", "escanos": ESCANOS_LBL}),
                use_container_width=True, hide_index=True,
                column_config={"Votos": st.column_config.NumberColumn(format="%,d")},
            )
    else:
        if len(sel_provs) > 1:
            tabs = st.tabs([f"{p}" for p in sel_provs])
            iter_provs = list(zip(tabs, sel_provs))
        else:
            iter_provs = [(st.container(), sel_provs[0])]

        for contenedor, prov_nombre in iter_provs:
            with contenedor:
                _show_provincia(
                    prov_nombre=prov_nombre,
                    anio_sel=anio_sel,
                    mes_sel=mes_sel,
                    sel_conv=sel_conv,
                    df_prov_conv=df_prov_conv,
                    t03_base=t03_base,
                    t05_prov=t05_prov,
                    t04_all=t04_all,
                    solo=(len(sel_provs) == 1),
                )
