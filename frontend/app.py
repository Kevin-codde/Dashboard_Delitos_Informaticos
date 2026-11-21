"""
Aplicación Principal Streamlit (app.py)
Dashboard de Business Intelligence interactivo sobre Delitos Informáticos en Colombia.
Con inicio de sesión y menú según el rol (Administrador / Analista / Consultor).

Ejecutar desde la raíz del proyecto:
    streamlit run frontend/app.py
"""
import os
import subprocess
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(RAIZ)

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from admin_ui import vista_usuarios
from auth import cerrar_sesion, pantalla_login, sesion_activa
from backend.db import consultar_datos_filtrados, obtener_metadatos_estado
from ml.modelo import entrenar_y_predecir_siguiente_anio

# Configuración de página de Streamlit (debe ser la primera llamada a st.*)
st.set_page_config(
    page_title="BI Dashboard - Ciberdelitos Colombia",
    page_icon="🛡️",
    layout="wide",
)

# Lista ordenada de meses para consistencia en los filtros
MESES_ORDENADOS = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]

# URL del tablero de Power BI (publicar en la web y pegar el enlace de "insertar")
POWERBI_URL = os.getenv("POWERBI_URL", "")


@st.cache_data(ttl=600)
def cargar_datos_cache(anio_range, meses, departamento, municipio, tipologias):
    """Carga los datos optimizada con caché de Streamlit."""
    return consultar_datos_filtrados(
        anio_range=anio_range,
        meses=meses,
        departamento=departamento,
        municipio=municipio,
        tipologias=tipologias,
    )


# =============================================================================
# 0. PUERTA DE ACCESO (CU1: Iniciar sesión)
# =============================================================================
if not sesion_activa():
    pantalla_login()
    st.stop()

# =============================================================================
# 1. FILTROS LATERALES (HU2) - solo para las vistas que consultan datos
# =============================================================================
def render_filtros() -> pd.DataFrame:
    """Dibuja los filtros en la barra lateral y devuelve el DataFrame filtrado."""
    df_base = consultar_datos_filtrados()

    if df_base.empty:
        st.error("❌ No se encontraron datos en la base de datos NoSQL. Pídele al Administrador que ejecute el ETL.")
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros de Análisis")

    min_anio = int(df_base["anio"].min())
    max_anio = int(df_base["anio"].max())
    if min_anio == max_anio:
        anio_range = (min_anio, max_anio)
        st.sidebar.caption(f"Año disponible: {min_anio}")
    else:
        anio_range = st.sidebar.slider(
            "Rango de Años:", min_value=min_anio, max_value=max_anio, value=(min_anio, max_anio)
        )

    meses_sel = st.sidebar.multiselect("Meses del Año:", options=MESES_ORDENADOS, default=[])

    deptos_lista = ["TODOS"] + sorted(list(df_base["departamento"].unique()))
    depto_sel = st.sidebar.selectbox("Departamento:", options=deptos_lista, index=0, key="f_depto")

    if depto_sel != "TODOS":
        muni_opciones = ["TODOS"] + sorted(
            list(df_base[df_base["departamento"] == depto_sel]["municipio"].unique())
        )
    else:
        muni_opciones = ["TODOS"] + sorted(list(df_base["municipio"].unique()))
    muni_sel = st.sidebar.selectbox("Municipio:", options=muni_opciones, index=0)

    tipos_lista = sorted(list(df_base["tipologia"].unique()))
    tipos_sel = st.sidebar.multiselect("Tipología de Delito:", options=tipos_lista, default=[])

    return cargar_datos_cache(
        anio_range=anio_range,
        meses=meses_sel if meses_sel else None,
        departamento=depto_sel,
        municipio=muni_sel,
        tipologias=tipos_sel if tipos_sel else None,
    )


