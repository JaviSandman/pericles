"""
Infoelectoral — Dashboard electoral histórico de España
Página de presentación
"""
import streamlit as st
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

st.set_page_config(
    page_title="Presentación · Infoelectoral España",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🗳️ Presentación — Infoelectoral España 1976–2023")
st.markdown(
    """
    Base de datos electoral histórica de España construida a partir de los ficheros DAT del
    **Ministerio del Interior** (Infoelectoral).  
    Cubre **todos los tipos de elección** — Congreso, Senado, Municipales y Europeas —
    desde las primeras elecciones democráticas de 1977 hasta 2023.
    """
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Procesos electorales", "167")
col2.metric("Filas totales", "68,9 M")
col3.metric("Tipos de elección", "4")
col4.metric("Años cubiertos", "1976–2023")

st.divider()

# ── Páginas disponibles ────────────────────────────────────────────────────────
st.subheader("📂 Páginas del dashboard")

pages = [
    (
        "🔍 Explorador de datos",
        "Acceso directo a los parquets subyacentes. Filtra, agrupa y exporta "
        "cualquier tabla en crudo.",
    ),
    (
        "📊 Participación",
        "Evolución histórica de participación y abstención por convocatoria, "
        "provincia y municipio. Mapas coropléticos a nivel nacional y provincial.",
    ),
    (
        "🏛️ Congreso",
        "Resultados al Congreso de los Diputados 1977–2023. Distribución de escaños, "
        "ganador por provincia, mapa interactivo clickable. Desglose a nivel de "
        "distrito y sección censal.",
    ),
    (
        "🏙️ Municipales",
        "Elecciones municipales 1979–2023. Ganador por municipio y provincia, "
        "mapa de partido ganador, desglose a nivel de distrito / sección / mesa "
        "electoral (tipo_10 · 48 M filas). Municipios de concejo abierto (<250 hab).",
    ),
    (
        "🏅 Mayorías",
        "Análisis del bipartidismo PP+PSOE a lo largo del tiempo, concentración "
        "de voto, evolución del número efectivo de partidos.",
    ),
    (
        "🏛️ Senado",
        "Resultados al Senado, distribución de senadores por provincia y "
        "comparativa con el Congreso.",
    ),
    (
        "🇪🇺 Europeas",
        "Elecciones al Parlamento Europeo 1987–2019. Resultados nacionales "
        "y evolución temporal por partido.",
    ),
    (
        "⚖️ Comparador",
        "Compara dos snapshots electorales cualesquiera (tipo, convocatoria y "
        "territorio independientes). Incluye:\n"
        "- **Comparación A ↔ B** — barras Δ por partido, tablas y descarga CSV\n"
        "- **Evolución temporal** — línea de tendencia con eje X cronológico\n"
        "- **Mapas A ↔ B** — choropleth side-by-side hasta nivel de sección censal",
    ),
    (
        "📋 Candidaturas Municipales",
        "Listas electorales completas: candidatos por candidatura, municipio y "
        "convocatoria. Mapa clickable de municipios. Filtros por provincia, "
        "partido y cargo (titular / suplente).",
    ),
]

for title, desc in pages:
    with st.expander(title, expanded=False):
        st.markdown(desc)

st.divider()

# ── Capacidades técnicas ───────────────────────────────────────────────────────
st.subheader("⚙️ Capacidades técnicas")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        """
        **Mapas**
        - Choropleth a 4 niveles: Nacional → Provincia → Municipio → Sección censal
        - Geometrías de secciones vía WFS INE (API en tiempo real)
        - Mapas clickables con popup (GeoJsonPopup)
        - Colores por partido ganador con paleta institucional
        """
    )

with c2:
    st.markdown(
        """
        **Granularidad de datos**
        - Nacional · Provincia · Municipio · Distrito · Sección · Mesa electoral
        - Desglose por distrito y mesa en Municipales y Comparador
        - Toggle bajo demanda (tipo_10 · 48 M filas, nunca cargado en startup)
        - Municipios de sistema mayoritario (<250 hab) tratados separadamente
        """
    )

with c3:
    st.markdown(
        """
        **Comparador**
        - Dos paneles A / B completamente independientes
        - Cruce libre: cualquier tipo × convocatoria × territorio
        - Gráfico Δ (variación B − A) por partido
        - Evolución temporal con eje X ordenado cronológicamente
        - Mapas side-by-side hasta nivel sección censal
        """
    )

st.divider()
st.caption(
    "Fuente: Ministerio del Interior — Infoelectoral · "
    "Geometrías: INE Secciones Censales 2025 (WFS) · "
    "Stack: Python · pandas · pyarrow · Streamlit · Plotly · Folium"
)

