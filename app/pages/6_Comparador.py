"""
Comparador electoral
====================
Dos paneles independientes (A y B) con selectores propios de tipo, convocatoria
y territorio + sección de comparación directa con gráfico Δ y descarga CSV.
Pestaña adicional de evolución temporal con gráfico lineal y tabla pivotada.
"""
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import DATA_DIR, PROV_NOMBRE_A_CCAA, PARTY_COLORS
from _mesa_view import (
    render_mesa_sidebar, get_t10_conv, add_partido_label, ms_scope_label,
    render_election_map, render_mesa_map, PROV_NOMBRE_A_COD,
)

st.set_page_config(page_title="Comparador", page_icon="⚖️", layout="wide")
st.title("⚖️ Comparador electoral")
st.caption(
    "Compara resultados entre convocatorias, tipos de elección y territorios · "
    "Fuente: Ministerio del Interior"
)

# ── Carga única de datos ───────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando datos del comparador…")
def _load() -> pd.DataFrame:
    # Votos por candidatura (primera vuelta)
    t06 = pd.read_parquet(
        str(DATA_DIR / "tipo_06.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "distrito_num",
            "cod_candidatura", "votos_obtenidos",
        ],
    )
    t06 = t06[t06["vuelta"].astype(str).str.split(".").str[0] == "1"].copy()
    t06["anio"] = t06["anio"].astype(str).str.split(".").str[0]
    t06["mes"]  = t06["mes"].astype(str).str.split(".").str[0].str.zfill(2)
    t06["votos_obtenidos"] = pd.to_numeric(t06["votos_obtenidos"], errors="coerce").fillna(0)
    t06["conv"] = t06["anio"] + "/" + t06["mes"]

    # Partidos
    t03 = pd.read_parquet(
        str(DATA_DIR / "tipo_03.parquet"),
        columns=["tipo_eleccion_cod", "anio", "mes", "cod_candidatura", "siglas", "denominacion"],
    )
    t03["anio"] = t03["anio"].astype(str).str.split(".").str[0]
    t03["mes"]  = t03["mes"].astype(str).str.split(".").str[0].str.zfill(2)
    t03["partido"] = t03["siglas"].where(
        t03["siglas"].notna() & (t03["siglas"].astype(str).str.strip() != ""),
        t03["denominacion"].astype(str).str[:28],
    )
    t03 = t03.drop_duplicates(subset=["tipo_eleccion_cod", "anio", "mes", "cod_candidatura"])

    df = t06.merge(
        t03[["tipo_eleccion_cod", "anio", "mes", "cod_candidatura", "partido"]],
        on=["tipo_eleccion_cod", "anio", "mes", "cod_candidatura"],
        how="left",
    )
    df["partido"] = df["partido"].fillna(df["cod_candidatura"].astype(str))

    # Nombres de municipio desde tipo_05
    t05 = pd.read_parquet(
        str(DATA_DIR / "tipo_05.parquet"),
        columns=[
            "tipo_eleccion_cod", "anio", "mes", "vuelta",
            "provincia_cod", "municipio_cod", "nombre_municipio",
        ],
    )
    t05 = t05[t05["vuelta"].astype(str).str.split(".").str[0] == "1"].copy()
    t05["anio"] = t05["anio"].astype(str).str.split(".").str[0]
    t05["mes"]  = t05["mes"].astype(str).str.split(".").str[0].str.zfill(2)
    muni_names = t05.drop_duplicates(
        subset=["tipo_eleccion_cod", "anio", "mes", "provincia_cod", "municipio_cod"]
    )[["tipo_eleccion_cod", "anio", "mes", "provincia_cod", "municipio_cod", "nombre_municipio"]]

    df = df.merge(
        muni_names,
        on=["tipo_eleccion_cod", "anio", "mes", "provincia_cod", "municipio_cod"],
        how="left",
    )
    df["nombre_municipio"] = df["nombre_municipio"].fillna(df["municipio_cod"])
    df["ccaa"] = df["provincia_cod"].map(PROV_NOMBRE_A_CCAA).fillna("Otras")
    return df


df_all = _load()
TIPOS = sorted(df_all["tipo_eleccion_cod"].unique())


# ── Funciones auxiliares ───────────────────────────────────────────────────────
def _convs(tipo: str) -> list[str]:
    return sorted(df_all[df_all["tipo_eleccion_cod"] == tipo]["conv"].unique())


