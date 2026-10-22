"""22/10/2026 - Asigna la contrasena de un usuario (el seed trae hashes de relleno).

    uv run python -m app.scripts.set_password usuario@umg.edu

Pide la contrasena por teclado (no se ve ni queda en el historial del shell).
`--password` existe para automatizar, pero la contrasena quedaria visible en el
historial y en la lista de procesos: usalo solo con valores de prueba.

Usa la base de DATABASE_URL (por defecto, la de desarrollo).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.core.database import session_scope
from app.core.security import hash_password
from app.repositories.sqlalchemy import SqlAlchemyUserRepository

MIN_LENGTH = 8
MAX_LENGTH = 128


def _ask_password() -> str | None:
    first = getpass.getpass("Nueva contrasena: ")
    second = getpass.getpass("Repite la contrasena: ")
    if first != second:
        print("Las contrasenas no coinciden.", file=sys.stderr)
        return None
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Asigna la contrasena de un usuario.")
    parser.add_argument("email")
    parser.add_argument("--password", help="solo para pruebas: queda visible en el historial")
    args = parser.parse_args(argv)

    password = args.password if args.password is not None else _ask_password()
    if password is None:
        return 1
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        print(f"La contrasena debe tener entre {MIN_LENGTH} y {MAX_LENGTH} caracteres.", file=sys.stderr)
        return 1

    with session_scope() as session:
        repository = SqlAlchemyUserRepository(session)
        user = repository.by_email(args.email)
        if user is None:
            print(f"No existe un usuario con el correo {args.email}.", file=sys.stderr)
            return 1
        repository.set_password_hash(user.id, hash_password(password))
    print(f"Contrasena actualizada para {user.email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
