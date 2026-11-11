-- =========================================================================
-- TAREA 4 DEL BLOQUE 2: Set de Datos de Prueba (26 al 30 de octubre 2026)
-- =========================================================================
-- Nota: Ajusta los nombres de tablas/columnas si en su Actividad 07 usaron
-- nombres en inglés (companies, accounts, transactions/movements, users).

-- 1. Asegurar que exista la Empresa #1
INSERT INTO companies (id, name, rfc, is_active)
VALUES (1, 'Empresa #1', 'EMP010101AAA', 1)
ON DUPLICATE KEY UPDATE name = 'Empresa #1';

-- 2. Asegurar las 3 cuentas del caso de prueba: Banco, Caja, Ahorro
INSERT INTO accounts (id, company_id, name, is_active) VALUES
(1, 1, 'Banco', 1),
(2, 1, 'Caja', 1),
(3, 1, 'Ahorro', 1)
ON DUPLICATE KEY UPDATE is_active = 1;

-- 3. Asegurar conceptos básicos de Ingreso y Egreso
INSERT INTO concepts (id, company_id, name, type) VALUES
(1, 1, 'Ventas / Ingreso General', 'INCOME'),
(2, 1, 'Gastos Operativos / Egreso', 'EXPENSE')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- Limpiar movimientos previos de las cuentas 1, 2 y 3 para no duplicar saldos
DELETE FROM movements WHERE account_id IN (1, 2, 3);

-- =========================================================================
-- OPCIÓN A: Datos exactos de tu Vista 3 de fínora (image_dd1bc3.png)
-- Totales Generales: Inicial=1000, Ingresos=3500, Egresos=2900, Profit=600, Final=1600
-- Desglose:
--   Banco:  Inicial=1000.00 | Ingresos=3000.00 | Egresos=2200.00 | Profit=800.00  | Final=1800.00
--   Caja:   Inicial=0.00    | Ingresos=500.00  | Egresos=700.00  | Profit=-200.00 | Final=-200.00 (EN ROJO)
--   Ahorro: Inicial=0.00    | Ingresos=0.00    | Egresos=0.00    | Profit=0.00    | Final=0.00 (Sin movimientos)
-- =========================================================================

-- Saldo Inicial (Movimiento previo al 2026-10-26)
INSERT INTO movements (company_id, account_id, concept_id, type, amount, movement_date, description) VALUES
(1, 1, 1, 'INCOME', 1000.00, '2026-10-20', 'Saldo inicial Banco');

-- Movimientos dentro del período (2026-10-26 al 2026-10-30)
INSERT INTO movements (company_id, account_id, concept_id, type, amount, movement_date, description) VALUES
-- Banco: +3000.00 ingresos, -2200.00 egresos
(1, 1, 1, 'INCOME',  3000.00, '2026-10-26', 'Cobro de facturas clientes'),
(1, 1, 2, 'EXPENSE', 2200.00, '2026-10-28', 'Pago a proveedores'),
-- Caja: +500.00 ingresos, -700.00 egresos (Deja Caja en -200.00 -> EN ROJO)
(1, 2, 1, 'INCOME',   500.00, '2026-10-27', 'Venta en efectivo mostrador'),
(1, 2, 2, 'EXPENSE',  700.00, '2026-10-29', 'Compra de insumos urgentes de caja');
-- Ahorro se queda sin movimientos para mostrar el badge "Sin movimientos" de tu diseño


-- =========================================================================
-- OPCIÓN B (Comentada): Datos de la Figura 2 del PDF (página 3)
-- Usa esta opción SOLO si prefieren que Ahorro también tenga movimientos.
-- =========================================================================
/*
DELETE FROM movements WHERE account_id IN (1, 2, 3);

-- Saldos Iniciales (previos al 2026-10-26): Banco=500, Caja=300, Ahorro=200 (Total=1,000.00)
INSERT INTO movements (company_id, account_id, concept_id, type, amount, movement_date, description) VALUES
(1, 1, 1, 'INCOME', 500.00, '2026-10-20', 'Apertura Banco'),
(1, 2, 1, 'INCOME', 300.00, '2026-10-20', 'Apertura Caja'),
(1, 3, 1, 'INCOME', 200.00, '2026-10-20', 'Apertura Ahorro');

-- Movimientos del período (2026-10-26 al 2026-10-30):
INSERT INTO movements (company_id, account_id, concept_id, type, amount, movement_date, description) VALUES
-- Banco: +2000.00, -1700.00 -> Final: 800.00
(1, 1, 1, 'INCOME',  2000.00, '2026-10-26', 'Ingreso Banco'),
(1, 1, 2, 'EXPENSE', 1700.00, '2026-10-27', 'Egreso Banco'),
-- Caja: +500.00, -1000.00 -> Profit: -500.00, Final: -200.00 (EN ROJO)
(1, 2, 1, 'INCOME',   500.00, '2026-10-28', 'Ingreso Caja'),
(1, 2, 2, 'EXPENSE', 1000.00, '2026-10-29', 'Egreso Caja'),
-- Ahorro: +1000.00, -200.00 -> Profit: 800.00, Final: 1000.00
(1, 3, 1, 'INCOME',  1000.00, '2026-10-28', 'Depósito Ahorro'),
(1, 3, 2, 'EXPENSE',  200.00, '2026-10-30', 'Retiro Ahorro');
*/