from sqlalchemy import text, inspect
from app.database import engine

insp = inspect(engine)

for tabla in ["users", "company_users", "company_user_roles", "roles"]:
    cols = [c["name"] for c in insp.get_columns(tabla)]
    cols_vista = [c for c in cols if "pass" not in c.lower() and "hash" not in c.lower()]
    print(f"\n=== {tabla} ===")
    print(" | ".join(cols_vista))
    with engine.connect() as conn:
        for fila in conn.execute(text(f"SELECT {', '.join(cols_vista)} FROM {tabla}")):
            print(" | ".join(str(v) for v in fila))