"""
exportar_para_powerbi.py
------------------------
Lee los datos desde MongoDB (la MISMA fuente que usa el dashboard de Streamlit)
y genera un archivo Excel con el modelo en estrella listo para importar en Power BI.

Uso (desde la carpeta raíz del repositorio, con el entorno virtual activo):

    pip install xlsxwriter
    python powerbi/exportar_para_powerbi.py

Opciones:
    --sin-prediccion   No calcula la tabla de predicciones (más rápido).

Variables de entorno opcionales:
    MONGO_URI   (por defecto mongodb://localhost:27017/)
    MONGO_DB    (por defecto bi_delitos_db)

Salida: powerbi/salida/ciberdelitos_powerbi.xlsx

Al terminar, el script también escribe la ruta REAL del Excel (la de este computador) en los
proyectos de Power BI (parámetro RutaExcel), para que baste con abrir el .pbip y pulsar Actualizar.
En el repositorio esa ruta está como valor neutro; ver la sección "Power BI" del README.
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))  # para poder importar ml.modelo

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB", "bi_delitos_db")
COLECCION = "delitos_informaticos"
SALIDA = RAIZ / "powerbi" / "salida" / "ciberdelitos_powerbi.xlsx"

COLUMNAS_OBLIGATORIAS = {"fecha", "anio", "departamento", "municipio", "tipologia", "cantidad"}

# La base guarda el código del artículo (Ley 1273 de 2009); aquí su nombre corto y legible.
NOMBRES_TIPOLOGIA = {
    "269A": "Hacking",
    "269B": "DDoS",
    "269C": "Sniffing",
    "269D": "Ransomware",
    "269E": "Malware",
    "269F": "Data breach",
    "269G": "Phishing",
    "269H": "Agravación punitiva",
    "269I": "Fraude informático",
    "269J": "Fraude financiero",
}

MESES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
         7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre",
         12: "Diciembre"}


def leer_mongo() -> pd.DataFrame:
    """Lee la colección completa. Si Mongo no responde, se detiene (no usa TinyDB)."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
    except PyMongoError as e:
        sys.exit(f"[ERROR] No se pudo conectar a MongoDB en {MONGO_URI}: {e}")

    docs = list(client[DB_NAME][COLECCION].find({}, {"_id": 0}))
    if not docs:
        sys.exit(f"[ERROR] La colección {DB_NAME}.{COLECCION} está vacía. Ejecuta primero el ETL.")

    df = pd.DataFrame(docs)
    faltan = COLUMNAS_OBLIGATORIAS - set(df.columns)
    if faltan:
        sys.exit(f"[ERROR] Faltan columnas en la colección: {sorted(faltan)}")

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["anio"] = df["anio"].astype(int)
    df["cantidad"] = df["cantidad"].astype(int)
    return df


def construir_tablas(df: pd.DataFrame) -> dict:
    # --- dim_departamento -------------------------------------------------
    dim_departamento = (df[["departamento"]].drop_duplicates()
                        .sort_values("departamento").reset_index(drop=True))

    # --- dim_geografia (un municipio puede repetirse en varios departamentos,
    #     por eso se usa una llave numérica) --------------------------------
    dim_geografia = (df[["departamento", "municipio"]].drop_duplicates()
                     .sort_values(["departamento", "municipio"]).reset_index(drop=True))
    dim_geografia.insert(0, "id_geografia", dim_geografia.index + 1)

    # --- dim_tipologia ----------------------------------------------------
    codigos = sorted(df["tipologia"].unique())
    dim_tipologia = pd.DataFrame({
        "codigo_tipologia": codigos,
        "tipologia": [NOMBRES_TIPOLOGIA.get(c, c) for c in codigos],
    })

    # --- fact_incidentes --------------------------------------------------
    fact = (df.merge(dim_geografia, on=["departamento", "municipio"], how="left")
              .rename(columns={"tipologia": "codigo_tipologia"})
              [["fecha", "id_geografia", "codigo_tipologia", "cantidad"]]
              .sort_values("fecha").reset_index(drop=True))

    # --- dim_fecha: llega SOLO hasta la última fecha con datos, para que la
    #     comparación contra el mismo periodo del año anterior sea justa -----
    fmin, fmax = df["fecha"].min(), df["fecha"].max()
    fechas = pd.date_range(f"{fmin.year}-01-01", fmax.normalize(), freq="D")
    dim_fecha = pd.DataFrame({"fecha": fechas})
    dim_fecha["anio"] = dim_fecha["fecha"].dt.year
    dim_fecha["mes_num"] = dim_fecha["fecha"].dt.month
    dim_fecha["mes"] = dim_fecha["mes_num"].map(MESES)
    dim_fecha["trimestre"] = "T" + dim_fecha["fecha"].dt.quarter.astype(str)
    dim_fecha["anio_mes"] = dim_fecha["fecha"].dt.strftime("%Y-%m")

    return {
        "fact_incidentes": fact,
        "dim_fecha": dim_fecha,
        "dim_departamento": dim_departamento,
        "dim_geografia": dim_geografia,
        "dim_tipologia": dim_tipologia,
    }


