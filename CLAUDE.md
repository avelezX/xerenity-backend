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

### USD/COP spot — fuente unica de verdad (abril 2026)

**Regla:** Toda valoracion de portafolio OTC debe usar `market_marks.fx_spot` (snapshot
EOD), NUNCA el ultimo tick intradia de `currency_hour` (SET-ICAP). Si no se respeta
esta regla, los NPVs del blotter brincan cada vez que la pagina se refresca porque
`currency_hour` recibe nuevos ticks continuamente durante el dia.

| Funcion | Que lee | Quien la usa |
|---------|---------|--------------|
| `loader.fetch_usdcop_spot(date)` | `market_marks.fx_spot` (con fallback a `currency_hour` solo si no hay mark) | `/pricing/curves/build`, `/pricing/reprice-portfolio`, todo lo que hace pricing |
| `loader.fetch_usdcop_spot_live(date)` | `currency_hour` directo (tick intradia) | **Solo** los jobs que CONSTRUYEN el mark: `run_compute_marks.py`, `run_backfill_marks.py`, `backfill_feb_mar_2026_marks.py` |

Sin la separacion `_live`, habria loop circular: el job que escribe el mark no
puede leerse a si mismo.

Fix aplicado en avelezX/xerenity-backend#85.

**Tablas relacionadas:**
- `xerenity.market_marks` — snapshot EOD (1 fila por dia, escrita por `run_compute_marks.py`)
- `xerenity.currency_hour` — ticks intradia de SET-ICAP (alimentada por `dm/run_collect_usd_to_cop.py`)

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

### Control de acceso por modulo

| Seccion | Roles permitidos | Mecanismo |
|---------|-----------------|-----------|
| Riesgos (todas las sub-secciones) | `super_admin`, `corp_admin` | `RoleGuard` + sidebar condicional |
| Creditos (Loans) | `super_admin`, `corp_admin` | RPCs con company filter via user_profiles |
| Portafolio OTC (Derivados) | `super_admin`, `corp_admin` | RPCs con company filter via user_profiles |
| Pricing (NDF, Swaps calculadoras) | Todos los logueados | Calculadoras stateless |
| Usuarios | `super_admin`, `corp_admin` | `RoleGuard` |
| Admin | `super_admin` | `RoleGuard` |

### Aislamiento de datos por modulo

| Modulo | Aislamiento | Mecanismo |
|--------|-------------|-----------|
| Risk (Commodities) | Por `company_id` | Frontend lee Supabase directo, filtra por empresa |
| Creditos (Loans) | Por empresa (via owner→user_profiles) | RPC `get_loans` con SECURITY DEFINER, JOIN user_profiles |
| Portafolio OTC | Por empresa (via owner→user_profiles) | RPCs `get_xccy/ndf/ibr_positions` con SECURITY DEFINER |
| Pricers (NDF, Swaps) | N/A | Calculadoras stateless, no guardan datos |
| Precios de mercado | N/A | Datos globales compartidos (risk_prices) |

### Super admin: visibilidad global

Super admin puede ver datos de cualquier empresa via selector global en el layout:
- **Selector global:** `CoreLayout.tsx` muestra barra con dropdown de empresas en toda la seccion de Riesgos
- **Store:** `selectedCompanyId` en UserSlice (Zustand), `activeCompanyId()` helper
- **RPCs:** Todas las funciones aceptan `p_company_id uuid DEFAULT NULL`
- **Logica:** Si `auth.uid()` es NULL pero `p_company_id` es NOT NULL → retorna datos de esa empresa
- **Resolucion empresa:** `position.owner → user_profiles.company_id` (JOIN, no columna directa)

### Arquitectura del modulo de Commodities (migrado abril 2026)

**ANTES:** Frontend → Fly.io (Python) → Supabase
**AHORA:** Frontend → Supabase (directo) → Frontend (calcula en TS)

El modulo de Commodities ya NO depende de Fly.io. Los calculos se hacen en el frontend:

