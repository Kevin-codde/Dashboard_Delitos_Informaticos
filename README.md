
# Dashboard de delitos informáticos en Colombia

Prototipo universitario de Business Intelligence con Python, Streamlit,
pandas, Plotly, scikit-learn y almacenamiento NoSQL.

## Requisitos

- Python 3.11 o superior.
- El archivo `delitos_informaticos.csv` descargado del conjunto oficial.
- MongoDB local, opcional. Si no está disponible, se utiliza TinyDB.
- Conexión a Internet solo para instalar las dependencias.

## 1. Preparar el entorno

En Windows, abre PowerShell dentro de esta carpeta:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno, puedes ejecutar
directamente el intérprete del entorno virtual usando `.venv\Scripts\python.exe`.

## 2. Colocar el CSV

Copia `delitos_informaticos.csv` en la carpeta raíz del proyecto.

El ETL detecta separadores comunes e imprime las columnas reales, los
tipos de datos originales y las primeras cinco filas. Si faltan columnas
obligatorias, detiene la carga para evitar resultados incorrectos.

## 3. Iniciar MongoDB (opcional)

Instala y ejecuta MongoDB Community Server localmente. La configuración
predeterminada utiliza:

- URI: `mongodb://localhost:27017`
- Base de datos: `ciberdelitos`
- Colección: `registros`

También puedes definir `MONGO_URI` y `MONGO_DB` como variables de entorno.

Si MongoDB no responde, el programa utiliza TinyDB en
`data/ciberdelitos_tinydb.json`.

## 4. Procesar y cargar los datos

```powershell
python etl.py
```

También puedes especificar una ruta:

```powershell
python etl.py --csv "C:\ruta\delitos_informaticos.csv"
```

Revisa el resumen final del ETL: registros leídos, cargados, descartados,
casos cargados y rango de fechas.

Cada ejecución reemplaza el conjunto almacenado; no suma otra copia de
los registros anteriores.

## 5. Ejecutar el dashboard

```powershell
streamlit run app.py
```

Streamlit abrirá el dashboard en el navegador. Si no lo abre
automáticamente, utiliza la URL local que muestra la terminal,
normalmente `http://localhost:8501`.

## Funcionalidades

- HU1: inspección, limpieza, carga y estado de los datos.
- HU2: filtros combinables por año, mes, departamento, municipio y tipología.
- HU3: evolución temporal y distribución por tipología.
- HU4: ranking departamental, porcentajes y tabla de resultados.
- HU5: predicción por tipología con regresión lineal y MAE.

## Consideraciones

- Los totales de casos son sumas de `CANTIDAD`, no conteos de filas.
- Los registros descartados se informan durante el ETL.
- Los filtros vacíos muestran un mensaje en lugar de una excepción.
- El modelo solo predice tipologías con suficientes años históricos.
- El pronóstico es una extrapolación estadística, no una certeza.
- TinyDB es adecuado para el prototipo local; MongoDB es preferible
  para manejar el conjunto completo y consultas concurrentes.
- La base local no reemplaza ni modifica el CSV original.

## Limitaciones conocidas

El prototipo no incluye un mapa coroplético. La predicción usa regresión
lineal por tipología y no incorpora variables explicativas externas.
La calidad del pronóstico depende de la longitud y estabilidad de las
series históricas.

Antes de presentar los resultados, verifica que la fecha de corte y
los registros cargados correspondan a la versión del CSV utilizado.
