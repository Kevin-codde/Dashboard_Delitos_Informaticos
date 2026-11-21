"""
auth.py - Conexión del frontend (Streamlit) con el backend de login (FastAPI).
Maneja el inicio/cierre de sesión y las llamadas a la API con el token JWT.
"""
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 5  # segundos

_CLAVES_SESION = ("token", "nombre", "rol", "menu")


def _headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state['token']}"}


def _detalle_error(respuesta: requests.Response) -> str:
    try:
        detalle = respuesta.json().get("detail")
    except ValueError:
        detalle = None
    return detalle if isinstance(detalle, str) else f"Error {respuesta.status_code}"


def login(email: str, password: str) -> tuple[bool, str]:
    """Llama a POST /auth/login y guarda el token y el menú en la sesión."""
    try:
        r = requests.post(
            f"{API_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return False, "No se pudo conectar con el backend. ¿Está corriendo uvicorn en el puerto 8000?"

    if r.status_code == 200:
        datos = r.json()
        st.session_state.update(
            token=datos["access_token"],
            nombre=datos["nombre"],
            rol=datos["rol"],
            menu=datos["menu"],
        )
        return True, ""
    if r.status_code == 422:
        return False, "Escribe un correo válido y tu contraseña."
    return False, _detalle_error(r)


def cerrar_sesion() -> None:
    for clave in _CLAVES_SESION:
        st.session_state.pop(clave, None)


def sesion_activa() -> bool:
    """Valida el token contra el backend en cada ejecución y refresca rol y menú.
    Si el usuario fue desactivado o su rol cambió, se aplica de inmediato."""
    if "token" not in st.session_state:
        return False
    try:
        r = requests.get(f"{API_URL}/auth/menu", headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException:
        cerrar_sesion()
        return False
    if r.status_code != 200:
        cerrar_sesion()
        return False
    datos = r.json()
    st.session_state["rol"] = datos["rol"]
    st.session_state["menu"] = datos["menu"]
    return True


def api(metodo: str, ruta: str, **kwargs):
    """Llamada autenticada al backend. Devuelve (ok, datos_o_mensaje_de_error)."""
    try:
        r = requests.request(
            metodo, f"{API_URL}{ruta}", headers=_headers(), timeout=TIMEOUT, **kwargs
        )
    except requests.RequestException:
        return False, "Sin conexión con el backend"
    if r.ok:
        return True, (r.json() if r.content else None)
    return False, _detalle_error(r)


def pantalla_login() -> None:
    """Formulario de inicio de sesión (CU1)."""
    st.title("🛡️ Dashboard BI: Delitos Informáticos en Colombia")
    st.caption("Inicia sesión para continuar")
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        with st.form("form_login"):
            email = st.text_input("Correo")
            password = st.text_input("Contraseña", type="password")
            enviar = st.form_submit_button("Iniciar sesión", use_container_width=True)
        if enviar:
            ok, mensaje = login(email.strip(), password)
            if ok:
                st.rerun()
            else:
                st.error(mensaje)