"""
conftest.py - Configuración común de las pruebas.

- Fuerza una base de datos de pruebas (bi_delitos_test): nunca se toca la real.
- En CI se usa MongoDB real (servicio de GitHub Actions). Si en tu PC no hay
  Mongo encendido, se usa mongomock (solo para desarrollo local).
- Registra el puntaje de cada prueba (ver puntuacion.py).
"""
import os
import sys
import types

import pandas as pd
import pytest

from puntuacion import Recolector

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUTA_RESULTADOS = os.path.join(RAIZ, "reports", "resultados.json")

# ---------------------------------------------------------------------------
# Entorno aislado de pruebas (antes de importar login.py)
# ---------------------------------------------------------------------------
os.environ["DB_NAME"] = "bi_delitos_test"
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas")
os.environ.setdefault("ADMIN_EMAIL", "admin@delitos.com")
os.environ.setdefault("ADMIN_PASSWORD", "Admin12345")


def _elegir_motor_bd() -> str:
    import pymongo

    try:
        pymongo.MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=1500).admin.command("ping")
        return "MongoDB real"
    except Exception:  # noqa: BLE001
        if os.getenv("EXIGIR_MONGO_REAL") == "1":
            raise pytest.UsageError("Se exige MongoDB real y no hay conexión en MONGO_URI.")
        try:
            import mongomock
        except ImportError:
            raise pytest.UsageError(
                "No hay MongoDB encendido en localhost:27017. Enciéndelo o instala mongomock."
            )
        # mongomock no soporta el validador $jsonSchema: se ignora solo en modo simulado
        crear_original = mongomock.database.Database.create_collection

        def crear_sin_validador(self, nombre, **kwargs):
            kwargs.pop("validator", None)
            return crear_original(self, nombre, **kwargs)

        mongomock.database.Database.create_collection = crear_sin_validador
        pymongo.MongoClient = mongomock.MongoClient
        return "mongomock (simulado, solo local)"


MOTOR_BD = _elegir_motor_bd()

# ---------------------------------------------------------------------------
# Puntaje por prueba
# ---------------------------------------------------------------------------
RECOLECTOR = Recolector()
RECOLECTOR.meta["motor_bd"] = MOTOR_BD


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultado = yield
    reporte = resultado.get_result()
    if reporte.when == "call" or (reporte.when == "setup" and not reporte.passed):
        RECOLECTOR.registrar(item, reporte)


def pytest_sessionfinish(session, exitstatus):
    RECOLECTOR.guardar(RUTA_RESULTADOS)


# ---------------------------------------------------------------------------
# Backend: base de datos, API y usuarios de prueba
# ---------------------------------------------------------------------------
PASSWORD_PRUEBA = "Prueba12345"
EMAIL_ADMIN = os.environ["ADMIN_EMAIL"]
PASSWORD_ADMIN = os.environ["ADMIN_PASSWORD"]
EMAIL_POR_ROL = {
    "Administrador": EMAIL_ADMIN,
    "Analista": "analista@prueba.com",
    "Consultor": "consultor@prueba.com",
}
PASSWORD_POR_ROL = {
    "Administrador": PASSWORD_ADMIN,
    "Analista": PASSWORD_PRUEBA,
    "Consultor": PASSWORD_PRUEBA,
}


@pytest.fixture(scope="session")
def login_mod():
    """Módulo login.py con la BD de pruebas limpia y el admin inicial creado."""
    import login

    db = login.MongoConexion().db
    db.drop_collection(login.COLECCION_USUARIOS)
    login.inicializar_bd()
    # Un usuario de prueba por perfil (el admin ya lo crea inicializar_bd)
    for rol in ("Analista", "Consultor"):
        login.repo.crear(
            login._nuevo_documento(f"Usuario {rol}", EMAIL_POR_ROL[rol], PASSWORD_POR_ROL[rol], rol)
        )
    yield login
    db.drop_collection(login.COLECCION_USUARIOS)


@pytest.fixture(scope="session")
def cliente(login_mod):
    from fastapi.testclient import TestClient

    return TestClient(login_mod.app)


@pytest.fixture(scope="session")
def tokens(cliente):
    """Token JWT de cada perfil (se obtiene una sola vez por sesión)."""
    resultado = {}
    for rol, email in EMAIL_POR_ROL.items():
        r = cliente.post("/auth/login", json={"email": email, "password": PASSWORD_POR_ROL[rol]})
        assert r.status_code == 200, f"No se pudo iniciar sesión como {rol}: {r.text}"
        resultado[rol] = r.json()["access_token"]
    return resultado


@pytest.fixture(scope="session")
def cabeceras(tokens):
    """Cabecera Authorization por perfil: cabeceras['Analista']."""
    return {rol: {"Authorization": f"Bearer {t}"} for rol, t in tokens.items()}


# ---------------------------------------------------------------------------
# Frontend: módulos falsos de datos/ML y puente front -> back
# ---------------------------------------------------------------------------
def _datos_demo() -> pd.DataFrame:
    filas = []
    for anio, factor in ((2022, 1), (2023, 2), (2024, 3)):
        for depto, muni in (("VALLE DEL CAUCA", "CALI"), ("ANTIOQUIA", "MEDELLIN")):
            for tipo in ("HURTO POR MEDIOS INFORMATICOS", "VIOLACION DE DATOS PERSONALES"):
                filas.append(
                    {"anio": anio, "mes": "ENERO", "departamento": depto, "municipio": muni,
                     "tipologia": tipo, "cantidad": 10 * factor}
                )
    return pd.DataFrame(filas)


@pytest.fixture
def datos_falsos(monkeypatch):
    """Reemplaza backend.db y ml.modelo por versiones pequeñas (el front se prueba aislado)."""
    df = _datos_demo()

    db = types.ModuleType("backend.db")
    db.consultar_datos_filtrados = lambda anio_range=None, meses=None, departamento="TODOS", \
        municipio="TODOS", tipologias=None: df
    db.obtener_metadatos_estado = lambda: (len(df), "2022 - 2024", 2, 2)

    ml = types.ModuleType("ml.modelo")
    ml.entrenar_y_predecir_siguiente_anio = lambda d: (
        pd.DataFrame({"tipologia": ["HURTO POR MEDIOS INFORMATICOS"], "casos_estimados_siguiente_anio": [42]}),
        "HURTO POR MEDIOS INFORMATICOS", 3.5, 2025,
    )
    monkeypatch.setitem(sys.modules, "backend.db", db)
    monkeypatch.setitem(sys.modules, "ml.modelo", ml)
    return df


class _RespuestaRequests:
    """Hace que una respuesta de TestClient (httpx) se vea como una de requests."""

    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.content = r.content
        self.ok = r.is_success

    def json(self):
        return self._r.json()


@pytest.fixture
def puente_front_back(cliente, monkeypatch):
    """Redirige las llamadas HTTP del frontend (requests) hacia la API real en memoria."""
    import requests

    from auth import API_URL

    def llamar(metodo, url, **kwargs):
        ruta = url.replace(API_URL, "")
        r = cliente.request(metodo, ruta, headers=kwargs.get("headers"), json=kwargs.get("json"))
        return _RespuestaRequests(r)

    monkeypatch.setattr(requests, "post", lambda url, **kw: llamar("POST", url, **kw))
    monkeypatch.setattr(requests, "get", lambda url, **kw: llamar("GET", url, **kw))
    monkeypatch.setattr(requests, "request", lambda metodo, url, **kw: llamar(metodo, url, **kw))
