# xerenity-backend - Claude Agent Workflow

## Project Info
- **GitHub Org:** avelezX
- **Repo:** xerenity-backend (formerly pysdk)
- **GitHub Project:** Xerenity (#4)
- **Description:** Backend consolidado — pricing, risk management, data collectors, core SDK

## Session Startup Protocol

**Al inicio de cada sesion, SIEMPRE ejecutar estos pasos antes de cualquier otra cosa:**

1. **Consultar GitHub Projects** - Listar las tareas pendientes del proyecto Xerenity:
   ```bash
   export PATH="$PATH:/c/Program Files/GitHub CLI"
   gh project item-list 4 --owner avelezX --format json
   ```

2. **Mostrar resumen al usuario** - Presentar tabla con:
   - Status (Todo, In Progress, Done)
   - Titulo
   - Repo asociado (filtrar las relevantes a este repo: pysdk)
   - Prioridad si la tiene
   Filtrar y mostrar primero las tareas "In Progress" y "Todo".

3. **Preguntar cual tarea trabajar** - Si el usuario no especifica, preguntar cual tarea del backlog quiere abordar.

---

## Correr Xerenity localmente

### Prerequisitos
- Python 3.10+ (actual: 3.13)
- Node.js 18+ (actual: 24.11)
- npm 10+

### Arquitectura local
```
xerenity-fe (:3000)  ──POST──>  xerenity-backend (:8000)  ──REST──>  Supabase
  (Next.js)                       (Django)                    (PostgreSQL)
      │                                                           ▲
      └──────────── Supabase RPCs directos (auth, trading) ──────┘
```

**IMPORTANTE:** Ambos servicios apuntan a la misma instancia de Supabase de produccion.
NO confundir con otras bases de datos o proyectos. Verificar siempre que `.env` apunte a
`tvpehjbqxpiswkqszwwv.supabase.co` (Xerenity).

### 1. Backend (Django :8000)

```bash
# Desde la raiz del repo pysdk/
# Activar virtualenv si existe
source myenv/Scripts/activate  # Windows Git Bash

# Variables de entorno (ya estan en .env, Django las carga via python-dotenv)
# Verificar que .env tiene: XTY_URL, XTY_TOKEN

# Instalar dependencias (primera vez o si cambian)
pip install -r requirements.txt

# Correr servidor de desarrollo
python manage.py runserver 8000
```

**Health check:** `curl http://localhost:8000/wake_up`
Debe retornar: `{"message": "Servidor de creditos activado"}`

**Nota:** La pagina raiz `http://localhost:8000/` muestra 404 con lista de URLs — esto es
normal (Django debug mode). Los endpoints son POST a rutas especificas.

### 2. Frontend (Next.js :3000)

```bash
# Desde el repo xerenity-fe/
cd C:/Users/DanielAristizabal/Documents/GitHub/xerenity-fe

# Instalar dependencias (primera vez)
npm install

# Verificar .env.local tiene:
#   NEXT_PUBLIC_SUPABASE_URL=https://tvpehjbqxpiswkqszwwv.supabase.co
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=<key>
#   NEXT_PUBLIC_PYSDK_URL=http://localhost:8000

# Correr servidor de desarrollo
npm run dev
```

**Abrir:** `http://localhost:3000` (redirige a /login si no hay sesion)

### 3. Verificacion rapida

```bash
# Backend OK?
curl -s http://localhost:8000/wake_up

# Frontend OK?
curl -s http://localhost:3000/login -o /dev/null -w "HTTP %{http_code}"
# Debe dar 200

# Conexion frontend → backend?
curl -s -X POST http://localhost:8000/risk_benchmark_factors \
  -H "Content-Type: application/json" \
  -d '{"filter_date": "2026-03-25"}' | python -m json.tool | head -5
```

### Errores comunes

| Problema | Causa | Solucion |
|----------|-------|----------|
| Frontend 404 en todas las paginas | Cache de `.next/` corrupto | Matar proceso, `rm -rf .next`, `npm run dev` |
| Frontend 404 solo paginas auth | No hay sesion de Supabase | Iniciar sesion en `/login` |
| Backend 404 en raiz `/` | Normal — no hay endpoint raiz | Usar endpoints especificos (`/wake_up`, etc.) |
| `NEVER run next build` mientras dev corre | Corrompe cache de dev server | Matar dev, borrar `.next/`, reiniciar |
| Supabase 404 en tabla nueva | Tabla no existe o sin permisos | Ejecutar DDL + `GRANT ALL ON tabla TO anon, authenticated, service_role` |

### Endpoints principales

**Risk Management:**
- `POST /risk_management` — tabla de riesgo completa
- `POST /risk_benchmark_factors` — factores VaR, precios, covarianza
- `POST /risk_rolling_var` — serie historica de precios y VaR
- `POST /risk_exposure` — exposicion USD por commodity
- `POST /risk_collectors_status` — estado de collectors
- `POST /risk_update_prices` — actualizar precios desde JSONs locales
- `POST /risk_futures_portfolio` — portafolio de futuros con P&L
- `POST /risk_futures_portfolio_upsert` — crear/actualizar posiciones
- `POST /risk_futures_portfolio_roll` — roll de contrato
- `POST /risk_futures_portfolio_close` — cerrar posicion
- `POST /risk_futures_portfolio_delete` — eliminar posicion
- `POST /risk_futures_portfolio_edit` — editar campos de posicion

**Pricing API:**
- `POST /pricing/curves/build` — construir curvas (IBR, SOFR, NDF, TES)
- `GET  /pricing/curves/status` — estado de curvas
- `POST /pricing/ndf` — valorar NDF
- `POST /pricing/ibr-swap` — valorar IBR swap
- `POST /pricing/tes-bond` — valorar bono TES
- `POST /pricing/xccy-swap` — valorar XCCY swap
- `POST /pricing/portfolio/reprice` — revalorar portafolio completo
- `GET  /pricing/marks/dates` — fechas de marcas disponibles
- `GET  /pricing/marks` — marcas de mercado

**Loans:**
- `POST /cash_flow` — flujo de caja de credito
- `POST /all_loans` — portafolio de creditos

Todos los endpoints de risk requieren `Authorization: Bearer <supabase_jwt>` + `{"filter_date": "YYYY-MM-DD"}` en el body.
Super admins pueden pasar `company_id` en el body para ver portafolios de otras empresas.
Endpoints de pricing y loans NO requieren auth (pricing es stateless, loans usa Supabase RLS).

---

## Repos del ecosistema Xerenity (consolidado marzo 2026)

| Repo | Tech | Deploy | Descripcion |
|------|------|--------|-------------|
| **xerenity-backend** (pysdk) | Django + QuantLib | Fly.io (pysdk.fly.dev:8000) | Backend consolidado (este repo) |
| **xerenity-fe** | Next.js 14 + React 18 | Vercel (xerenity.vercel.app) | Frontend |
| **xerenity-db** | SQL/PLpgSQL | Supabase (managed) | Migraciones y schema (40+ archivos) |
| **xerenity-py** | Python | PyPI (v0.3.0) | Libreria publica para clientes |
| **xerenity** | — | — | Landing page / redirect |

### Archivados
- xerenity-api, ui-components (archivados, codigo absorbido o sin uso)
- xerenity-dm (codigo en dm/ de este repo, pendiente archivar)

### Conexiones entre repos
```
xerenity-fe (:3000)
  ├── POST → xerenity-backend (:8000)    Pricing, Risk, Loans
  ├── Supabase RPCs directos             Trading positions CRUD, auth, users
  └── Supabase Auth                      Login/session management

xerenity-backend (:8000)
  ├── Supabase REST API                  Market data, risk prices, positions
  ├── QuantLib (en memoria)              Curvas, pricing de derivados
  └── JSON locales (IB)                  Precios de futuros (collectors)

xerenity-db
  └── Migrations SQL → Supabase          Schema xerenity.*, trading.*
```

### Patrones de comunicacion frontend → backend
- **Risk endpoints:** `fetch(PYSDK_URL + '/risk_*', {headers: {'Authorization': 'Bearer <jwt>'}})` — requieren JWT
- **Pricing endpoints:** `fetch(PYSDK_URL + '/pricing/*', {method: 'POST'})` — sin auth (calculadoras stateless)
- **Loans endpoints:** `fetch(PYSDK_URL + '/all_loans')` — datos pre-filtrados por Supabase RLS
- **Trading positions:** Supabase RPCs directos (`supabase.rpc('get_xccy_positions')`)
- **Auth:** Supabase auth-helpers-nextjs (`createClientComponentClient()`)
- **State:** Zustand stores (trading, loans, curve, user, series, dashboard)

## Autenticacion y Multi-tenancy

### Sistema de usuarios (creado por Andres Velez)
- **Tabla:** `xerenity.user_profiles` — role, company_id, account_type
- **Roles:** `super_admin > corp_admin > gestor > lector`
- **Empresas:** `trading.company` — multi-tenancy por empresa
- **RPCs:** `get_user_profile()`, `list_company_users()`, `invite_user()`, etc.

### Auth en el backend (server/auth.py)
- Lee `Authorization: Bearer <token>` del request
- Decodifica JWT con `SUPABASE_JWT_SECRET` (HS256)
- Consulta `user_profiles` para obtener `role` + `company_id`
- Retorna user context: `{user_id, email, role, company_id, is_super_admin}`

### Aislamiento por modulo

| Modulo | Auth | Aislamiento | Mecanismo |
|--------|------|-------------|-----------|
| Risk (Commodities) | JWT en backend | Por `company_id` | `server/auth.py` + filtros en `db_risk.py` |
| Creditos (Loans) | Supabase RLS | Por `user_id` (owner) | RPCs con `auth.uid()`, RLS en `loans.loan` |
| Portafolio OTC | Supabase RLS | Por `company_id` | RPCs autenticados en trading schema |
| Pricers (NDF, Swaps) | Sin auth | N/A | Calculadoras stateless, no guardan datos |
| Precios de mercado | Sin auth | N/A | Datos globales compartidos (risk_prices) |

### Tablas con company_id (multi-tenant)
- `xerenity.risk_futures_portfolio` — posiciones de futuros
- `xerenity.risk_positions` — posiciones benchmark/GR
- `xerenity.risk_portfolio_config` — configuracion del portafolio

### Tablas SIN company_id (datos globales)
- `xerenity.risk_prices` — precios historicos de mercado (compartidos)

### Logica de company_id en RiskManagementServer
- **Sin auth (legacy):** no filtra por empresa
- **Super admin:** puede pasar `company_id` en body para ver otros portafolios
- **Otros roles:** siempre usan su propio `company_id` del perfil

### Variables de entorno requeridas para auth
```
SUPABASE_JWT_SECRET=<jwt-secret-de-supabase-dashboard>
```

## Estructura del monorepo
```
xerenity-backend/
├── pricing/              # Instrumentos financieros (NDF, CCS, TES, swaps)
│   ├── curves/           #   CurveManager, IBR, SOFR, NDF, TES curves
│   ├── instruments/      #   Pricers: NDF, IBR Swap, TES Bond, XCCY Swap
│   ├── data/             #   MarketDataLoader (Supabase)
│   ├── cashflows/        #   Fixings, realized cashflows, OIS compounding
│   └── portfolio.py      #   PortfolioEngine (batch repricing)
├── gestion_de_riesgos/   # VaR, exposicion, portafolio de riesgo
│   ├── var_engine/       #   VaR parametrico (rolling 180d)
│   ├── collectors/       #   Collectors de precios (IB JSON, TRM Excel)
│   ├── sql/              #   DDL para tablas Supabase
│   ├── db_risk.py        #   CRUD Supabase REST
│   ├── portfolio.py      #   Consolidacion benchmark vs GR
│   ├── futures_portfolio.py # Posiciones individuales de futuros
│   └── exposure.py       #   Exposicion USD por commodity
├── server/               # Django API
│   ├── auth.py           #   JWT auth helper (Supabase token → user context)
│   ├── main_server.py    #   Base classes (XerenityError, responseHttpOk)
│   ├── pricing_api/      #   Pricing endpoints (views.py, schemas.py)
│   ├── risk_management_server/  # Risk endpoints (multi-tenant via company_id)
│   ├── loan_calculator/  #   Loan endpoints
│   └── ...
├── src/                  # Modulos core (xerenity, collectors)
├── dm/                   # Data management (collectors de xerenity-dm)
├── core-sdk/             # Core SDK original (connection, search, marks, loans)
├── utilities/            # Date functions, rate conversions, Colombia calendar
├── notebooks/            # Jupyter notebooks de ejemplo
├── .env                  # Variables de entorno (NO commitear)
├── .env.example          # Template de variables
├── requirements.txt      # Dependencias Python
├── manage.py             # Django CLI
├── fly.toml              # Deploy Fly.io (app: pysdk, region: dfw)
└── Dockerfile            # Python 3.10, Gunicorn, port 8000
```

## Workflow por Tarea

### 1. Crear branch
```bash
git checkout main && git pull
git checkout -b feature/<issue-number>-<short-description>
```

### 2. Trabajar en la tarea
- Leer y entender el codigo existente antes de modificar
- Hacer commits frecuentes con mensajes descriptivos
- Seguir las convenciones del proyecto existente

### 3. Documentar mientras se trabaja
- Si hay cambios significativos, actualizar documentacion relevante
- Cada commit debe tener un mensaje claro que explique el "por que"

### 4. Al completar la tarea
- Crear un Pull Request con:
  - Titulo claro referenciando la tarea
  - Descripcion detallada de los cambios
  - Referencia al issue (`Closes #N`)
- Agregar issue al project si no esta:
  ```bash
  gh project item-add 4 --owner avelezX --url <issue-url>
  ```

### 5. Crear nuevas tareas si se descubren
```bash
gh issue create --repo avelezX/xerenity-backend --title "..." --body "..."
gh project item-add 4 --owner avelezX --url <issue-url>
```

## Convenciones de Commits
```
<type>(<scope>): <description>

[optional body]

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```
Tipos: feat, fix, docs, refactor, test, chore

## Supabase — Tablas y permisos

Cuando se crea una tabla nueva en Supabase (schema `xerenity`):

```sql
-- 1. Crear tabla en schema xerenity
CREATE TABLE IF NOT EXISTS xerenity.<tabla> ( ... );

-- 2. SIEMPRE dar permisos al API REST (sin esto, 404)
GRANT USAGE ON SCHEMA xerenity TO anon, authenticated, service_role;
GRANT ALL ON xerenity.<tabla> TO anon, authenticated, service_role;
```

Los DDL de nuevas tablas se guardan en `gestion_de_riesgos/sql/` y tambien deben
agregarse al repo `xerenity-db/migrations/` para trazabilidad.
