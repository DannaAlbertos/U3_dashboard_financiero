"""Persona 4: contrato GraphQL y persistencia aislada en SQLite en memoria.

Desde la raíz: .venv/bin/python -B -m pytest -c U3_Act2/pytest.ini
    U3_Act2/tests/test_conceptos.py -v -p no:cacheprovider

Incluso el arranque de main (create_all y semillas) usa una BD en memoria.
No se abre ni se modifica sistema.db; no hace falta httpx ni un servidor.
"""
import importlib
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from graphql import parse, validate
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "conceptos-pruebas-aisladas-clave-de-32-caracteres")

from app import database, models

# Proteger la BD del equipo antes de importar cualquier código de arranque.
_bootstrap_engine = create_engine("sqlite://", poolclass=StaticPool)
with patch.object(database, "engine", _bootstrap_engine), patch.object(
    database, "SessionLocal", sessionmaker(bind=_bootstrap_engine)
):
    main = importlib.import_module("app.main")

from app.seguridad import crear_token

CATALOG = """query($companyId:ID,$type:ConceptType,$active:Boolean){
  concepts(companyId:$companyId,conceptType:$type,activeOnly:$active){
    id companyId name conceptType isActive shortDescription
  }
}"""
ACCESS = "query{conceptAccess{companyId canRead canWrite}}"
CREATE = """mutation($input:CreateConceptInput!){createConcept(input:$input){
  id companyId name conceptType isActive shortDescription
}}"""
ASSIGNED = """query($accountId:ID!){accountConcepts(accountId:$accountId){
  id accountId conceptId isActive concept{id name conceptType}
}}"""
ASSIGN = """mutation($input:AssignConceptToAccountInput!){
  assignConceptToAccount(input:$input){id accountId conceptId isActive}
}"""
REMOVE = """mutation($accountId:ID!,$conceptId:ID!){
  removeConceptFromAccount(accountId:$accountId,conceptId:$conceptId)
}"""


@pytest.fixture
def env():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    companies = [models.Company(name=n) for n in ("Empresa A", "Empresa B")]
    db.add_all(companies)
    db.flush()
    permissions = {code: models.Permission(code=code, name=code) for code in
                   ("concepts.read", "concepts.write", "accounts.read")}
    db.add_all(permissions.values())
    db.flush()
    tokens = {}
    members = {}
    for index, (name, codes) in enumerate({
        "writer": list(permissions),
        "reader": ["concepts.read", "accounts.read"],
        "concept_reader": ["concepts.read"],
        "write_only": ["concepts.write"],
        "denied": [],
        "other": list(permissions),
    }.items()):
        company = companies[1] if name == "other" else companies[0]
        role = models.Role(code=name, name=name)
        user = models.User(name=name, email=f"{name}@conceptos.test", hashed_password="unused")
        db.add_all([role, user])
        db.flush()
        member = models.CompanyUser(company_id=company.id, user_id=user.id)
        db.add(member)
        db.flush()
        db.add(models.CompanyUserRole(company_user_id=member.id, role_id=role.id))
        db.add_all([models.RolePermission(role_id=role.id, permission_id=permissions[c].id)
                    for c in codes])
        members[name] = member
        tokens[name] = crear_token(member.id, company.id)
    accounts = [models.Account(company_id=c.id, name=f"Cuenta {i}", account_type=models.AccountTypeEnum.CASH)
                for i, c in enumerate(companies)]
    concepts = [
        models.Concept(company_id=companies[0].id, name="Venta", concept_type=models.ConceptTypeEnum.INCOME),
        models.Concept(company_id=companies[0].id, name="Servicio", concept_type=models.ConceptTypeEnum.EXPENSE),
        models.Concept(company_id=companies[0].id, name="Histórico", concept_type=models.ConceptTypeEnum.INCOME, is_active=False),
        models.Concept(company_id=companies[1].id, name="Ajeno", concept_type=models.ConceptTypeEnum.INCOME),
    ]
    db.add_all(accounts + concepts)
    db.commit()

    def gql(query, variables=None, actor="writer"):
        token = tokens.get(actor, actor)
        request = SimpleNamespace(headers={} if token is None else {"Authorization": f"Bearer {token}"})
        return main.schema.execute_sync(query, variable_values=variables or {},
                                        context_value={"db": db, "request": request})

    def ok(query, variables=None, actor="writer"):
        result = gql(query, variables, actor)
        assert not result.errors, result.errors
        return result.data

    def link(active=True, concept=None):
        relation = models.AccountConcept(account_id=accounts[0].id,
                                         concept_id=(concept or concepts[0]).id, is_active=active)
        db.add(relation)
        db.commit()
        return relation

    yield SimpleNamespace(db=db, companies=companies, accounts=accounts, concepts=concepts,
                          gql=gql, ok=ok, link=link, members=members, tokens=tokens,
                          pair={"accountId": str(accounts[0].id), "conceptId": str(concepts[0].id)})
    db.close()
    engine.dispose()


