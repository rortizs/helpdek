# Lista de verificación operativa - HelpDesk EDU (semana 17)

22/10/2026 - Richard Ortiz: esta es la lista que recorro **antes, durante y después** de desplegar. Sirve igual para mi laptop,
la de ustedes o un servidor. Cada punto se puede comprobar con un comando; si no puedo comprobarlo, no lo marco.

> Los comandos asumen que estás en la carpeta del proyecto. Si usas un proyecto de compose con otro nombre, agrega `-p NOMBRE`
> a `docker compose` y `--project NOMBRE` al script de respaldo.

## 1. Antes de desplegar (pre-deploy)

- [ ] `git status` limpio y estoy en la rama/etiqueta que quiero desplegar (`git log --oneline -1`).
- [ ] Las pruebas pasan: `uv run pytest -q` (con `TEST_DATABASE_URL` apuntando a una base cuyo nombre contenga `test`).
- [ ] `.env` existe, **no está en Git** (`git check-ignore .env` imprime `.env`) y tiene `SECRET_KEY` (≥ 32 caracteres) y `POSTGRES_PASSWORD`.
- [ ] `docker compose config -q` no muestra errores (si falta un secreto, aquí se ve).
- [ ] Hay espacio en disco y los puertos están libres (`APP_PORT`, `DB_PORT`): `docker ps` y `lsof -i :8000`.
- [ ] **Respaldo de la base actual** (si ya hay datos): `uv run python -m app.scripts.db_backup backup` y anoto el nombre del archivo.
- [ ] Conservo la imagen vigente para poder volver: `docker tag helpdesk-edu:local helpdesk-edu:previous`.
- [ ] Si el cambio toca el esquema (`docs/database/*.sql`): recuerdo que **solo corre con el volumen vacío**; la base con datos necesita una migración manual (respaldo → `ALTER` revisado → verificación).

## 2. Despliegue (deploy)

```bash
cp .env.example .env                 # solo la primera vez; completa SECRET_KEY y POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps                    # espero (healthy) en db y app
```

- [ ] `docker compose ps` muestra `db` y `app` en `healthy` (la app tarda unos segundos: espera a la base).
- [ ] Primera vez: asigno la contraseña de cada usuario con el que se va a ingresar (el seed trae hashes de relleno):
      `docker compose exec app python -m app.scripts.set_password requester@example.com`

## 3. Prueba de humo (post-deploy smoke)

Cinco comprobaciones, en este orden (cada una descarta una capa). Si una falla, no sigo con la siguiente: voy a la tabla de diagnóstico del README.

```bash
B=http://localhost:8000
curl -s $B/api/health                                   # 1. API + base            -> {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" $B/app/        # 2. cliente web           -> 200
curl -s -o /dev/null -w "%{http_code}\n" $B/api/tickets # 3. API exige token       -> 401
TOKEN=$(curl -s -X POST $B/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"requester@example.com","password":"LA_CONTRASENA"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s -o /dev/null -w "%{http_code}\n" $B/api/tickets -H "Authorization: Bearer $TOKEN"   # 4. login + lectura -> 200
curl -s -X POST $B/api/tickets -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"title":"Prueba de humo","description":"Creado por la lista operativa","category":"General","priority":"Low"}'  # 5. escritura -> 201
```

- [ ] Los cinco resultados coinciden con lo esperado.
- [ ] `docker compose logs app --tail 20` muestra líneas `helpdesk.request` y `helpdesk.audit` con la hora local, y **ningún** token ni contraseña.
- [ ] Abrí `http://localhost:8000/app` en el navegador, ingresé y vi la lista de tickets.
- [ ] La hora del ticket nuevo coincide con la del reloj (zona `America/Guatemala`).
- [ ] Borro el ticket de prueba o lo cancelo desde la interfaz si no quiero dejarlo.

## 4. Respaldo y restauración (backup / restore)

```bash
uv run python -m app.scripts.db_backup backup                        # crea backups/helpdesk_AAAAMMDDTHHMMSS.dump (permiso 600)
uv run python -m app.scripts.db_backup restore backups/ARCHIVO.dump --yes   # REEMPLAZA los datos actuales
```

- [ ] Hago un respaldo **antes** de cada despliegue y **antes** de cualquier migración.
- [ ] El archivo no está vacío y empieza con `PGDMP` (el script lo valida; si no, lo borra y avisa).
- [ ] `backups/` y `*.dump` están en `.gitignore`: un respaldo tiene hashes de contraseñas y datos de personas. Lo guardo fuera del repositorio y no lo comparto.
- [ ] **Un respaldo que nunca restauré no es un respaldo**: al menos una vez restauro uno en un proyecto desechable
      (`docker compose -p prueba ...`) y cuento filas (`select count(*) from tickets`).
- [ ] `restore` sin `--yes` no hace nada (sale con código 2): es a propósito.
- [ ] Conservo varios respaldos (por ejemplo los últimos 7) y borro los viejos a mano.

## 5. Reversa (rollback)

Si la prueba de humo falla y no puedo arreglarlo en pocos minutos, vuelvo atrás **en este orden**:

1. **Código**: `git checkout <commit o etiqueta anterior>` y `docker compose up -d --build`
   (o, si guardé la imagen: `docker tag helpdesk-edu:previous helpdesk-edu:local && docker compose up -d --no-build`).
2. **Datos** (solo si el despliegue cambió o dañó datos): `uv run python -m app.scripts.db_backup restore backups/ARCHIVO.dump --yes`
   con el respaldo que hice en el paso pre-deploy.
3. Repito la prueba de humo (sección 3) sobre la versión restaurada.
4. Dejo anotado qué falló (hora, comando, línea de `docker compose logs`) **sin copiar secretos**.

- [ ] Sé qué commit estaba desplegado antes (`git log --oneline`) y dónde está el último respaldo.
- [ ] `docker compose down -v` **borra el volumen y todos los datos**: no es una reversa, es el último recurso y solo con respaldo.

## 6. Evidencia que puedo compartir

- [ ] Salida de `docker compose ps`, `curl /api/health` y las líneas de log con método, ruta, estado y duración.
- [ ] Capturas del cliente en `/app`.
- [ ] **No** comparto: `.env`, el archivo `.dump`, tokens, contraseñas, ni el resultado de `docker compose config` (expande los secretos).
