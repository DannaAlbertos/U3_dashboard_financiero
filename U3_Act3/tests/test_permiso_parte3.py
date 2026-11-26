"""Parte 3 - vista previa, guardado idempotente y myPermissions."""
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

CODES = ["company.users.read","company.users.write","accounts.read","accounts.write",
         "concepts.read","concepts.write","transactions.read","transactions.write",
         "roles.read","roles.write"]

class Req:
    def __init__(s, t): s.headers = {"Authorization": f"Bearer {t}"}

@pytest.fixture()
def env():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    F = sessionmaker(bind=eng, autoflush=False)
    with F() as db:
        perms = {c: models.Permission(code=c, name=c, is_active=True) for c in CODES}
        roles = {c: models.Role(code=c, name=c.title(), is_active=True)
                 for c in ["ADMINISTRADOR","CONTADOR","CAPTURISTA","CONSULTA"]}
        db.add_all(list(perms.values())+list(roles.values())); db.flush()
        for c in ["accounts.read","transactions.read","transactions.write"]:
            db.add(models.RolePermission(role_id=roles["CAPTURISTA"].id, permission_id=perms[c].id, is_active=True))
        for c in CODES:
            db.add(models.RolePermission(role_id=roles["ADMINISTRADOR"].id, permission_id=perms[c].id, is_active=True))
        emp = models.Company(name="E"); db.add(emp); db.flush()
        toks = {}
        for rc in ["ADMINISTRADOR","CAPTURISTA"]:
            u = models.User(name=rc, email=rc+"@t.com", hashed_password="x", is_active=True)
            db.add(u); db.flush()
            m = models.CompanyUser(company_id=emp.id, user_id=u.id, is_active=True)
            db.add(m); db.flush()
            db.add(models.CompanyUserRole(company_user_id=m.id, role_id=roles[rc].id, is_active=True))
            toks[rc] = crear_token(m.id, emp.id)
        db.commit()
        ids = {c: p.id for c, p in perms.items()}
        rid = {c: r.id for c, r in roles.items()}
    def run(q, tok, **v):
        with F() as db:
            return schema.execute_sync(q, variable_values=v, context_value={"db": db, "request": Req(toks[tok])})
    run.ids, run.rid, run.F = ids, rid, F
    return run

PREV = "query($r:ID!,$p:[ID!]!){previewRolePermissions(roleId:$r,permissionIds:$p){changed finalCount activated{code} deactivated{code} unchanged{code}}}"
SET = "mutation($i:SetRolePermissionsInput!){setRolePermissions(input:$i){changed finalCount activated{code} deactivated{code}}}"
MY = "{myPermissions{code}}"

def lista(env, extra=()):
    base = ["accounts.read","transactions.read","transactions.write", *extra]
    return [str(env.ids[c]) for c in base]

def activos(env):
    with env.F() as db:
        return db.query(models.RolePermission).filter_by(role_id=env.rid["CAPTURISTA"], is_active=True).count()

def test_preview_no_modifica(env):
    r = env(PREV, "ADMINISTRADOR", r=str(env.rid["CAPTURISTA"]), p=lista(env, ["accounts.write"]))
    assert r.errors is None, r.errors
    d = r.data["previewRolePermissions"]
    assert [x["code"] for x in d["activated"]] == ["accounts.write"]
    assert d["deactivated"] == [] and len(d["unchanged"]) == 3 and d["changed"] is True
    assert activos(env) == 3

def test_preview_desactiva(env):
    r = env(PREV, "ADMINISTRADOR", r=str(env.rid["CAPTURISTA"]), p=[str(env.ids["accounts.read"])])
    d = r.data["previewRolePermissions"]
    assert sorted(x["code"] for x in d["deactivated"]) == ["transactions.read","transactions.write"]
    assert activos(env) == 3

def test_guardar_dos_veces_idempotente(env):
    v = dict(i={"roleId": str(env.rid["CAPTURISTA"]), "permissionIds": lista(env, ["accounts.write"])})
    a = env(SET, "ADMINISTRADOR", **v); b = env(SET, "ADMINISTRADOR", **v)
    assert a.data["setRolePermissions"]["changed"] is True
    assert b.errors is None and b.data["setRolePermissions"]["changed"] is False
    assert activos(env) == 4

def test_capturista_no_puede_guardar(env):
    v = dict(i={"roleId": str(env.rid["CAPTURISTA"]), "permissionIds": lista(env)})
    assert env(SET, "CAPTURISTA", **v).errors

def test_admin_no_modificable(env):
    r = env(PREV, "ADMINISTRADOR", r=str(env.rid["ADMINISTRADOR"]), p=[])
    assert r.errors

def test_my_permissions_refleja_cambio(env):
    antes = [x["code"] for x in env(MY, "CAPTURISTA").data["myPermissions"]]
    assert "accounts.write" not in antes
    env(SET, "ADMINISTRADOR", i={"roleId": str(env.rid["CAPTURISTA"]), "permissionIds": lista(env, ["accounts.write"])})
    despues = [x["code"] for x in env(MY, "CAPTURISTA").data["myPermissions"]]
    assert "accounts.write" in despues