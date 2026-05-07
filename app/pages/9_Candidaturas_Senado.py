"""
Candidaturas al Senado — listas electorales por provincia y convocatoria.

Fuentes:
  tipo_06 → votos y senadores por candidatura/municipio (agregados a provincia)
  tipo_05 → datos de participación por municipio (agregados a provincia)
  tipo_03 → siglas y denominación de la candidatura
  tipo_04 → candidatos individuales (municipio_cod="999", provincia_cod = código INE 2 dig.)

El Senado usa un sistema de **voto limitado** (cada elector vota a 3 de 4 candidatos).
Los candidatos compiten a título individual, aunque se presentan bajo candidaturas de partido.

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

TIPO        = "Senado"
ESCANOS_LBL = "Senadores"

st.set_page_config(
    page_title="Candidaturas Senado",
    page_icon="⚖️",
    layout="wide",
)


# =============================================================================
#  CARGA DE DATOS
# =============================================================================

@st.cache_resource(show_spinner="Cargando datos del Senado…")
def _load_base():
    """tipo_06 + tipo_05 + tipo_03, filtrados para TIPO y vuelta 1.

    NOTA: en el Senado tipo_06 almacena votos por CANDIDATO INDIVIDUAL, no por
    partido. El cod_candidatura de tipo_06 es un código provincial secuencial
    (ej. '019001' = candidato nº 1 en Álava). Para asignar partido, construimos
    un índice desde tipo_04: dentro de cada (anio, mes, provincia_cod), los
    candidatos titulares ordenados por (cod_candidatura, orden) reciben la
    posición 1..N, que coincide con los últimos 3 dígitos del cod de tipo_06.
    """
    # ── tipo_04: índice candidato-posición → cod_candidatura(partido) ────────
    # NOTA OFICIAL (doc Ministerio): en el Senado, el campo municipio_cod de
    # tipo_04 lleva EL ORDEN DEL CANDIDATO EN LA CIRCUNSCRIPCIÓN (no el código
    # del municipio). El código tipo_06 se forma como:
    #   prov_ine(2) + "9" + orden_en_circunscripcion(3)
    # Esto coincide EXACTAMENTE con municipio_cod de tipo_04.
    t04_idx = pd.read_parquet(
        str(DATA_DIR / "tipo_04.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "cod_candidatura",
            "orden", "tipo_candidato", "elegido",
        ],
    )
    t04_idx = t04_idx[
        (t04_idx["tipo_eleccion_cod"] == TIPO) &
        (t04_idx["vuelta"] == "1") &
        (t04_idx["tipo_candidato"] == "T")
    ].copy()
    t04_idx["anio"] = t04_idx["anio"].astype(int)
    t04_idx["mes"]  = t04_idx["mes"].astype(int)
    # municipio_cod = orden en la circunscripción → clave de enlace con tipo_06
    t04_idx["_t06_cod"] = (
        t04_idx["provincia_cod"].astype(str).str.zfill(2)
        + "9"
        + t04_idx["municipio_cod"].astype(str).str.zfill(3)
    )
    # Escaños por partido y provincia
    escanos_idx = (
        t04_idx.groupby(["anio", "mes", "provincia_cod", "cod_candidatura"])
        .apply(lambda x: (x["elegido"] == "S").sum(), include_groups=False)
        .reset_index(name="escanos_reales")
    )
    escanos_idx["provincia_nombre"] = escanos_idx["provincia_cod"].map(PROVINCIAS)

    # ── tipo_06: votos por candidato ─────────────────────────────────────────
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "cod_candidatura",
            "votos_obtenidos",
        ],
    )
    t06 = t06[
        (t06["tipo_eleccion_cod"] == TIPO) &
        (t06["vuelta"].astype(int) == 1)
    ].copy()
    t06["anio"] = t06["anio"].astype(int)
    t06["mes"]  = t06["mes"].astype(int)
    t06["conv"] = t06["anio"].astype(str) + "/" + t06["mes"].astype(str).str.zfill(2)

    # Enlazar cada fila de tipo_06 con el cod_candidatura (partido) de tipo_04
    t06 = t06.merge(
        t04_idx[["anio", "mes", "_t06_cod", "cod_candidatura"]].rename(
            columns={"cod_candidatura": "cod_candidatura_partido"}
        ),
        left_on=["anio", "mes", "cod_candidatura"],
        right_on=["anio", "mes", "_t06_cod"],
        how="left",
    )
    # Usar cod_candidatura_partido cuando existe, sino conservar el original
    t06["cod_candidatura"] = t06["cod_candidatura_partido"].fillna(t06["cod_candidatura"])
    t06 = t06.drop(columns=["cod_candidatura_partido", "_t06_cod"], errors="ignore")

    # ── Corrección voto múltiple Senado ──────────────────────────────────────
    # tipo_06 tiene una fila por candidato individual. Tras mapear a partido,
    # un mismo partido puede tener N filas por municipio (una por candidato).
    # Usar SUM inflaría los votos N veces (PP: 4 candidatos → ×4).
    # Usamos MAX por (municipio, partido) = votos del candidato más votado del
    # partido en ese municipio, que es la mejor aproximación al "voto al partido".
    t06_muni = (
        t06.groupby(["anio", "mes", "conv", "provincia_cod", "municipio_cod", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "max"))
    )

    # Agregar por provincia+partido (SUM sobre municipios ya normalizados)
    t06_prov = (
        t06_muni.groupby(["anio", "mes", "conv", "provincia_cod", "cod_candidatura"], as_index=False)
        .agg(votos_obtenidos=("votos_obtenidos", "sum"))
    )

    # ── tipo_05: totales de participación ────────────────────────────────────
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
    t05_prov = (
        t05.groupby(["anio", "mes", "provincia_cod"], as_index=False)
        .agg(
            censo_ine=("censo_ine", "sum"),
            votos_candidaturas=("votos_candidaturas", "sum"),
            num_escanos=("num_escanos", "max"),
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

    # Enriquecer t06_prov con partido desde t03
    df_votos = t06_prov.merge(
        t03[["anio", "mes", "cod_candidatura", "partido"]],
        on=["anio", "mes", "cod_candidatura"], how="left",
    )
    df_votos["partido"] = df_votos["partido"].fillna(df_votos["cod_candidatura"].astype(str))
    df_votos["partido"] = df_votos["partido"].map(normalize_partido)
    df_votos["ccaa_nombre"] = df_votos["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Desconocida")
    # Añadir escaños reales desde tipo_04
    df_votos = df_votos.merge(
        escanos_idx[["anio", "mes", "provincia_nombre", "cod_candidatura", "escanos_reales"]],
        left_on=["anio", "mes", "provincia_cod", "cod_candidatura"],
        right_on=["anio", "mes", "provincia_nombre", "cod_candidatura"],
        how="left",
    ).drop(columns=["provincia_nombre"], errors="ignore")
    df_votos["escanos_reales"] = df_votos["escanos_reales"].fillna(0).astype(int)
    df_votos["candidatos_obtenidos"] = df_votos["escanos_reales"]

    # t06 enriquecido para el mapa (municipio-nivel)
    # Usar t06_muni (ya normalizado a MAX por municipio+partido) en lugar de t06 raw
    t06_muni_enrich = t06_muni.merge(
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
    """tipo_04 para Senado, vuelta 1, solo titulares."""
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
    t05_row = t05_prov[
        (t05_prov["anio"] == anio_sel) &
        (t05_prov["mes"]  == mes_sel) &
        (t05_prov["provincia_cod"] == prov_nombre)
    ]
    # num_escanos desde tipo_04 (elegido=='S'), no t05 (siempre 0 en Senado)
    num_escanos = int(
        df_prov_conv.loc[df_prov_conv["provincia_cod"] == prov_nombre, "candidatos_obtenidos"].sum()
    )
    censo       = int(t05_row["censo_ine"].iloc[0])   if not t05_row.empty else 0
    votos_tot   = int(t05_row["votos_candidaturas"].iloc[0]) if not t05_row.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric(ESCANOS_LBL, num_escanos)
    c2.metric("Censo electoral", f"{censo:,}")
    c3.metric("Votos a candidaturas", f"{votos_tot:,}")
    st.caption("ℹ️ En el Senado cada elector vota hasta 3 candidatos de 4 (voto limitado). El recuento aquí es por candidatura.")

    st.divider()

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
            "Votos":     st.column_config.NumberColumn(format="%,d"),
            "% Votos":   st.column_config.NumberColumn(format="%.1f%%"),
            ESCANOS_LBL: st.column_config.NumberColumn(format="%d"),
        },
    )
    csv_res = resumen.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar resultados (CSV)", data=csv_res,
        file_name=f"senado_{prov_nombre}_{sel_conv.replace('/','_')}.csv",
        mime="text/csv", key=f"dl_res_{prov_nombre}_{anio_sel}",
    )

    st.divider()
    st.subheader("Candidatos")

    t04_prov = t04_all[
        (t04_all["anio"] == anio_sel) &
        (t04_all["mes"]  == mes_sel) &
        (t04_all["provincia_nombre"] == prov_nombre)
    ].copy()

    if t04_prov.empty:
        st.info("Sin datos de candidatos individuales para esta convocatoria. (tipo_04 disponible desde 1987)")
        return

    st.caption(
        f"{len(t04_prov):,} candidatos en {t04_prov['cod_candidatura'].nunique()} candidaturas."
    )

    for _, cand_row in df_p.iterrows():
        cod_c = cand_row["cod_candidatura"]
        sig_c = str(cand_row.get("siglas") or cand_row.get("partido") or cod_c)
        den_c = str(cand_row.get("denominacion") or sig_c)[:70]
        vot_c = int(cand_row.get("votos_obtenidos") or 0)
        esc_c = int(cand_row.get("candidatos_obtenidos") or 0)
        pct_c = float(cand_row.get("pct_votos") or 0)

        lista = t04_prov[t04_prov["cod_candidatura"] == cod_c].sort_values("orden")
        if lista.empty:
            continue

        esc_str = f"  |  {esc_c} elegido(s)" if esc_c > 0 else ""
        label   = f"{sig_c}  -  {vot_c:,} votos ({pct_c:.1f}%){esc_str}"

        with st.expander(label, expanded=(solo and df_p["cod_candidatura"].nunique() <= 4)):
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
                f"Descargar {sig_c} (CSV)", data=csv_l,
                file_name=f"senado_{prov_nombre}_{sig_c}_{sel_conv.replace('/','_')}.csv",
                mime="text/csv", key=f"dl_l_{prov_nombre}_{cod_c}_{anio_sel}",
            )


# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================

df_prov, df_muni, t03_base, t05_prov = _load_base()
t04_all = _load_candidatos()

convs_ord = sorted(df_prov["conv"].unique())

if st.session_state.get("_sen_pending_prov"):
    _pending = st.session_state.pop("_sen_pending_prov")
    _cur = list(st.session_state.get("sen_provs") or [])
    if _pending not in _cur:
        st.session_state["sen_provs"] = _cur + [_pending]

st.title("⚖️ Candidaturas al Senado")
st.caption("Listas electorales, candidatos y resultados por provincia · 1979-2023 · Fuente: Ministerio del Interior")

with st.sidebar:
    st.header("Filtros")
    sel_conv = st.selectbox(
        "Convocatoria", convs_ord, index=len(convs_ord) - 1, key="sen_conv",
    )
    anio_sel = int(sel_conv[:4])
    mes_sel  = int(sel_conv[5:])

    provs_conv = sorted(
        df_prov[
            (df_prov["anio"] == anio_sel) & (df_prov["mes"] == mes_sel)
        ]["provincia_cod"].dropna().unique()
    )
    sel_provs = st.multiselect(
        "Provincias", provs_conv,
        placeholder="Selecciona una o más...",
        key="sen_provs",
    )
    st.divider()
    if sel_provs:
        st.success(f"{len(sel_provs)} provincia(s) seleccionada(s)")
    else:
        st.info("Selecciona provincias en el mapa o en la lista.")

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
            key="sen_mapa_nac",
            height=500,
        )
        _last_popup = st.session_state.get("_sen_last_popup")
        if _tooltip and _tooltip != _last_popup:
            st.session_state["_sen_last_popup"] = _tooltip
            _clicked_raw = _re.sub(r'<[^>]+>', ' ', _tooltip)
            _clicked_raw = _re.sub(r'\s+', ' ', _clicked_raw).strip()
            if _clicked_raw:
                _upper_map = {n.upper(): n for n in provs_conv}
                _matched   = _upper_map.get(_clicked_raw.upper())
                if _matched and _matched not in (st.session_state.get("sen_provs") or []):
                    st.session_state["_sen_pending_prov"] = _matched
                    st.rerun()
    st.caption("Provincias coloreadas por partido con más votos. Haz clic para seleccionar.")

with col_tabla:
    df_prov_conv = df_prov[
        (df_prov["anio"] == anio_sel) & (df_prov["mes"] == mes_sel)
    ].copy()

    if not sel_provs:
        st.info("Selecciona una o más provincias en el mapa o en el panel lateral para ver las candidaturas.")
        if not df_prov_conv.empty:
            nac = (
                df_prov_conv.groupby("partido", as_index=False)
                .agg(votos=("votos_obtenidos", "sum"), senadores=("candidatos_obtenidos", "sum"))
                .sort_values("votos", ascending=False)
                .head(10)
            )
            st.caption(f"Resumen nacional {sel_conv} — top 10 partidos:")
            st.dataframe(
                nac.rename(columns={"partido": "Partido", "votos": "Votos", "senadores": ESCANOS_LBL}),
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
