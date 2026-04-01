# Gestión de Riesgos - Module Guide

## Propósito
Sistema de gestión de riesgo de commodities multi-tenant. Calcula VaR paramétrico, exposición USD, y consolida portafolio de cobertura (benchmark vs. gestión de riesgo).

**IMPORTANTE (abril 2026):** Los cálculos de este módulo se migraron al frontend (xerenity-fe).
El backend Python sigue existiendo pero ya NO es llamado por el frontend para el módulo de Commodities.
Solo se usa para pricing de derivados (NDF, Swaps, COLTES) que requieren QuantLib.

## Arquitectura actual

```
ANTES (hasta marzo 2026):
  Frontend → Django API (Fly.io) → Supabase

AHORA (abril 2026):
  Frontend → Supabase (directo) → Frontend (calcula en TypeScript)
```

### Código del frontend (xerenity-fe)
Los cálculos equivalentes a este módulo viven en:

| Archivo frontend | Equivalente Python |
|-----------------|-------------------|
| `src/lib/risk/supabaseRisk.ts` | `db_risk.py` |
| `src/lib/risk/varCalculator.ts` | `var_engine/var_calculator.py` |
| `src/lib/risk/exposureCalculator.ts` | `exposure.py` |
| `src/lib/risk/futuresCalculator.ts` | `futures_portfolio.py` |
| `src/lib/risk/companyConfig.ts` | (nuevo) config dinámica por empresa |
| `src/lib/risk/resumenCalculator.ts` | (nuevo) dashboard consolidado |

## Estructura del directorio (backend Python)

```
gestion_de_riesgos/
├── db_risk.py              # CRUD Supabase REST (con filtro company_id)
├── exposure.py             # Cálculo de exposición USD por commodity
├── portfolio.py            # Portafolio consolidado: posiciones + VaR + P&L
├── futures_portfolio.py    # P&L por posición individual de futuros
├── collectors/
│   ├── base_collector.py   # Framework de collectors (IB JSON, TRM Excel)
│   └── ibkr/               # Notebooks IB + datos históricos CSV
├── var_engine/
│   └── var_calculator.py   # Motor VaR paramétrico (rolling 180d, 99%)
└── sql/
    ├── risk_futures_portfolio.sql   # DDL posiciones de futuros (con company_id)
    ├── risk_company_config.sql      # DDL config por empresa + seed Super de Alimentos
    └── add_company_id_to_risk_tables.sql  # Migración multi-tenant
```

## Tablas en Supabase (schema xerenity)

| Tabla | Scope | company_id | Descripción |
|-------|-------|-----------|-------------|
| `risk_prices` | Global | No | Precios históricos de futuros (datos de mercado) |
| `risk_positions` | Per-company | Sí | Posiciones benchmark y GR por activo |
| `risk_futures_portfolio` | Per-company | Sí | Posiciones individuales de futuros |
| `risk_portfolio_config` | Per-company | Sí | Configuración del portafolio (fechas, ventana) |
| `risk_company_config` | Per-company | Sí (UNIQUE) | Commodities y parámetros por empresa |

## Collectors (actualización de precios)

### Correr collectors manualmente
```python
# Solo contratos activos (rápido, ~2 min)
import asyncio
from gestion_de_riesgos.collectors.base_collector import IBUpdater
updater = IBUpdater()
await updater.update_all()

# Subir a Supabase
from gestion_de_riesgos.collectors.base_collector import collect_all
collect_all(start_date, end_date)
```

### Config de contratos
| Asset   | Ticker | Exchange | Meses      | Multiplier |
|---------|--------|----------|------------|------------|
| MAIZ    | ZC     | CME/CBOT | H,K,N,U,Z | 5,000 bu   |
| AZUCAR  | SB     | ICE/NYBOT| H,K,N,V   | 112,000 lbs|
| CACAO   | CC     | ICE/NYBOT| H,K,N,U,Z | 10 ton     |

### Datos locales
- `DATA_DIR`: SharePoint de Saman (`Banca de Inversión - Documents/Super de Alimentos/Gestión de riesgo/Data`)
- JSONs: `data_zc1.json` (maíz), `data_sb.json` (azúcar), `data_cc.json` (cacao)
- `trm.xlsx`: TRM histórica

## Multi-tenancy

### Configuración por empresa (risk_company_config)
Cada empresa define sus commodities en JSONB:
```json
{
  "commodities": [
    {"asset": "MAIZ", "unit": "TONS", "price_unit": "cents/bu", "contract_multiplier": 5000, "chart_color": "#f59e0b"},
    {"asset": "AZUCAR", ...}
  ],
  "exposure_defaults": { ... },
  "rolling_window": 180,
  "confidence_level": 0.99
}
```

### Control de acceso
- Solo `super_admin` y `corp_admin` ven la sección de Riesgos
- Super admin puede ver cualquier empresa via selector
- Corp admin ve solo su empresa
- Empresa sin config ve pantalla de setup para seleccionar commodities

## Fórmulas clave

### VaR paramétrico
```
log_return = ln(price[t] / price[t-1])
rolling_std = std(log_returns[-180:], min_periods=30)
var_factor = z_score × rolling_std     // z_99 = 2.3263
var_usd = |posición| × var_factor
```

### P&L de futuros
```
direction_sign = LONG ? 1 : -1
valor_t = nominal × multiplicador × precio_actual
pnl_inicio = (precio_actual - precio_compra) × nominal × mult × dirección
pnl_mes = (precio_actual - precio_previo) × nominal × mult × dirección
```

### Precio previo
- Si posición abierta en el mes actual → entry_price
- Si posición de meses anteriores → último día hábil del mes anterior

## Convenciones
- Posiciones negativas = compra de commodity (exposición natural del negocio)
- Posiciones GR positivas en USD = cobertura vendida (forwards)
- Label "Exposición Natural" = posición del negocio (antes "Super USD")
- VaR siempre en valor absoluto
- Factores VaR en porcentaje (e.g., 2.55% diario)

## Frontend tabs en Commodities (/risk-management)

| Tab | Descripción | Fuente de datos |
|-----|-------------|-----------------|
| Resumen | Dashboard consolidado: 4 cards + tabla | Supabase + Zustand stores |
| Benchmark | Tabla de riesgo: VaR, P&L, Info Ratio por activo | Supabase (risk_prices) |
| Rolling VaR | Gráfica de precios y VaR rolling 180d | Supabase (risk_prices) |
| Exposición | Exposición USD por commodity | Cálculo local + precios Supabase |
| Matrices | Covarianza y correlación | Calculado de returns |
| Portafolio GR | Posiciones individuales de futuros con CRUD | Supabase (risk_futures_portfolio) |

## Deuda técnica
- Rutas de datos hardcodeadas a SharePoint Windows — no funciona en deploy
- `exposure.py` tiene fórmulas hardcoded para Super de Alimentos — necesita ser genérico
- TRM collector desactualizado (último dato: marzo 2026)
- Backend Python ya no se usa para risk pero no se ha eliminado (mantener por referencia)
