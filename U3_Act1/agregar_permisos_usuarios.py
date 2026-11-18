"""Agrega los permisos company.users.read y company.users.write y los asigna a roles.

Copiar a: U3_Act1/agregar_permisos_usuarios.py
Uso (desde U3_Act1, con venv activo):   python agregar_permisos_usuarios.py

Se puede ejecutar varias veces: no duplica nada.
Despues de volver a correr preparar_parte3.py o seed.py, vuelve a ejecutarlo
(o llama a asegurar_permisos_usuarios(db) al final de esos scripts).
"""
from app.database import SessionLocal
from app import models

# permiso: (descripcion, roles que lo reciben)
PERMISOS = {
    "company.users.read": (
        "Ver usuarios de la empresa",
        ["ADMINISTRADOR", "CONTADOR", "CONSULTA"],
    ),
    "company.users.write": (
        "Crear y desactivar usuarios de la empresa",
        ["ADMINISTRADOR"],
    ),
}


def _columnas(modelo):
    return set(modelo.__table__.columns.keys())


def _solo_existentes(modelo, valores: dict) -> dict:
    cols = _columnas(modelo)
    return {k: v for k, v in valores.items() if k in cols}


def asegurar_permisos_usuarios(db):
    cols_permiso = _columnas(models.Permission)
    col_codigo = "code" if "code" in cols_permiso else "name"

    for codigo, (descripcion, roles) in PERMISOS.items():
        permiso = db.query(models.Permission).filter(
            getattr(models.Permission, col_codigo) == codigo).first()
        if not permiso:
            permiso = models.Permission(**_solo_existentes(models.Permission, {
                "code": codigo,
                "name": descripcion if "code" in cols_permiso else codigo,
                "description": descripcion,
                "is_active": True,
            }))
            db.add(permiso)
            db.flush()
            print(f"  + permiso creado: {codigo}")

        for codigo_rol in roles:
            rol = db.query(models.Role).filter(
                models.Role.code == codigo_rol).first()
            if not rol:
                print(f"  ! rol {codigo_rol} no existe, se omite")
                continue
            rp = db.query(models.RolePermission).filter(
                models.RolePermission.role_id == rol.id,
                models.RolePermission.permission_id == permiso.id).first()
            if not rp:
                db.add(models.RolePermission(**_solo_existentes(
                    models.RolePermission, {
                        "role_id": rol.id,
                        "permission_id": permiso.id,
                        "is_active": True,
                    })))
                print(f"  + {codigo} -> {codigo_rol}")
            elif "is_active" in _columnas(models.RolePermission) and not rp.is_active:
                rp.is_active = True
                print(f"  ~ {codigo} -> {codigo_rol} reactivado")


def main():
    db = SessionLocal()
    try:
        asegurar_permisos_usuarios(db)
        db.commit()
        print("Permisos de usuarios listos.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
