"""
reporte_ci.py - Convierte los resultados de Pytest en un reporte con puntuación.

Lee:   reports/resultados.json (puntaje por prueba) y reports/coverage.json
Crea:  reports/resumen.md            -> se muestra en GitHub Actions (Summary) y en el PR
       reports/matriz_resultados.csv -> "Resultado obtenido" y "Estado final" de la matriz del informe
"""
import csv
import json
import os
import sys
from collections import OrderedDict

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORTES = os.path.join(RAIZ, "reports")

# Niveles de puntuación: (mínimo %, título, imagen, mensaje)
NIVELES = [
    (100, "🏆 ¡PERFECTO!", "perfecto.png", "Todas las pruebas pasaron. ¡Equipo imparable! 🎉🥳"),
    (90, "🎉 ¡EXCELENTE!", "excelente.png", "Casi perfecto: solo falta pulir un detalle. ¡Sigan así! 👏"),
    (75, "👍 ¡MUY BIEN!", "bien.png", "Buen trabajo, pero hay pruebas que revisar antes de integrar. 🔧"),
    (50, "⚠️ HAY QUE MEJORAR", "mejorar.png", "Varias pruebas fallan. Revisen los defectos de abajo. 🛠️"),
    (0, "🚨 PIPELINE EN ROJO", "critico.png", "Demasiados fallos: este cambio no debería unirse a main. 🛑"),
]

LOGROS = OrderedDict(
    [
        ("Seguridad", "🔐 Seguridad blindada"),
        ("Backend", "⚙️ Backend sólido"),
        ("Frontend", "🖥️ Frontend impecable"),
        ("Integración", "🔗 Todo conectado"),
    ]
)


def barra(porcentaje: float, largo: int = 20) -> str:
    llenos = round(largo * porcentaje / 100)
    return "🟩" * llenos + "⬜" * (largo - llenos)


def icono(porcentaje: float) -> str:
    return "🟢" if porcentaje >= 90 else "🟡" if porcentaje >= 70 else "🔴"


def url_imagen(nombre: str) -> str:
    repo = os.getenv("GITHUB_REPOSITORY")
    if not repo:
        return f".github/imagenes/{nombre}"
    servidor = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    sha = os.getenv("GITHUB_SHA", "main")
    return f"{servidor}/{repo}/raw/{sha}/.github/imagenes/{nombre}"


def primera_linea_de_error(mensaje: str) -> str:
    lineas = [l.strip() for l in mensaje.splitlines() if l.strip()]
    for l in lineas:
        if l.startswith("E ") and l[2:].strip():
            return l[2:].strip()[:160]
    return (lineas[-1] if lineas else "sin detalle")[:160]


