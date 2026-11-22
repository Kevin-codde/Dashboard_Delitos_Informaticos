"""Pruebas del frontend: app.py con sesión iniciada, menú por rol y vistas."""
import os

import pytest
import requests
from streamlit.testing.v1 import AppTest

from test_login_ui import RespuestaFalsa

RUTA_APP = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app.py")

MENU_CONSULTOR = [
    {"caso_uso": 8, "permiso": "resumen_ejecutivo", "opcion": "Visualizar resumen ejecutivo"},
    {"caso_uso": 9, "permiso": "predicciones_departamento", "opcion": "Consultar predicciones por departamento"},
    {"caso_uso": 10, "permiso": "tableros_powerbi", "opcion": "Consultar tableros de Power BI"},
    {"caso_uso": 11, "permiso": "exportar_reportes", "opcion": "Exportar reportes PDF / CSV"},
]
MENU_ANALISTA = [
    {"caso_uso": 4, "permiso": "consultar_incidentes", "opcion": "Consultar y filtrar incidentes"},
    {"caso_uso": 5, "permiso": "mapa_calor", "opcion": "Visualizar mapa de calor"},
    {"caso_uso": 6, "permiso": "entrenar_modelo", "opcion": "Entrenar modelo predictivo ML"},
    {"caso_uso": 7, "permiso": "consultar_metricas", "opcion": "Consultar métricas MAE/RMSE/MAPE"},
    {"caso_uso": 11, "permiso": "exportar_reportes", "opcion": "Exportar reportes PDF / CSV"},
]


def _abrir_app(monkeypatch, rol, menu):
    """Abre app.py como si el usuario ya hubiera iniciado sesión con ese rol."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespuestaFalsa(200, {"rol": rol, "menu": menu}))
    at = AppTest.from_file(RUTA_APP, default_timeout=60)
    at.session_state["token"] = "tok"
    at.session_state["nombre"] = f"Usuario {rol}"
    at.session_state["rol"] = rol
    at.session_state["menu"] = menu
    return at.run()


@pytest.mark.caso("FE-06", modulo="Frontend", puntos=5)
def test_sin_sesion_la_app_muestra_solo_el_login(datos_falsos):
    """Sin sesión iniciada, app.py muestra el login y ningún dato"""
    at = AppTest.from_file(RUTA_APP, default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.text_input] == ["Correo", "Contraseña"]
    assert len(at.sidebar.radio) == 0
    assert len(at.metric) == 0


@pytest.mark.caso("FE-07", modulo="Frontend", puntos=5)
def test_menu_del_consultor_solo_tiene_sus_opciones(datos_falsos, monkeypatch):
    """El menú lateral del consultor muestra solo sus opciones"""
    at = _abrir_app(monkeypatch, "Consultor", MENU_CONSULTOR)
    assert not at.exception
    assert list(at.sidebar.radio[0].options) == [m["opcion"] for m in MENU_CONSULTOR]
    assert "Rol: Consultor" in at.sidebar.markdown[0].value


@pytest.mark.caso("FE-08", modulo="Frontend", puntos=5)
def test_menu_del_analista_no_incluye_administracion(datos_falsos, monkeypatch):
    """El analista no ve las opciones de administración (usuarios ni ETL)"""
    at = _abrir_app(monkeypatch, "Analista", MENU_ANALISTA)
    opciones = list(at.sidebar.radio[0].options)
    assert opciones == [m["opcion"] for m in MENU_ANALISTA]
    assert not any("usuarios" in o.lower() or "etl" in o.lower() for o in opciones)


@pytest.mark.caso("FE-09", modulo="Frontend", puntos=5)
def test_resumen_ejecutivo_muestra_metricas(datos_falsos, monkeypatch):
    """La vista de resumen ejecutivo calcula y muestra sus métricas"""
    at = _abrir_app(monkeypatch, "Consultor", MENU_CONSULTOR)
    etiquetas = [m.label for m in at.metric]
    assert "Total de Casos Filtrados" in " ".join(etiquetas)
    assert "Año con más casos" in etiquetas
    valores = {m.label: m.value for m in at.metric}
    assert valores["Año con más casos"].startswith("2024")          # 2024 tiene el factor más alto
    assert valores["Tipología más frecuente"] == "HURTO POR MEDIOS INFORMATICOS" or valores["Tipología más frecuente"]


@pytest.mark.caso("FE-10", modulo="Frontend", puntos=5)
def test_cerrar_sesion_vuelve_al_login(datos_falsos, monkeypatch):
    """El botón 'Cerrar sesión' elimina la sesión y regresa al login"""
    at = _abrir_app(monkeypatch, "Analista", MENU_ANALISTA)
    boton = [b for b in at.sidebar.button if b.label == "Cerrar sesión"][0]
    boton.click()
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespuestaFalsa(401, {"detail": "x"}))
    at.run()
    assert "token" not in at.session_state
    assert [t.label for t in at.text_input] == ["Correo", "Contraseña"]


@pytest.mark.caso("FE-11", modulo="Frontend", puntos=5)
def test_vista_de_exportacion_ofrece_descarga_csv(datos_falsos, monkeypatch):
    """La vista de exportar reportes ofrece la descarga del CSV"""
    at = _abrir_app(monkeypatch, "Consultor", MENU_CONSULTOR)
    at.sidebar.radio[0].set_value("Exportar reportes PDF / CSV").run()
    assert not at.exception
    assert any("Descargar CSV" in str(e.proto) for e in at.get("download_button"))
