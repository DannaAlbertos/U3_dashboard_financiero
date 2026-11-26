"""Etapa 4: GraphQL real, sesiones nuevas y datos ficticios en SQLite en memoria."""
import re
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from graphql import parse, validate
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.main import schema, get_password_hash

ASSIGN = """mutation($member:ID!,$role:ID!){
  assignRole(companyUserId:$member,roleId:$role)
}"""
MY = "{myPermissions{code}}"
USERS = "{companyUsers{id isAdmin role{id code name}}}"
ROLES = "{roles(activeOnly:true){id code name}}"
MOVEMENTS = "query($id:ID!){transactions(accountId:$id){id amount}}"
CREATE = """mutation($input:CreateTransactionInput!){
  createTransaction(input:$input){id amount}
}"""
MATRIX = {
    "ADMINISTRADOR": ["company.users.read", "company.users.write", "accounts.read",
                      "accounts.write", "concepts.read", "concepts.write",
                      "transactions.read", "transactions.write", "roles.read", "roles.write"],
    "CONTADOR": ["company.users.read", "accounts.read", "accounts.write", "concepts.read",
                 "concepts.write", "transactions.read", "transactions.write", "roles.read"],
    "CAPTURISTA": ["accounts.read", "concepts.read", "transactions.read", "transactions.write"],
    "CONSULTA": ["company.users.read", "accounts.read", "concepts.read", "transactions.read"],
}


class Environment:
    def run(self, query, actor="ADMINISTRADOR", variables=None, token=None):
        headers = {}
        value = self.tokens.get(actor) if token is None else token
        if value:
            headers["Authorization"] = "Bearer " + value
        with self.Factory() as db:
            return schema.execute_sync(query, variable_values=variables,
                                       context_value={"db": db, "request": SimpleNamespace(headers=headers)})

    def assign(self, role="CAPTURISTA", member="CONSULTA", **kw):
        return self.run(ASSIGN, variables={"member": str(self.members.get(member, member)),
                                          "role": str(self.roles.get(role, role))}, **kw)

    def snapshot(self, model):
        with self.Factory() as db:
            return [tuple(getattr(row, c.name) for c in model.__table__.columns)
                    for row in db.query(model).order_by(model.id)]

    def active(self, member="CONSULTA"):
        with self.Factory() as db:
            return [(x.id, x.role_id) for x in db.query(models.CompanyUserRole).filter_by(
                company_user_id=self.members[member], is_active=True).all()]


@pytest.fixture
def env():
    e = Environment()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    e.Factory = sessionmaker(bind=engine, autoflush=False)
    e.members, e.roles, e.tokens = {}, {}, {}
    password = secrets.token_urlsafe(24)
    e.password = password  # Solo memoria; permite reutilizar el entorno en pruebas HTTP.
    hashed = get_password_hash(password)
    with e.Factory() as db:
        company, foreign = models.Company(name="Empresa A"), models.Company(name="Empresa B")
        db.add_all([company, foreign]); db.flush()
        permissions = {c: models.Permission(code=c, name=c) for c in MATRIX["ADMINISTRADOR"]}
        roles = {c: models.Role(code=c, name=c.title()) for c in MATRIX}
        db.add_all(list(permissions.values()) + list(roles.values())); db.flush()
        for code, role in roles.items():
            e.roles[code] = role.id
            db.add_all(models.RolePermission(role_id=role.id, permission_id=permissions[c].id)
                       for c in MATRIX[code])
        for code in [*MATRIX, "SIN_ROL", "AJENA"]:
            user = models.User(name=code, email=code.lower()+"@prueba.invalid",
                               hashed_password=hashed)
            db.add(user); db.flush()
            member = models.CompanyUser(company_id=foreign.id if code=="AJENA" else company.id,
                                        user_id=user.id, is_admin=code=="ADMINISTRADOR")
            db.add(member); db.flush(); e.members[code] = member.id
            if code != "SIN_ROL":
                role = roles["CONSULTA" if code=="AJENA" else code]
                db.add(models.CompanyUserRole(company_user_id=member.id, role_id=role.id))
        account = models.Account(company_id=company.id, name="Caja", account_type=models.AccountTypeEnum.CASH)
        concept = models.Concept(company_id=company.id, name="Ingreso", concept_type=models.ConceptTypeEnum.INCOME)
        db.add_all([account, concept]); db.flush()
        db.add(models.AccountConcept(account_id=account.id, concept_id=concept.id))
        e.account, e.concept = account.id, concept.id
        db.commit()
    # Tokens obtenidos mediante login, no creados directamente por la prueba.
    for code in MATRIX:
        r = e.run("mutation($input:LoginInput!){login(input:$input){token}}", actor="SIN_TOKEN",
                  variables={"input": {"email":code.lower()+"@prueba.invalid", "password":password}})
        assert not r.errors
        e.tokens[code] = r.data["login"]["token"]
    yield e
    engine.dispose()


