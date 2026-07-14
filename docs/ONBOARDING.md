# Onboarding — antes de tocar Board Agent por primera vez

Este checklist existe porque lo probamos en carne propia: simulamos generar el board de junio-26 como si fuéramos alguien nuevo con solo el link del repo, y nos trabamos en varios puntos que no estaban documentados en ningún lado. Esto los cierra.

**Actualizado 2026-07-10:** el pipeline migró de Redshift a Metabase — ya no hace falta AWS CLI, sesión SSO, ni credenciales de Redshift para correr Board Agent. El único acceso a datos es el MCP de Metabase, ya autenticado por OAuth dentro de tu sesión de Claude Code.

## 1. Prerrequisitos — antes de clonar nada

- [ ] **Cuenta de GitHub** con acceso al repo `board-agent` — pedírsela a Sebastián (necesita tu usuario de GitHub, no el correo).
- [ ] **`uv` instalado** — [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).
- [ ] **Claude Code con el MCP de Metabase conectado** (OAuth) — es lo único que hace falta para acceder a datos. Si no está disponible como herramienta al abrir el repo, hay que conectarlo desde la configuración de conectores.

## 2. La primera vez que lo uses — en este orden

**Paso 1 — nunca corras `run.py` directo la primera vez.** Corre esto primero:

```bash
cd "Board Agent"
uv run --with pyyaml python check_setup.py --month 2026-06
```

Este comando **no crea ni cambia nada** — solo te dice:
1. Si te falta una herramienta a ti (`uv`) o si falta poblar el cache de Metabase para este mes.
2. Si las fuentes de datos ya tienen el mes que quieres generar, o si alguien todavía no las actualizó ese mes.

**Paso 2 — si `check_setup.py` marca que falta el cache de Metabase**, pídele a Claude Code que lo pueble: tiene que leer `board_agent/metabase_fetch_spec.py` (la lista completa de qué correr, con la tabla de Metabase y el patrón MBQL de cada query — ver `memory/project_board_agent.md` para el detalle de sintaxis ya resuelto) y escribir los resultados en `data/.metabase_cache.json`. Esto es trabajo de una sesión de Claude Code, no algo que corras tú a mano.

**Paso 3 — si algo más sale en ❌ o ⚠️, no asumas que el agente está roto.** El mensaje de cada check te dice exactamente qué falta. Si es una fuente de datos (no una herramienta tuya), revisa el RACI en el [Playbook de la wiki](https://wiki.alegra.com/doc/playbook-del-board-como-colaborar-sin-depender-de-sebastian-6s5Xu0UKD4) para saber a quién avisarle — por ejemplo, hoy: `tb_trm_banrep` (tasas de cambio) → Luis Caro, `fact_cac_version_segments` → Santiago González.

**Paso 4 — cuando todo esté en ✅**, corre el flujo completo:

```bash
uv run --with pyyaml python run.py --month 2026-06
```

## 3. Troubleshooting

| Síntoma | Qué hacer |
|---|---|
| `check_setup.py` dice que falta `data/.metabase_cache.json` | Pídele a Claude Code que corra las queries de `metabase_fetch_spec.py` vía el MCP de Metabase antes de seguir. |
| `check_setup.py` marca ❌ en una fuente de datos (P&L, FX, CAC, etc.) | No es un bug del agente — avísale a la persona responsable según el RACI del Playbook y espera a que la actualice. |
| El MCP de Metabase no aparece como herramienta disponible | Conectalo desde la configuración de conectores de Claude Code (OAuth) — no hace falta ninguna API key ni credencial manual. |
| Quiero explorar un dato puntual sin correr todo el pipeline | Usa Metabase directamente — no hace falta tocar este repo para eso. |

## 4. Qué NO hace falta que sepas

No necesitas entender Python a fondo, ni Git, ni el diseño del HTML — para proponer cambios (un discussion topic, un ajuste editorial) existe la skill de self-service y el flujo de Pull Request, ambos explicados en el Playbook. Este checklist es solo para el caso de que necesites correr el pipeline tú mismo.