| Archivo frontend | Funcion |
|-----------------|---------|
| `src/pages/risk-resumen/index.tsx` | Pagina Resumen (dashboard consolidado, selector de mes, propaga fecha a OTC y Commodities) |
| `src/pages/risk-management/index.tsx` | Pagina Commodities con tabs (Benchmark, Rolling VaR, Exposicion, Matrices, Portafolio GR) |
| `src/lib/risk/supabaseRisk.ts` | Queries directas a Supabase (risk_prices, positions, futures) |
| `src/lib/risk/varCalculator.ts` | Motor VaR: log returns, rolling std, z-scores, covarianza |
| `src/lib/risk/exposureCalculator.ts` | Exposicion USD por commodity |
| `src/lib/risk/futuresCalculator.ts` | P&L de futuros con multiplicadores de contrato |
| `src/lib/risk/companyConfig.ts` | Config dinamica por empresa + `DEFAULT_EXPOSURE_PARAMS` compartidos |
| `src/lib/risk/resumenCalculator.ts` | Helper que arma el `ResumenData` (creditos + composicion final OTC) |
| `src/models/risk/riskApi.ts` | API client que orquesta queries + calculos |

### Configuracion por empresa (risk_company_config)

Cada empresa configura sus propios commodities via `xerenity.risk_company_config`:

```json
{
  "company_id": "uuid",
  "commodities": [
    {"asset": "MAIZ", "unit": "TONS", "price_unit": "cents/bu", "contract_multiplier": 5000, "chart_color": "#f59e0b", "exchange": "CME", "symbol": "ZC"},
    {"asset": "AZUCAR", ...},
    {"asset": "CACAO", ...}
  ],
  "exposure_defaults": { ... },
  "rolling_window": 180,
  "confidence_level": 0.99
}
```

- **Super admin sin empresa:** ve selector para elegir empresa
- **Corp admin con config:** ve su modulo completo
- **Corp admin sin config:** ve pantalla de setup para seleccionar commodities
- **Gestor/lector:** no tienen acceso a Riesgos

### Pagina Resumen (dashboard consolidado, abril 2026)

**Pagina propia** en `/risk-resumen` (entry del sidebar arriba de Commodities).
Antes era un tab dentro de `/risk-management`; se movio para que tuviera selector
de mes propio y pudiera propagar la fecha a las 3 secciones.

Archivo: `xerenity-fe/src/pages/risk-resumen/index.tsx`

| Seccion | Fuente de datos | Campos | Respeta el mes? |
|---------|----------------|--------|-----------------|
| Commodities | `fetchBenchmarkFactors` + `fetchFuturesPortfolio` + `fetchExposure` (todos con `filterDate`) | Por activo: Exp. Natural, GR, Total + P&G Super/GR/Total | Si |
| Derivados OTC | `repriceAllWithMark(filterDate)` + `loadReferencePrices(prevMonthDate)` | NPV COP, NPV USD, FX Delta, P&L MTD COP, P&L MTD USD | Si |
| Creditos | Supabase RPC `get_loans` directo | # creditos, deuda total, IBR vs Tasa Fija | **No** (snapshot actual; la RPC no acepta fecha. Marcado con disclaimer en la UI) |

**Selector de mes:** mismo patron que Benchmark (`< Marzo 2026 >`). Al cambiar de
mes, un solo `useEffect` dispara en cascada:
1. `repriceAllWithMark(filterDate)` → reprice OTC con curvas EOD del mes
2. `loadReferencePrices(prevMonthLastBD)` → MTD reference para calcular P&L MTD
3. `fetchBenchmarkFactors` + `fetchFuturesPortfolio` + `fetchExposure` en paralelo
4. Build local de la tabla de commodities (incluye fila USD desde el store OTC)

**Fila USD en la tabla de Commodities:**
- `position_super` = `exposicion_real_usd` (de fetchExposure)
- `position_gr` = sum de `fx_delta` de `pricedXccy` + `pricedNdf`
- `pnl_super` = `(price_end - price_start) × super / price_start`
- `pnl_gr` = P&L MTD USD del store OTC

**Exposicion Natural por mes:** `fetchExposure(filterDate, DEFAULT_EXPOSURE_PARAMS)`
trae los precios de fin de mes desde Supabase y los inyecta en los parametros de
proyeccion. Asi la exposicion se recalcula correctamente para cada mes aunque los
parametros de proyeccion sean los mismos.

`DEFAULT_EXPOSURE_PARAMS` vive en `xerenity-fe/src/lib/risk/companyConfig.ts` para
evitar duplicacion entre `/risk-management` y `/risk-resumen`.
**Pendiente:** persistir estos parametros a `risk_company_config.exposure_defaults`
para que cada empresa pueda guardar los suyos.

