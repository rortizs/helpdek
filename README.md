# helpdek

HelpDesk EDU: proyecto de clase de Programacion II (Python). Se construye semana a semana
sobre una arquitectura en capas: modelos de dominio, servicios, repositorios y, desde la
semana 14, una API REST con FastAPI.

## Puesta en marcha (semana 14)

22/10/2026 - Estos son los pasos que seguimos en clase para levantar la API:

```bash
docker compose up -d db          # PostgreSQL 16 en el puerto 5433
uv sync                          # dependencias del proyecto
cp .env.example .env             # y completa SECRET_KEY (ver abajo)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # genera una clave propia
uv run python -m app.scripts.set_password requester@example.com    # el seed trae hashes de relleno
uv run uvicorn app.main:app --reload --env-file .env
```

- Documentacion interactiva (OpenAPI): <http://localhost:8000/docs>
- Login: `POST /api/auth/login` devuelve un token; en `/docs` usa el boton **Authorize**.
- `SECRET_KEY` es obligatoria: la aplicacion no arranca sin ella (y nunca se sube a Git).

## Pruebas

```bash
uv run pytest -q
```

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
| `docs/database` | Esquema, triggers, seed y consultas SQL |
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
- **Y CORS?** Hoy cliente y API comparten origen, asi que no hace falta; en la semana 17 se explica cuando si y se configura.
