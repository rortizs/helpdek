# helpdek

HelpDesk EDU: proyecto de clase de Programacion II (Python). Se construye semana a semana
sobre una arquitectura en capas: modelos de dominio, servicios, repositorios y, desde la
semana 14, una API REST con FastAPI.

## Puesta en marcha (semana 14)

22/10/2026 - Estos son los pasos que seguimos en clase para levantar la API:

```bash
cp .env.example .env             # completa SECRET_KEY y POSTGRES_PASSWORD (ver abajo y la tabla de la semana 17)
docker compose up -d db          # PostgreSQL 16 en el puerto 5433
uv sync                          # dependencias del proyecto
python -c "import secrets; print(secrets.token_urlsafe(48))"   # genera una clave propia
uv run python -m app.scripts.set_password requester@example.com    # el seed trae hashes de relleno
uv run uvicorn app.main:app --reload --env-file .env
```

- Documentacion interactiva (OpenAPI): <http://localhost:8000/docs>
- Login: `POST /api/auth/login` devuelve un token; en `/docs` usa el boton **Authorize**.
- `SECRET_KEY` es obligatoria: la aplicacion no arranca sin ella (y nunca se sube a Git).
- 22/10/2026 - Desde la semana 17 `docker-compose.yml` tambien exige `POSTGRES_PASSWORD`. Si ya tenias la base de las semanas 13-16
  (contrasena `helpdesk`), ponla igual en tu `.env` (`POSTGRES_PASSWORD=helpdesk` y la misma en `DATABASE_URL`): un volumen
  que ya existe conserva la contrasena con la que nacio.

## Pruebas

```bash
uv run pytest -q                       # todas
uv run pytest -m "not integration"     # unitarias: rapidas, no necesitan PostgreSQL
uv run pytest -m integration           # integracion: usan PostgreSQL real (TEST_DATABASE_URL), incluye el recorrido de punta a punta
```

22/10/2026 - Semana 17: el marcador `integration` se agrega solo a toda prueba que use la base (ver `tests/conftest.py`).

Las pruebas de integracion usan la base dedicada `helpdesk_test`, que se recrea desde
`docs/database/`. La base `helpdesk` (practica de los alumnos) no se toca nunca.

22/10/2026 - Desde la semana 16 tambien hay pruebas de JavaScript con Node (opcional, hace falta Node 22 o mayor):

```bash
node --test "tests/web/*.test.mjs"    # funciones puras del cliente: api.js, sesion, reglas, validacion
```

`uv run pytest` tambien las ejecuta si encuentra `node`; si no, las omite y el resto sigue igual.

## Estructura

| Carpeta | Que contiene |
| --- | --- |
| `app/models`, `app/domain` | Entidades, enums, reglas y errores de dominio |
| `app/repositories` | Contratos y su implementacion en memoria / SQLAlchemy |
| `app/services` | Reglas de negocio (tickets, usuarios, avisos, autenticacion) |
| `app/api`, `app/schemas`, `app/main.py` | Rutas HTTP, esquemas Pydantic y fabrica de la app |
| `app/core` | Configuracion, base de datos, seguridad (hash y JWT) |
| `app/web` | Cliente web (semana 16): HTML, CSS y JavaScript servidos en `/app` |
| `app/scripts` | Utilidades de linea de comandos: `set_password` y `db_backup` (respaldo / restauracion) |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Despliegue reproducible: base + aplicacion (semana 17) |
| `docs/database` | Esquema, triggers, seed y consultas SQL |
| `docs/operacion` | Lista de verificacion operativa: despliegue, prueba de humo, respaldo y reversa |
| `docs/decisions` | ADR: decisiones de arquitectura con su problema, patron y limites |

## Patrones (semana 15)

22/10/2026 - Aplicados solo donde resuelven un problema real (ver `docs/decisions/0005-patrones-semana-15.md`):

- **Observer**: `TicketService` publica eventos (`app/domain/events.py`); avisos y auditoria son suscriptores.
- **Facade**: las rutas hablan con `HelpDeskFacade` (`app/services/helpdesk.py`).
- **Inyeccion de dependencias**: `Depends` + `app.dependency_overrides` para cambiar piezas en las pruebas.
- **Singleton (critica)**: el engine ya no es global; lo posee cada aplicacion (`app.state.database`).
- **Decorator**: no se aplico, y el ADR explica por que.

## Cliente web (semana 16)

22/10/2026 - El navegador es un cliente mas de la API: habla HTTP + JSON y **nunca** toca la base de datos.
El mismo servidor entrega los archivos del cliente en `/app` (ver `docs/decisions/0006-cliente-web-semana-16.md`).

```bash
docker compose up -d db                       # PostgreSQL
uv run python -m app.scripts.set_password requester@example.com   # dale una contrasena al usuario con el que vas a ingresar
uv run uvicorn app.main:app --reload --env-file .env
```