**FX Delta:** suma de `fx_delta` de `pricedXccy` + `pricedNdf` (con su signo).
**P&L MTD:** `summary.total_npv_* − refPrices.mtd.summary.total_npv_*`
**Auto-load:** Al entrar a la pagina y al cambiar de mes/empresa, sin boton manual.
**Formato:** `fmtCompact()` muestra valores como $13.4M, $453K, $15.
**Sin Fly.io para risk:** Todo desde frontend (Supabase directo) excepto el repricing
de OTC que sigue usando el backend Django para QuantLib.

Labels renombrados en Benchmark: "Exposicion Natural" (antes "Super USD").

### Portafolio GR (futuros)

Posiciones individuales de futuros con P&L:
- Sin unique constraint (permite multiples entradas al mismo contrato a diferentes precios)
- Multiplicadores: MAIZ=5,000 bu, AZUCAR=112,000 lbs, CACAO=10 ton
- Conversion cents→USD: MAIZ y AZUCAR multiplican × 0.01, CACAO sin conversion
- Valor T = nominal × multiplicador × precio_actual × toUsd
- P&L Mes = (precio_actual - precio_previo) × nominal × multiplicador × direccion × toUsd
- P&L Inicio = (precio_actual - precio_compra) × nominal × multiplicador × direccion × toUsd
- Filtro por fecha: solo se muestran posiciones con `entry_date <= filterDate` (consistente con Benchmark)
- Subtotales por activo en la tabla (Total MAIZ, Total AZUCAR, etc.)
- `futuresMonth` sincronizado con `benchmarkMonth` (ambas vistas muestran el mismo periodo)

