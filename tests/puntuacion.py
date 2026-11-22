"""
puntuacion.py - Recolector de resultados con puntaje por prueba.

Cada prueba se marca con:
    @pytest.mark.caso("TC-10", modulo="Seguridad", puntos=10)
Al terminar la sesión se genera reports/resultados.json, que lee
scripts/reporte_ci.py para armar el reporte con puntuación del pipeline.
"""
import json
import os
import platform
from datetime import datetime, timezone

PUNTOS_POR_DEFECTO = 5


class Recolector:
    def __init__(self):
        self.resultados = []
        self.meta = {}

    def registrar(self, item, reporte):
        marca = item.get_closest_marker("caso")
        args = marca.args if marca else ()
        kwargs = marca.kwargs if marca else {}
        doc = (item.function.__doc__ or item.name).strip().splitlines()[0]

        if reporte.passed:
            estado = "aprobado"
        elif reporte.failed:
            estado = "fallido"
        else:
            estado = "omitido"

        puntos = kwargs.get("puntos", PUNTOS_POR_DEFECTO)
        mensaje = ""
        if reporte.failed:
            mensaje = (reporte.longreprtext or "")[-1500:]
        elif reporte.skipped and isinstance(reporte.longrepr, tuple):
            mensaje = str(reporte.longrepr[-1])

        self.resultados.append(
            {
                "id": args[0] if args else item.name,
                "descripcion": doc,
                "modulo": kwargs.get("modulo", "General"),
                "puntos_posibles": puntos,
                "puntos_obtenidos": puntos if estado == "aprobado" else 0,
                "estado": estado,
                "duracion_s": round(reporte.duration, 3),
                "mensaje": mensaje,
                "archivo": item.nodeid.split("::")[0],
            }
        )

    def guardar(self, ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        meta = {
            **self.meta,
            "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "python": platform.python_version(),
            "commit": os.getenv("GITHUB_SHA", "local")[:7],
            "rama": os.getenv("GITHUB_REF_NAME", "local"),
        }
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "resultados": self.resultados}, f, ensure_ascii=False, indent=2)