# =============================================================================
# 2. VISTAS (una por caso de uso del diagrama)
# =============================================================================
def mostrar_prediccion(df_pred, tipo_riesgo, mae_error, anio_futuro) -> None:
    """Resultados del modelo (HU5)."""
    if df_pred is None or df_pred.empty:
        st.info(
            "Para generar estimaciones predictivas, seleccione un rango de filtros "
            "que contenga al menos 2 años con registros."
        )
        return

    st.warning("⚠️ Estimación basada en datos históricos, no es una certeza.")
    m1, m2, m3 = st.columns(3)
    m1.metric("Año Proyectado", f"{anio_futuro}")
    m2.metric("Tipología con Mayor Riesgo Estimado", f"{tipo_riesgo}")
    m3.metric("Error Absoluto Medio (MAE del Modelo)", f"{mae_error:.2f} casos")

    st.write(f"**Proyección de Casos por Tipología Penal para el Año {anio_futuro}:**")
    fig_pred = px.bar(
        df_pred,
        x="casos_estimados_siguiente_anio",
        y="tipologia",
        orientation="h",
        title=f"Estimación de Frecuencia de Ciberataques ({anio_futuro})",
        labels={"casos_estimados_siguiente_anio": "Casos Estimados", "tipologia": "Tipología Penal"},
        hover_data={"casos_estimados_siguiente_anio": ":,"},
    )
    fig_pred.update_traces(marker_color="#d62728")
    st.plotly_chart(fig_pred, use_container_width=True)


# --- CU3: Ejecutar pipeline ETL (Administrador) ------------------------------
def vista_etl() -> None:
    st.subheader("⚙️ Pipeline ETL de datos")
    st.write("Ejecuta `etl/etl.py` para limpiar el dataset y recargarlo en MongoDB.")
    if st.button("▶️ Ejecutar ETL"):
        with st.spinner("Ejecutando ETL, esto puede tardar un momento..."):
            try:
                r = subprocess.run(
                    [sys.executable, os.path.join(RAIZ, "etl", "etl.py")],
                    capture_output=True,
                    text=True,
                    cwd=RAIZ,
                    env={**os.environ, "PYTHONPATH": RAIZ},
                    timeout=600,
                )
            except subprocess.TimeoutExpired:
                st.error("El ETL superó el tiempo máximo (10 min).")
                return
        if r.returncode == 0:
            st.cache_data.clear()
            st.success("✅ ETL finalizado correctamente.")
        else:
            st.error("❌ El ETL falló. Revisa el detalle:")
        st.code((r.stdout + r.stderr) or "(sin salida)")


# --- CU4: Consultar y filtrar incidentes (Analista) --------------------------
def vista_incidentes(df: pd.DataFrame) -> None:
    # HU1: Estado de los datos
    with st.expander("📌 Estado de los Datos (Metadatos NoSQL)", expanded=False):
        total_db, rango_f, total_deptos, total_tipos = obtener_metadatos_estado()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Registros Cargados", f"{total_db:,}")
        c2.metric("Rango Histórico de Años", rango_f)
        c3.metric("Departamentos Cubiertos", total_deptos)
        c4.metric("Tipologías Penales", total_tipos)

    # HU3: Gráficas estadísticas
    st.subheader("📈 Comportamiento y Distribución de Ciberdelitos")
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        df_evo = df.groupby("anio")["cantidad"].sum().reset_index()
        fig_linea = px.line(
            df_evo, x="anio", y="cantidad", markers=True,
            title="Evolución Histórica Anual de Casos",
            labels={"anio": "Año", "cantidad": "Número de Casos"},
            hover_data={"cantidad": ":,"},
        )
        fig_linea.update_traces(line_color="#1f77b4", line_width=3)
        st.plotly_chart(fig_linea, use_container_width=True)

    with col_g2:
        df_tipo = (
            df.groupby("tipologia")["cantidad"].sum().reset_index().sort_values(by="cantidad", ascending=True)
        )
        fig_barras_tipo = px.bar(
            df_tipo, x="cantidad", y="tipologia", orientation="h",
            title="Distribución de Casos por Tipología Penal",
            labels={"cantidad": "Número de Casos", "tipologia": "Tipología"},
            hover_data={"cantidad": ":,"},
        )
        fig_barras_tipo.update_traces(marker_color="#ff7f0e")
        st.plotly_chart(fig_barras_tipo, use_container_width=True)

    # HU4: Comparación por departamento
    st.markdown("---")
    st.subheader("🗺️ Ranking y Análisis Comparativo por Departamento")

    df_depto = df.groupby("departamento")["cantidad"].sum().reset_index().sort_values(by="cantidad", ascending=False)
    df_depto["Porcentaje (%)"] = ((df_depto["cantidad"] / df_depto["cantidad"].sum()) * 100).round(2)
    df_depto.rename(columns={"departamento": "Departamento", "cantidad": "Casos Totales"}, inplace=True)

    col_dep1, col_dep2 = st.columns([3, 2])
    with col_dep1:
        fig_rank = px.bar(
            df_depto.head(15), x="Departamento", y="Casos Totales",
            title="Top Departamentos con Mayor Incidencia",
            labels={"Casos Totales": "Número de Casos"},
            hover_data={"Casos Totales": ":,", "Porcentaje (%)": ":.2f"},
        )
        fig_rank.update_traces(marker_color="#2ca02c")
        st.plotly_chart(fig_rank, use_container_width=True)
    with col_dep2:
        st.write("**Tabla Detallada de Participación (%)**")
        st.dataframe(
            df_depto.style.format({"Casos Totales": "{:,}", "Porcentaje (%)": "{:.2f}%"}),
            use_container_width=True,
            height=380,
        )


