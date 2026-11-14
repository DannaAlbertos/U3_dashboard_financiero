# Dashboard Financiero (Unidad 3, Actividad 1)

Sistema que muestra el balance financiero de una empresa.

- **Backend:** FastAPI + GraphQL (carpeta `U3_Act1`)
- **Base de datos:** SQLite (archivo local `sistema.db`, no requiere instalar nada)
- **Dashboard:** página web (`dashboard.html`)

Los totales los calcula el backend. El dashboard solo los muestra.

**Integrantes:**

Albertos Sosa Danna Pamela 

Cetzal Cetzal Astrit Airan 

Díaz Anduze Giovana Ruby 

Semino Alemán Venus Getsemani 

## Puertos

| Qué | Dirección |
|---|---|
| Backend | `http://127.0.0.1:8000` (GraphQL en `/graphql`) |
| Dashboard | `http://127.0.0.1:5500` |

La base de datos es un archivo, así que no usa puerto.

## Antes de empezar

Necesitas tener instalado:

- Python 3.12
- Git
- VS Code con la extensión **Live Server**

## Cómo ponerlo a funcionar

> **Importante:** ejecuta todos los comandos desde la carpeta `U3_Act1`. La base de datos se crea en la carpeta donde corras los comandos; si los corres desde otra, se crea una base vacía distinta.

### Paso 1. Descargar el proyecto

```powershell
git clone https://github.com/DannaAlbertos/U3_dashboard_financiero.git
cd U3_dashboard_financiero
git checkout feature/U3-Act1
cd U3_Act1
```

### Paso 2. Instalar Python y las librerías

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Paso 3. Crear el archivo `.env`

```powershell
copy ..\.env.example .env
```

Abre `.env` y reemplaza el valor de `JWT_SECRET` por una clave tuya. Puedes generarla así:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Debe quedar así (sin espacios):

```
JWT_SECRET=la_clave_que_generaste
```

> El archivo `.env` es secreto. No se sube a GitHub ni va en el ZIP.

### Paso 4. Cargar los datos de prueba

```powershell
python preparar_parte3.py
```

Esto crea el archivo `sistema.db` con dos usuarios de prueba:

| Para qué | Correo | Contraseña |
|---|---|---|
| Ver datos | `parte3.ref@example.com` | `Admin123!` |
| Probar empresa sin datos | `parte3.vacia@example.com` | `Admin123!` |

### Paso 5. Encender el backend

```powershell
uvicorn app.main:app --reload
```

Debe aparecer `Uvicorn running on http://127.0.0.1:8000`. **Deja esta terminal abierta.**

### Paso 6. Abrir el dashboard

1. Abre `dashboard.html` en VS Code.
2. Clic derecho y elige **Open with Live Server**.
3. Inicia sesión con `parte3.ref@example.com` y `Admin123!`.

> No abras el archivo con doble clic. Tiene que ser con Live Server, si no el navegador bloquea la conexión (CORS).

## ¿Cómo sé que funciona?

Elige el período **2026-10-26 al 2026-10-30**. Debes ver:

| Indicador | Valor |
|---|---|
| Saldo inicial | 1,000.00 |
| Ingresos | 3,500.00 |
| Egresos | 2,900.00 |
| Profit | 600.00 |
| Saldo final | 1,600.00 |

La cuenta **Caja** debe verse en **rojo** (-200.00).

## Pruebas automáticas

```powershell
pytest -v
```

## Si algo falla

| Error | Qué hacer |
|---|---|
| `Falta la variable de entorno JWT_SECRET` | Revisa el Paso 3: el archivo debe llamarse `.env` y estar en `U3_Act1` |
| "Correo o contraseña incorrectos" | Ejecuta el Paso 4 desde `U3_Act1` |
| `405 Method Not Allowed` en la terminal | Enciende el backend desde `U3_Act1` y abre el dashboard con Live Server |
| `ModuleNotFoundError` | Activa el `venv` y repite `pip install -r requirements.txt` |
| La base aparece vacía | Estás en otra carpeta. Ve a `U3_Act1` y repite el Paso 4 |
| Quiero empezar de cero | Apaga el backend, borra `sistema.db` y repite el Paso 4 |

## Evidencias

Las capturas de pantalla están en [U3_ActividadI.docx](https://github.com/user-attachments/files/34819397/U3_ActividadI.docx)
