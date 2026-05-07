"""
Herramienta Pericles — Dashboard electoral histórico de España
Página de presentación
"""
import streamlit as st
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

st.set_page_config(
    page_title="Herramienta Pericles",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🗳️ Herramienta Pericles")
st.markdown(
    """
    Base de datos electoral histórica de España construida a partir de los ficheros DAT del
    **Ministerio del Interior** (Infoelectoral).  
    Cubre los siguientes tipos de elección: **Congreso, Senado, Municipales y Europeas**,
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
        "pages/0_Explorador.py", "🔍", "Explorador de datos",
        "Acceso directo a los parquets subyacentes. Filtra, agrupa y exporta "
        "cualquier tabla en crudo.",
    ),
    (
        "pages/1_Participacion.py", "📊", "Participación",
        "Evolución histórica de participación, abstención, voto en blanco y nulo "
        "para Congreso, Senado, Municipales y Europeas. Filtrable por comunidad autónoma, provincia y municipio.",
    ),
    (
        "pages/2_Congreso.py", "🏛️", "Congreso",
        "Resultados al Congreso de los Diputados 1977–2023. Distribución de escaños, "
        "ganador por provincia, mapa interactivo clickable. Desglose hasta sección censal.",
    ),
    (
        "pages/3_Municipales.py", "🏙️", "Municipales",
        "Elecciones municipales 1979–2023. Ganador por municipio y provincia, "
        "mapa de partido ganador, desglose hasta mesa electoral (tipo_10 · 48 M filas).",
    ),
    (
        "pages/4_Mayorias.py", "🏅", "Mayorías",
        "Análisis del bipartidismo PP+PSOE a lo largo del tiempo, concentración "
        "de voto, evolución del número efectivo de partidos.",
    ),
    (
        "pages/4_Senado.py", "⚖️", "Senado",
        "Resultados al Senado, distribución de senadores por provincia y "
        "comparativa con el Congreso.",
    ),
    (
        "pages/5_Europeas.py", "🇪🇺", "Europeas",
        "Elecciones al Parlamento Europeo 1987–2024. Resultados nacionales "
        "y evolución temporal por partido.",
    ),
    (
        "pages/6_Comparador.py", "🔀", "Comparador",
        "Compara dos snapshots electorales cualesquiera (tipo, convocatoria y "
        "territorio independientes). Barras Δ, evolución temporal y mapas side-by-side.",
    ),
    (
        "pages/7_Candidaturas_Municipales.py", "📋", "Candidaturas Municipales",
        "Listas electorales completas por candidatura, municipio y convocatoria. "
        "Mapa clickable. Filtros por provincia, partido y cargo.",
    ),
    (
        "pages/8_Candidaturas_Congreso.py", "📋", "Candidaturas Congreso",
        "Listas electorales al Congreso por provincia y convocatoria. "
        "Escaños obtenidos, votos y mapa clickable de provincias.",
    ),
    (
        "pages/9_Candidaturas_Senado.py", "📋", "Candidaturas Senado",
        "Candidatos al Senado por provincia y convocatoria. "
        "Senadores elegidos, votos individuales y mapa clickable.",
    ),
    (
        "pages/10_Candidaturas_Europeas.py", "📋", "Candidaturas Europeas",
        "Listas electorales al Parlamento Europeo. "
        "Eurodiputados obtenidos y resultados por convocatoria.",
    ),
    (
        "pages/11_Analisis_(en_desarrollo).py", "🔬", "Análisis (en desarrollo)",
        "Módulo de análisis estadístico avanzado. En construcción.",
    ),
]

# Mostrar en grid de 2 columnas
for i in range(0, len(pages), 2):
    cols = st.columns(2)
    for j, col in enumerate(cols):
        if i + j >= len(pages):
            break
        path, icon, title, desc = pages[i + j]
        with col:
            with st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(desc)
                st.page_link(path, label=f"Ir a {title} →")

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

st.divider()
st.markdown(
    """
    **Herramienta Pericles** · Desarrollado por **Javier Ramos Herrero**  
    """
)

