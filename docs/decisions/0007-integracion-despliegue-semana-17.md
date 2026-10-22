# ADR 0007 - Integración, pruebas y despliegue reproducible (semana 17)

- Fecha: 22/10/2026
- Autor: Ing. Richard Ortiz
- Estado: aceptado
- Contexto del curso: semana 17, "Integración, pruebas y despliegue reproducible" (Programación II)

## Qué tenemos que lograr

Hasta la semana 16 el sistema funciona **en mi máquina**: PostgreSQL en un contenedor, la API con `uvicorn` a mano y el
cliente en `/app`. Esta semana lo convertimos en algo que otra persona pueda levantar siguiendo instrucciones, y que podamos
diagnosticar cuando falla. Los cuatro indicadores de la semana son mi criterio de aceptación:

1. **Se ejecuta desde instrucciones limpias**: clonar → `.env` → `docker compose up` → `/app`.
2. **Demuestra flujos de punta a punta**: cliente → API → base de datos.
3. **Diagnostica fallas entre capas**: sé decir si el problema está en el navegador, la API o la base.
4. **Entrega evidencia sin secretos**: logs, respaldos y capturas que se pueden compartir.

## 1. Configuración por entorno

Todo lo que cambia entre mi máquina, la de ustedes y un servidor sale de **variables de entorno** (`app/core/config.py`) y está
documentado en `.env.example` y en el README. Hay dos grupos:

| Grupo | Variables | Regla |
| --- | --- | --- |
| Secretos | `SECRET_KEY`, `POSTGRES_PASSWORD` | Obligatorias. Sin ellas la app no arranca y `docker compose` se detiene (`${VAR:?mensaje}`). El valor de ejemplo no sirve |
| Ajustes | `DATABASE_URL`, `APP_TIMEZONE`, `ACCESS_TOKEN_MINUTES`, `CORS_ORIGINS`, `LOG_LEVEL`, puertos... | Tienen un valor por defecto razonable |

Las variables se **validan al arrancar** (`CORS_ORIGINS=*` o `LOG_LEVEL=ruidoso` hacen fallar el arranque con un mensaje claro). Prefiero un
contenedor que no levanta a uno que levanta mal configurado y falla a las 3 de la mañana.

El archivo `.env` real nunca se sube: está en `.gitignore` y la imagen no lo recibe (ver sección 6).

## 2. CORS: lista explícita, vacía por defecto

El navegador compara el **origen** (esquema + host + puerto) de la página con el de la API. `/app` y `/api` salen del mismo servidor,
así que **no necesitan CORS**. Hace falta cuando el cliente se sirve desde otro origen, por ejemplo `python -m http.server 5500` llamando
a la API en el puerto 8000: el navegador envía un *preflight* (`OPTIONS`) y bloquea la respuesta si la API no lo autoriza.

| Opción | A favor | En contra |
| --- | --- | --- |
| `allow_origins=["*"]` | "Funciona" siempre | Cualquier página de Internet puede llamar a la API desde el navegador de una persona. Con credenciales ni siquiera es válido |
| Siempre activo con una lista fija en el código | Simple | Cambiar de origen exige tocar el código |
| **Lista en `CORS_ORIGINS`, vacía por defecto** (la elegida) | Seguro por defecto; se abre con una línea del `.env`; sin lista no se instala ningún middleware | Hay que acordarse de reiniciar la app al cambiarla |

El cliente de `/app` llama a la API con la ruta relativa `/api` (`API_BASE` en `app/web/static/js/api.js`): moverlo a otro origen implica cambiar
ese valor por la URL completa. Detalles que decidí: `allow_credentials=False` (el token viaja en `Authorization`, no en cookies); métodos `GET`, `POST`, `PATCH` (los que
usa la API); encabezados permitidos `Authorization` y `Content-Type`; `X-Total-Count` expuesto porque el cliente pagina con él y un cliente
de otro origen no podría leerlo.

## 3. Logging