# --- CU5: Mapa de calor (Analista) -------------------------------------------
def vista_mapa_calor(df: pd.DataFrame) -> None:
    st.subheader("🔥 Mapa de calor: departamento vs. año")
    fig = px.density_heatmap(
        df, x="anio", y="departamento", z="cantidad", histfunc="sum",
        color_continuous_scale="YlOrRd",
        labels={"anio": "Año", "departamento": "Departamento", "cantidad": "Casos"},
    )
    fig.update_layout(height=max(500, 18 * df["departamento"].nunique()))
    st.plotly_chart(fig, use_container_width=True)


# --- CU6: Entrenar modelo predictivo (Analista) ------------------------------
def vista_entrenar(df: pd.DataFrame) -> None:
    st.subheader("🤖 Entrenar modelo predictivo")
    st.write("El modelo se entrena con los datos que dejan los filtros actuales.")
    if st.button("🚀 Entrenar modelo"):
        with st.spinner("Entrenando..."):
            st.session_state["resultado_ml"] = entrenar_y_predecir_siguiente_anio(df)
    resultado = st.session_state.get("resultado_ml")
    if resultado:
        mostrar_prediccion(*resultado)


# --- CU7: Consultar métricas MAE / RMSE / MAPE (Analista) --------------------
def vista_metricas() -> None:
    st.subheader("📏 Métricas del modelo")
    resultado = st.session_state.get("resultado_ml")
    if not resultado or resultado[0] is None:
        st.info("Primero entrena el modelo en la opción «Entrenar modelo predictivo ML».")
        return
    _, _, mae_error, _ = resultado
    m1, m2, m3 = st.columns(3)
    m1.metric("MAE", f"{mae_error:.2f} casos")
    m2.metric("RMSE", "—")
    m3.metric("MAPE", "—")
    st.caption("RMSE y MAPE aparecerán cuando ml/modelo.py los calcule y los devuelva.")


# --- CU8: Resumen ejecutivo (Consultor) --------------------------------------
def vista_resumen(df: pd.DataFrame) -> None:
    st.subheader("📋 Resumen ejecutivo")
    por_anio = df.groupby("anio")["cantidad"].sum()
    tipo_top = df.groupby("tipologia")["cantidad"].sum().idxmax()
    depto_top = df.groupby("departamento")["cantidad"].sum().idxmax()

    c1, c2, c3 = st.columns(3)
    c1.metric("Año con más casos", f"{int(por_anio.idxmax())} ({int(por_anio.max()):,})")
    c2.metric("Tipología más frecuente", tipo_top)
    c3.metric("Departamento con más casos", depto_top)

    df_evo = por_anio.reset_index()
    fig = px.line(
        df_evo, x="anio", y="cantidad", markers=True,
        title="Evolución anual de casos",
        labels={"anio": "Año", "cantidad": "Número de Casos"},
    )
    fig.update_traces(line_color="#1f77b4", line_width=3)
    st.plotly_chart(fig, use_container_width=True)


