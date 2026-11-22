"""Pruebas del backend: login, menú por rol y gestión de usuarios (CU1 y CU2)."""
import pytest

from conftest import EMAIL_POR_ROL, PASSWORD_POR_ROL

CASOS_POR_ROL = {
    "Administrador": {2, 3},
    "Analista": {4, 5, 6, 7, 11},
    "Consultor": {8, 9, 10, 11},
}


@pytest.mark.caso("BE-01", modulo="Backend", puntos=5)
def test_login_correcto_devuelve_token_rol_y_menu(cliente):
    """Login correcto devuelve token, rol y menú del usuario"""
    r = cliente.post("/auth/login", json={"email": EMAIL_POR_ROL["Analista"], "password": PASSWORD_POR_ROL["Analista"]})
    assert r.status_code == 200
    datos = r.json()
    assert datos["access_token"] and datos["rol"] == "Analista"
    assert {i["caso_uso"] for i in datos["menu"]} == CASOS_POR_ROL["Analista"]


@pytest.mark.caso("BE-02", modulo="Backend", puntos=5)
def test_credenciales_incorrectas_dan_el_mismo_error(cliente):
    """Contraseña incorrecta y correo inexistente responden 401 con el mismo mensaje"""
    mala = cliente.post("/auth/login", json={"email": EMAIL_POR_ROL["Analista"], "password": "incorrecta1"})
    inexistente = cliente.post("/auth/login", json={"email": "nadie@prueba.com", "password": "incorrecta1"})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json()["detail"] == inexistente.json()["detail"]


@pytest.mark.caso("BE-03", modulo="Backend", puntos=5)
def test_menu_de_cada_rol_coincide_con_el_diagrama(login_mod):
    """El menú de cada rol corresponde a los casos de uso del diagrama"""
    for rol, esperados in CASOS_POR_ROL.items():
        obtenidos = {i["caso_uso"] for i in login_mod.menu_por_rol(rol)}
        assert obtenidos == esperados, f"{rol}: esperado {esperados}, obtenido {obtenidos}"


@pytest.mark.caso("BE-04", modulo="Backend", puntos=5)
def test_usuario_desactivado_pierde_el_acceso(cliente, cabeceras):
    """Al desactivar un usuario, su token deja de funcionar de inmediato"""
    admin = cabeceras["Administrador"]
    creado = cliente.post("/usuarios", headers=admin, json={
        "nombre": "Temporal", "email": "temporal@prueba.com", "password": "Temporal12345", "rol": "Analista"}).json()
    token = cliente.post("/auth/login", json={"email": "temporal@prueba.com", "password": "Temporal12345"}).json()["access_token"]
    asi = {"Authorization": f"Bearer {token}"}
    assert cliente.get("/auth/me", headers=asi).status_code == 200

    assert cliente.put(f"/usuarios/{creado['id']}", headers=admin, json={"activo": False}).status_code == 200
    assert cliente.get("/auth/me", headers=asi).status_code == 401
    r = cliente.post("/auth/login", json={"email": "temporal@prueba.com", "password": "Temporal12345"})
    assert r.status_code == 403


@pytest.mark.caso("BE-05", modulo="Backend", puntos=5)
def test_no_permite_correo_duplicado(cliente, cabeceras):
    """Crear un usuario con un correo ya registrado responde 409"""
    datos = {"nombre": "Repetido", "email": EMAIL_POR_ROL["Consultor"], "password": "Repetido12345", "rol": "Consultor"}
    assert cliente.post("/usuarios", headers=cabeceras["Administrador"], json=datos).status_code == 409


@pytest.mark.caso("BE-06", modulo="Backend", puntos=5)
def test_valida_rol_y_longitud_de_contrasena(cliente, cabeceras):
    """Un rol inexistente o una contraseña corta responden 422"""
    admin = cabeceras["Administrador"]
    base = {"nombre": "Validar", "email": "validar@prueba.com", "password": "Validar12345", "rol": "Consultor"}
    assert cliente.post("/usuarios", headers=admin, json={**base, "rol": "SuperAdmin"}).status_code == 422
    assert cliente.post("/usuarios", headers=admin, json={**base, "password": "corta"}).status_code == 422


@pytest.mark.caso("BE-07", modulo="Backend", puntos=5)
def test_el_admin_no_puede_quitarse_el_acceso_a_si_mismo(cliente, cabeceras):
    """El administrador no puede eliminarse, desactivarse ni cambiarse el rol"""
    admin = cabeceras["Administrador"]
    mi_id = cliente.get("/auth/me", headers=admin).json()["id"]
    assert cliente.delete(f"/usuarios/{mi_id}", headers=admin).status_code == 400
    assert cliente.put(f"/usuarios/{mi_id}", headers=admin, json={"rol": "Consultor"}).status_code == 400
    assert cliente.put(f"/usuarios/{mi_id}", headers=admin, json={"activo": False}).status_code == 400


@pytest.mark.caso("BE-08", modulo="Backend", puntos=5)
def test_crud_completo_de_usuarios(cliente, cabeceras):
    """El administrador crea, edita, lista y elimina un usuario"""
    admin = cabeceras["Administrador"]
    creado = cliente.post("/usuarios", headers=admin, json={
        "nombre": "Ciclo Vida", "email": "ciclo@prueba.com", "password": "Ciclo12345", "rol": "Consultor"})
    assert creado.status_code == 201
    uid = creado.json()["id"]

    editado = cliente.put(f"/usuarios/{uid}", headers=admin, json={"rol": "Analista"})
    assert editado.status_code == 200 and editado.json()["rol"] == "Analista"
    assert any(u["id"] == uid for u in cliente.get("/usuarios", headers=admin).json())

    assert cliente.delete(f"/usuarios/{uid}", headers=admin).status_code == 204
    assert cliente.delete(f"/usuarios/{uid}", headers=admin).status_code == 404


@pytest.mark.caso("BE-09", modulo="Backend", puntos=5)
def test_bd_tiene_indice_unico_de_correo(login_mod):
    """La colección usuarios tiene un índice único sobre el correo"""
    indices = login_mod.repo.col.index_information()
    assert "uq_email" in indices and indices["uq_email"].get("unique") is True


@pytest.mark.caso("BE-10", modulo="Backend", puntos=5)
def test_admin_pasa_el_control_de_acceso_del_pipeline(cliente, cabeceras, monkeypatch):
    """El administrador sí puede ejecutar el ETL y el analista reentrenar (control positivo)"""
    import servicios

    monkeypatch.setattr(servicios, "ejecutar_etl", lambda: {"exito": True, "salida": "simulado"})
    monkeypatch.setattr(servicios, "reentrenar_modelo", lambda: {"entrenado": True})
    assert cliente.post("/etl/ejecutar", headers=cabeceras["Administrador"]).json()["exito"] is True
    assert cliente.post("/modelo/reentrenar", headers=cabeceras["Analista"]).json()["entrenado"] is True
