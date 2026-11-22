"""Pruebas de seguridad y control de acceso (TC-10 a TC-15 de la matriz)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest


@pytest.mark.caso("TC-10", modulo="Seguridad", puntos=10)
def test_endpoint_protegido_sin_token(cliente):
    """Un endpoint protegido sin token responde 401 Unauthorized"""
    for ruta in ("/usuarios", "/auth/me", "/auth/menu"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 401, f"{ruta} respondió {respuesta.status_code}"


@pytest.mark.caso("TC-11", modulo="Seguridad", puntos=10)
def test_token_vencido_es_rechazado(cliente, login_mod, tokens):
    """Un token JWT vencido responde 401 y es rechazado"""
    valido = jwt.decode(tokens["Administrador"], login_mod.SECRET_KEY, algorithms=[login_mod.ALGORITHM])
    vencido = jwt.encode(
        {"sub": valido["sub"], "rol": "Administrador",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
        login_mod.SECRET_KEY,
        algorithm=login_mod.ALGORITHM,
    )
    # Control: el token válido sí funciona
    assert cliente.get("/auth/me", headers={"Authorization": f"Bearer {tokens['Administrador']}"}).status_code == 200
    respuesta = cliente.get("/auth/me", headers={"Authorization": f"Bearer {vencido}"})
    assert respuesta.status_code == 401


@pytest.mark.caso("TC-12", modulo="Seguridad", puntos=10)
def test_consultor_no_puede_reentrenar_modelo(cliente, cabeceras):
    """Un consultor que llama el endpoint de reentrenar el modelo recibe 403"""
    respuesta = cliente.post("/modelo/reentrenar", headers=cabeceras["Consultor"])
    assert respuesta.status_code == 403


@pytest.mark.caso("TC-13", modulo="Seguridad", puntos=10)
def test_consultor_no_puede_gestionar_usuarios(cliente, cabeceras):
    """Un consultor que llama el endpoint de gestión de usuarios recibe 403"""
    assert cliente.get("/usuarios", headers=cabeceras["Consultor"]).status_code == 403
    nuevo = {"nombre": "Intruso", "email": "intruso@prueba.com", "password": "Intruso12345", "rol": "Administrador"}
    assert cliente.post("/usuarios", headers=cabeceras["Consultor"], json=nuevo).status_code == 403


@pytest.mark.caso("TC-14", modulo="Seguridad", puntos=10)
def test_analista_no_puede_ejecutar_etl(cliente, cabeceras):
    """Un analista que llama el endpoint de carga de datos y ETL recibe 403"""
    respuesta = cliente.post("/etl/ejecutar", headers=cabeceras["Analista"])
    assert respuesta.status_code == 403


@pytest.mark.caso("TC-15", modulo="Seguridad", puntos=10)
def test_contrasena_se_guarda_como_hash_bcrypt(cliente, login_mod, cabeceras):
    """La contraseña se guarda como hash bcrypt, nunca en texto plano"""
    clave = "ClaveSegura123"
    r = cliente.post(
        "/usuarios",
        headers=cabeceras["Administrador"],
        json={"nombre": "Usuario Hash", "email": "hash@prueba.com", "password": clave, "rol": "Consultor"},
    )
    assert r.status_code == 201, r.text
    guardado = login_mod.repo.por_email("hash@prueba.com")
    assert guardado["password_hash"] != clave
    assert guardado["password_hash"].startswith("$2")
    assert bcrypt.checkpw(clave.encode(), guardado["password_hash"].encode())
    assert clave not in str(guardado)