def assert_error(result, text=None):
    assert result.errors, result.data
    if text:
        assert text.lower() in result.errors[0].message.lower()


def test_catalogo_empresa_autenticada(env):
    result = env.ok(CATALOG)["concepts"]
    assert {c["name"] for c in result} == {"Venta", "Servicio", "Histórico"}
    assert {c["companyId"] for c in result} == {str(env.companies[0].id)}


def test_company_id_compatible_y_aislamiento(env):
    assert len(env.ok(CATALOG, {"companyId": str(env.companies[0].id)})["concepts"]) == 3
    assert_error(env.gql(CATALOG, {"companyId": str(env.companies[1].id)}), "otra empresa")
    assert [c["name"] for c in env.ok(CATALOG, actor="other")["concepts"]] == ["Ajeno"]


@pytest.mark.parametrize("variables,names", [
    ({"type": "INCOME"}, {"Venta", "Histórico"}),
    ({"type": "EXPENSE"}, {"Servicio"}),
    ({"active": True}, {"Venta", "Servicio"}),
    ({"active": False}, {"Venta", "Servicio", "Histórico"}),
    ({"type": "INCOME", "active": True}, {"Venta"}),
])
def test_filtros_catalogo(env, variables, names):
    assert {c["name"] for c in env.ok(CATALOG, variables)["concepts"]} == names


def test_lector_conceptos_no_depende_de_permisos_de_cuentas(env):
    assert env.ok(CATALOG, actor="concept_reader")["concepts"]
    assert env.ok(ACCESS, actor="concept_reader")["conceptAccess"] == {
        "companyId": str(env.companies[0].id), "canRead": True, "canWrite": False}


@pytest.mark.parametrize("actor,read,write", [
    ("writer", True, True), ("reader", True, False),
    ("write_only", False, True), ("denied", False, False),
])
def test_permisos_efectivos_sin_consultar_usuarios(env, actor, read, write):
    access = env.ok(ACCESS, actor=actor)["conceptAccess"]
    assert (access["canRead"], access["canWrite"]) == (read, write)


def test_permisos_se_revisan_en_cada_peticion(env):
    role_id = env.db.query(models.CompanyUserRole).filter_by(company_user_id=env.members["writer"].id).one().role_id
    permission = env.db.query(models.Permission).filter_by(code="concepts.write").one()
    env.db.query(models.RolePermission).filter_by(role_id=role_id, permission_id=permission.id).one().is_active = False
    env.db.commit()
    assert env.ok(ACCESS)["conceptAccess"]["canWrite"] is False
    assert_error(env.gql(CREATE, {"input": {"name": "Nuevo", "conceptType": "INCOME"}}), "concepts.write")


def test_crear_persiste_nombre_normalizado_y_empresa_de_sesion(env):
    new = env.ok(CREATE, {"input": {"name": "  Nuevo ingreso  ", "conceptType": "INCOME",
                                   "shortDescription": "Descripción"}})["createConcept"]
    row = env.db.get(models.Concept, int(new["id"]))
    assert row.name == "Nuevo ingreso"
    assert row.company_id == env.companies[0].id
    assert row.short_description == "Descripción"
    assert new["isActive"] is True
    assert new in env.ok(CATALOG)["concepts"]


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_rechaza_nombre_vacio(env, name):
    count = env.db.query(models.Concept).count()
    assert_error(env.gql(CREATE, {"input": {"name": name, "conceptType": "INCOME"}}), "obligatorio")
    assert env.db.query(models.Concept).count() == count


def test_rechaza_tipo_invalido(env):
    assert_error(env.gql(CREATE, {"input": {"name": "Nuevo", "conceptType": "INVALID"}}), "ConceptType")


def test_conserva_regla_existente_de_nombre_repetido(env):
    assert_error(env.gql(CREATE, {"input": {"name": "Venta", "conceptType": "EXPENSE"}}), "ya existe")
    assert env.ok(CREATE, {"input": {"name": "Venta", "conceptType": "INCOME"}}, "other")["createConcept"]


def test_alta_no_acepta_empresa_ajena(env):
    assert_error(env.gql(CREATE, {"input": {"companyId": str(env.companies[1].id),
                                           "name": "Invasión", "conceptType": "INCOME"}}), "otra empresa")


def test_lista_relaciones_activas_y_excluye_inactivas(env):
    active = env.link()
    env.link(False, env.concepts[1])
    rows = env.ok(ASSIGNED, {"accountId": env.pair["accountId"]})["accountConcepts"]
    assert [r["id"] for r in rows] == [str(active.id)]
    assert rows[0]["concept"]["name"] == "Venta"


def test_listas_vacias(env):
    assert env.ok(ASSIGNED, {"accountId": env.pair["accountId"]})["accountConcepts"] == []
    for row in env.concepts[:3]:
        env.db.delete(row)
    env.db.commit()
    assert env.ok(CATALOG)["concepts"] == []