Sin configuración, `uvicorn app.main:app` **no mostraba** las líneas de `helpdesk.audit`: uvicorn solo configura sus propios loggers y
Python descarta los INFO de los demás. `app/core/logging_config.py` agrega un handler **solo** a los loggers `helpdesk` y `app`
(no toca el logger raíz ni los de uvicorn/SQLAlchemy), es idempotente y toma el nivel de `LOG_LEVEL`. Formato:
`hora NIVEL [logger] mensaje`.

`app/core/request_logging.py` escribe **una línea por petición**: `method=POST path=/api/tickets status=201 duration_ms=14.6`.
Lo que **nunca** se registra: encabezados (ahí va el token), cuerpo (ahí va la contraseña) ni query string (`?token=...` es un error común).
Una prueba con `caplog` lo comprueba, y comprobé que **falla** si el middleware escribe la query string. Por la misma razón el contenedor
arranca uvicorn con `--no-access-log`: su access log sí imprime la URL completa. `/api/health` se registra en `DEBUG` porque Docker la consulta cada 10 s.

## 4. Un error real encontrado: `/api/health` respondía 500

Al tumbar la base con la API ya corriendo, la **primera** consulta a `/api/health` devolvía 500 y recién la segunda 503. Causa: el pool
guardaba una conexión muerta; la ruta capturaba el error y respondía 503, pero la sesión quedaba con una transacción inválida y el cierre
de `get_db` intentaba un `COMMIT` → `PendingRollbackError`. Es justo el endpoint que más necesito cuando todo falla.
Arreglo: `db.rollback()` en la rama de error. La prueba (`tests/test_week17_salud.py`) mata en el servidor, con `pg_terminate_backend`,
la conexión que el pool de la app dejó guardada, y se escribió **antes** del arreglo (falló con el 500).

## 5. Esquema de la base: creación controlada, no `create_all`

| Opción | A favor | En contra |
| --- | --- | --- |
| `Base.metadata.create_all()` al arrancar la app | Cero pasos | La app decide el esquema en producción; no crea triggers, funciones ni la extensión `vector`; oculta diferencias entre ambientes |
| Alembic (migraciones versionadas) | Es lo que se usa en equipos grandes | Es un tema por sí mismo; no cabe en una semana de integración |
| **Scripts SQL de `docs/database/` montados en `docker-entrypoint-initdb.d`** (la elegida) | Una sola fuente de verdad (la misma que usan las pruebas); reproducible; el esquema se revisa como código | Solo corren con el **volumen vacío**: cambiar el esquema de una base con datos es una migración manual (respaldo → `ALTER` → verificar) |

Esa limitación es una decisión consciente y está en el README, en el `docker-compose.yml` y en la lista de verificación.

## 6. Imagen y compose

- **Dos etapas**: la primera instala dependencias con `uv sync --frozen --no-dev` (`uv.lock` manda: el mismo árbol de paquetes siempre); la
  final solo recibe el entorno y `app/`. Sin `uv`, sin caché, sin pytest.
- **Usuario sin privilegios** (uid 10001), `read_only` con `tmpfs` en `/tmp`, `cap_drop: ALL` y `no-new-privileges`.
- **`HEALTHCHECK`** sobre `/api/health`: la salud la decide la propia API (200 solo si la base contesta).
- **`.dockerignore` de lista blanca** (`*` y después `!app`, `!pyproject.toml`, `!uv.lock`): un `.env`, un respaldo o un PDF nuevos no pueden
  terminar dentro de una imagen por descuido. El repositorio es público; esto es parte de protegerlo.
- **Compose**: `app` espera a `db` con `condition: service_healthy`. El healthcheck de la base usa `pg_isready -h 127.0.0.1` a propósito:
  durante los scripts de init PostgreSQL arranca un servidor temporal que solo escucha por socket, y sin `-h` diría "listo" antes de cargar el seed.
- **Zona horaria**: `TZ`/`PGTZ` en la base y `APP_TIMEZONE` en la app. Sin ellas el contenedor de PostgreSQL trabaja en UTC y el seed
  (`CURRENT_TIMESTAMP`) queda con horas distintas a las que escribe la aplicación.
