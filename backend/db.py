"""
Módulo de acceso a datos (db.py)
Gestión de conexión NoSQL (MongoDB local con fallback a TinyDB) y consultas.
"""

import os
import pandas as pd

# Intentar importar pymongo y tinydb
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

try:
    from tinydb import TinyDB, Query
    HAS_TINYDB = True
except ImportError:
    HAS_TINYDB = False


DB_NAME = "bi_delitos_db"
COLLECTION_NAME = "delitos_informaticos"
TINYDB_FILE = "delitos_db.json"


def check_mongo_connection(uri="mongodb://localhost:27017/", timeout_ms=2000):
    """Verifica si MongoDB local está activo y respondiendo."""
    if not HAS_PYMONGO:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command('ping')
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError):
        return None


def get_db_engine():
    """
    Retorna el motor de base de datos disponible.
    Prioridad: 1. MongoDB Local -> 2. TinyDB Local.
    """
    client = check_mongo_connection()
    if client:
        return {"type": "mongodb", "client": client, "db": client[DB_NAME]}
    elif HAS_TINYDB:
        db = TinyDB(TINYDB_FILE)
        return {"type": "tinydb", "db": db}
    else:
        raise RuntimeError("No se encontró ni MongoDB ni TinyDB instalados.")


def cargar_datos_nosql(df: pd.DataFrame):
    """
    Inserta o reemplaza el dataframe limpio en la base NoSQL elegida.
    """
    engine = get_db_engine()
    records = df.to_dict(orient="records")

    # Asegurar tipos nativos de Python para JSON/BSON
    for r in records:
        if isinstance(r.get('fecha'), pd.Timestamp):
            r['fecha'] = r['fecha'].strftime('%Y-%m-%d')

    if engine["type"] == "mongodb":
        db = engine["db"]
        collection = db[COLLECTION_NAME]
        collection.drop()  # Limpiar carga previa para idempotencia
        if records:
            collection.insert_many(records)
        print(f"[BD] MongoDB: Se insertaron {len(records)} registros exitosamente.")
    else:
        db = engine["db"]
        db.truncate()  # Limpiar carga previa
        if records:
            db.insert_multiple(records)
        print(f"[BD] TinyDB (Fallback): Se insertaron {len(records)} registros en '{TINYDB_FILE}'.")


def consultar_datos_filtrados(anio_range=None, meses=None, departamento=None, municipio=None, tipologias=None) -> pd.DataFrame:
    """
    Realiza la consulta de datos aplicando los filtros de la historia de usuario HU2.
    """
    engine = get_db_engine()

    if engine["type"] == "mongodb":
        collection = engine["db"][COLLECTION_NAME]
        query = {}

        if anio_range:
            query["anio"] = {"$gte": int(anio_range[0]), "$lte": int(anio_range[1])}
        if meses:
            query["mes_nombre"] = {"$in": meses}
        if departamento and departamento != "TODOS":
            query["departamento"] = departamento
        if municipio and municipio != "TODOS":
            query["municipio"] = municipio
        if tipologias:
            query["tipologia"] = {"$in": tipologias}

        cursor = collection.find(query, {"_id": 0})
        df = pd.DataFrame(list(cursor))
    else:
        db = engine["db"]
        Q = Query()
        
        def match_record(r):
            if anio_range and not (anio_range[0] <= r.get("anio", 0) <= anio_range[1]):
                return False
            if meses and r.get("mes_nombre") not in meses:
                return False
            if departamento and departamento != "TODOS" and r.get("departamento") != departamento:
                return False
            if municipio and municipio != "TODOS" and r.get("municipio") != municipio:
                return False
            if tipologias and r.get("tipologia") not in tipologias:
                return False
            return True

        res = db.search(match_record)
        df = pd.DataFrame(res)

    if not df.empty and "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"])

    return df


def obtener_metadatos_estado():
    """Retorna métricas generales para la sección 'Estado de los datos' (HU1)."""
    engine = get_db_engine()
    if engine["type"] == "mongodb":
        col = engine["db"][COLLECTION_NAME]
        total = col.count_documents({})
        if total == 0:
            return 0, "N/A", 0, 0
        
        deptos = len(col.distinct("departamento"))
        tipos = len(col.distinct("tipologia"))
        
        min_doc = col.find_one(sort=[("anio", 1)])
        max_doc = col.find_one(sort=[("anio", -1)])
        rango_fechas = f"{min_doc.get('anio', 'N/A')} - {max_doc.get('anio', 'N/A')}"
        return total, rango_fechas, deptos, tipos
    else:
        db = engine["db"]
        docs = db.all()
        total = len(docs)
        if total == 0:
            return 0, "N/A", 0, 0
        df = pd.DataFrame(docs)
        deptos = df["departamento"].nunique() if "departamento" in df.columns else 0
        tipos = df["tipologia"].nunique() if "tipologia" in df.columns else 0
        min_a = df["anio"].min() if "anio" in df.columns else "N/A"
        max_a = df["anio"].max() if "anio" in df.columns else "N/A"
        return total, f"{min_a} - {max_a}", deptos, tipos