**Precios per-contrato (fix abril 2026, avelezX/xerenity-fe#256):**
Cada contrato del Portafolio GR tiene su propio Px Actual y Px Previo, leidos
de `xerenity.risk_prices_all_contracts` (no del front contract de `risk_prices`).
Antes del fix, todos los contratos del mismo activo mostraban el mismo precio
(ej. ZCN26, ZCU26, ZCZ26 todos en 457.75 porque se usaba el front contract
ZCK26). Match 100% verificado contra el broker StoneX.

Flujo:
1. `riskApi.fetchFuturesPortfolio` carga en paralelo:
   - `fetchRiskPricesAllContracts(start, end, contracts)` filtrado a los contratos
     del portafolio (no se trae toda la tabla)
   - `fetchRiskPrices` (front contract) como fallback
2. `pivotPricesByContract` arma `{ ZCN26: [...], SBV26: [...], ... }`
3. `calculateFuturesPortfolio` busca primero `pricesByContract[pos.contract]`;
   si no hay datos cae al front contract (comportamiento legacy)

**Helper `parseContractMaturity`** (en `futuresCalculator.ts`) convierte el
codigo del contrato al mes de vencimiento usando los month codes estandar
(F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct,
X=Nov, Z=Dec). La columna Contrato del Portafolio GR muestra
`ZCN26 (Jul 26)`, `SBV27 (Oct 27)`, etc.

**Bug del boton Crear (fix avelezX/xerenity-fe#254):**
`upsertFuturesPositionsDB` usaba `.upsert()` con `onConflict` apuntando a
la constraint `uq_futures_position` que fue eliminada para permitir multiples
entradas al mismo contrato. PostgREST retornaba 400 y el insert fallaba
en silencio. Cambiado a `.insert()` puro.

**Operacion: mantener `risk_prices_all_contracts` poblada:**
Para que el Portafolio GR muestre precios correctos cada dia, hay que correr
periodicamente `collect_all_contracts()` desde el backend (existe collector
en `gestion_de_riesgos/collectors/base_collector.py`). Si la tabla no tiene
el contrato/fecha, el frontend cae al fallback del front contract y los
calculos vuelven a quedar incorrectos para los meses traseros.

### Auto-llenado del Benchmark desde Portafolio GR y OTC

`position_gr` y `pnl_gr` del Benchmark se llenan automaticamente:

**Filas MAIZ / AZUCAR / CACAO** (desde `risk_futures_portfolio`):
- `position_gr` = sum(Valor Compra) por activo del Portafolio GR
- `pnl_gr` = sum((price_end - price_start) × multiplier × nominal × dirSign × toUsd)

**Fila USD** (desde el store de trading OTC):
- `position_gr` = sum de `fx_delta` de `pricedXccy` + `pricedNdf`
- `pnl_gr` = `summary.total_npv_usd − refPrices.mtd.summary.total_npv_usd`

- Se recalcula al cambiar el mes del Benchmark o al repricar OTC
- Read-only en la UI (ya no se editan manualmente)
- Celdas vacias se inicializan en `'0'` para que la fila Total sume todas las filas correctamente

### Aislamiento de datos multi-tenant en Commodities (fix abril 2026)

**Problema resuelto:** una empresa nueva (e.g. "El Embrujo") al configurar sus
commodities veia datos de Super de Alimentos en Benchmark, Rolling VaR, Exposicion
y Matrices. Esto se daba porque esos tabs leian de `risk_prices` (tabla global) y
NO filtraban por los commodities seleccionados en `risk_company_config`.

**Fix aplicado (branch `riesgos-v1` de xerenity-fe):**

| Modulo | Antes | Ahora |
|--------|-------|-------|
| `fetchBenchmarkFactors` | Pivoteaba TODOS los assets de `risk_prices` | Filtra por `companyConfig.commodities + currency_asset` |
| `fetchRollingVar` | Igual que arriba | Filtra igual |
| `handleFetchExposure` | Usaba `DEFAULT_EXPOSURE_PARAMS` (hardcoded Super) para TODAS las empresas | Skipea si `companyConfig.exposure_defaults` esta vacio. Solo Super de Alimentos tiene exposure_defaults poblados |
| Benchmark fallback | Caia a `DEFAULT_ASSETS = [MAIZ, AZUCAR, CACAO, USD]` | Cae a `dynamicAssets` del config de la empresa |

**Resultado por empresa:**
- **Super de Alimentos** (tiene exposure_defaults + risk_prices con MAIZ/AZUCAR/CACAO/USD): ve todo igual que antes.
- **Empresa nueva sin datos** (e.g. El Embrujo con CAFE): ve dashboard vacio con toast "Sin datos de mercado para los commodities de esta empresa". Para que aparezcan datos de CAFE, hay que: (1) agregar un collector de cafe a TWS, (2) correr `collect_all` para subir precios de CAFE a `risk_prices`.
- **Empresa nueva con datos** (si se configura y hay precios en risk_prices para sus commodities): funciona out-of-the-box, ve solo sus commodities.

**Tablas de empresas — dual tables (problema heredado):**
Existen dos tablas de empresas en Supabase:

| Tabla | Schema | Creada por | Usada por |
|-------|--------|-----------|-----------|
| `trading.company` | trading | Sistema viejo | FKs de: `risk_company_config`, `risk_futures_portfolio`, `risk_positions`, `risk_portfolio_config` |
| `xerenity.companies` | xerenity | Sistema multi-tenant (Andres) | RPCs `list_companies`, `create_company`, `user_profiles.company_id`, dropdown global |

**Bug:** al crear una empresa desde el frontend via `xerenity.create_company()`, solo
se insertaba en `xerenity.companies`. Luego al guardar config en `risk_company_config`
el FK a `trading.company` fallaba silenciosamente (409 PostgREST).

**Fix aplicado (SQL en Supabase, abril 2026):**
1. Se creo la fila espejo de "El Embrujo" en `trading.company` con el MISMO uuid.
2. Se actualizo `xerenity.create_company()` para insertar en AMBAS tablas en la misma transaccion. Cualquier empresa nueva se crea automaticamente en ambas.

La migracion SQL se guardo en `gestion_de_riesgos/sql/fix_create_company_dual_insert.sql`.

**Pendiente (deuda tecnica):** unificar las dos tablas en una sola fuente de verdad
(migrar todos los FKs a `xerenity.companies` y deprecar `trading.company`). Hacerlo
en un PR aparte porque requiere migrar datos existentes.

**Exposicion por empresa — estado actual:**
- `DEFAULT_EXPOSURE_PARAMS` en `companyConfig.ts` es **especifico de Super de Alimentos** (toneladas de azucar, glucosa, cacao, fletes, processing fees, etc.).
- Solo aplica si `risk_company_config.exposure_defaults` tiene data (actualmente solo Super de Alimentos).
- Para empresas nuevas (e.g. El Embrujo con cafe): hay que crear un formulario generico de exposicion donde cada empresa ingrese sus parametros de proyeccion. Mientras tanto el tab Exposicion queda vacio.

### Tablas de riesgo en Supabase

| Tabla | Scope | company_id |
|-------|-------|-----------|
| `risk_prices` | Global (front contract solo) | No |
| `risk_prices_all_contracts` | Global (TODOS los contratos, solo close) | No |
| `risk_positions` | Per-company | Si |
| `risk_futures_portfolio` | Per-company | Si |
| `risk_portfolio_config` | Per-company | Si |
| `risk_company_config` | Per-company | Si (UNIQUE) |
| `trading.company` | Global | N/A (es la tabla de empresas legacy) |
| `xerenity.companies` | Global | N/A (tabla de empresas nueva, mismos UUIDs que trading.company) |

### Collectors de precios

Funciones en `gestion_de_riesgos/collectors/base_collector.py`:

| Funcion | Proposito |
|---------|-----------|
| `collect_all(start, end)` | Sube precios del front contract a `risk_prices` |
| `collect_all_contracts(start?, end?)` | Sube precios de TODOS los contratos a `risk_prices_all_contracts` |
| `IBUpdater.update_all()` | Actualiza JSONs locales desde TWS via ib_async |

Para actualizar precios:
1. Abrir TWS
2. `await IBUpdater().update_all()` — actualiza JSONs locales
3. `collect_all(start, end)` — sube front contract a Supabase (para VaR)
4. `collect_all_contracts()` — sube todos los contratos (para mark-to-market del Portafolio GR)

### Sidebar consolidado (abril 2026)

```
Riesgos (solo super_admin y corp_admin)
  ├── Resumen            → /risk-resumen      (dashboard consolidado con selector de mes)
  ├── Commodities        → /risk-management   (Benchmark, Rolling VaR, Exposicion, Matrices, Portafolio GR)
  ├── Creditos           → /loans
  ├── Portafolio OTC     → /portfolio
  ├── NDF Pricer         → /ndf-pricer
  ├── IBR Swap           → /ibr-swap
  ├── XCCY Swap          → /xccy-swap
  ├── COLTES             → /coltes-calculator
  └── Portafolio TES     → /tes-portfolio
```

`/risk-resumen` esta en `RISK_PATHS` de `CoreLayout.tsx` para que el selector
global de empresa de super_admin tambien aparezca en esa pagina.

### Deploy

| Servicio | Plataforma | Trigger |
|----------|-----------|---------|
| Frontend (xerenity-fe) | Vercel | Auto-deploy on merge to main |
| Backend (xerenity-backend) | Fly.io | GitHub Actions on merge to main (`--no-cache`) |
| Base de datos | Supabase | Migraciones manuales en SQL Editor |

### Variables de entorno requeridas

**Backend (xerenity-backend / pysdk):**
```
XTY_URL=https://tvpehjbqxpiswkqszwwv.supabase.co
XTY_TOKEN=<service_role_jwt_legacy>                      # Formato JWT eyJ... (no sb_secret_*)
COLLECTOR_BEARER=<service_role_jwt_legacy>
SUPABASE_JWT_SECRET=<jwt-secret-de-supabase-dashboard>   # Para auth en backend
FLY_API_TOKEN=<fly-deploy-token>                         # Secret en GitHub para CI/CD
```

**Frontend (xerenity-fe) — local y Vercel:**
```
NEXT_PUBLIC_SUPABASE_URL=https://tvpehjbqxpiswkqszwwv.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon_jwt_legacy>          # Formato eyJ... (NO sb_publishable_*)
NEXT_PUBLIC_PYSDK_URL=https://pysdk.fly.dev              # localhost:8000 en dev
SUPABASE_SERVICE_ROLE_KEY=<service_role_jwt_legacy>      # Formato eyJ... (NO sb_secret_*)
```

**IMPORTANTE — formato de API keys de Supabase:**
Supabase rotó a un formato nuevo de API keys (`sb_publishable_*` / `sb_secret_*`).
**Estos NO funcionan** con `@supabase/auth-helpers-nextjs` (libreria deprecated que
usa el frontend). Si los builds de Vercel fallan con `Error: either NEXT_PUBLIC_SUPABASE_URL
and NEXT_PUBLIC_SUPABASE_ANON_KEY env variables ... are required`, es porque alguien
puso un key con el formato nuevo. **Solucion:** revertir al JWT legacy (`eyJhbGc...`)
disponible en Supabase Dashboard → Project Settings → API → Legacy API keys.

**Migracion futura:** mover el frontend de `@supabase/auth-helpers-nextjs` (deprecated)
a `@supabase/ssr` para soportar el formato nuevo. Es refactor de ~10-15 archivos,
hacerlo en PR aparte.

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
