# 1. Flujo Git/GitHub que se usará todo el curso

## 1.1 Ramas principales

Rama = main (Versión estable,, aprobada y demostrable para producción), quién debe tocar esta rama mediante Pull Rquest aprobados.
Rama = developer (Integración de trabajo semanal, antes pasar a la rama estable), quién lo hace? = Todo el equipo developers.

## Feauture/week

feature/week-07-08-inital project.

## 1.2 Por qué no trabajar directo en main

main representa lo que se puede presentar, evaluar o desplegar. Si se trabaja directo ahí, cualquier error queda mezclado con la versión estable. La rama developer permite integrar avances sin romper la línea estable. Las ramas feature/* permiten revisar cambios pequeños y claros.

## 1.3 Ciclo semanal recomendado

```bash
git checkout developer
git pull origin developer
git checkout -b feature/week-07-models
```

## trabajar código de la semana

```bash
git status
git add . # agrega todo
git commit -m "feat(models): add initial user and ticket domain"
git push -u origin feature/week-07-models
```

## Luego se crea un PR (Pull Request)

```bash
gh pr create --base developer --head feature/week-07-models --title "feat(models): add initial domain" --body "Adds User and Ticket models for Week 7. Includes basic validation evidence."
```

## Después de aprobar y fusionar el PR en GitHub

```bash
git checkout developer
git pull origin developer
```

## Ese pull es importante: actualiza la rama local con lo que GitHub ya fusionó. Si el estudiante no lo hace, la siguiente semana empieza desde una copia atrasada

# 2. Etapa 0 - Crear carpeta, inicializar Git y subir developer

Esta etapa prepara el terreno. Todavía no estamos programando el sistema; estamos creando una base ordenada para que el proyecto pueda crecer sin convertirse en un desorden.

## 2.1 Crear carpeta del proyecto

```bash
mkdir HelpDesk_EDU
cd HelpDesk_EDU
```

Explicación para clase: una carpeta de proyecto no es solo un lugar para guardar archivos. Es el límite del sistema: aquí vivirán el código, pruebas, documentación, configuración y control de versiones.

## 2.2 Inicializar Git con main

```bash
git init -b main
git init
```

convierte la carpeta en un repositorio. La opción -b main crea la rama principal con el nombre moderno usado por GitHub.

## 2.3 Crear archivos base

``bash
touch README.md .gitignore pyproject.tomlmkdir -p app/models app/services app/repositories app/schemas app/core tests docs
``

### 2.3.1 Estructura del proyecto

HelpDesk_EDU/
├── .github
│ ├── workflows
│ │ └── ci.yml
│ └── pull_request_template.md
├── app
│ ├── api #api rest (end-point que van a recibir y enviar datos, get, push, put, post)
│ │ ├── routes
│ │ │ ├── __init__.py
│ │ │ ├── assistance.py
│ │ │ ├── auth.py
│ │ │ ├── knowledge_base.py
│ │ │ ├── mobile.py
│ │ │ ├── notifications.py
│ │ │ ├── system.py
│ │ │ ├── tickets.py
│ │ │ └── users.py
│ │ └── __init__.py
│ ├── core
│ │ ├── __init__.py
│ │ ├── config.py
│ │ ├── database.py
│ │ ├── dependencies.py
│ │ └── security.py
│ ├── domain
│ │ ├── __init__.py
│ │ ├── errors.py
│ │ └── workflow.py
│ ├── models
│ │ ├── __init__.py
│ │ ├── entities.py
│ │ └── enums.py
│ ├── repositories
│ │ ├── __init__.py
│ │ ├── articles.py
│ │ ├── base.py
│ │ ├── notifications.py
│ │ └── sqlalchemy.py
│ ├── schemas
│ │ ├── __init__.py
│ │ ├── articles.py
│ │ ├── assistance.py
│ │ ├── auth.py
│ │ ├── mobile.py
│ │ ├── notifications.py
│ │ ├── tickets.py
│ │ └── users.py
│ ├── services
│ │ ├── __init__.py
│ │ ├── articles.py
│ │ ├── assistance.py
│ │ ├── auth.py
│ │ ├── notifications.py
│ │ ├── tickets.py
│ │ └── users.py
│ ├── web
│ │ ├── templates
│ │ │ ├── portal
│ │ │ │ ├── _ticket_table.html
│ │ │ │ ├── detail.html
│ │ │ │ ├── home.html
│ │ │ │ ├── new.html
│ │ │ │ └── tickets.html
│ │ │ ├── staff
│ │ │ │ ├── _ticket_table.html
│ │ │ │ ├── dashboard.html
│ │ │ │ ├── detail.html
│ │ │ │ ├── new.html
│ │ │ │ ├── notifications.html
│ │ │ │ └── tickets.html
│ │ │ ├── base_public.html
│ │ │ ├── base_staff.html
│ │ │ ├── knowledge_base.html
│ │ │ ├── landing.html
│ │ │ └── login.html
│ │ ├── __init__.py
│ │ └── routes.py
│ ├── __init__.py
│ └── main.py
├── docs
│ ├── database
│ │ ├── er.md
│ │ ├── queries.sql
│ │ ├── schema.sql
│ │ └── seed.sql
│ ├── decisions
│ │ ├── 0001-fastapi-y-sqlalchemy.md
│ │ └── 0002-errores-de-dominio.md
│ ├── architecture.md
│ ├── manual_tecnico.md
│ └── manual_usuario.md
├── scripts
│ ├── __init__.py
│ ├── backup_db.py
│ ├── console.py
│ ├── seed_demo.py
│ └── sql_lab.py
├── tests
│ ├── __init__.py
│ ├── conftest.py
│ ├── test_week07_domain.py
│ ├── test_week08_relations.py
│ ├── test_week09_architecture.py
│ ├── test_week10_schema.py
│ ├── test_week11_persistence.py
│ ├── test_week12_exam.py
│ ├── test_week13_persistence.py
│ ├── test_week14_api.py
│ ├── test_week15_architecture.py
│ ├── test_week15_web.py
│ ├── test_week16_release.py
│ └── test_week17_modules.py
├── .dockerignore
├── .env.example
├── .gitignore
├── .python-version
├── Dockerfile
├── README.md
├── docker-compose.yml
└── pyproject.toml

## 2.4 .gitignore

Este archivo oculto de git, ignora archivos que no son necesarios en el repositorio remoto.

.venv/
__pycache__
*.pyc
.env
*.db
.pytest_cache/
.coverage
.DS_Store

__Por qué: Git debe guardar código fuente y documentos importantes, no entornos virtuales, bases locales, cachés ni secretos.__

## 2.5 pyproject.toml inicial

[project]name = "helpdesk-edu"
version = "0.1.0"
description = "A teachable HelpDesk EDU application"
requires-python = ">=3.12"
dependencies = []
[dependency-groups]
dev = ["pytest>=8.3"]
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

## 2.6 Primer commit

git statusgit add .git commit -m "chore: initialize project structure"
Explicación: este commit no agrega funcionalidad. Por eso usa chore:. Guarda la estructura inicial del proyecto.

## 2.7 Crear repositorio remoto y subir main

Si se usará GitHub CLI:

```bash
gh repo create TU_USUARIO/HelpDesk_EDU --public --source=. --remote=origin --push
```

Si el repositorio ya fue creado en GitHub:

```bash
git remote add origin https://github.com/TU_USUARIO/HelpDesk_EDU.gitgit
git push -u origin main
```

## 2.8 Crear y subir developer

```bash
git checkout -b develper
git push -u origin develper
```

Por qué: developer será la rama de integración del curso. Cada avance semanal entra primero allí. Solo cuando una etapa esté validada se prepara un PR hacia main.

## 2.9 Validación de la etapa 0

```bash
git branch
git remote -v
git status
```

Debe observarse:
  -- Rama local main creada.
  -- Rama local developer creada.
  -- Remoto origin configurado.
  --Árbol limpio: working tree clean.

## 2.10 Commit/PR de etapa 0

Normalmente el primer push de main no requiere PR si el repo estaba vacío. A partir de aquí, sí trabajaremos con PRs.

## 3. Desarrollo semana por semana

 --Semana 7 - Encapsulamiento, listas y primer dominio
 --Versión objetivo: v0.1
 --Incremento: Crear las primeras clases del dominio y trabajar en memoria.

 Resultado esperado
Al finalizar, el proyecto tendrá modelos base User y Ticket, servicio en memoria, prueba mínima y primer PR funcional hacia developer.

## Flujo Git de la semana

```bash
git checkout developer
git pull origin developer
git checkout -b feature/week-7-encapsulamiento-listas-y-primer-dominio
```

Desarrollo paso a paso
  -- 1. Crear vocabulario del dominio: roles, estados, categorías y prioridades.
  -- 2. Crear entidades simples User y Ticket.
  -- 3. Crear un servicio en memoria para registrar tickets.
  -- 4. Escribir una prueba mínima.
  -- 5. Confirmar que la prueba pasa.

## Semana 8 - Relaciones prácticas: técnico, categoría, comentario y asignación

Versión objetivo: v0.2
Incremento: Conectar objetos para que el sistema deje de ser una lista plana.

## Resultado esperado

El sistema tendrá relaciones básicas entre ticket, solicitante, técnico, categoría y comentarios.

Flujo Git de la semana

```bash
git checkout developer
git pull origin developer
git checkout -b feature/week-8-relaciones-practicas-tecnico-categoria
```

## Desarrollo paso a paso

1. Agregar clases para Category, Comment y Assignment.
2. Relacionar ticket con solicitante y técnico asignado.
3. Agregar operaciones: asignar técnico y comentar ticket.
4. Crear pruebas de asignación y comentario.

```py
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Category:
    id: int
    name: str


@dataclass
class Comment:
    id: int
    ticket_id: int
    author_id: int
    body: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Assignment:
    ticket_id: int
    technician_id: int
    assigned_at: datetime = field(default_factory=datetime.utcnow)
```

Regla de clase: una relación no es “una variable más”. Una relación expresa una pregunta del negocio:

- ¿Quién reportó el ticket?
- ¿Quién lo atiende?
- ¿Qué comentarios documentan el seguimiento?
- ¿Qué categoría ayuda a filtrar y priorizar?

## Validación mínima

```bash
uv run pytest -q
```

### git Commit de la semana

```bash
git status
git add .
git commit -m "feat(domain): complete week 8 increment"
git push -u origin feature/week-8-relaciones-practicas-tecnico-categoria
```


## Abstracción, repositorios, polimorfismo y excepciones

## Incremente: Separar reglas de negocio de almacenamiento y manjear errores del dominio

con esto el sistema separará dominio, respositorios y servicios. El almacenamiento en memoria quedará detrás de una abstracción.

## Primero vamos a revisar el Status de nuestro flujo de git de la semana

```git
git chetckout developer
git pull origin developer #recuerde este comando permite traer todo lo que tenemos en el repositorio.
git checkout -b feature/week-9-abstraccion-repositorio-polimorfismo
```

## para los test en cada feature realizar las pruebas minimas

```bash
 uv run pytest -q
```

## commit de la semana

```git
git status
git add .
git commit -m "feat(architecture): complete week 9 increment"
git push -u origin feature/week-9-abstraccion-repositorio-polimorfismo
```

## Crear el Pull Request hacia develper

``` git
gh pr create --base developer --head feature/weei-9-abstraccion-repositorios-polimorfismo --title "feat(architecture): week 9 increment" --body "Week 9 increment. Includes source code, validation evidence, and acceptance checklist."
```

## validaciones o checklist

Checklist del PR:
☐ El PR sale de una rama feature/*.
☐ La base del PR es developer.
☐ Hay explicación de qué cambió.
☐ Hay evidencia de validación.
☐ No se subieron .env, .venv, bases locales ni secretos.

## merge a la rama

``` git
git checkout developer
git pull origin developer
git branch --delete feature/week-9-abstraccion-repositorios-polimorfismo
```
## SEMANA 10 Y 11
Entidades del negocio del sistema Help Desk Edu. 

## users
Pregunta de negocio: Quién reporta, atiende, comenta, administra?

├ Atributo --├── Tipo         ----├── Restricciones           ├── Por qué este tipo                                                   ├── Origen en el ORM              ├
├ id.        ├   INTEGER (SERIAL).├──   PK, NO ACEPTA NULOS.  ├── Identificador interno; la base de datos lo asgina al insertar.      ├─mapperd_column(primary_key=true)
├ email      ├.  VARCHAR(120).    ├──. NO ACEPTA NULOS, UNICO ├── Es una llave natural (candidata) para el login, UNIQUE              ├──. 
├ name.      ├   VARCAHR(100).    ├──. NO ACEPTA NULOS        ├── Nombres que podemos mostrar con 100 caracteres.                     ├──. String(100)
├ role       ├── VARCHAR(20).     ├──. NO ACEPTA NULOS.       ├── Vocabulario cerrado (Administrador,Supervisor,Tecnico,recepcionista)├──  String(20) Validado por Roles├
├ password_h ├─. VARCHAR(255).    ├──  NO ACEPTA NULOS.       ├── Hash PBKDF2-SHA256 con sal(~90 caracteres); 255 margen algoritmos.  ├──. hash_password


Dependencias funcionales: id -> email,name, role, passowrd_hash; email -> id (llave candidata alterna)
FORMA NORMAL: 3FN (y BCNF). Está en 1FN (valores atómicos, PK), en 2FN Trivialmente (PK simple, no hay dependencias); en 3FN porque ningún atributo no clave depende de otro no clave: name, role y password_hash dependen del usuario. email es determinante  pero es llave candidata, lo que cumple también BNCF.


