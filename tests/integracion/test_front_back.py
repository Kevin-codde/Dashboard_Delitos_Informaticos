"""Integración frontend <-> backend <-> MongoDB (el frontend habla con la API real)."""
import os

import pytest
from streamlit.testing.v1 import AppTest

from conftest import EMAIL_POR_ROL, PASSWORD_POR_ROL

RUTA_APP = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app.py")


def _iniciar_sesion_en_la_app(rol):
    at = AppTest.from_file(RUTA_APP, default_timeout=60).run()
    at.text_input[0].set_value(EMAIL_POR_ROL[rol])
    at.text_input[1].set_value(PASSWORD_POR_ROL[rol])
    at.button[0].click().run()
    return at


@pytest.mark.caso("INT-01", modulo="Integración", puntos=10)
def test_login_completo_desde_la_interfaz(datos_falsos, puente_front_back):
    """Un analista inicia sesión desde la UI y ve su menú (front + API + MongoDB)"""
    at = _iniciar_sesion_en_la_app("Analista")
    assert not at.exception
    assert at.session_state["rol"] == "Analista"
    assert list(at.sidebar.radio[0].options) == [
        "Consultar y filtrar incidentes", "Visualizar mapa de calor", "Entrenar modelo predictivo ML",
        "Consultar métricas MAE/RMSE/MAPE", "Exportar reportes PDF / CSV",
    ]


@pytest.mark.caso("INT-02", modulo="Integración", puntos=10)
def test_contrasena_incorrecta_desde_la_interfaz(datos_falsos, puente_front_back):
    """Una contraseña incorrecta en la UI muestra el error que devuelve la API"""
    at = AppTest.from_file(RUTA_APP, default_timeout=60).run()
    at.text_input[0].set_value(EMAIL_POR_ROL["Analista"])
    at.text_input[1].set_value("incorrecta123")
    at.button[0].click().run()
    assert "token" not in at.session_state
    assert "Correo o contraseña incorrectos" in at.error[0].value


@pytest.mark.caso("INT-03", modulo="Integración", puntos=10)
def test_administrador_ve_opciones_de_administracion(datos_falsos, puente_front_back):
    """El administrador ve 'Gestionar usuarios' y 'Ejecutar ETL' y la lista real de usuarios"""
    at = _iniciar_sesion_en_la_app("Administrador")
    assert list(at.sidebar.radio[0].options) == ["Gestionar usuarios y roles", "Ejecutar pipeline ETL de datos"]
    assert not at.exception
    tabla = at.dataframe[0].value
    assert EMAIL_POR_ROL["Analista"] in set(tabla["email"])


@pytest.mark.caso("INT-04", modulo="Integración", puntos=10)
def test_admin_crea_usuario_desde_la_interfaz_y_queda_en_mongodb(datos_falsos, puente_front_back, login_mod):
    """El administrador crea un usuario desde la UI y queda guardado en MongoDB"""
    at = _iniciar_sesion_en_la_app("Administrador")
    campos = at.tabs[0].text_input
    campos[0].set_value("Nuevo Desde UI")
    campos[1].set_value("desde.ui@prueba.com")
    campos[2].set_value("DesdeUI12345")
    at.tabs[0].button[0].click().run()
    assert not at.exception
    guardado = login_mod.repo.por_email("desde.ui@prueba.com")
    assert guardado is not None and guardado["rol"] == "Analista"  # rol por defecto del formulario
    assert guardado["password_hash"].startswith("$2")
