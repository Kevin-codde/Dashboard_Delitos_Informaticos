"""
Frontend de Streamlit: muestra el reporte de Power BI dentro de la página.

Streamlit NO dibuja gráficos aquí; solo enmarca el reporte publicado.
Los enlaces de los reportes están en frontend/config.py. Para usar otros sin tocar el repo:

    Windows (PowerShell):   $env:POWERBI_URL="https://app.powerbi.com/view?r=..."
    (para el reporte oscuro: POWERBI_URL_OSCURO)

Ejecutar desde la raíz del repositorio:
    streamlit run frontend/app.py
"""

import html
import os

import streamlit as st

from config import REPORTE_CLARO, REPORTE_OSCURO  # enlaces públicos: ver frontend/config.py

# El reporte mide 1280x720; se suman ~42 px de la barra inferior de Power BI (proporción 1280 / 762).


def obtener_url(oscuro: bool = False) -> str:
    """URL del reporte: variable de entorno, luego secrets.toml, luego frontend/config.py.
    En modo oscuro usa POWERBI_URL_OSCURO; si no está definida, cae al reporte claro."""
    clave = "POWERBI_URL_OSCURO" if oscuro else "POWERBI_URL"
    por_defecto = REPORTE_OSCURO if oscuro else REPORTE_CLARO
    if clave in os.environ:
        return os.environ[clave].strip()
    try:
        url = str(st.secrets.get(clave, "")).strip()
        if url:
            return url
    except Exception:  # no existe secrets.toml
        pass
    return por_defecto


def url_valida(url: str) -> bool:
    return url.startswith("https://app.powerbi.com/")


CSS_OSCURO = """
<style>
  .stApp, [data-testid="stAppViewContainer"] {background: #0A1222; color: #E8EEF9;}
  header[data-testid="stHeader"] {background: transparent;}
  .titulo {color: #E8EEF9 !important;}
  .sub, .stCaption, [data-testid="stCaptionContainer"] {color: #9FB0CC !important;}
  .pbi {border: 1px solid #243350 !important;}
  [data-testid="stBaseLinkButton-secondary"] {background: #121C31 !important; color: #E8EEF9 !important;
                                              border: 1px solid #243350 !important;}
  [data-testid="stBaseLinkButton-secondary"] p {color: #E8EEF9 !important;}
  [data-testid="stBaseButton-secondary"] {background: #121C31; color: #E8EEF9; border-color: #243350;}
  label, p {color: #E8EEF9;}
</style>
"""


def main() -> None:
    st.set_page_config(page_title="Ciberdelitos en Colombia", page_icon="🛡️",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown(
        """
        <style>
          .block-container {padding-top: 1.2rem; padding-bottom: 0.5rem; max-width: 1500px;}
          .titulo {font-size: 1.7rem; font-weight: 700; color: #0B2545; margin: 0;}
          .sub {color: #5B6B8C; margin: 0 0 .8rem 0;}
          header[data-testid="stHeader"] {background: transparent;}
          .pbi {position: relative; width: 100%; aspect-ratio: 1280 / 762; overflow: hidden;
                border: 1px solid #DDE3EE; border-radius: 10px;}
          .pbi iframe {position: absolute; inset: 0; width: 100%; height: 100%; border: 0;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="titulo">🛡️ Delitos informáticos en Colombia</p>'
                '<p class="sub">Ley 1273 de 2009 · datos abiertos 2006–2026 · '
                'reporte interactivo en Power BI</p>', unsafe_allow_html=True)

    _, col_modo = st.columns([6, 1])
    oscuro = col_modo.toggle("🌙 Modo oscuro", key="oscuro")
    if oscuro:
        st.markdown(CSS_OSCURO, unsafe_allow_html=True)

    url = obtener_url(oscuro)
    if oscuro and not url:  # aún no hay versión oscura publicada: se muestra la clara
        url = obtener_url(False)
        st.caption("La versión oscura del reporte aún no está publicada; se muestra la clara.")

    if not url:
        st.info("Aún no hay un reporte configurado. Publica el reporte en Power BI "
                "(Archivo → Insertar informe → Publicar en la web) y define la variable "
                "`POWERBI_URL` con el enlace.")
        with st.expander("¿Cómo lo configuro?", expanded=True):
            st.code('$env:POWERBI_URL="https://app.powerbi.com/view?r=TU_ENLACE"\n'
                    "streamlit run frontend/app.py", language="powershell")
        return

    if not url_valida(url):
        st.error("La URL configurada no parece de Power BI (debe empezar por "
                 "`https://app.powerbi.com/`).")
        return

    st.markdown(
        f'<div class="pbi"><iframe src="{html.escape(url, quote=True)}" title="Reporte de Power BI" '
        'allowfullscreen="true" frameborder="0"></iframe></div>',
        unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    col1.link_button("Abrir en pantalla completa", url)
    col2.caption("Usa los filtros del reporte (año, departamento, tipología) para explorar. "
                 "Los datos corresponden al último corte cargado en MongoDB.")


main()