- La base solo se publica en `127.0.0.1` (la app no usa ese puerto: habla con `db:5432` por la red interna).

## 7. Respaldo

`app/scripts/db_backup.py` (biblioteca estándar) le pide al contenedor `db` que ejecute `pg_dump -Fc` / `pg_restore`: no hay que instalar
PostgreSQL en el host y el usuario y la base los toma el contenedor de sus propias variables. El archivo se crea con permiso 600, se valida
(marca `PGDMP`) y se borra si salió mal. `restore` **exige `--yes`** porque reemplaza los datos. `backups/` y `*.dump` están en `.gitignore`:
un respaldo lleva hashes de contraseñas y datos de personas, es tan sensible como la base.

## 8. Pruebas: unitarias e integración

`pytest -m "not integration"` (rápidas, sin PostgreSQL) y `pytest -m integration` (contra `TEST_DATABASE_URL`). El marcador se agrega **solo**
a toda prueba que use `pg_engine`, `db` o `committed_db` (`tests/conftest.py`): nadie tiene que acordarse de marcar a mano. La prueba de
punta a punta (`tests/test_week17_integracion.py`) recorre login → crear → asignar → comentar → cambiar estado → notificaciones sin reemplazar
ninguna capa, y comprueba que un dato confirmado por un proceso lo lee otro (otro pool = otro reinicio del servidor).

## Evidencia (sin secretos)

Proyecto desechable `hd_wk17_check` (puertos 5434 y 8017, `.env` con valores generados que no se publican):

```text
$ docker compose -p hd_wk17_check up -d --build
 Container hd_wk17_check-db-1   Healthy
 Container hd_wk17_check-app-1  Started
$ docker compose -p hd_wk17_check ps
hd_wk17_check-app-1   helpdesk-edu:local   Up (healthy)   0.0.0.0:8017->8000/tcp
hd_wk17_check-db-1    pgvector/pgvector:pg16   Up (healthy)   127.0.0.1:5434->5432/tcp
$ curl -s localhost:8017/api/health            -> {"status":"ok"}
$ POST /api/auth/login (clave correcta)        -> 200 + token
$ POST /api/auth/login (clave mala)            -> 401
$ POST /api/tickets                            -> 201 (id 7)
$ GET  /app/                                   -> 200 text/html, con Content-Security-Policy
$ docker compose stop db; curl /api/health x2  -> 503 y 503 (antes: 500 y 503)
$ docker compose start db; curl /api/health    -> 200 (la API se recupera sola)
```

Con `CORS_ORIGINS=http://localhost:5500` y `docker compose up -d` (recrea la app): el preflight desde ese origen responde 200 con
`access-control-allow-origin: http://localhost:5500`; desde `http://evil.example` responde 400 `Disallowed CORS origin` y sin esa cabecera.
Sin la variable, el preflight devuelve 405 sin cabeceras CORS y `/app` sigue funcionando (mismo origen).

Las líneas del contenedor ahora muestran la auditoría y las peticiones, con la hora local:

```text
2026-10-22 17:22:36,147 INFO [helpdesk.audit] event=ticket_created ticket=7 actor=4
2026-10-22 17:22:36,148 INFO [helpdesk.request] method=POST path=/api/tickets status=201 duration_ms=14.6
```

Respaldo y restauración: con 7 tickets se respaldó, se borró el ticket 7 (quedaron 6), `restore` sin `--yes` salió con código 2 sin tocar
nada, y con `--yes` volvieron los 7 tickets.

## Lo que NO resuelve esta semana

- **HTTPS**: el contenedor habla HTTP. En un servidor real va detrás de un proxy inverso con TLS (uvicorn ya acepta `--proxy-headers`).
- **Gestor de secretos**: `.env` es suficiente para el curso; en producción se usan los secretos de la plataforma.
- **Migraciones versionadas** (Alembic), **límite de intentos de login**, **métricas** y **respaldos automáticos programados**.
- **Consecuencia aceptada**: cambiar `SECRET_KEY` invalida todos los tokens emitidos (todos deben volver a ingresar).
