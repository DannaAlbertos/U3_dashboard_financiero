"""Crea (o reutiliza) un usuario CAPTURISTA en la empresa de referencia.

Uso (desde U3_Act3/, con el entorno virtual activo):
    python crear_capturista.py
No borra nada. Se puede ejecutar varias veces.
"""
import bcrypt

from app.database import SessionLocal
import app.models as models

EMAIL = "capturista@example.com"
PASSWORD = "Capturista123!"
EMPRESA_REF = "Empresa Parte3 Referencia"


def main():
    db = SessionLocal()
    try:
        empresa = db.query(models.Company).filter_by(name=EMPRESA_REF).first()
        rol = db.query(models.Role).filter_by(code="CAPTURISTA").first()
        if empresa is None or rol is None:
            raise SystemExit("Falta la empresa de referencia o el rol CAPTURISTA. "
                             "Ejecuta antes python preparar_parte3.py (con el servidor levantado una vez).")
        user = db.query(models.User).filter_by(email=EMAIL).first()
        if user is None:
            user = models.User(
                name="Capturista Prueba", email=EMAIL, is_active=True,
                hashed_password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
            db.add(user)
            db.flush()
        cu = db.query(models.CompanyUser).filter_by(company_id=empresa.id, user_id=user.id).first()
        if cu is None:
            cu = models.CompanyUser(company_id=empresa.id, user_id=user.id, is_admin=False, is_active=True)
            db.add(cu)
            db.flush()
        for r in db.query(models.CompanyUserRole).filter_by(company_user_id=cu.id, is_active=True).all():
            r.is_active = False
        db.add(models.CompanyUserRole(company_user_id=cu.id, role_id=rol.id, is_active=True))
        db.commit()
        print(f"Listo. Login: {EMAIL} / {PASSWORD}  (empresa: {empresa.name}, rol: CAPTURISTA)")
    finally:
        db.close()


if __name__ == "__main__":
    main()