def test_cambio_historial_isadmin_matriz_y_otras_membresias(env):
    matrix = env.snapshot(models.RolePermission)
    memberships = env.snapshot(models.CompanyUser)
    others = [r for r in env.snapshot(models.CompanyUserRole) if r[1] != env.members["CONSULTA"]]
    previous = env.active()[0][0]
    assert env.assign().data == {"assignRole": True}
    assert len(env.active()) == 1 and env.active()[0][1] == env.roles["CAPTURISTA"]
    history = env.snapshot(models.CompanyUserRole)
    assert next(r for r in history if r[0] == previous)[3] is False
    assert [r for r in history if r[1] != env.members["CONSULTA"]] == others
    assert env.snapshot(models.RolePermission) == matrix
    assert env.snapshot(models.CompanyUser) == memberships


def test_repetir_y_volver_reutiliza_asignaciones_sin_duplicados(env):
    assert not env.assign().errors
    once = env.snapshot(models.CompanyUserRole)
    assert not env.assign().errors
    assert env.snapshot(models.CompanyUserRole) == once
    assert not env.assign(role="CONSULTA").errors
    assert len(env.active()) == 1 and env.active()[0][1] == env.roles["CONSULTA"]
    assert len(env.snapshot(models.CompanyUserRole)) == len(once)


def test_asignar_a_membresia_sin_rol(env):
    assert not env.active("SIN_ROL")
    assert not env.assign(member="SIN_ROL").errors
    assert len(env.active("SIN_ROL")) == 1


def test_isadmin_se_conserva_y_no_sustituye_los_permisos_del_puesto(env):
    original = env.tokens["ADMINISTRADOR"]
    assert not env.assign(member="ADMINISTRADOR", role="CONSULTA").errors
    with env.Factory() as db:
        assert db.get(models.CompanyUser, env.members["ADMINISTRADOR"]).is_admin is True
    # El indicador de administrador principal no concede roles.write por sí solo.
    assert env.assign(token=original).errors
    assert "roles.write" not in [p["code"] for p in env.run(MY, token=original).data["myPermissions"]]


@pytest.mark.parametrize("case", ["sin_jwt", "jwt_invalido", "sin_permiso", "membresia_inexistente",
                                   "rol_inexistente", "rol_inactivo", "otra_empresa", "membresia_inactiva",
                                   "actor_inactivo", "empresa_inactiva", "rol_actor_inactivo"])
def test_rechazos_no_dejan_cambios_parciales(env, case):
    kw, target, role = {}, "CONSULTA", "CAPTURISTA"
    if case == "sin_jwt": kw["actor"] = "SIN_TOKEN"
    if case == "jwt_invalido": kw["token"] = "token-invalido"
    if case == "sin_permiso": kw["actor"] = "CONTADOR"
    if case == "membresia_inexistente": target = "999999"
    if case == "rol_inexistente": role = "999999"
    if case == "otra_empresa": target = "AJENA"
    with env.Factory() as db:
        if case == "rol_inactivo": db.get(models.Role, env.roles[role]).is_active = False
        if case == "membresia_inactiva": db.get(models.CompanyUser, env.members[target]).is_active = False
        actor = db.get(models.CompanyUser, env.members["ADMINISTRADOR"])
        if case == "actor_inactivo": actor.user.is_active = False
        if case == "empresa_inactiva": actor.company.is_active = False
        if case == "rol_actor_inactivo": db.get(models.Role, env.roles["ADMINISTRADOR"]).is_active = False
        db.commit()
    before = env.snapshot(models.CompanyUserRole)
    matrix = env.snapshot(models.RolePermission)
    r = env.assign(role=role, member=target, **kw)
    assert r.errors and r.data is None
    assert env.snapshot(models.CompanyUserRole) == before
    assert env.snapshot(models.RolePermission) == matrix