1. Abre <http://localhost:8000/> (te lleva a <http://localhost:8000/app/>).
2. Ingresa con el correo y la contrasena que asignaste con `set_password`. Usuarios del seed: `requester@example.com` y
   `ana@umg.edu` (solicitantes), `technician@example.com` y `carlos@umg.edu` (tecnicos), `supervisor@example.com`, `admin@example.com`.
3. Un **solicitante** crea tickets, ve los suyos, comenta y cancela los propios. El **personal** (tecnico, supervisor, administrador) ve todos,
   asigna, cambia estado y prioridad. Lo que tu rol no puede hacer no se muestra, y aunque lo forzaras la API responde 403.

| Pagina | Que llama |
| --- | --- |
| `/app/` (ingreso) | `POST /api/auth/login`, `GET /api/users/me` |
| `/app/tickets.html` | `GET /api/tickets` (filtros, `limit`/`offset`, total en `X-Total-Count`), `GET /api/users` (solo personal) |
| `/app/ticket-new.html` | `POST /api/tickets` |
| `/app/ticket.html?id=N` | `GET /api/tickets/{id}`, `POST .../comments`, `POST .../assign`, `PATCH .../status`, `PATCH .../priority`, `POST .../cancel` |
| `/app/notifications.html` | `GET /api/notifications`, `POST /api/notifications/read-all` |

- **Token**: se guarda en `sessionStorage` (muere al cerrar la pestana) y vence con `ACCESS_TOKEN_MINUTES`. El ADR explica por que no `localStorage` ni cookie.
- **Seguridad**: los datos de la API se pintan con `textContent` (nunca `innerHTML`) y cada archivo de `/app` lleva una politica CSP estricta.
- **Sin build**: nada de `npm`. Bootstrap 5.3.8 esta copiado en `app/web/static/vendor/bootstrap/` (con su suma SHA-256), asi funciona sin Internet.
- **Capturas** a 1280 y 390 px: `docs/img/semana16/`.
- **Y CORS?** Cliente y API comparten origen, asi que no hace falta. Cuando el cliente se sirve desde otro origen se configura con `CORS_ORIGINS` (ver la semana 17).

## Despliegue (semana 17)

22/10/2026 - Integracion, pruebas y despliegue reproducible (ver `docs/decisions/0007-integracion-despliegue-semana-17.md`).
Con Docker, la base y la aplicacion (API + cliente web) se levantan juntas, sin instalar Python ni PostgreSQL en tu maquina.

### De cero a funcionando

```bash
git clone https://github.com/rortizs/helpdek.git && cd helpdek
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copia el resultado en SECRET_KEY dentro de .env
# edita .env: SECRET_KEY=<lo que imprimio> y POSTGRES_PASSWORD=<una contrasena propia>
docker compose up -d --build
docker compose ps                                               # espera "healthy" en db y app
curl http://localhost:8000/api/health                           # {"status":"ok"}
docker compose exec app python -m app.scripts.set_password requester@example.com   # el seed trae hashes de relleno
```

Abre <http://localhost:8000/app> e ingresa con ese correo y la contrasena que acabas de asignar. La documentacion de la API esta en <http://localhost:8000/docs>.
Para apagar: `docker compose down` (los datos quedan en el volumen). `docker compose down -v` **borra los datos**.

### Variables de entorno

Todo esta en `.env.example`. Compose lee tu `.env`; `uvicorn --env-file .env` tambien. **Nunca se sube**: esta en `.gitignore` y la imagen no lo recibe.

| Variable | Por defecto | Para que sirve |
| --- | --- | --- |
| `SECRET_KEY` | *(obligatoria)* | Firma los tokens. Minimo 32 caracteres. Si cambia, todos los tokens emitidos dejan de valer |
| `POSTGRES_PASSWORD` | *(obligatoria en compose)* | Contrasena de la base. Solo aplica al crear el volumen. Usa letras, numeros, `-` y `_` (va dentro de una URL) |
| `POSTGRES_DB`, `POSTGRES_USER` | `helpdesk` | Nombre de la base y del usuario |
| `DATABASE_URL` | `...@localhost:5433/helpdesk` | Solo para `uvicorn` en tu maquina. En compose se arma sola (host `db`) |
| `TEST_DATABASE_URL` | `...helpdesk_test` | Solo pytest. El nombre de la base debe contener `test`; se borra y recrea en cada corrida |
| `APP_TIMEZONE` | `America/Guatemala` | Zona de la aplicacion, de la base y de los logs |
| `ACCESS_TOKEN_MINUTES` | `60` | Vida del token |
| `CORS_ORIGINS` | *(vacio)* | Origenes permitidos desde otro origen, separados por coma. Vacio = solo el mismo origen. `*` esta prohibido |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` o `CRITICAL` |
| `APP_PORT`, `DB_PORT` | `8000`, `5433` | Puertos de TU maquina (la base solo escucha en `127.0.0.1`) |
| `APP_NAME`, `DEBUG` | `HelpDesk EDU`, `false` | `DEBUG=true` devuelve trazas al cliente: solo en tu maquina |

### El esquema de la base

Se crea con los scripts de `docs/database/` (`database.sql`, `functions_triggers.sql`, `seed.sql`), montados en el contenedor de PostgreSQL.
**Solo se ejecutan cuando el volumen esta vacio** (la primera vez o despues de `down -v`). La aplicacion nunca crea tablas por su cuenta
(no hay `create_all` en produccion). Cambiar el esquema de una base que ya tiene datos es una migracion manual: respaldo, `ALTER` revisado y verificacion.

### Logs

Cada peticion deja una linea: `method=POST path=/api/tickets status=201 duration_ms=14.6`, junto a las lineas de auditoria
(`helpdesk.audit`). Nunca se registran encabezados, cuerpos ni query strings (ahi viajan tokens y contrasenas).
Ver en vivo: `docker compose logs -f app`. Para mas detalle, `LOG_LEVEL=DEBUG`.

### CORS: cuando si y cuando no

`/app` y `/api` salen del mismo servidor: **mismo origen**, no hace falta nada. Un origen es esquema + host + puerto; si una pagina de
`http://localhost:5500` llama a la API en `http://localhost:8000`, el navegador bloquea la respuesta hasta que la API lo autorice. Para verlo:

