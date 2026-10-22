"""22/10/2026 - Como sirvo el cliente web: archivos estaticos con encabezados de seguridad.

Starlette trae `StaticFiles`, pero no agrega ningun encabezado de seguridad. Aqui lo extiendo
para que TODA respuesta del cliente (pagina, script, hoja de estilos) lleve una politica de
contenido (CSP) estricta. La CSP es la segunda barrera contra XSS: la primera es no pintar jamas
datos de la API con innerHTML; si alguna vez se me escapa un caso, la CSP impide que un script
inyectado se ejecute (`script-src 'self'` no admite scripts en linea ni de otros dominios).

Solo se aplica bajo /app. Las rutas /docs y /redoc de FastAPI cargan su propio JavaScript desde un CDN
y necesitan otra politica, por eso no comparto el encabezado con toda la aplicacion.
"""

from __future__ import annotations

from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

# 22/10/2026 - Cada directiva dice de donde puede venir cada tipo de recurso. 'self' = este mismo origen.
# - script-src 'self': sin scripts en linea ni onclick="..." (por eso el HTML no tiene ninguno).
# - style-src 'self': sin <style> ni style="..." en el HTML; Bootstrap solo cambia estilos desde JS (permitido).
# - connect-src 'self': fetch solo hacia nuestra propia API (la semana 17 abre CORS de forma explicita si hace falta).
# - frame-ancestors 'none': nadie puede incrustar el cliente en un iframe (clickjacking).
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # `no-cache` no impide guardar: obliga a preguntar al servidor (ETag) antes de reutilizar. Asi, cuando
    # edito un archivo en clase, los alumnos ven el cambio sin vaciar la cache a mano.
    "Cache-Control": "no-cache",
}


class ClientStaticFiles(StaticFiles):
    """22/10/2026 - StaticFiles + encabezados de seguridad en cada respuesta con archivo."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers.update(SECURITY_HEADERS)
        return response
