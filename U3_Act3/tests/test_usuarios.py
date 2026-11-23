"""Pruebas del modulo Usuarios (Actividad 2, Persona 2).

Copiar a: U3_Act1/tests/test_usuarios.py

Antes de correrlas (desde U3_Act1, con el venv activo):
  1. Tener el archivo .env con JWT_SECRET.
  2. python preparar_parte3.py      (crea parte3.ref@example.com / Admin123!)
  3. pip install httpx               (lo usa TestClient de FastAPI)

Correr:  pytest tests/test_usuarios.py -v

Usan la base real (sistema.db) con correos unicos en cada ejecucion,
asi que se pueden repetir sin chocar entre si.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN_EMAIL = "parte3.ref@example.com"
ADMIN_PASSWORD = "Admin123!"
PASSWORD_NUEVO = "Prueba1234"

LOGIN = """mutation($input: LoginInput!) { login(input: $input) { token } }"""

Q_LISTA = """query { companyUsers { id isAdmin isActive user { name email } role { code } } }"""
Q_SOLO_ACTIVOS = """query { companyUsers(activeOnly: true) { id } }"""

CREAR = """
mutation($input: CreateCompanyUserInput!) {
  createCompanyUser(input: $input) { id isAdmin isActive user { email } role { code } }
}"""

DESACTIVAR = """
mutation($id: ID!) {
  deactivateCompanyUser(companyUserId: $id) { id isActive }
}"""


# ---------------------------------------------------------------- ayudas
def gql(client, query, variables=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = client.post("/graphql",
                    json={"query": query, "variables": variables or {}},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def login(client, email, password):
    resp = gql(client, LOGIN, {"input": {"email": email, "password": password}})
    assert "errors" not in resp, resp
    return resp["data"]["login"]["token"]


def correo_unico():
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


def mensaje(resp):
    return resp["errors"][0]["message"]


def crear(client, token, correo=None, **extra):
    datos = {"name": "Usuario Prueba",
             "email": correo or correo_unico(),
             "password": PASSWORD_NUEVO, **extra}
    return gql(client, CREAR, {"input": datos}, token)


def listar(client, token):
    resp = gql(client, Q_LISTA, token=token)
    assert "errors" not in resp, resp
    return resp["data"]["companyUsers"]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


# ------------------------------------------------------------ lectura
def test_lista_solo_trae_la_empresa_de_la_sesion(client, admin_token):
    correos = [u["user"]["email"] for u in listar(client, admin_token)]
    assert ADMIN_EMAIL in correos
    assert "parte3.vacia@example.com" not in correos  # es de otra empresa


def test_sin_token_se_rechaza(client):
    resp = gql(client, Q_LISTA)
    assert "errors" in resp


def test_company_id_de_otra_empresa_se_rechaza(client, admin_token):
    resp = gql(client, 'query { companyUsers(companyId: "999999") { id } }',
               token=admin_token)
    assert "errors" in resp
    assert "otra empresa" in mensaje(resp).lower()


def test_la_contrasena_no_existe_en_el_esquema(client, admin_token):
    for campo in ("password", "hashedPassword"):
        resp = gql(client,
                   f"query {{ companyUsers {{ user {{ name {campo} }} }} }}",
                   token=admin_token)
        assert "errors" in resp
        assert campo in mensaje(resp)


# -------------------------------------------------------------- alta
def test_crear_usuario_aparece_en_la_lista(client, admin_token):
    correo = correo_unico()
    resp = crear(client, admin_token, correo)
    assert "errors" not in resp, resp
    nuevo = resp["data"]["createCompanyUser"]
    assert nuevo["isActive"] is True
    assert nuevo["isAdmin"] is False
    assert nuevo["role"] is None  # el alta no asigna rol

    correos = [u["user"]["email"] for u in listar(client, admin_token)]
    assert correo in correos


def test_correo_duplicado_se_rechaza(client, admin_token):
    correo = correo_unico()
    assert "errors" not in crear(client, admin_token, correo)

    repetido = crear(client, admin_token, correo)
    assert "errors" in repetido
    assert "ya existe un usuario con ese correo" in mensaje(repetido).lower()

    # tambien con mayusculas
    mayusculas = crear(client, admin_token, correo.upper())
    assert "errors" in mayusculas


def test_segundo_administrador_se_rechaza(client, admin_token):
    correo = correo_unico()
    resp = crear(client, admin_token, correo, isAdmin=True)
    assert "errors" in resp
    assert "administrador principal" in mensaje(resp).lower()

    # y no se creo nada
    correos = [u["user"]["email"] for u in listar(client, admin_token)]
    assert correo not in correos


# -------------------------------------------------------------- baja
def test_baja_logica_conserva_la_fila(client, admin_token):
    nuevo = crear(client, admin_token)["data"]["createCompanyUser"]

    baja = gql(client, DESACTIVAR, {"id": nuevo["id"]}, admin_token)
    assert "errors" not in baja, baja
    assert baja["data"]["deactivateCompanyUser"]["isActive"] is False

    # la fila sigue en la lista, ahora inactiva
    fila = next(u for u in listar(client, admin_token) if u["id"] == nuevo["id"])
    assert fila["isActive"] is False

    # y el filtro de activos ya no la trae
    activos = gql(client, Q_SOLO_ACTIVOS, token=admin_token)["data"]["companyUsers"]
    assert nuevo["id"] not in [u["id"] for u in activos]


def test_no_se_puede_desactivar_al_administrador(client, admin_token):
    admin = next(u for u in listar(client, admin_token) if u["isAdmin"])
    resp = gql(client, DESACTIVAR, {"id": admin["id"]}, admin_token)
    assert "errors" in resp


# ----------------------------------------------- usuario de solo consulta
def test_usuario_de_consulta_lee_pero_no_escribe(client, admin_token):
    correo = correo_unico()
    alta = crear(client, admin_token, correo, roleCode="CONSULTA")
    assert "errors" not in alta, alta
    id_consulta = alta["data"]["createCompanyUser"]["id"]

    token = login(client, correo, PASSWORD_NUEVO)

    # puede leer
    assert listar(client, token)

    # no puede crear ni desactivar
    escritura = crear(client, token)
    assert "errors" in escritura
    assert "company.users.write" in mensaje(escritura)

    baja = gql(client, DESACTIVAR, {"id": id_consulta}, token)
    assert "errors" in baja