def _provincias(tipo: str, conv: str) -> list[str]:
    mask = (df_all["tipo_eleccion_cod"] == tipo) & (df_all["conv"] == conv)
    return sorted(df_all.loc[mask, "provincia_cod"].dropna().unique())


def _municipios(tipo: str, conv: str, prov: str) -> list[tuple[str, str]]:
    """Devuelve lista de (municipio_cod, nombre_municipio) ordenada por nombre."""
    mask = (
        (df_all["tipo_eleccion_cod"] == tipo)
        & (df_all["conv"] == conv)
        & (df_all["provincia_cod"] == prov)
    )
    pairs = (
        df_all.loc[mask, ["municipio_cod", "nombre_municipio"]]
        .drop_duplicates()
        .sort_values("nombre_municipio")
    )
    return list(zip(pairs["municipio_cod"], pairs["nombre_municipio"]))


def _aggregate(
    tipo: str, conv: str, nivel: str,
    prov, muni_cod,
    top_n: int, min_votos: int = 0,
    ms_state: dict | None = None,
) -> tuple:
    """Agrega votos por partido para un snapshot dado."""
    # ── Nivel Mesa: usar tipo_10 via render_mesa_sidebar state ───────────────
    if (
        nivel == "Municipio"
        and ms_state is not None
        and ms_state.get("active")
        and (ms_state.get("sel_distritos") or ms_state.get("sel_mesas"))
    ):
        df_t10 = get_t10_conv(ms_state)
        if df_t10.empty:
            return pd.DataFrame(columns=["partido", "votos", "pct"]), 0
        df_t10 = add_partido_label(df_t10, tipo)
        agg = df_t10.groupby("partido", as_index=False)["votos_obtenidos"].sum()
        total = int(agg["votos_obtenidos"].sum())
        agg["pct"] = (agg["votos_obtenidos"] / total * 100).round(2) if total > 0 else 0.0
        agg = agg.rename(columns={"votos_obtenidos": "votos"})
        agg = agg.nlargest(top_n, "votos").reset_index(drop=True)
        return agg, total

    # ── Niveles estándar (Nacional / Provincia / Municipio) ──────────────────
    mask = (df_all["tipo_eleccion_cod"] == tipo) & (df_all["conv"] == conv)
    sub = df_all.loc[mask]
    if nivel == "Provincia" and prov:
        sub = sub[sub["provincia_cod"] == prov]
    elif nivel == "Municipio" and prov and muni_cod:
        sub = sub[(sub["provincia_cod"] == prov) & (sub["municipio_cod"] == muni_cod)]
    agg = sub.groupby("partido", as_index=False)["votos_obtenidos"].sum()
    if min_votos > 0:
        agg = agg[agg["votos_obtenidos"] >= min_votos]
    total = int(agg["votos_obtenidos"].sum())
    agg["pct"] = (agg["votos_obtenidos"] / total * 100).round(2) if total > 0 else 0.0
    agg = agg.rename(columns={"votos_obtenidos": "votos"})
    agg = agg.nlargest(top_n, "votos").reset_index(drop=True)
    return agg, total


def _color_map(partidos: list) -> dict:
    palette = px.colors.qualitative.Plotly + px.colors.qualitative.D3
    result = {}
    idx = 0
    for p in partidos:
        result[p] = PARTY_COLORS.get(p) or palette[idx % len(palette)]
        if p not in PARTY_COLORS:
            idx += 1
    return result


