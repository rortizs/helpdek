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

## Estructura

| Carpeta | Que contiene |
| --- | --- |
| `app/models`, `app/domain` | Entidades, enums, reglas y errores de dominio |
| `app/repositories` | Contratos y su implementacion en memoria / SQLAlchemy |
| `app/services` | Reglas de negocio (tickets, usuarios, avisos, autenticacion) |
| `app/api`, `app/schemas`, `app/main.py` | Rutas HTTP, esquemas Pydantic y fabrica de la app |
| `app/core` | Configuracion, base de datos, seguridad (hash y JWT) |
| `docs/database` | Esquema, triggers, seed y consultas SQL |
| `docs/decisions` | ADR: decisiones de arquitectura con su problema, patron y limites |

## Patrones (semana 15)

22/10/2026 - Aplicados solo donde resuelven un problema real (ver `docs/decisions/0005-patrones-semana-15.md`):

- **Observer**: `TicketService` publica eventos (`app/domain/events.py`); avisos y auditoria son suscriptores.
- **Facade**: las rutas hablan con `HelpDeskFacade` (`app/services/helpdesk.py`).
- **Inyeccion de dependencias**: `Depends` + `app.dependency_overrides` para cambiar piezas en las pruebas.
- **Singleton (critica)**: el engine ya no es global; lo posee cada aplicacion (`app.state.database`).
- **Decorator**: no se aplico, y el ADR explica por que.
