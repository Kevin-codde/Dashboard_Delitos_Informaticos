"""
Aplicación Principal Streamlit (app.py)
Dashboard de Business Intelligence interactivo sobre Delitos Informáticos en Colombia.
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from backend.Bd.db import consultar_datos_filtrados, obtener_metadatos_estado
from ml.modelo import entrenar_y_predecir_siguiente_anio

# Configuración de página de Streamlit
st.set_page_config(
    page_title="BI Dashboard - Ciberdelitos Colombia",
    page_icon="🛡️",
    layout="wide"
)

# Lista ordenada de meses para consistencia en los filtros
MESES_ORDENADOS = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
]


@st.cache_data(ttl=600)
def cargar_datos_cache(anio_range, meses, departamento, municipio, tipologias):
    """Carga los datos optimizada con caché de Streamlit."""
    return consultar_datos_filtrados(
        anio_range=anio_range,
        meses=meses,
        departamento=departamento,
        municipio=municipio,
        tipologias=tipologias
    )


# -----------------------------------------------------------------------------
# ENCABEZADO Y TITULO
# -----------------------------------------------------------------------------
st.title("🛡️ Dashboard BI: Delitos Informáticos en Colombia")
st.markdown("Prototipo de Inteligencia de Negocios basado en microdatos de **datos.gov.co** (MinDefensa / Policía Nacional).")

# -----------------------------------------------------------------------------
# HU1: ESTADO DE LOS DATOS (Carga y Metadatos)
# -----------------------------------------------------------------------------
with st.expander("📌 Estado de los Datos (Metadatos NoSQL)", expanded=False):
    total_db, rango_f, total_deptos, total_tipos = obtener_metadatos_estado()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Registros Cargados", f"{total_db:,}")
    c2.metric("Rango Histórico de Años", rango_f)
    c3.metric("Departamentos Cubiertos", total_deptos)
    c4.metric("Tipologías Penales", total_tipos)

# -----------------------------------------------------------------------------
# HU2: FILTROS LATERALES DINÁMICOS
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filtros de Análisis")

# Carga inicial sin filtros para extraer listas maestras
df_base = consultar_datos_filtrados()

if df_base.empty:
    st.error("❌ No se encontraron datos en la base de datos NoSQL. Ejecute primero 'python etl.py'.")
    st.stop()

# 1. Filtro de Rango de Años
min_anio = int(df_base['anio'].min())
max_anio = int(df_base['anio'].max())
anio_range = st.sidebar.slider("Rango de Años:", min_value=min_anio, max_value=max_anio, value=(min_anio, max_anio))

# 2. Filtro de Meses
meses_sel = st.sidebar.multiselect("Meses del Año:", options=MESES_ORDENADOS, default=[])

# 3. Filtro de Departamento
deptos_lista = ["TODOS"] + sorted(list(df_base['departamento'].unique()))
depto_sel = st.sidebar.selectbox("Departamento:", options=deptos_lista, index=0)

# 4. Filtro Dependiente de Municipio
if depto_sel != "TODOS":
    muni_opciones = ["TODOS"] + sorted(list(df_base[df_base['departamento'] == depto_sel]['municipio'].unique()))
else:
    muni_opciones = ["TODOS"] + sorted(list(df_base['municipio'].unique()))
muni_sel = st.sidebar.selectbox("Municipio:", options=muni_opciones, index=0)

# 5. Filtro de Tipología Penal
tipos_lista = sorted(list(df_base['tipologia'].unique()))
tipos_sel = st.sidebar.multiselect("Tipología de Delito:", options=tipos_lista, default=[])

# -----------------------------------------------------------------------------
# CONSULTA CON FILTROS APLICADOS
# -----------------------------------------------------------------------------
df_filtrado = cargar_datos_cache(
    anio_range=anio_range,
    meses=meses_sel if meses_sel else None,
    departamento=depto_sel,
    municipio=muni_sel,
    tipologias=tipos_sel if tipos_sel else None
)

# Indicador Destacado de Casos Filtrados
total_casos_filtrados = int(df_filtrado['cantidad'].sum()) if not df_filtrado.empty else 0
st.metric(label="📊 Total de Casos Filtrados", value=f"{total_casos_filtrados:,}")

# Manejo de Filtros sin Resultados (HU2)
if df_filtrado.empty:
    st.info("⚠️ No hay registros para los filtros seleccionados.")
    st.stop()

# -----------------------------------------------------------------------------
# HU3: GRÁFICAS ESTADÍSTICAS
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 Comportamiento y Distribución de Ciberdelitos")

col_g1, col_g2 = st.columns(2)

with col_g1:
    df_evo = df_filtrado.groupby('anio')['cantidad'].sum().reset_index()
    fig_linea = px.line(
        df_evo,
        x='anio',
        y='cantidad',
        markers=True,
        title="Evolución Histórica Anual de Casos",
        labels={'anio': 'Año', 'cantidad': 'Número de Casos'},
        hover_data={'cantidad': ':,'}
    )
    fig_linea.update_traces(line_color="#1f77b4", line_width=3)
    st.plotly_chart(fig_linea, use_container_width=True)

with col_g2:
    df_tipo = df_filtrado.groupby('tipologia')['cantidad'].sum().reset_index().sort_values(by='cantidad', ascending=True)
    fig_barras_tipo = px.bar(
        df_tipo,
        x='cantidad',
        y='tipologia',
        orientation='h',
        title="Distribución de Casos por Tipología Penal",
        labels={'cantidad': 'Número de Casos', 'tipologia': 'Tipología'},
        hover_data={'cantidad': ':,'}
    )
    fig_barras_tipo.update_traces(marker_color="#ff7f0e")
    st.plotly_chart(fig_barras_tipo, use_container_width=True)

# -----------------------------------------------------------------------------
# HU4: COMPARACIÓN POR DEPARTAMENTO
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🗺️ Ranking y Análisis Comparativo por Departamento")

df_depto = df_filtrado.groupby('departamento')['cantidad'].sum().reset_index().sort_values(by='cantidad', ascending=False)
total_general_filtrado = df_depto['cantidad'].sum()

df_depto['Porcentaje (%)'] = ((df_depto['cantidad'] / total_general_filtrado) * 100).round(2)
df_depto.rename(columns={'departamento': 'Departamento', 'cantidad': 'Casos Totales'}, inplace=True)

col_dep1, col_dep2 = st.columns([3, 2])

with col_dep1:
    fig_rank = px.bar(
        df_depto.head(15),
        x='Departamento',
        y='Casos Totales',
        title="Top Departamentos con Mayor Incidencia",
        labels={'Casos Totales': 'Número de Casos'},
        hover_data={'Casos Totales': ':,', 'Porcentaje (%)': ':.2f'}
    )
    fig_rank.update_traces(marker_color="#2ca02c")
    st.plotly_chart(fig_rank, use_container_width=True)

with col_dep2:
    st.write("**Tabla Detallada de Participación (%)**")
    st.dataframe(
        df_depto.style.format({'Casos Totales': '{:,}', 'Porcentaje (%)': '{:.2f}%'}),
        use_container_width=True,
        height=380
    )

# -----------------------------------------------------------------------------
# HU5: MÓDULO DE PREDICCIÓN CON MACHINE LEARNING
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🤖 Módulo Predictivo de Riesgo Futuro")

st.warning("⚠️ Estimación basada en datos históricos, no es una certeza.")

df_pred, tipo_riesgo, mae_error, anio_futuro = entrenar_y_predecir_siguiente_anio(df_filtrado)

if df_pred is not None and not df_pred.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Año Proyectado", f"{anio_futuro}")
    m2.metric("Tipología con Mayor Riesgo Estimado", f"{tipo_riesgo}")
    m3.metric("Error Absoluto Medio (MAE del Modelo)", f"{mae_error:.2f} casos")

    st.write(f"**Proyección de Casos por Tipología Penal para el Año {anio_futuro}:**")
    
    fig_pred = px.bar(
        df_pred,
        x='casos_estimados_siguiente_anio',
        y='tipologia',
        orientation='h',
        title=f"Estimación de Frecuencia de Ciberataques ({anio_futuro})",
        labels={'casos_estimados_siguiente_anio': 'Casos Estimados', 'tipologia': 'Tipología Penal'},
        hover_data={'casos_estimados_siguiente_anio': ':,'}
    )
    fig_pred.update_traces(marker_color="#d62728")
    st.plotly_chart(fig_pred, use_container_width=True)
else:
    st.info("Para generar estimaciones predictivas, seleccione un rango de filtros que contenga al menos 2 años con registros.")