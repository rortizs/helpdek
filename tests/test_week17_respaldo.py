"""22/10/2026 - Semana 17: respaldo y restauracion de la base con pg_dump / pg_restore.

Estas pruebas NO necesitan Docker ni PostgreSQL: el script recibe el "ejecutor" de comandos como parametro y
aqui le paso uno falso que anota lo que le pidieron. El respaldo REAL (contra el contenedor de compose) lo
verifico a mano en el proyecto desechable y queda documentado en docs/operacion/checklist_operativa.md.
"""

from __future__ import annotations

import stat
from datetime import datetime
from pathlib import Path

import pytest

from app.scripts import db_backup

DUMP_BYTES = b"PGDMP" + b"\x01\x0e\x00" + b"contenido-binario-del-respaldo"


class FakeRunner:
    """22/10/2026 - Reemplaza a subprocess.run: guarda los comandos y escribe un respaldo falso en stdout."""

    def __init__(self, payload: bytes = DUMP_BYTES, returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.payload = payload
        self.returncode = returncode

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if "stdout" in kwargs and kwargs["stdout"] is not None:
            kwargs["stdout"].write(self.payload)
        return type("Completed", (), {"returncode": self.returncode})()


def test_backup_filename_is_timestamped_and_sortable():
    assert db_backup.backup_filename(datetime(2026, 10, 22, 15, 30, 5)) == "helpdesk_20261022T153005.dump"


def test_backup_runs_pg_dump_inside_the_db_service_in_custom_format(tmp_path):
    runner = FakeRunner()

    path = db_backup.backup(tmp_path, now=datetime(2026, 10, 22, 8, 0, 0), runner=runner)

    command, kwargs = runner.calls[0]
    # El usuario y la base los toma el SHELL DEL CONTENEDOR de sus propias variables (POSTGRES_USER / POSTGRES_DB):
    # el script del host no necesita leer el .env ni conocer la contrasena (el socket local de la imagen no la pide).
    assert command == [
        "docker", "compose", "exec", "-T", "db",
        "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
    ]
    assert kwargs["check"] is True
    assert path == tmp_path / "helpdesk_20261022T080000.dump"
    assert path.read_bytes() == DUMP_BYTES


def test_backup_can_target_another_compose_project(tmp_path):
    runner = FakeRunner()

    db_backup.backup(tmp_path, project="hd_wk17_check", runner=runner)

    assert runner.calls[0][0][:5] == ["docker", "compose", "-p", "hd_wk17_check", "exec"]


def test_backup_file_is_private_to_the_owner(tmp_path):
    path = db_backup.backup(tmp_path, runner=FakeRunner())

    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # lleva hashes de contrasenas


def test_backup_creates_the_output_folder(tmp_path):
    target = tmp_path / "backups" / "nuevo"

    path = db_backup.backup(target, runner=FakeRunner())

    assert path.parent == target and path.exists()


def test_a_backup_that_is_not_a_pg_dump_file_is_rejected_and_removed(tmp_path):
    with pytest.raises(db_backup.BackupError, match="PGDMP"):
        db_backup.backup(tmp_path, runner=FakeRunner(payload=b"error: connection refused"))

    assert list(tmp_path.iterdir()) == []  # no queda un respaldo corrupto que parezca bueno


def test_restore_without_confirmation_does_nothing(tmp_path, capsys):
    dump = tmp_path / "helpdesk_x.dump"
    dump.write_bytes(DUMP_BYTES)
    runner = FakeRunner()

    code = db_backup.main(["restore", str(dump)], runner=runner)

    assert code == 2
    assert runner.calls == []
    assert "--yes" in capsys.readouterr().err


def test_restore_pipes_the_file_into_pg_restore_with_clean_and_no_owner(tmp_path):
    dump = tmp_path / "helpdesk_x.dump"
    dump.write_bytes(DUMP_BYTES)
    runner = FakeRunner()

    code = db_backup.main(["restore", str(dump), "--yes", "--project", "hd_wk17_check"], runner=runner)

    command, kwargs = runner.calls[0]
    assert code == 0
    assert command == [
        "docker", "compose", "-p", "hd_wk17_check", "exec", "-T", "db",
        "sh", "-c", 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner',
    ]
    assert kwargs["check"] is True
    assert kwargs["stdin"].name == str(dump)


def test_restore_refuses_a_missing_or_foreign_file(tmp_path, capsys):
    not_a_dump = tmp_path / "notas.txt"
    not_a_dump.write_text("hola")
    runner = FakeRunner()

    assert db_backup.main(["restore", str(tmp_path / "no_existe.dump"), "--yes"], runner=runner) == 1
    assert db_backup.main(["restore", str(not_a_dump), "--yes"], runner=runner) == 1

    assert runner.calls == []
    assert "no existe" in capsys.readouterr().err


def test_main_backup_prints_the_path_and_returns_zero(tmp_path, capsys):
    code = db_backup.main(["backup", "--output-dir", str(tmp_path)], runner=FakeRunner())

    assert code == 0
    assert str(tmp_path) in capsys.readouterr().out
    assert isinstance(next(tmp_path.iterdir()), Path)
