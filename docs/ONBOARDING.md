# Onboarding — antes de tocar Board Agent por primera vez

Este checklist existe porque lo probamos en carne propia: simulamos generar el board de junio-26 como si fuéramos alguien nuevo con solo el link del repo, y nos trabamos en varios puntos que no estaban documentados en ningún lado. Esto los cierra.

## 1. Prerrequisitos — antes de clonar nada

- [ ] **Cuenta de GitHub** con acceso al repo `board-agent` — pedírsela a Sebastián (necesita tu usuario de GitHub, no el correo).
- [ ] **`uv` instalado** — [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).
- [ ] **AWS CLI instalado** (v1 o v2 sirven para los comandos de este repo).
- [ ] **Cuenta de AWS SSO con perfil `alegra`** — *(pendiente confirmar el proceso exacto de alta — hoy solo Sebastián la tiene; si eres la primera persona más allá de él en necesitarla, pregúntale directamente cómo se solicita)*.
- [ ] **Acceso a Metabase** — para explorar los datos por tu cuenta, no hace falta para correr el pipeline.

## 2. La primera vez que lo uses — en este orden

**Paso 1 — nunca corras `run.py` directo la primera vez.** Corre esto primero:

```bash
cd "Board Agent"
uv run --with boto3 --with pyyaml python check_setup.py --month 2026-06
```

Este comando **no crea ni cambia nada** — solo te dice:
1. Si te falta una herramienta o acceso a ti (`uv`, AWS CLI, sesión SSO).
2. Si las fuentes de datos en Redshift ya tienen el mes que quieres generar, o si alguien todavía no las actualizó ese mes.

**Paso 2 — si algo sale en ❌ o ⚠️, no asumas que el agente está roto.** El mensaje de cada check te dice exactamente qué falta. Si es una fuente de datos (no una herramienta tuya), revisa el RACI en el [Playbook de la wiki](https://wiki.alegra.com/doc/playbook-del-board-como-colaborar-sin-depender-de-sebastian-6s5Xu0UKD4) para saber a quién avisarle — por ejemplo, hoy: `tb_trm_banrep` (tasas de cambio) → Luis Caro, `fact_cac_version_segments` → Santiago González.

**Paso 3 — cuando todo esté en ✅**, corre el flujo completo:

```bash
uv run --with boto3 --with pyyaml python run.py --month 2026-06
```

## 3. Troubleshooting

| Síntoma | Qué hacer |
|---|---|
| `check_setup.py` dice que la sesión SSO no está activa | Correr `aws sso login --profile alegra` — abre el navegador para que apruebes. Esto pasa solo, incluso a Sebastián le pasó de un día para otro — no es un error tuyo, la sesión simplemente vence. |
| `check_setup.py` marca ❌ en una fuente de datos (P&L, FX, CAC, etc.) | No es un bug del agente — avísale a la persona responsable según el RACI del Playbook y espera a que la actualice. |
| No sé a quién pedirle la cuenta de AWS SSO | Pregúntale directamente a Sebastián — todavía no hay un proceso de autoservicio documentado para esto. |
| Quiero explorar un dato puntual sin correr todo el pipeline | Usa Metabase directamente — no hace falta tocar este repo para eso. |

## 4. Qué NO hace falta que sepas

No necesitas entender Python a fondo, ni Git, ni el diseño del HTML — para proponer cambios (un discussion topic, un ajuste editorial) existe la skill de self-service y el flujo de Pull Request, ambos explicados en el Playbook. Este checklist es solo para el caso de que necesites correr el pipeline tú mismo.
