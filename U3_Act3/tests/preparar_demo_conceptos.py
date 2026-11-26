"""Copia segura para evidencias P4; jamás prepara datos sobre sistema.db original.

Uso desde la raíz (el directorio debe estar fuera del repositorio):
    python -B U3_Act2/tests/preparar_demo_conceptos.py /tmp/u3-p4-demo

Pide una contraseña sin mostrarla. Para automatizar, usa P4_DEMO_PASSWORD.
Usuarios creados exclusivamente en la copia:
    p4.editor@demo.test     — concepts.read/write, accounts.read
    p4.consulta@demo.test   — concepts.read, accounts.read
"""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import sqlite3
import sys

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directorio", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    directory = args.directorio.resolve()
    if directory.is_relative_to(repo):
        parser.error("La demostración debe estar fuera del repositorio, por ejemplo en /tmp.")
    target = directory / "sistema.db"
    if target.exists() or target.is_symlink():
        parser.error("La base de destino ya existe. Usa un directorio temporal nuevo.")
    source = repo / "sistema.db"
    if not source.is_file():
        parser.error("No existe sistema.db en la raíz del repositorio.")
    password = os.environ.get("P4_DEMO_PASSWORD") or getpass.getpass("Contraseña para los dos usuarios de demostración: ")
    if not password.strip():
        parser.error("La contraseña no puede estar vacía.")
    before = hashlib.sha256(source.read_bytes()).digest()
    directory.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(target) as copy:
            original.backup(copy)

    # Importar modelos no importa main ni ejecuta sus semillas.
    sys.path.insert(0, str(repo / "U3_Act2"))
    from app import models
    from app.database import Base

    engine = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(engine)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with sessionmaker(bind=engine)() as db:
        company = db.query(models.Company).filter_by(is_active=True).order_by(models.Company.id).first()
        if company is None:
            raise RuntimeError("La copia no contiene una empresa activa.")
        for code, email, codes in [
            ("P4_EDITOR", "p4.editor@demo.test", ["concepts.read", "concepts.write", "accounts.read"]),
            ("P4_CONSULTA", "p4.consulta@demo.test", ["concepts.read", "accounts.read"]),
        ]:
            role = models.Role(code=code, name=code)
            user = models.User(name=code, email=email, hashed_password=hashed)
            db.add_all([role, user])
            db.flush()
            member = models.CompanyUser(company_id=company.id, user_id=user.id)
            db.add(member)
            db.flush()
            db.add(models.CompanyUserRole(company_user_id=member.id, role_id=role.id))
            for permission_code in codes:
                permission = db.query(models.Permission).filter_by(code=permission_code, is_active=True).one()
                db.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
        db.commit()
    engine.dispose()
    if hashlib.sha256(source.read_bytes()).digest() != before:
        raise RuntimeError("La base original cambió durante la preparación; revisa otros procesos.")
    print(f"Base de demostración: {target}")
    print("Editor: p4.editor@demo.test")
    print("Consulta: p4.consulta@demo.test")
    print("Base original sin cambios. No se muestran contraseñas ni tokens.")


if __name__ == "__main__":
    main()
