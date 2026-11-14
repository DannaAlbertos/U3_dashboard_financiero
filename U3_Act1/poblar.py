import sqlite3

def poblar_bd():
    # Se conecta a tu archivo local de SQLite
    conexion = sqlite3.connect("sistema.db")
    cursor = conexion.cursor()

    try:
        # 1. Limpiamos transacciones viejas de las cuentas 1, 2 y 3 para no duplicar sumas
        cursor.execute("DELETE FROM transactions WHERE account_id IN (1, 2, 3);")
        
        # 2. Preparamos los datos EXACTOS sin la columna company_id
        # Orden: account_id, concept_id, transaction_type, amount, transaction_date, captured_at, captured_by, is_active
        datos = [
            (1, 1, 'INCOME', 1000.00, '2026-10-20 12:00:00', '2026-10-20 12:00:00', 1, 1), # Saldo inicial banco
            (1, 1, 'INCOME', 3000.00, '2026-10-26 12:00:00', '2026-10-26 12:00:00', 1, 1), # Ingreso banco
            (1, 2, 'EXPENSE', 2200.00, '2026-10-28 12:00:00', '2026-10-28 12:00:00', 1, 1), # Egreso banco
            (2, 1, 'INCOME',  500.00, '2026-10-27 12:00:00', '2026-10-27 12:00:00', 1, 1), # Ingreso caja
            (2, 2, 'EXPENSE', 700.00, '2026-10-29 12:00:00', '2026-10-29 12:00:00', 1, 1)  # Egreso caja (la deja en -200)
        ]
        
        # 3. Insertamos los datos
        query = """
        INSERT INTO transactions 
        (account_id, concept_id, transaction_type, amount, transaction_date, captured_at, captured_by, is_active) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        cursor.executemany(query, datos)
        conexion.commit()
        print("✅ ¡Datos del dashboard insertados correctamente en SQLite!")
        
    except Exception as e:
        print(f"❌ Hubo un error: {e}")
    finally:
        conexion.close()

if __name__ == "__main__":
    poblar_bd()