def test_fallo_de_persistencia_hace_rollback(env):
    before = env.snapshot(models.CompanyUserRole)
    with patch.object(Session, "commit", side_effect=RuntimeError("fallo de persistencia controlado")):
        r = env.assign()
    assert r.errors
    assert env.snapshot(models.CompanyUserRole) == before


def test_asignaciones_concurrentes_mantienen_un_solo_rol_activo(env, tmp_path):
    path = tmp_path/"concurrencia.db"
    with env.Factory() as db:
        with sqlite3.connect(path) as dest:
            db.connection().connection.driver_connection.backup(dest)
    engine = create_engine("sqlite:///"+str(path), connect_args={"check_same_thread":False,"timeout":10})
    env.Factory = sessionmaker(bind=engine, autoflush=False)
    barrier = Barrier(2)

    @event.listens_for(engine, "before_cursor_execute")
    def ambas_autorizadas(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE company_user_roles"):
            barrier.wait(timeout=10)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(env.assign, role=role) for role in ("CAPTURISTA", "CONTADOR")]
            assert all(not result.result(timeout=15).errors for result in futures)
        assert len(env.active()) == 1
        history = [r for r in env.snapshot(models.CompanyUserRole) if r[1] == env.members["CONSULTA"]]
        assert len(history) == 3
    finally:
        engine.dispose()


def test_jwt_original_reconoce_el_nuevo_puesto_y_revocacion(env):
    token = env.tokens["CONSULTA"]
    matrix = env.snapshot(models.RolePermission)
    assert not env.run(MOVEMENTS, token=token, variables={"id":str(env.account)}).errors
    body = {"accountId":str(env.account), "conceptId":str(env.concept),
            "transactionType":"INCOME", "amount":"12.34", "idempotencyKey":"etapa4-mismo-jwt"}
    denied = env.run(CREATE, token=token, variables={"input":body})
    assert denied.errors and "transactions.write" in denied.errors[0].message
    assert not env.assign().errors
    allowed = env.run(CREATE, token=token, variables={"input":body})
    assert not allowed.errors and allowed.data["createTransaction"]["amount"] == "12.34"
    assert "transactions.write" in [p["code"] for p in env.run(MY, token=token).data["myPermissions"]]
    assert env.snapshot(models.RolePermission) == matrix
    with env.Factory() as db:
        assert db.get(models.CompanyUser, env.members["CONSULTA"]).is_admin is False
        assert db.query(models.Transaction).count() == 1
    assert not env.assign(role="CONSULTA").errors
    assert env.run(CREATE, token=token, variables={"input":{**body,"idempotencyKey":"otro"}}).errors


@pytest.mark.parametrize("actor", list(MATRIX))
def test_accesos_segun_matriz_inicial(env, actor):
    mine = env.run(MY, actor=actor)
    assert {p["code"] for p in mine.data["myPermissions"]} == set(MATRIX[actor])
    assert bool(env.run(USERS, actor=actor).errors) == ("company.users.read" not in MATRIX[actor])
    assert bool(env.run(ROLES, actor=actor).errors) == ("roles.read" not in MATRIX[actor])
    if actor != "ADMINISTRADOR": assert env.assign(actor=actor).errors


def test_catalogo_para_asignar_no_exige_permiso_de_matriz(env):
    with env.Factory() as db:
        p = db.query(models.Permission).filter_by(code="roles.read").one()
        db.query(models.RolePermission).filter_by(role_id=env.roles["ADMINISTRADOR"], permission_id=p.id).one().is_active = False
        db.commit()
    r = env.run(ROLES)
    assert not r.errors and len(r.data["roles"]) == 4
    assert not env.assign().errors


def test_contrato_frontend_asignacion_y_roles(env):
    html = (Path(__file__).resolve().parents[2]/"dashboard.html").read_text()
    for name in ["QU", "QU_ASSIGN_ROLE", "QR_ROLES", "QP_MY"]:
        query = re.search(r"const " + name + r"\s*=\s*`([^`]+)`", html).group(1)
        assert not validate(schema._schema, parse(query)), name
    assert "actorCompanyUserId" not in re.search(r"const QU_ASSIGN_ROLE[^;]+",html).group()