def _render_slot_selectors(prefix: str, col) -> tuple:
    """
    Renderiza los selectores de un slot dentro de col.
    Devuelve (tipo, conv, nivel, prov, muni_cod, muni_nombre, ms_state).
    ms_state es el dict de render_mesa_sidebar (None si nivel != Municipio).
    """
    with col:
        tipo = st.selectbox("Tipo de elección", TIPOS, key=f"{prefix}_tipo")
        convs = _convs(tipo)
        if not convs:
            st.warning("Sin convocatorias disponibles.")
            return tipo, "", "Nacional", None, None, None, None
        conv = st.selectbox(
            "Convocatoria", convs,
            index=len(convs) - 1,
            key=f"{prefix}_conv",
        )
        nivel = st.radio(
            "Ámbito", ["Nacional", "Provincia", "Municipio"],
            horizontal=True, key=f"{prefix}_nivel",
        )
        prov = muni_cod = muni_nombre = None
        if nivel in ("Provincia", "Municipio"):
            provs = _provincias(tipo, conv)
            if provs:
                prov = st.selectbox("Provincia", provs, key=f"{prefix}_prov")
        ms_state = None
        if nivel == "Municipio" and prov:
            munis = _municipios(tipo, conv, prov)
            if munis:
                labels = [f"{nom} [{cod}]" for cod, nom in munis]
                sel = st.selectbox("Municipio", labels, key=f"{prefix}_muni")
                muni_cod    = sel.split("[")[-1].rstrip("]")
                muni_nombre = sel.rsplit(" [", 1)[0]
                if muni_cod and muni_nombre:
                    anio_i, mes_i = int(conv[:4]), int(conv[5:])
                    ms_state = render_mesa_sidebar(
                        tipo=tipo, anio=anio_i, mes=mes_i, vuelta=1,
                        prov_nombre=prov,
                        muni_cod=muni_cod,
                        muni_name=muni_nombre,
                        key_prefix=prefix,
                        container=col,
                        show_map_toggle=True,
                    )
        return tipo, conv, nivel, prov, muni_cod, muni_nombre, ms_state