1. Sirve cualquier carpeta con `python -m http.server 5500`, abre <http://localhost:5500> y, en la consola del navegador (F12), ejecuta
   `fetch("http://localhost:8000/api/health")`: falla con *blocked by CORS policy*.
2. Autoriza ese origen y recrea la aplicacion:

```bash
# en .env
CORS_ORIGINS=http://localhost:5500
docker compose up -d        # recrea la app con la nueva configuracion
```

3. Repite el `fetch`: ahora responde `{status: "ok"}`.

El cliente de `/app` llama a la API con la ruta relativa `/api` (`API_BASE` en `app/web/static/js/api.js`); para servirlo desde otro origen habria que
cambiar ese valor por la URL completa de la API. Nunca uses `*`: la aplicacion se niega a arrancar con ese valor.

### Respaldo y restauracion

```bash
uv run python -m app.scripts.db_backup backup                              # backups/helpdesk_AAAAMMDDTHHMMSS.dump
uv run python -m app.scripts.db_backup restore backups/ARCHIVO.dump --yes  # REEMPLAZA los datos actuales
```

Los respaldos no se suben a Git (`backups/`, `*.dump`). Procedimiento completo, prueba de humo y reversa: `docs/operacion/checklist_operativa.md`.

### Si algo falla: diagnostico entre capas

Empieza por `docker compose ps` y `docker compose logs app --tail 30`; la linea de log dice en que capa murio la peticion.

| Sintoma | Capa | Como confirmarlo | Que hacer |
| --- | --- | --- | --- |
| `/api/health` responde **503** `database_unavailable` | Base de datos | `docker compose ps` (db sin `healthy`), `docker compose logs db` | `docker compose up -d db`. La API se recupera sola; no hace falta reiniciarla |
| El contenedor `app` se reinicia o sale al arrancar | Configuracion | `docker compose logs app`: `RuntimeError: SECRET_KEY...`, `CORS_ORIGINS...` o `LOG_LEVEL...` | Corrige el valor en `.env` y `docker compose up -d` |
| `password authentication failed for user "helpdesk"` | Base vs. `.env` | Cambiaste `POSTGRES_PASSWORD` despues de crear el volumen | Vuelve a la contrasena original, o respalda y recrea el volumen (`down -v`) |
| En la consola del navegador: *"blocked by CORS policy: No 'Access-Control-Allow-Origin' header"* | Navegador / red | El cliente no se sirve desde el mismo origen que la API; en el log aparece `method=OPTIONS ... status=400` o `405` | Agrega ese origen a `CORS_ORIGINS` y `docker compose up -d`. `curl -i -X OPTIONS ... -H "Origin: ..."` debe devolver `access-control-allow-origin` |
| **401** en el login (`invalid credentials`) | API / datos | El seed trae hashes de relleno | `docker compose exec app python -m app.scripts.set_password CORREO` |
| **401** en cualquier ruta que antes funcionaba | Token | El token vencio (`ACCESS_TOKEN_MINUTES`) o cambiaste `SECRET_KEY` | Vuelve a ingresar |
| **403** / **404** al abrir un ticket | Reglas de negocio | Un solicitante solo ve sus tickets (404 si es de otra persona) | Ingresa con el rol correcto |
| `port is already allocated` | Tu maquina | Otro programa usa 8000 o 5433 | Cambia `APP_PORT` / `DB_PORT` en `.env` |
| Las horas salen desfasadas 6 horas | Base | El volumen se creo sin `TZ`/`PGTZ` | Respalda, `docker compose down -v` y vuelve a levantar |

