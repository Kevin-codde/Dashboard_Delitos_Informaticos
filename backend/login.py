"""
login.py - Autenticación, roles y gestión de usuarios
Sistema de Gestión y Predicción de Ciberataques (FastAPI + MongoDB local)

Ejecutar desde la carpeta backend:
    uvicorn login:app --reload --port 8000
Documentación interactiva: http://localhost:8000/docs

Patrones de diseño usados:
    - Singleton   -> MongoConexion (una sola conexión a Mongo)
    - Repository  -> UsuarioRepository (todo el acceso a la colección usuarios)
    - Dependency Injection -> usuario_actual() / requiere_permiso() de FastAPI
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "bi_delitos_db")
COLECCION_USUARIOS = "usuarios"

SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
ALGORITHM = "HS256"
TOKEN_MINUTOS = 60

# Administrador por defecto (se crea solo si no existe ningún usuario)
ADMIN_NOMBRE = os.getenv("ADMIN_NOMBRE", "Administrador del sistema")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@delitos.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin12345")

# ----------------------------------------------------------------------------
# Roles y permisos (según el diagrama de casos de uso)
# El caso de uso 1 (Iniciar sesión) aplica a todos los roles.
# ----------------------------------------------------------------------------
ROL_ADMIN = "Administrador"
ROL_ANALISTA = "Analista"
ROL_CONSULTOR = "Consultor"
ROLES = (ROL_ADMIN, ROL_ANALISTA, ROL_CONSULTOR)

# permiso -> (número de caso de uso, texto del menú, roles autorizados)
PERMISOS = {
    "gestionar_usuarios":        (2,  "Gestionar usuarios y roles",       (ROL_ADMIN,)),
    "ejecutar_etl":              (3,  "Ejecutar pipeline ETL de datos",   (ROL_ADMIN,)),
    "consultar_incidentes":      (4,  "Consultar y filtrar incidentes",   (ROL_ANALISTA,)),
    "mapa_calor":                (5,  "Visualizar mapa de calor",         (ROL_ANALISTA,)),
    "entrenar_modelo":           (6,  "Entrenar modelo predictivo ML",    (ROL_ANALISTA,)),
    "consultar_metricas":        (7,  "Consultar métricas MAE/RMSE/MAPE", (ROL_ANALISTA,)),
    "resumen_ejecutivo":         (8,  "Visualizar resumen ejecutivo",     (ROL_CONSULTOR,)),
    "predicciones_departamento": (9,  "Consultar predicciones por departamento", (ROL_CONSULTOR,)),
    "tableros_powerbi":          (10, "Consultar tableros de Power BI",   (ROL_CONSULTOR,)),
    "exportar_reportes":         (11, "Exportar reportes PDF / CSV",      (ROL_ANALISTA, ROL_CONSULTOR)),
}


def menu_por_rol(rol: str) -> list[dict]:
    """Opciones de menú que le corresponden a un rol (ordenadas por caso de uso)."""
    items = [
        {"caso_uso": cu, "permiso": permiso, "opcion": texto}
        for permiso, (cu, texto, roles) in PERMISOS.items()
        if rol in roles
    ]
    return sorted(items, key=lambda i: i["caso_uso"])


# ----------------------------------------------------------------------------
# Base de datos: Singleton + Repository
# ----------------------------------------------------------------------------
class MongoConexion:
    """Singleton: garantiza una sola instancia de MongoClient en toda la app."""

    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            cls._instancia.db = cls._instancia.client[DB_NAME]
        return cls._instancia


def _object_id(valor: str) -> ObjectId:
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")


class UsuarioRepository:
    """Repository: encapsula todas las operaciones sobre la colección usuarios."""

    def __init__(self):
        self.col = MongoConexion().db[COLECCION_USUARIOS]

    def crear(self, doc: dict) -> dict:
        self.col.insert_one(doc)
        return doc

    def por_email(self, email: str) -> Optional[dict]:
        return self.col.find_one({"email": email.lower()})

    def por_id(self, usuario_id: str) -> Optional[dict]:
        return self.col.find_one({"_id": _object_id(usuario_id)})

    def listar(self) -> list[dict]:
        return list(self.col.find().sort("nombre", ASCENDING))

    def actualizar(self, usuario_id: str, cambios: dict) -> Optional[dict]:
        return self.col.find_one_and_update(
            {"_id": _object_id(usuario_id)},
            {"$set": cambios},
            return_document=ReturnDocument.AFTER,
        )

    def eliminar(self, usuario_id: str) -> bool:
        return self.col.delete_one({"_id": _object_id(usuario_id)}).deleted_count == 1

    def contar(self) -> int:
        return self.col.count_documents({})


repo = UsuarioRepository()


def inicializar_bd() -> None:
    """Crea (si no existen) la colección con validación, el índice único y el admin inicial."""
    db = MongoConexion().db

    if COLECCION_USUARIOS not in db.list_collection_names():
        db.create_collection(
            COLECCION_USUARIOS,
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["nombre", "email", "password_hash", "rol", "activo", "creado_en"],
                    "properties": {
                        "nombre": {"bsonType": "string"},
                        "email": {"bsonType": "string"},
                        "password_hash": {"bsonType": "string"},
                        "rol": {"enum": list(ROLES)},
                        "activo": {"bsonType": "bool"},
                        "creado_en": {"bsonType": "date"},
                        "ultimo_acceso": {"bsonType": ["date", "null"]},
                    },
                }
            },
        )

    # El email no se puede repetir
    db[COLECCION_USUARIOS].create_index([("email", ASCENDING)], unique=True, name="uq_email")

    if repo.contar() == 0:
        repo.crear(_nuevo_documento(ADMIN_NOMBRE, ADMIN_EMAIL, ADMIN_PASSWORD, ROL_ADMIN))
        print(f"[login] Administrador inicial creado: {ADMIN_EMAIL}")


# ----------------------------------------------------------------------------
# Seguridad: contraseñas y JWT
# ----------------------------------------------------------------------------
def hashear(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def crear_token(usuario: dict) -> str:
    payload = {
        "sub": str(usuario["_id"]),
        "rol": usuario["rol"],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTOS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _nuevo_documento(nombre: str, email: str, password: str, rol: str) -> dict:
    return {
        "nombre": nombre,
        "email": email.lower(),
        "password_hash": hashear(password),
        "rol": rol,
        "activo": True,
        "creado_en": datetime.now(timezone.utc),
        "ultimo_acceso": None,
    }


# ----------------------------------------------------------------------------
# Modelos (Pydantic)
# ----------------------------------------------------------------------------
class LoginEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    rol: str


class UsuarioActualizar(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=100)
    rol: Optional[str] = None
    activo: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class UsuarioSalida(BaseModel):
    id: str
    nombre: str
    email: str
    rol: str
    activo: bool


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    nombre: str
    rol: str
    menu: list[dict]


def a_salida(u: dict) -> UsuarioSalida:
    return UsuarioSalida(
        id=str(u["_id"]), nombre=u["nombre"], email=u["email"], rol=u["rol"], activo=u["activo"]
    )


def _validar_rol(rol: str) -> None:
    if rol not in ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Rol inválido. Opciones: {', '.join(ROLES)}"
        )


# ----------------------------------------------------------------------------
# Dependencias de autenticación / autorización
# ----------------------------------------------------------------------------
bearer = HTTPBearer()


def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Valida el token y recarga el usuario desde la BD (así un cambio de rol o
    una desactivación se aplican de inmediato)."""
    no_autorizado = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credenciales.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        usuario = repo.por_id(payload["sub"])
    except (jwt.PyJWTError, KeyError, HTTPException):
        raise no_autorizado
    if not usuario or not usuario["activo"]:
        raise no_autorizado
    return usuario