def test_asignar_y_actualizar_consulta(env):
    assigned = env.ok(ASSIGN, {"input": env.pair})["assignConceptToAccount"]
    assert assigned["isActive"] is True
    assert env.ok(ASSIGNED, {"accountId": env.pair["accountId"]})["accountConcepts"][0]["id"] == assigned["id"]


def test_rechaza_duplicada_activa_sin_crear_otra_fila(env):
    env.ok(ASSIGN, {"input": env.pair})
    assert_error(env.gql(ASSIGN, {"input": env.pair}), "ya existe")
    assert env.db.query(models.AccountConcept).count() == 1


def test_reactivar_reutiliza_la_misma_relacion(env):
    relation = env.link(False)
    result = env.ok(ASSIGN, {"input": env.pair})["assignConceptToAccount"]
    assert result["id"] == str(relation.id)
    assert result["isActive"] is True
    assert env.db.query(models.AccountConcept).count() == 1


def test_baja_logica_conserva_registro_y_actualiza_lista(env):
    relation = env.link()
    assert env.ok(REMOVE, env.pair)["removeConceptFromAccount"] is True
    env.db.expire_all()
    assert env.db.get(models.AccountConcept, relation.id).is_active is False
    assert env.db.query(models.AccountConcept).count() == 1
    assert env.ok(ASSIGNED, {"accountId": env.pair["accountId"]})["accountConcepts"] == []


@pytest.mark.parametrize("field,foreign_index", [("accountId", 1), ("conceptId", 3)])
def test_asignacion_entre_empresas_rechazada(env, field, foreign_index):
    pair = dict(env.pair)
    pair[field] = str(env.accounts[foreign_index].id if field == "accountId" else env.concepts[foreign_index].id)
    assert_error(env.gql(ASSIGN, {"input": pair}), "empresa")
    assert env.db.query(models.AccountConcept).count() == 0


@pytest.mark.parametrize("field", ["accountId", "conceptId"])
def test_asignacion_inexistente_rechazada(env, field):
    pair = dict(env.pair, **{field: "99999"})
    assert_error(env.gql(ASSIGN, {"input": pair}))


def test_consulta_y_baja_de_cuenta_ajena_rechazadas(env):
    pair = dict(env.pair, accountId=str(env.accounts[1].id))
    assert_error(env.gql(ASSIGNED, {"accountId": pair["accountId"]}), "empresa")
    assert_error(env.gql(REMOVE, pair), "empresa")


def test_cuenta_inexistente_y_relacion_inexistente(env):
    assert_error(env.gql(ASSIGNED, {"accountId": "99999"}))
    assert_error(env.gql(REMOVE, env.pair), "Relación no encontrada")


def test_relacion_inconsistente_no_expone_concepto_ajeno(env):
    relation = env.link(concept=env.concepts[3])
    assert env.ok(ASSIGNED, {"accountId": env.pair["accountId"]})["accountConcepts"] == []
    assert_error(env.gql(REMOVE, dict(env.pair, conceptId=str(env.concepts[3].id))), "empresa")
    assert env.db.get(models.AccountConcept, relation.id).is_active is True


@pytest.mark.parametrize("actor", [None, "token.invalido", "denied"])
@pytest.mark.parametrize("query,variables", [(CATALOG, {}), (ACCESS, {}), (ASSIGNED, {"accountId": "1"})])
def test_consultas_no_autorizadas(env, actor, query, variables):
    if actor == "denied" and query == ACCESS:
        assert env.ok(ACCESS, actor=actor)["conceptAccess"]["canRead"] is False
    else:
        assert_error(env.gql(query, variables, actor))


@pytest.mark.parametrize("actor", [None, "token.invalido", "reader", "denied"])
@pytest.mark.parametrize("operation", ["create", "assign", "remove"])
def test_mutations_no_autorizadas_no_alteran_datos(env, actor, operation):
    relation = env.link()
    queries = {
        "create": (CREATE, {"input": {"name": "No permitido", "conceptType": "INCOME"}}),
        "assign": (ASSIGN, {"input": dict(env.pair, conceptId=str(env.concepts[1].id))}),
        "remove": (REMOVE, env.pair),
    }
    query, variables = queries[operation]
    assert_error(env.gql(query, variables, actor))
    assert env.db.query(models.Concept).count() == 4
    assert env.db.query(models.AccountConcept).count() == 1
    assert relation.is_active is True


def test_contrato_operaciones_del_frontend():
    html = (Path(__file__).resolve().parents[2] / "dashboard.html").read_text()
    for name in ("QC", "QC_ACCESS", "QC_NEW", "QAC", "QAC_ADD", "QAC_DEL"):
        query = re.search(r"const " + name + r" = `([^`]+)`", html).group(1)
        assert validate(main.schema._schema, parse(query)) == [], name