def _slot_label(tipo: str, conv: str, nivel: str, prov, muni_cod, ms_state=None) -> str:
    parts = [tipo, conv]
    if nivel == "Provincia" and prov:
        parts.append(prov)
    elif nivel == "Municipio" and prov:
        parts.append(prov)
        if muni_cod:
            parts.append(muni_cod)
        if ms_state and ms_state.get("active") and (
            ms_state.get("sel_distritos") or ms_state.get("sel_mesas")
        ):
            parts.append(ms_scope_label(ms_state))
    return " · ".join(parts)


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False, decimal=",", sep=";", encoding="utf-8-sig")
    return buf.getvalue()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Opciones")
    top_n     = st.slider("Top N partidos", 5, 25, 12)
    min_votos = st.number_input(
        "Votos mínimos por partido", 0, 100_000, 0, step=500,
        help="Filtra partidos con pocos votos (útil en ámbito nacional)"
    )
    st.divider()
    st.info("Los paneles A y B son completamente independientes entre sí.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS DE MAPA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _render_map_slot(
    label: str,
    col,
    tipo: str, conv: str, nivel: str,
    prov: "str | None",
    ms_state: "dict | None",
    map_key: str,
    height: int = 500,
) -> None:
    """Renderiza un mapa choropleth electoral en col para un panel del comparador."""
    with col:
        st.markdown(f"#### {label}")
        if not tipo or not conv:
            st.info("📊 Configura el panel en la pestaña **Comparación A ↔ B**.")
            return
        # Filtrar por tipo_eleccion_cod antes de pasar: render_election_map solo filtra por anio+mes
        df_v = df_all[df_all["tipo_eleccion_cod"] == tipo]
        sel_prov_list = [prov] if (nivel in ("Provincia", "Municipio") and prov) else None
        _ms = ms_state if (ms_state and ms_state.get("active")) else None
        render_election_map(
            nivel=nivel,
            df_votos=df_v,
            color_fn=_color_map,
            sel_conv=conv,
            sel_prov=sel_prov_list,
            prov_nombre_a_cod=PROV_NOMBRE_A_COD,
            mesa_state=_ms,
            key=map_key,
            height=height,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
tab_comp, tab_evo, tab_mapa = st.tabs([
    "⚖️  Comparación A ↔ B",
    "📈  Evolución temporal",
    "🗺️  Mapas A ↔ B",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — COMPARACIÓN DIRECTA
# ─────────────────────────────────────────────────────────────────────────────
with tab_comp:
    col_a, col_b = st.columns(2)

    tipo_a, conv_a, nivel_a, prov_a, muni_a, muni_nombre_a, ms_a = _render_slot_selectors("a", col_a)
    tipo_b, conv_b, nivel_b, prov_b, muni_b, muni_nombre_b, ms_b = _render_slot_selectors("b", col_b)

    lbl_a = _slot_label(tipo_a, conv_a, nivel_a, prov_a, muni_a, ms_a)
    lbl_b = _slot_label(tipo_b, conv_b, nivel_b, prov_b, muni_b, ms_b)

    st.divider()

    df_a, total_a = _aggregate(tipo_a, conv_a, nivel_a, prov_a, muni_a, top_n, int(min_votos), ms_a)
    df_b, total_b = _aggregate(tipo_b, conv_b, nivel_b, prov_b, muni_b, top_n, int(min_votos), ms_b)

    if df_a.empty and df_b.empty:
        st.warning("Sin datos para ninguno de los dos paneles con los filtros actuales.")
    else:
        # Métricas de resumen
        m1, m2, m3 = st.columns(3)
        m1.metric("Votos totales — A", f"{total_a:,}")
        m2.metric("Votos totales — B", f"{total_b:,}")
        if total_a > 0:
            delta_tot = total_b - total_a
            m3.metric(
                "Δ votos (B − A)",
                f"{delta_tot:+,}",
                delta=f"{delta_tot / total_a * 100:+.1f}%",
            )

        # Tablas individuales lado a lado
        st.markdown("#### Resultados")
        ta, tb = st.columns(2)

        cfg_tabla = {
            "partido": st.column_config.TextColumn("Partido", width="medium"),
            "votos":   st.column_config.NumberColumn("Votos", format="%d"),
            "pct":     st.column_config.NumberColumn("%", format="%.2f %%"),
        }
        with ta:
            st.caption(f"**A** — {lbl_a}")
            st.dataframe(
                df_a[["partido", "votos", "pct"]],
                use_container_width=True, hide_index=True,
                column_config=cfg_tabla, height=380,
            )
        with tb:
            st.caption(f"**B** — {lbl_b}")
            st.dataframe(
                df_b[["partido", "votos", "pct"]],
                use_container_width=True, hide_index=True,
                column_config=cfg_tabla, height=380,
            )

        # Comparación y deltas
        st.markdown("#### Variaciones B − A")

        df_cmp = df_a.merge(df_b, on="partido", how="outer", suffixes=("_a", "_b"))
        df_cmp = df_cmp.fillna({"votos_a": 0, "pct_a": 0.0, "votos_b": 0, "pct_b": 0.0})
        df_cmp["delta_pct"]   = (df_cmp["pct_b"]  - df_cmp["pct_a"]).round(2)
        df_cmp["delta_votos"] = (df_cmp["votos_b"] - df_cmp["votos_a"]).astype(int)
        df_cmp["votos_a"]     = df_cmp["votos_a"].astype(int)
        df_cmp["votos_b"]     = df_cmp["votos_b"].astype(int)

        # Gráfico de barras horizontales — delta pp
        df_delta_plot = df_cmp.sort_values("delta_pct").copy()
        df_delta_plot["sentido"] = df_delta_plot["delta_pct"].apply(
            lambda x: "Sube ↑" if x > 0 else ("Baja ↓" if x < 0 else "Sin cambio")
        )
        fig_delta = px.bar(
            df_delta_plot,
            x="delta_pct", y="partido", orientation="h",
            color="sentido",
            color_discrete_map={"Sube ↑": "#2ca02c", "Baja ↓": "#d62728", "Sin cambio": "#aaa"},
            labels={"delta_pct": "Δ puntos porcentuales (B − A)", "partido": ""},
        )
        fig_delta.update_layout(
            height=max(280, len(df_cmp) * 24),
            showlegend=False,
            xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="#333"),
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig_delta, use_container_width=True)

        # Tabla completa de comparación
        with st.expander("📋 Tabla completa (todos los partidos)"):
            cfg_cmp = {
                "partido":     st.column_config.TextColumn("Partido"),
                "votos_a":     st.column_config.NumberColumn("Votos A", format="%d"),
                "pct_a":       st.column_config.NumberColumn("% A",     format="%.2f %%"),
                "votos_b":     st.column_config.NumberColumn("Votos B", format="%d"),
                "pct_b":       st.column_config.NumberColumn("% B",     format="%.2f %%"),
                "delta_pct":   st.column_config.NumberColumn("Δ pp",    format="%+.2f"),
                "delta_votos": st.column_config.NumberColumn("Δ votos", format="%+d"),
            }
            st.caption(f"A = {lbl_a}  ·  B = {lbl_b}")
            st.dataframe(
                df_cmp[["partido", "votos_a", "pct_a", "votos_b", "pct_b",
                         "delta_pct", "delta_votos"]].sort_values("pct_a", ascending=False),
                use_container_width=True, hide_index=True, column_config=cfg_cmp,
            )

        # Descarga CSV
        csv_out = df_cmp[["partido", "votos_a", "pct_a", "votos_b", "pct_b",
                           "delta_pct", "delta_votos"]].copy()
        csv_out.columns = ["partido", "votos_A", "pct_A", "votos_B", "pct_B",
                           "delta_pp", "delta_votos"]
        st.download_button(
            "⬇️  Descargar comparación CSV",
            data=_to_csv_bytes(csv_out),
            file_name=(
                f"comparacion"
                f"_{conv_a.replace('/', '-')}_{tipo_a[:6].replace(' ', '_')}"
                f"_{conv_b.replace('/', '-')}_{tipo_b[:6].replace(' ', '_')}"
                ".csv"
            ),
            mime="text/csv",
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — EVOLUCIÓN TEMPORAL
# ─────────────────────────────────────────────────────────────────────────────
with tab_evo:
    st.markdown(
        "Selecciona un **tipo de elección** y un **territorio** para ver cómo ha "
        "evolucionado el voto a lo largo de todas las convocatorias disponibles."
    )

    ec1, ec2, ec3 = st.columns([2, 2, 2])
    with ec1:
        evo_tipo = st.selectbox("Tipo de elección", TIPOS, key="evo_tipo")
    with ec2:
        evo_nivel = st.radio(
            "Ámbito", ["Nacional", "Provincia", "Municipio"],
            horizontal=True, key="evo_nivel",
        )

    evo_prov = evo_muni_cod = None

    if evo_nivel in ("Provincia", "Municipio"):
        evo_provs = sorted(
            df_all[df_all["tipo_eleccion_cod"] == evo_tipo]["provincia_cod"].dropna().unique()
        )
        with ec3:
            evo_prov = st.selectbox("Provincia", evo_provs, key="evo_prov")

    if evo_nivel == "Municipio" and evo_prov:
        evo_munis = (
            df_all[
                (df_all["tipo_eleccion_cod"] == evo_tipo)
                & (df_all["provincia_cod"] == evo_prov)
            ][["municipio_cod", "nombre_municipio"]]
            .drop_duplicates()
            .sort_values("nombre_municipio")
        )
        evo_labels = [
            f"{row['nombre_municipio']} [{row['municipio_cod']}]"
            for _, row in evo_munis.iterrows()
        ]
        evo_sel_label = st.selectbox("Municipio", evo_labels, key="evo_muni")
        if evo_sel_label:
            evo_muni_cod = evo_sel_label.split("[")[-1].rstrip("]")

    st.divider()

    # Filtrar datos
    mask_evo = df_all["tipo_eleccion_cod"] == evo_tipo
    df_evo_raw = df_all.loc[mask_evo]
    if evo_nivel == "Provincia" and evo_prov:
        df_evo_raw = df_evo_raw[df_evo_raw["provincia_cod"] == evo_prov]
    elif evo_nivel == "Municipio" and evo_prov and evo_muni_cod:
        df_evo_raw = df_evo_raw[
            (df_evo_raw["provincia_cod"] == evo_prov)
            & (df_evo_raw["municipio_cod"] == evo_muni_cod)
        ]

    if df_evo_raw.empty:
        st.warning("Sin datos para los filtros seleccionados.")
    else:
        # Agregar por conv + partido
        agg_evo = df_evo_raw.groupby(["conv", "partido"], as_index=False)["votos_obtenidos"].sum()
        totals_evo = agg_evo.groupby("conv")["votos_obtenidos"].sum().rename("total")
        agg_evo = agg_evo.merge(totals_evo, on="conv")
        agg_evo["pct"] = (agg_evo["votos_obtenidos"] / agg_evo["total"] * 100).round(2)
        agg_evo = agg_evo.rename(columns={"votos_obtenidos": "votos"})

        # Top N partidos por suma total de votos en todas las convocatorias
        top_partidos = (
            agg_evo.groupby("partido")["votos"].sum()
            .nlargest(top_n).index.tolist()
        )
        # Ordenar convocatorias cronológicamente ("YYYY/MM" → orden lexicográfico es correcto)
        conv_order = sorted(agg_evo["conv"].unique())
        agg_evo["conv"] = pd.Categorical(agg_evo["conv"], categories=conv_order, ordered=True)
        agg_top = agg_evo[agg_evo["partido"].isin(top_partidos)].sort_values("conv")

        # Título descriptivo del ámbito
        evo_scope = evo_tipo
        if evo_nivel == "Provincia" and evo_prov:
            evo_scope += f" · {evo_prov}"
        elif evo_nivel == "Municipio" and evo_prov and evo_muni_cod:
            evo_scope += f" · {evo_prov} · {evo_muni_cod}"

        cmap_evo = _color_map(top_partidos)

        # Gráfico de líneas
        fig_evo = px.line(
            agg_top,
            x="conv", y="pct", color="partido",
            markers=True,
            color_discrete_map=cmap_evo,
            labels={"conv": "Convocatoria", "pct": "% votos", "partido": "Partido"},
            title=f"Evolución del voto — {evo_scope}",
        )
        fig_evo.update_layout(
            height=480,
            legend=dict(orientation="h", yanchor="top", y=-0.22, font_size=11),
            margin=dict(b=130),
            xaxis_tickangle=-35,
        )
        fig_evo.update_traces(line_width=2.2, marker_size=7)
        st.plotly_chart(fig_evo, use_container_width=True)

        # Tabla pivotada: partido x convocatoria (% votos)
        st.markdown("#### Tabla — % votos por convocatoria")
        piv = agg_top.pivot_table(
            index="partido", columns="conv", values="pct", aggfunc="sum",
        ).reset_index()
        piv.columns.name = None
        conv_cols = [c for c in piv.columns if c != "partido"]
        if conv_cols:
            piv = piv.sort_values(conv_cols[-1], ascending=False)
        st.dataframe(piv, use_container_width=True, hide_index=True)

        # Tabla de votos absolutos
        with st.expander("📋 Tabla de votos absolutos por convocatoria"):
            piv_votos = agg_top.pivot_table(
                index="partido", columns="conv", values="votos", aggfunc="sum",
            ).reset_index()
            piv_votos.columns.name = None
            if conv_cols:
                piv_votos = piv_votos.sort_values(conv_cols[-1], ascending=False)
            st.dataframe(piv_votos, use_container_width=True, hide_index=True)

        # Descargas CSV
        csv_evo_long = agg_evo[agg_evo["partido"].isin(top_partidos)][
            ["partido", "conv", "votos", "pct"]
        ].sort_values(["partido", "conv"])

        fname_scope = evo_tipo.replace(" ", "_")[:20]
        if evo_prov:
            fname_scope += f"_{evo_prov[:10].replace(' ', '_')}"

        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                "⬇️  Evolución CSV (formato largo)",
                data=_to_csv_bytes(csv_evo_long),
                file_name=f"evolucion_{fname_scope}.csv",
                mime="text/csv",
            )
        with c_dl2:
            st.download_button(
                "⬇️  Evolución CSV (tabla pivotada)",
                data=_to_csv_bytes(piv),
                file_name=f"evolucion_pivot_{fname_scope}.csv",
                mime="text/csv",
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — MAPAS A ↔ B
# ─────────────────────────────────────────────────────────────────────────────
with tab_mapa:
    st.caption(
        "🗺️ Partido ganador por circunscripción · "
        "Para nivel municipio activa **🗳️ Desglosar por mesa** en el panel A o B "
        "(aparece tras seleccionar un municipio en la pestaña Comparación). "
        "Activa además **📍 Mapa por sección** para llegar al nivel censal."
    )
    mcol_a, mcol_b = st.columns(2)
    _render_map_slot(
        label=f"🅰 Panel A · {lbl_a}",
        col=mcol_a,
        tipo=tipo_a, conv=conv_a, nivel=nivel_a, prov=prov_a,
        ms_state=ms_a,
        map_key="cmp_map_a",
        height=520,
    )
    _render_map_slot(
        label=f"🅱 Panel B · {lbl_b}",
        col=mcol_b,
        tipo=tipo_b, conv=conv_b, nivel=nivel_b, prov=prov_b,
        ms_state=ms_b,
        map_key="cmp_map_b",
        height=520,
    )