def requiere_permiso(permiso: str):
    """Uso:  Depends(requiere_permiso("ejecutar_etl"))  en cualquier ruta."""
    roles_permitidos = PERMISOS[permiso][2]

    def verificador(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario["rol"] not in roles_permitidos:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para esta acción"
            )
        return usuario

    return verificador


# ----------------------------------------------------------------------------
# Aplicación FastAPI
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    inicializar_bd()
    yield


app = FastAPI(title="Login - Gestión y Predicción de Ciberataques", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],  # Streamlit
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- CU1: Iniciar sesión (todos los roles) ---------------------------------
@app.post("/auth/login", response_model=TokenSalida, tags=["Autenticación"])
def login(datos: LoginEntrada):
    usuario = repo.por_email(datos.email)
    if not usuario or not verificar(datos.password, usuario["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    if not usuario["activo"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario desactivado")

    repo.actualizar(str(usuario["_id"]), {"ultimo_acceso": datetime.now(timezone.utc)})
    return TokenSalida(
        access_token=crear_token(usuario),
        nombre=usuario["nombre"],
        rol=usuario["rol"],
        menu=menu_por_rol(usuario["rol"]),
    )


@app.get("/auth/me", response_model=UsuarioSalida, tags=["Autenticación"])
def perfil(usuario: dict = Depends(usuario_actual)):
    return a_salida(usuario)


@app.get("/auth/menu", tags=["Autenticación"])
def menu(usuario: dict = Depends(usuario_actual)):
    """Menú dinámico según el rol (lo consume el frontend)."""
    return {"rol": usuario["rol"], "menu": menu_por_rol(usuario["rol"])}


# --- CU2: Gestionar usuarios y roles (solo Administrador) ------------------
@app.get("/usuarios", response_model=list[UsuarioSalida], tags=["Usuarios (Admin)"])
def listar_usuarios(_: dict = Depends(requiere_permiso("gestionar_usuarios"))):
    return [a_salida(u) for u in repo.listar()]


@app.post(
    "/usuarios",
    response_model=UsuarioSalida,
    status_code=status.HTTP_201_CREATED,
    tags=["Usuarios (Admin)"],
)
def crear_usuario(datos: UsuarioCrear, _: dict = Depends(requiere_permiso("gestionar_usuarios"))):
    _validar_rol(datos.rol)
    doc = _nuevo_documento(datos.nombre, datos.email, datos.password, datos.rol)
    try:
        repo.crear(doc)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    return a_salida(doc)


@app.put("/usuarios/{usuario_id}", response_model=UsuarioSalida, tags=["Usuarios (Admin)"])
def actualizar_usuario(
    usuario_id: str,
    datos: UsuarioActualizar,
    admin: dict = Depends(requiere_permiso("gestionar_usuarios")),
):
    cambios = datos.model_dump(exclude_none=True)
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay cambios para aplicar")
    if "rol" in cambios:
        _validar_rol(cambios["rol"])

    # Un admin no puede quitarse a sí mismo el rol ni desactivarse
    if str(admin["_id"]) == usuario_id and (
        cambios.get("rol", ROL_ADMIN) != ROL_ADMIN or cambios.get("activo") is False
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "No puedes cambiar tu propio rol ni desactivarte"
        )

    if "password" in cambios:
        cambios["password_hash"] = hashear(cambios.pop("password"))

    actualizado = repo.actualizar(usuario_id, cambios)
    if not actualizado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return a_salida(actualizado)


@app.delete("/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Usuarios (Admin)"])
def eliminar_usuario(usuario_id: str, admin: dict = Depends(requiere_permiso("gestionar_usuarios"))):
    if str(admin["_id"]) == usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes eliminar tu propia cuenta")
    if not repo.eliminar(usuario_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")