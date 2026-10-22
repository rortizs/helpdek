"""22/10/2026 - Respaldo y restauracion de la base de datos del despliegue con Docker (semana 17).

    uv run python -m app.scripts.db_backup backup                    # crea backups/helpdesk_AAAAMMDDTHHMMSS.dump
    uv run python -m app.scripts.db_backup restore backups/ARCHIVO.dump --yes

Corre en TU maquina y le pide al contenedor `db` (docker compose) que ejecute `pg_dump` / `pg_restore`. Asi no
hace falta instalar PostgreSQL en el host, y el usuario y la base los toma el propio contenedor de sus variables
POSTGRES_USER / POSTGRES_DB: este script no lee el .env ni conoce la contrasena.

Formato custom de pg_dump (-Fc): comprimido, se restaura con pg_restore y permite elegir que restaurar.
Un respaldo contiene hashes de contrasenas y datos de personas: se guarda con permiso 600 y `backups/` y `*.dump`
estan en .gitignore. Solo usa la biblioteca estandar.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("backups")
# 22/10/2026 - Todo archivo en formato custom de pg_dump empieza con estos cinco bytes.
DUMP_MAGIC = b"PGDMP"

DUMP_COMMAND = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'
# --clean --if-exists: borra los objetos antes de recrearlos (sin error si no existen); --no-owner: no intenta
# reasignar duenos que quiza no existan en la base de destino.
RESTORE_COMMAND = 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'

Runner = Callable[..., object]


class BackupError(RuntimeError):
    """22/10/2026 - Algo salio mal al respaldar o restaurar; el mensaje dice que y que revisar."""


def backup_filename(now: datetime) -> str:
    """22/10/2026 - Nombre con fecha y hora: ordenado alfabeticamente es tambien ordenado en el tiempo."""
    return f"helpdesk_{now:%Y%m%dT%H%M%S}.dump"


def _compose(project: str | None, *args: str) -> list[str]:
    """22/10/2026 - `docker compose [-p proyecto] exec -T db ...`; -T porque no hay terminal (se usan tuberias)."""
    base = ["docker", "compose"]
    if project:
        base += ["-p", project]
    return [*base, "exec", "-T", "db", *args]


def _looks_like_a_dump(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(DUMP_MAGIC)) == DUMP_MAGIC


def backup(
    output_dir: Path,
    *,
    project: str | None = None,
    now: datetime | None = None,
    runner: Runner = subprocess.run,
) -> Path:
    """22/10/2026 - Guarda un pg_dump de la base en `output_dir` y devuelve la ruta del archivo.

    El archivo se crea con permiso 600 ANTES de escribir nada. Si pg_dump falla, o lo que quedo no es un
    respaldo valido (por ejemplo un mensaje de error), lo borro: un archivo roto que parece bueno es peor
    que ningun archivo.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / backup_filename(now or datetime.now())
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            runner(_compose(project, "sh", "-c", DUMP_COMMAND), stdout=handle, check=True)
        if not _looks_like_a_dump(path):
            raise BackupError(f"{path.name} no es un respaldo valido (falta la marca PGDMP); revisa 'docker compose ps'.")
    except (BackupError, subprocess.CalledProcessError, OSError) as error:
        path.unlink(missing_ok=True)
        if isinstance(error, BackupError):
            raise
        raise BackupError(f"pg_dump fallo ({error}); la base esta arriba? Prueba 'docker compose ps'.") from error
    return path


def restore(
    dump: Path,
    *,
    project: str | None = None,
    runner: Runner = subprocess.run,
) -> None:
    """22/10/2026 - Restaura `dump` sobre la base del contenedor. DESTRUCTIVO: reemplaza los datos actuales."""
    if not dump.is_file():
        raise BackupError(f"El archivo {dump} no existe.")
    if not _looks_like_a_dump(dump):
        raise BackupError(f"{dump} no parece un respaldo de pg_dump (falta la marca PGDMP).")
    try:
        with dump.open("rb") as handle:
            runner(_compose(project, "sh", "-c", RESTORE_COMMAND), stdin=handle, check=True)
    except (subprocess.CalledProcessError, OSError) as error:
        raise BackupError(f"pg_restore fallo ({error}); revisa 'docker compose logs db'.") from error


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    """22/10/2026 - Interfaz de linea de comandos. Devuelve 0 si salio bien, 1 si fallo y 2 si falta confirmar."""
    parser = argparse.ArgumentParser(description="Respalda o restaura la base de HelpDesk EDU (docker compose).")
    # --project se escribe despues del subcomando (backup / restore), asi que lo comparten por "parents".
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", help="nombre del proyecto de compose (docker compose -p); por defecto, el de esta carpeta")
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup", parents=[common], help="crea un respaldo con fecha y hora")
    backup_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="carpeta de destino (backups/)")

    restore_parser = commands.add_parser("restore", parents=[common], help="restaura un respaldo (reemplaza los datos actuales)")
    restore_parser.add_argument("file", type=Path)
    restore_parser.add_argument("--yes", action="store_true", help="confirmo que quiero reemplazar los datos actuales")

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            print(backup(args.output_dir, project=args.project, runner=runner))
            return 0
        if not args.yes:
            print("Restaurar REEMPLAZA los datos actuales de la base. Repite el comando con --yes para confirmar.", file=sys.stderr)
            return 2
        restore(args.file, project=args.project, runner=runner)
        print(f"Restauracion terminada desde {args.file}")
        return 0
    except BackupError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
