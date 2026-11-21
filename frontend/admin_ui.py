"""
admin_ui.py - Pantalla de gestión de usuarios y roles (CU2, solo Administrador).
Consume los endpoints /usuarios del backend.
"""
import pandas as pd
import streamlit as st

from auth import api

ROLES = ["Administrador", "Analista", "Consultor"]


def _avisar_y_recargar(mensaje: str) -> None:
    st.session_state["flash"] = mensaje
    st.rerun()


def vista_usuarios() -> None:
    st.subheader("👥 Gestión de usuarios y roles")

    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))

    ok, usuarios = api("GET", "/usuarios")
    if not ok:
        st.error(usuarios)
        return

    st.dataframe(
        pd.DataFrame(usuarios)[["nombre", "email", "rol", "activo"]],
        use_container_width=True,
        hide_index=True,
    )

    tab_crear, tab_editar = st.tabs(["➕ Crear usuario", "✏️ Editar / eliminar"])

    # --- Crear ---------------------------------------------------------------
    with tab_crear:
        with st.form("form_crear", clear_on_submit=True):
            nombre = st.text_input("Nombre completo")
            email = st.text_input("Correo")
            password = st.text_input("Contraseña (mínimo 8 caracteres)", type="password")
            rol = st.selectbox("Rol", ROLES, index=1)
            crear = st.form_submit_button("Crear usuario")
        if crear:
            ok, resp = api(
                "POST",
                "/usuarios",
                json={"nombre": nombre.strip(), "email": email.strip(), "password": password, "rol": rol},
            )
            if ok:
                _avisar_y_recargar(f"Usuario {resp['email']} creado con rol {resp['rol']}.")
            else:
                st.error(resp)

    # --- Editar / eliminar ---------------------------------------------------
    with tab_editar:
        por_id = {u["id"]: u for u in usuarios}
        sel = st.selectbox(
            "Usuario",
            options=list(por_id),
            format_func=lambda i: f"{por_id[i]['nombre']} ({por_id[i]['email']})",
        )
        u = por_id[sel]

        with st.form(f"form_editar_{sel}"):
            nombre_n = st.text_input("Nombre", value=u["nombre"])
            rol_n = st.selectbox("Rol", ROLES, index=ROLES.index(u["rol"]))
            activo_n = st.checkbox("Activo", value=u["activo"])
            pass_n = st.text_input("Nueva contraseña (opcional)", type="password")
            guardar = st.form_submit_button("Guardar cambios")
        if guardar:
            cambios = {"nombre": nombre_n.strip(), "rol": rol_n, "activo": activo_n}
            if pass_n:
                cambios["password"] = pass_n
            ok, resp = api("PUT", f"/usuarios/{sel}", json=cambios)
            if ok:
                _avisar_y_recargar("Usuario actualizado.")
            else:
                st.error(resp)

        st.markdown("---")
        confirmar = st.checkbox("Confirmo que quiero eliminar este usuario", key=f"conf_{sel}")
        if st.button("🗑️ Eliminar usuario", disabled=not confirmar):
            ok, resp = api("DELETE", f"/usuarios/{sel}")
            if ok:
                _avisar_y_recargar("Usuario eliminado.")
            else:
                st.error(resp)