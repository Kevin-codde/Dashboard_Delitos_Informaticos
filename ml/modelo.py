"""
Módulo de Inteligencia Artificial / Predicción (modelo.py)
Proyecciones de series de tiempo por tipología penal mediante Random Forest.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


def entrenar_y_predecir_siguiente_anio(df: pd.DataFrame):
    """
    Entrena un modelo predictivo sobre la serie temporal de delitos por tipología (HU5).
    Calcula la estimación para el año futuro consecutivo y reporta la métrica MAE.
    """
    if df.empty or 'anio' not in df.columns or 'tipologia' not in df.columns:
        return None, "Sin datos suficientes", 0.0, 0

    # Agrupar casos por Año y Tipología
    df_agrupado = df.groupby(['anio', 'tipologia'])['cantidad'].sum().reset_index()
    
    anios_disponibles = sorted(df_agrupado['anio'].unique())
    if len(anios_disponibles) < 2:
        return None, "Requiere al menos 2 años de datos históricos", 0.0, 0

    ultimo_anio = max(anios_disponibles)
    siguiente_anio = ultimo_anio + 1

    resultados = []
    maes = []

    tipologias = df_agrupado['tipologia'].unique()

    for tipo in tipologias:
        df_tipo = df_agrupado[df_agrupado['tipologia'] == tipo].sort_values('anio')
        
        # Completar años faltantes con 0 casos
        full_years = pd.DataFrame({'anio': anios_disponibles})
        df_full = pd.merge(full_years, df_tipo, on='anio', how='left').fillna({'cantidad': 0, 'tipologia': tipo})
        
        X = df_full[['anio']].values
        y = df_full['cantidad'].values

        # Entrenamiento con Random Forest Regressor
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        
        if len(X) > 2:
            # División Train/Test para error MAE de validación
            X_train, X_test = X[:-1], X[-1:]
            y_train, y_test = y[:-1], y[-1:]
            
            model.fit(X_train, y_train)
            pred_test = model.predict(X_test)
            mae = mean_absolute_error(y_test, pred_test)
            maes.append(mae)

        # Re-entrenar con todo el histórico disponible para proyectar el siguiente año
        model.fit(X, y)
        pred_futuro = model.predict([[siguiente_anio]])[0]
        cant_estimada = max(0, int(round(pred_futuro)))

        resultados.append({
            "tipologia": tipo,
            "casos_historicos_ultimo_anio": int(y[-1]),
            "casos_estimados_siguiente_anio": cant_estimada
        })

    df_res = pd.DataFrame(resultados).sort_values(by="casos_estimados_siguiente_anio", ascending=False)
    
    tipo_mayor_riesgo = df_res.iloc[0]["tipologia"] if not df_res.empty else "N/A"
    mae_promedio = float(np.mean(maes)) if maes else 0.0

    return df_res, tipo_mayor_riesgo, mae_promedio, siguiente_anio