def construir_predicciones(df: pd.DataFrame) -> pd.DataFrame:
    """Usa el modelo actual (ml/modelo.py) sin modificarlo: una vez a nivel
    nacional y una vez por departamento."""
    from ml.modelo import entrenar_y_predecir_siguiente_anio

    ambitos = [("NACIONAL", "Nacional", df)]
    for depto, sub in df.groupby("departamento"):
        ambitos.append((depto, "Departamento", sub))

    piezas = []
    for etiqueta, ambito, sub in ambitos:
        df_pred, _, mae, anio = entrenar_y_predecir_siguiente_anio(sub)
        if df_pred is None or df_pred.empty:
            continue
        out = df_pred.rename(columns={
            "tipologia": "codigo_tipologia",
            "casos_historicos_ultimo_anio": "casos_ultimo_anio",
            "casos_estimados_siguiente_anio": "casos_estimados",
        }).copy()
        out.insert(0, "ambito", ambito)
        out.insert(1, "departamento", etiqueta)
        out["anio_proyectado"] = int(anio)
        out["mae_modelo"] = round(float(mae), 2)
        piezas.append(out)

    if not piezas:
        return pd.DataFrame(columns=["ambito", "departamento", "codigo_tipologia",
                                     "casos_ultimo_anio", "casos_estimados",
                                     "anio_proyectado", "mae_modelo"])
    return pd.concat(piezas, ignore_index=True)


def tabla_control(df: pd.DataFrame) -> pd.DataFrame:
    """Cifras para comparar contra Power BI después de importar."""
    ctrl = df.groupby("anio").agg(registros=("cantidad", "size"),
                                  casos=("cantidad", "sum")).reset_index()
    total = pd.DataFrame([{"anio": "TOTAL", "registros": ctrl["registros"].sum(),
                           "casos": ctrl["casos"].sum()}])
    return pd.concat([ctrl.astype({"anio": str}), total], ignore_index=True)


def verificar_integridad(tablas: dict, df: pd.DataFrame) -> None:
    f = tablas["fact_incidentes"]
    assert len(f) == len(df), "Se perdieron o duplicaron filas al unir con geografía"
    assert f["id_geografia"].notna().all(), "Hay filas sin geografía"
    assert f["cantidad"].sum() == df["cantidad"].sum(), "No coincide el total de casos"
    assert set(f["codigo_tipologia"]) <= set(tablas["dim_tipologia"]["codigo_tipologia"])
    assert f["fecha"].between(tablas["dim_fecha"]["fecha"].min(),
                              tablas["dim_fecha"]["fecha"].max()).all()


def actualizar_ruta_en_proyectos(ruta_excel: Path, carpeta_powerbi: Path = None) -> list:
    """Escribe la ruta del Excel (parámetro RutaExcel) en cada proyecto de Power BI (.SemanticModel).
    Conserva los saltos de línea del archivo. Devuelve los archivos modificados."""
    carpeta_powerbi = carpeta_powerbi or (RAIZ / "powerbi")
    patron = re.compile(r'(expression RutaExcel = ")[^"]*(")')
    cambiados = []
    for tmdl in sorted(carpeta_powerbi.glob("*/*.SemanticModel/definition/expressions.tmdl")):
        texto = tmdl.read_bytes().decode("utf-8")
        nuevo = patron.sub(lambda m: m.group(1) + str(ruta_excel) + m.group(2), texto, count=1)
        if nuevo != texto:
            tmdl.write_bytes(nuevo.encode("utf-8"))
            cambiados.append(tmdl)
    return cambiados


def main() -> None:
    con_prediccion = "--sin-prediccion" not in sys.argv

    print(f"[1/4] Leyendo MongoDB ({MONGO_URI} -> {DB_NAME}.{COLECCION}) ...")
    df = leer_mongo()
    print(f"      {len(df):,} registros, {int(df['cantidad'].sum()):,} casos, "
          f"{df['fecha'].min().date()} a {df['fecha'].max().date()}")

    print("[2/4] Construyendo tablas del modelo en estrella ...")
    tablas = construir_tablas(df)
    verificar_integridad(tablas, df)

    if con_prediccion:
        print("[3/4] Calculando predicciones (nacional + por departamento) ...")
        tablas["fact_prediccion"] = construir_predicciones(df)
    else:
        print("[3/4] Predicciones omitidas (--sin-prediccion)")

    tablas["control"] = tabla_control(df)

    print(f"[4/4] Escribiendo {SALIDA} ...")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SALIDA, engine="xlsxwriter",
                        datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
        for nombre, tabla in tablas.items():
            tabla.to_excel(xw, sheet_name=nombre, index=False)

    print("\nTablas generadas:")
    for nombre, tabla in tablas.items():
        print(f"  - {nombre:<18} {len(tabla):>8,} filas")
    print("\nCIFRAS DE CONTROL (compáralas con Power BI):")
    print(tablas["control"].to_string(index=False))

    modificados = actualizar_ruta_en_proyectos(SALIDA.resolve())
    if modificados:
        print(f"\nRuta del Excel actualizada en {len(modificados)} proyecto(s) de Power BI:")
        archivos = []
        for f in modificados:
            rel = f.relative_to(RAIZ).as_posix()
            archivos.append(rel)
            print(f"  - {rel}")
        print("\nPara que git NO suba tu ruta personal, ejecuta UNA vez (por computador):")
        print("  git update-index --skip-worktree " + " ".join(archivos))


if __name__ == "__main__":
    main()
