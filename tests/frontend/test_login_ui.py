"""Pruebas del frontend: pantalla de inicio de sesión (CU1) y manejo de sesión."""
import pytest
import requests
from streamlit.testing.v1 import AppTest


class RespuestaFalsa:
    def __init__(self, status_code=200, datos=None):
        self.status_code = status_code
        self._datos = datos if datos is not None else {}
        self.ok = status_code < 400
        self.content = b"x"

    def json(self):
        return self._datos


def _app_login():
    from auth import pantalla_login

    pantalla_login()


def _enviar_login(correo="x@prueba.com", clave="Prueba12345"):
    at = AppTest.from_function(_app_login).run()
    at.text_input[0].set_value(correo)
    at.text_input[1].set_value(clave)
    at.button[0].click().run()
    return at


@pytest.mark.caso("FE-01", modulo="Frontend", puntos=5)
def test_pantalla_login_muestra_campos_y_boton():
    """La pantalla de login muestra título, correo, contraseña y botón"""
    at = AppTest.from_function(_app_login).run()
    assert not at.exception
    assert [t.label for t in at.text_input] == ["Correo", "Contraseña"]
    assert at.text_input[1].proto.type == 1  # 1 = campo de contraseña (oculta lo escrito)
    assert at.button[0].label == "Iniciar sesión"
    assert "Dashboard BI" in at.title[0].value


@pytest.mark.caso("FE-02", modulo="Frontend", puntos=5)
def test_login_correcto_guarda_la_sesion(monkeypatch):
    """Un login correcto guarda token, nombre, rol y menú en la sesión"""
    respuesta = {"access_token": "tok123", "nombre": "Ana", "rol": "Analista",
                 "menu": [{"caso_uso": 4, "permiso": "consultar_incidentes", "opcion": "Consultar y filtrar incidentes"}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa(200, respuesta))
    at = _enviar_login()
    assert at.session_state["token"] == "tok123"
    assert at.session_state["rol"] == "Analista"
    assert at.session_state["nombre"] == "Ana"
    assert not at.error


@pytest.mark.caso("FE-03", modulo="Frontend", puntos=5)
def test_login_incorrecto_muestra_el_error_del_backend(monkeypatch):
    """Con credenciales incorrectas se muestra el mensaje y no se crea sesión"""
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa(401, {"detail": "Correo o contraseña incorrectos"}))
    at = _enviar_login(clave="mala")
    assert "token" not in at.session_state
    assert "Correo o contraseña incorrectos" in at.error[0].value


@pytest.mark.caso("FE-04", modulo="Frontend", puntos=5)
def test_backend_caido_muestra_mensaje_claro(monkeypatch):
    """Si el backend no responde, el login avisa que no hay conexión"""
    def sin_conexion(*a, **k):
        raise requests.ConnectionError("sin conexión")

    monkeypatch.setattr(requests, "post", sin_conexion)
    at = _enviar_login()
    assert "No se pudo conectar con el backend" in at.error[0].value


def _app_validar_sesion():
    import streamlit as st

    from auth import sesion_activa

    st.session_state["activa"] = sesion_activa()


@pytest.mark.caso("FE-05", modulo="Frontend", puntos=5)
def test_token_rechazado_por_el_backend_cierra_la_sesion(monkeypatch):
    """Si el backend rechaza el token (401), el frontend cierra la sesión"""
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespuestaFalsa(401, {"detail": "Token inválido"}))
    at = AppTest.from_function(_app_validar_sesion)
    at.session_state["token"] = "vencido"
    at.session_state["rol"] = "Analista"
    at.run()
    assert at.session_state["activa"] is False
    assert "token" not in at.session_state
