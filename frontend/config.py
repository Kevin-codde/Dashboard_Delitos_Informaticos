"""
Configuración del frontend: enlaces públicos de los reportes de Power BI.

Son los enlaces de "Publicar en la web" (no son claves). Si se republica un reporte y el enlace
cambia, solo hay que editar este archivo. Para cambiarlos sin tocar el repositorio (por ejemplo al
desplegar), definir las variables de entorno POWERBI_URL y POWERBI_URL_OSCURO.
"""

REPORTE_CLARO = (
    "https://app.powerbi.com/view?r=eyJrIjoiNzNhNjliYTMtN2QxMi00YjE5LTkzMmItNDI4NDI0MDFjZDIw"
    "IiwidCI6ImZkNzY2ZWRkLThiZWEtNGM5OS04NjcyLTU2ZDFjYWJjMjcwNiIsImMiOjR9"
)

REPORTE_OSCURO = (
    "https://app.powerbi.com/view?r=eyJrIjoiMzg1N2VmODYtYjIxOS00YjU3LWE2YWMtOGIwMzY5Zjk2NzI5"
    "IiwidCI6ImZkNzY2ZWRkLThiZWEtNGM5OS04NjcyLTU2ZDFjYWJjMjcwNiIsImMiOjR9"
)
