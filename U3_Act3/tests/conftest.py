"""Aislar incluso el arranque de app.main antes de recolectar las pruebas.

No se abre sistema.db. Las semillas automáticas y las pruebas heredadas de
Usuarios usan una BD SQLite en memoria; las demás fixtures crean su propia BD.
"""
import importlib
import os
import secrets

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))

from app import database, models

database.engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False)
main = importlib.import_module("app.main")


@pytest.fixture(scope="module", autouse=True)
def datos_usuarios_heredados(request):
    """Satisfacer el login de las pruebas antiguas sin poblar la BD del equipo."""
    if not request.module.__name__.endswith("test_usuarios"):
        yield
        return
    with database.SessionLocal() as db:
        company = models.Company(name="Empresa aislada de Usuarios")
        db.add(company)
        db.flush()
        user = models.User(
            name="Administrador de pruebas",
            email=request.module.ADMIN_EMAIL,
            hashed_password=main.get_password_hash(request.module.ADMIN_PASSWORD),
        )
        db.add(user)
        db.flush()
        membership = models.CompanyUser(company_id=company.id, user_id=user.id, is_admin=True)
        db.add(membership)
        db.flush()
        role = db.query(models.Role).filter_by(code="ADMINISTRADOR").one()
        db.add(models.CompanyUserRole(company_user_id=membership.id, role_id=role.id))
        db.commit()
    yield
