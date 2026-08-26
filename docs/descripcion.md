# 1. Flujo Git/GitHub que se usará todo el curso
## 1.1 Ramas principales

Rama = main (Versión estable,, aprobada y demostrable para producción), quién debe tocar esta rama mediante Pull Rquest aprobados. 
Rama = developer (Integración de trabajo semanal, antes pasar a la rama estable), quién lo hace? = Todo el equipo developers. 

## Feauture/week
feature/week-07-08-inital project. 

## 1.2 Por qué no trabajar directo en main
main representa lo que se puede presentar, evaluar o desplegar. Si se trabaja directo ahí, cualquier error queda mezclado con la versión estable. La rama developer permite integrar avances sin romper la línea estable. Las ramas feature/* permiten revisar cambios pequeños y claros.

## 1.3 Ciclo semanal recomendado
``bash
git checkout developer
git pull origin developer
git checkout -b feature/week-07-models
``
## trabajar código de la semana
``bash 
git status
git add . # agrega todo 
git commit -m "feat(models): add initial user and ticket domain"
git push -u origin feature/week-07-models
``
## Luego se crea un PR (Pull Request):
``bash
gh pr create --base developer --head feature/week-07-models --title "feat(models): add initial domain" --body "Adds User and Ticket models for Week 7. Includes basic validation evidence."
``

## Después de aprobar y fusionar el PR en GitHub:
``bash
git checkout developer
git pull origin developer
``
## Ese pull es importante: actualiza la rama local con lo que GitHub ya fusionó. Si el estudiante no lo hace, la siguiente semana empieza desde una copia atrasada.

# 2. Etapa 0 - Crear carpeta, inicializar Git y subir developer
Esta etapa prepara el terreno. Todavía no estamos programando el sistema; estamos creando una base ordenada para que el proyecto pueda crecer sin convertirse en un desorden.
## 2.1 Crear carpeta del proyecto
``bash
mkdir HelpDesk_EDU
cd HelpDesk_EDU
``
Explicación para clase: una carpeta de proyecto no es solo un lugar para guardar archivos. Es el límite del sistema: aquí vivirán el código, pruebas, documentación, configuración y control de versiones.

## 2.2 Inicializar Git con main
``bash 
git init -b main
git init
`` 
convierte la carpeta en un repositorio. La opción -b main crea la rama principal con el nombre moderno usado por GitHub.

## 2.3 Crear archivos base
``bash 
touch README.md .gitignore pyproject.tomlmkdir -p app/models app/services app/repositories app/schemas app/core tests docs
``
### 2.3.1 Estructura del proyecto 
helpdesk
|--app/
  |
  |--core/
  |--models/
  |--repositories/
  |--shcemas/
  |--services/
|--docs/
|--test/
|-- .gitignore
|-- pyproject.toml
|-- README.md 

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

**Por qué: Git debe guardar código fuente y documentos importantes, no entornos virtuales, bases locales, cachés ni secretos.**

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
