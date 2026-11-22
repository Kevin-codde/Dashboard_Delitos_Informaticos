"""
servicios.py - Lógica que ejecutan los endpoints del pipeline (ETL y modelo).
Se mantiene separada de login.py para poder reemplazarla en las pruebas.
"""
import os
import subprocess
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ejecutar_etl() -> dict:
    """Corre etl/etl.py en un proceso aparte y devuelve el resultado."""
    r = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "etl", "etl.py")],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        env={**os.environ, "PYTHONPATH": RAIZ},
        timeout=600,
    )
    return {"exito": r.returncode == 0, "salida": (r.stdout + r.stderr)[-4000:]}


def reentrenar_modelo() -> dict:
    """Reentrena el modelo con todos los datos de MongoDB y devuelve la predicción."""
    if RAIZ not in sys.path:
        sys.path.append(RAIZ)
    from backend.db import consultar_datos_filtrados
    from ml.modelo import entrenar_y_predecir_siguiente_anio

    df = consultar_datos_filtrados()
    df_pred, tipo_riesgo, mae, anio_futuro = entrenar_y_predecir_siguiente_anio(df)
    if df_pred is None or df_pred.empty:
        return {"entrenado": False, "detalle": "No hay suficientes años de datos para entrenar."}
    return {
        "entrenado": True,
        "anio_proyectado": int(anio_futuro),
        "tipologia_mayor_riesgo": str(tipo_riesgo),
        "mae": float(mae),
        "predicciones": df_pred.to_dict("records"),
    }