# --- CU9: Predicciones por departamento (Consultor) --------------------------
def vista_predicciones_depto(df: pd.DataFrame) -> None:
    st.subheader("🔮 Predicciones por departamento")
    depto = st.session_state.get("f_depto", "TODOS")
    if depto == "TODOS":
        st.info("Elige un departamento en el filtro lateral para ver su predicción. Abajo se muestra la nacional.")
    else:
        st.caption(f"Departamento seleccionado: **{depto}**")
    mostrar_prediccion(*entrenar_y_predecir_siguiente_anio(df))


# --- CU10: Tableros de Power BI (Consultor) ----------------------------------
def vista_powerbi() -> None:
    st.subheader("📊 Tableros de Power BI")
    if POWERBI_URL:
        components.iframe(POWERBI_URL, height=700)
    else:
        st.info("Aún no hay un tablero configurado. Define la variable de entorno POWERBI_URL con el enlace del informe.")


# --- CU11: Exportar reportes (Analista y Consultor) --------------------------
def vista_exportar(df: pd.DataFrame) -> None:
    st.subheader("📤 Exportar reportes")
    st.write(f"El reporte incluye los **{len(df):,}** registros que dejan los filtros actuales.")
    st.download_button(
        "⬇️ Descargar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="reporte_delitos_informaticos.csv",
        mime="text/csv",
    )
    st.caption("La exportación a PDF está pendiente de implementar.")


# permiso (backend/login.py) -> función que dibuja la vista
VISTAS = {
    "gestionar_usuarios": vista_usuarios,
    "ejecutar_etl": vista_etl,
    "consultar_incidentes": vista_incidentes,
    "mapa_calor": vista_mapa_calor,
    "entrenar_modelo": vista_entrenar,
    "consultar_metricas": vista_metricas,
    "resumen_ejecutivo": vista_resumen,
    "predicciones_departamento": vista_predicciones_depto,
    "tableros_powerbi": vista_powerbi,
    "exportar_reportes": vista_exportar,
}

# Vistas que necesitan los filtros y el DataFrame filtrado
VISTAS_CON_FILTROS = {
    "consultar_incidentes", "mapa_calor", "entrenar_modelo",
    "resumen_ejecutivo", "predicciones_departamento", "exportar_reportes",
}

# =============================================================================
# 3. BARRA LATERAL: USUARIO, CIERRE DE SESIÓN Y MENÚ SEGÚN EL ROL
# =============================================================================
st.sidebar.title("🛡️ Ciberdelitos")
st.sidebar.markdown(f"👤 **{st.session_state['nombre']}**  \nRol: {st.session_state['rol']}")
if st.sidebar.button("Cerrar sesión"):
    cerrar_sesion()
    st.rerun()

opciones = {item["opcion"]: item["permiso"] for item in st.session_state["menu"]}
if not opciones:
    st.error("Tu rol no tiene opciones asignadas.")
    st.stop()

opcion_elegida = st.sidebar.radio("Menú", list(opciones))
permiso = opciones[opcion_elegida]

# =============================================================================
# 4. CONTENIDO PRINCIPAL
# =============================================================================
st.title("🛡️ Dashboard BI: Delitos Informáticos en Colombia")
st.markdown("Prototipo de Inteligencia de Negocios basado en microdatos de **datos.gov.co** (MinDefensa / Policía Nacional).")

if permiso not in VISTAS:
    st.info("Esta opción aún no está implementada.")
elif permiso in VISTAS_CON_FILTROS:
    df_filtrado = render_filtros()
    total_casos = int(df_filtrado["cantidad"].sum()) if not df_filtrado.empty else 0
    st.metric(label="📊 Total de Casos Filtrados", value=f"{total_casos:,}")
    if df_filtrado.empty:
        st.info("⚠️ No hay registros para los filtros seleccionados.")
        st.stop()
    st.markdown("---")
    VISTAS[permiso](df_filtrado)
else:
    st.markdown("---")
    VISTAS[permiso]()