def cargar(ruta):
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    datos = cargar(os.path.join(REPORTES, "resultados.json"))
    if not datos or not datos["resultados"]:
        texto = "# 🚨 No se generaron resultados\n\nPytest no llegó a ejecutar pruebas. Revisa el paso «Ejecutar pruebas».\n"
        open(os.path.join(REPORTES, "resumen.md"), "w", encoding="utf-8").write(texto)
        print(texto)
        return 0

    resultados, meta = datos["resultados"], datos["meta"]
    posibles = sum(r["puntos_posibles"] for r in resultados)
    obtenidos = sum(r["puntos_obtenidos"] for r in resultados)
    porcentaje = round(100 * obtenidos / posibles, 1) if posibles else 0.0
    aprobadas = sum(r["estado"] == "aprobado" for r in resultados)
    fallidas = [r for r in resultados if r["estado"] == "fallido"]
    nivel = next(n for n in NIVELES if porcentaje >= n[0])

    # --- por módulo ---------------------------------------------------------
    modulos = OrderedDict()
    for r in resultados:
        m = modulos.setdefault(r["modulo"], {"pos": 0, "obt": 0, "ok": 0, "total": 0})
        m["pos"] += r["puntos_posibles"]
        m["obt"] += r["puntos_obtenidos"]
        m["ok"] += r["estado"] == "aprobado"
        m["total"] += 1

    # --- cobertura ----------------------------------------------------------
    cobertura = cargar(os.path.join(REPORTES, "coverage.json"))
    pct_cob = round(cobertura["totals"]["percent_covered"], 1) if cobertura else None

    L = []
    L.append(f"# {nivel[1]}")
    L.append(f"![{nivel[1]}]({url_imagen(nivel[2])})")
    L.append("")
    L.append(f"## 🏅 Puntuación: **{obtenidos} / {posibles} puntos ({porcentaje}%)**")
    L.append(f"{barra(porcentaje)}")
    L.append("")
    L.append(f"> {nivel[3]}")
    L.append("")
    L.append(
        f"**{aprobadas} de {len(resultados)} pruebas aprobadas** · commit `{meta.get('commit')}` · "
        f"rama `{meta.get('rama')}` · BD: {meta.get('motor_bd')} · Python {meta.get('python')}"
    )
    L.append("")

    # Logros
    logros = [txt for mod, txt in LOGROS.items() if mod in modulos and modulos[mod]["ok"] == modulos[mod]["total"]]
    if pct_cob is not None and pct_cob >= 70:
        logros.append("🛡️ Cobertura de campeón (≥ 70%)")
    if not fallidas:
        logros.append("✨ Cero defectos")
    L.append("## 🎖️ Logros desbloqueados")
    L.append(" · ".join(logros) if logros else "_Aún no hay logros: ¡corrijan los fallos para desbloquearlos!_ 💪")
    L.append("")

    # Módulos
    L.append("## 📊 Puntuación por módulo")
    L.append("| Módulo | Pruebas | Puntos | Avance | |")
    L.append("|---|:-:|:-:|---|:-:|")
    for nombre, m in modulos.items():
        p = round(100 * m["obt"] / m["pos"], 1) if m["pos"] else 0
        L.append(f"| **{nombre}** | {m['ok']}/{m['total']} | {m['obt']}/{m['pos']} | {barra(p, 10)} {p}% | {icono(p)} |")
    L.append("")

    # Por prueba
    L.append("## 🧪 Detalle por prueba")
    L.append("| ID | Prueba | Módulo | Estado | Puntos | Tiempo |")
    L.append("|---|---|---|:-:|:-:|:-:|")
    estado_txt = {"aprobado": "✅ Aprobada", "fallido": "❌ Fallida", "omitido": "⏭️ Omitida"}
    for r in resultados:
        L.append(
            f"| `{r['id']}` | {r['descripcion']} | {r['modulo']} | {estado_txt[r['estado']]} | "
            f"{r['puntos_obtenidos']}/{r['puntos_posibles']} | {r['duracion_s']} s |"
        )
    L.append("")

    # Defectos
    if fallidas:
        L.append("## 🐞 Defectos detectados")
        for r in fallidas:
            L.append(f"- ❌ **`{r['id']}`** — {r['descripcion']}  ")
            L.append(f"  `{primera_linea_de_error(r['mensaje'])}`  ")
            L.append(f"  📁 `{r['archivo']}` · 💸 pierde {r['puntos_posibles']} puntos")
        L.append("")
        L.append("_Abre el paso «Ejecutar pruebas» para ver el detalle completo de cada fallo._")
        L.append("")

    # Cobertura
    if cobertura:
        L.append(f"## 🛡️ Cobertura de código: **{pct_cob}%**")
        L.append(f"{barra(pct_cob)}")
        L.append("")
        L.append("| Archivo | Cobertura | |")
        L.append("|---|:-:|:-:|")
        for archivo, info in sorted(cobertura["files"].items()):
            p = round(info["summary"]["percent_covered"], 1)
            L.append(f"| `{archivo}` | {barra(p, 10)} {p}% | {icono(p)} |")
        L.append("")

    texto = "\n".join(L) + "\n"

    with open(os.path.join(REPORTES, "resumen.md"), "w", encoding="utf-8") as f:
        f.write(texto)

    # Matriz de resultados (para copiar a las columnas del informe)
    with open(os.path.join(REPORTES, "matriz_resultados.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Descripción", "Resultado obtenido", "Estado final", "Puntos"])
        for r in resultados:
            if r["estado"] == "aprobado":
                obtenido, estado = "Comportamiento conforme al resultado esperado", "Aprobado"
            elif r["estado"] == "fallido":
                obtenido, estado = f"Falló: {primera_linea_de_error(r['mensaje'])}", "Fallido"
            else:
                obtenido, estado = "No se ejecutó", "No aplica"
            w.writerow([r["id"], r["descripcion"], obtenido, estado, f"{r['puntos_obtenidos']}/{r['puntos_posibles']}"])

    destino = os.getenv("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto)
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
