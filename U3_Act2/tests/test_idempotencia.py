"""Unidad III - Actividad 2, Parte 1: idempotencia en createTransaction.

BD SQLite en memoria, autocontenida. Ejecutar desde U3_Act2/:
    pytest -v tests/test_idempotencia.py
"""
import os

import pytest

os.environ.setdefault("JWT_SECRET", "secreto-solo-para-pruebas")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.main import schema
from app.seguridad import crear_token

M_CREAR = """
mutation($input: CreateTransactionInput!) {
  createTransaction(input: $input) { id amount }
}"""


class _Request:
    def __init__(self, token):
        self.headers = {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def entorno():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()

    permiso = models.Permission(code="transactions.write", name="Escribir movimientos",
                                is_active=True)
    rol = models.Role(code="ADMINISTRADOR", name="Administrador", is_active=True)
    empresa = models.Company(name="Empresa Test")
    usuario = models.User(name="Tester", email="t@test.com", hashed_password="x", is_active=True)
    db.add_all([permiso, rol, empresa, usuario])
    db.flush()
    db.add(models.RolePermission(role_id=rol.id, permission_id=permiso.id, is_active=True))
    membresia = models.CompanyUser(company_id=empresa.id, user_id=usuario.id, is_active=True)
    db.add(membresia)
    db.flush()
    db.add(models.CompanyUserRole(company_user_id=membresia.id, role_id=rol.id, is_active=True))
    cuenta = models.Account(company_id=empresa.id, name="Banco",
                            account_type=models.AccountTypeEnum.DEBIT)
    concepto = models.Concept(company_id=empresa.id, name="Ingreso",
                              concept_type=models.ConceptTypeEnum.INCOME)
    db.add_all([cuenta, concepto])
    db.flush()
    db.add(models.AccountConcept(account_id=cuenta.id, concept_id=concepto.id, is_active=True))
    db.commit()

    token = crear_token(membresia.id, empresa.id)

    class Env:
        pass

    env = Env()
    env.db, env.cuenta_id, env.concepto_id = db, cuenta.id, concepto.id

    def crear(llave, monto="100.00"):
        entrada = {
            "accountId": str(cuenta.id), "conceptId": str(concepto.id),
            "transactionType": "INCOME", "amount": monto, "idempotencyKey": llave,
        }
        ctx = {"db": db, "request": _Request(token)}
        return schema.execute_sync(M_CREAR, variable_values={"input": entrada}, context_value=ctx)

    env.crear = crear
    yield env
    db.close()


def _total(env):
    return env.db.query(models.Transaction).count()


def test_misma_llave_devuelve_mismo_movimiento_sin_duplicar(entorno):
    r1 = entorno.crear("llave-1")
    r2 = entorno.crear("llave-1")
    assert r1.errors is None and r2.errors is None
    assert r1.data["createTransaction"]["id"] == r2.data["createTransaction"]["id"]
    assert _total(entorno) == 1
    assert entorno.db.query(models.IdempotencyKey).count() == 1


def test_llave_distinta_crea_movimiento_aparte_aunque_el_monto_sea_igual(entorno):
    r1 = entorno.crear("llave-A")
    r2 = entorno.crear("llave-B")
    assert r1.errors is None and r2.errors is None
    assert r1.data["createTransaction"]["id"] != r2.data["createTransaction"]["id"]
    assert _total(entorno) == 2


def test_misma_llave_con_monto_distinto_se_rechaza(entorno):
    assert entorno.crear("llave-X", "100.00").errors is None
    r = entorno.crear("llave-X", "250.00")
    assert r.errors is not None
    assert "idempotencia" in str(r.errors[0]).lower()
    assert _total(entorno) == 1


@pytest.mark.parametrize("llave", ["", "   ", "\t\n"])
def test_llave_vacia_o_en_blanco_se_rechaza(entorno, llave):
    r = entorno.crear(llave)
    assert r.errors is not None
    assert "obligatoria" in str(r.errors[0]).lower()
    assert _total(entorno) == 0


def test_llave_de_mas_de_100_caracteres_se_rechaza(entorno):
    r = entorno.crear("x" * 101)
    assert r.errors is not None
    assert _total(entorno) == 0
