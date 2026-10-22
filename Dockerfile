# 22/10/2026 - Richard Ortiz: imagen de la API + cliente web de HelpDesk EDU (semana 17).
# Dos etapas: en la primera instalo las dependencias con uv; la segunda solo recibe el entorno ya armado y el
# codigo, asi la imagen final no lleva uv, ni cache de pip, ni herramientas de compilacion.

# ---- etapa 1: dependencias -------------------------------------------------------------------------------
# Version fija de Python (no `latest`): el mismo build hoy y dentro de seis meses. Es la misma que probamos con pytest.
FROM python:3.14-slim AS builder

# UV_COMPILE_BYTECODE: compilo los .pyc una vez aqui y el arranque del contenedor es mas rapido.
# UV_LINK_MODE=copy: uv copia los archivos en vez de enlazar a su cache (que no viaja a la etapa final).
# UV_PROJECT_ENVIRONMENT: el entorno virtual queda en una ruta fija que luego copio tal cual.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv

WORKDIR /srv/helpdesk

# Copio SOLO los archivos de dependencias antes que el codigo: mientras pyproject.toml y uv.lock no cambien,
# Docker reutiliza esta capa y no vuelve a descargar nada cuando edito un archivo de app/.
COPY pyproject.toml uv.lock ./
# --frozen: instala EXACTAMENTE lo que dice uv.lock (si el lock no coincide, falla en vez de actualizar).
# --no-dev: sin pytest. --no-install-project: el proyecto no es un paquete instalable; el codigo se copia abajo.
RUN uv sync --frozen --no-dev --no-install-project

# ---- etapa 2: imagen de ejecucion ------------------------------------------------------------------------
FROM python:3.14-slim

# PYTHONUNBUFFERED: los logs salen en el momento (docker logs) y no se quedan en un buffer.
# PYTHONDONTWRITEBYTECODE: el sistema de archivos del contenedor puede ser de solo lectura (ver compose).
# PATH: asi `python` y `uvicorn` son los del entorno virtual.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Usuario sin privilegios: si alguien logra ejecutar codigo dentro de la API, no es root dentro del contenedor.
# --no-log-init evita un archivo de log enorme con uids altos; sin shell de login y sin carpeta personal.
RUN groupadd --system --gid 10001 helpdesk \
    && useradd --system --uid 10001 --gid helpdesk --no-log-init --no-create-home --shell /usr/sbin/nologin helpdesk

WORKDIR /srv/helpdesk
COPY --from=builder /opt/venv /opt/venv
# Solo el codigo de la aplicacion (el .dockerignore deja fuera pruebas, docs, .env y todo el material docente).
COPY --chown=helpdesk:helpdesk app ./app

USER helpdesk
EXPOSE 8000

# La salud la decide la propia API: /api/health responde 200 solo si la base contesta (503 si no, y entonces
# urlopen lanza una excepcion y el comando sale con error). Es lo que ve `docker compose ps`.
# start-period: tiempo de gracia al arrancar; los fallos dentro de ese plazo no cuentan.
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

# --no-access-log: el log de peticiones es el de la aplicacion (helpdesk.request), que registra metodo, ruta,
# estado y duracion SIN query string; el access log de uvicorn si imprimiria la URL completa con sus parametros.
# --proxy-headers: si algun dia hay un proxy inverso (HTTPS) delante, uvicorn respeta X-Forwarded-*.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
