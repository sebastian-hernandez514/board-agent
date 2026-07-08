# Playbook del Board — Cómo colaborar sin depender de Sebastián

> **Borrador — 2026-07-06.** Este documento se revisa con Sebastián antes de publicarse en la wiki de
> Alegra. Las filas del RACI marcadas **"a confirmar"** necesitan su validación — no se inventaron,
> pero tampoco están confirmadas con cada persona todavía.

---

## 1. ¿Qué es Board Agent?

Es el sistema que arma el board ejecutivo mensual de Alegra de forma automática. Antes, cada mes había
que actualizar a mano un montón de números en un archivo HTML gigante — y cada vez que se corría el
proceso completo, lo que alguien había escrito a mano (un comentario, un ajuste) se borraba sin avisar.
Eso generaba errores que llegaban hasta la versión final del board.

Hoy, casi todos los números (ARR, MRR, Churn, Headcount, NPS, Payback) salen automáticamente de
Redshift. Lo único que sigue siendo humano es el contenido editorial — highlights del CEO, discussion
topics, comentarios de contexto — porque eso es criterio, no un dato que se pueda calcular.

El sistema corre en 6 pasos (fases), uno después del otro:

| Fase | Qué hace | En español simple |
|---|---|---|
| 0 — Human Inputs Gate | Revisa que los archivos que llenan las personas (highlights, discussion topics) no estén vacíos o con placeholders | "¿Ya alguien escribió lo que le tocaba este mes?" |
| 1 — Data Freshness | Revisa que Redshift tenga los datos del mes que se va a generar | "¿Ya está la información del mes cerrado?" |
| 2 — Metrics Computation | Calcula todos los números (ARR, MRR, Churn, etc.) | "Hacer las cuentas" |
| 3 — HTML Builder | Arma el HTML final del board con esos números | "Armar las slides" |
| 4 — Validator | Revisa que los números cuadren entre sí (14 reglas hoy) — por ejemplo, que el ARR total sí incluya Alanube | "¿Esto tiene sentido matemáticamente?" |
| 5 — Diff Review | Compara este board contra el mes anterior y avisa si algo cambió mucho de golpe | "¿Hay algo raro que valga la pena revisar antes de mandarlo?" |
| 6 — PDF | Genera el PDF final, solo cuando alguien lo aprueba a mano | "Ya quedó, generar el PDF" |

**Lo único que sigue siendo 100% humano:** el texto de highlights/lowlights del CEO, los discussion
topics (contenido, no el diseño — para eso ya hay una skill, ver sección 5), y la aprobación final
antes de publicar.

---

## 2. Cómo acceder

### GitHub

El código vive en un repo privado: `sebastian-hernandez514/board-agent`.

1. Si no tienes cuenta de GitHub, crear una gratis con tu correo de Alegra en [github.com](https://github.com).
2. Pedirle a Sebastián que te invite al repo (necesita tu usuario de GitHub, no el correo).
3. Una vez invitado, puedes ver el código, proponer cambios (sección 4) y ver el historial de boards generados en `boards/YYYY-MM/`.

### Metabase

Para consultar datos directamente (fuera del board ya armado), se pide acceso puntual al equipo de
datos cuando se necesite una tabla específica — no hay acceso general de entrada.

---

## 3. RACI — quién entrega qué y cuándo

**Qué es un RACI:** para cada tarea recurrente, dice quién la **hace** (Responsable), quién la
**aprueba** (Accountable — es quien firma al final, solo puede haber una persona por tarea), a quién
se **consulta** antes de hacerla, y a quién se le **avisa** cuando está lista.

| Insumo | Responsable (R) | Aprueba (A) | Consultado (C) | Informado (I) | Cuándo (relativo al cierre de mes) |
|---|---|---|---|---|---|
| CEO Highlights / Lowlights (`editorial/ceo.yaml`) | Sebastián | *a confirmar* | Liderazgo | Equipo Board | ~3 días antes del board |
| Discussion Topics (contenido) | Luis Caro, Mayra Gutiérrez, Sebastián | *a confirmar* | — | Equipo Board | ~5 días antes del board |
| Discussion Topics (HTML — vía skill, sección 5) | Quien tenga el contenido listo (ya no depende solo de Sebastián) | Sebastián (revisión de diseño) | — | — | Al mismo tiempo que el contenido |
| ARR Walk Alanube (comentarios) | *a confirmar — hoy Sebastián* | *a confirmar* | Equipo Alanube | — | ~3 días antes |
| Headcount (Sheets EoP + Forecast) | People & Talent | *a confirmar* | — | Sebastián | Antes del cierre de mes |
| P&L (CSV real) | Santiago González | Finance | — | Sebastián | Cierre de mes contable |
| Template 4 (Financial Performance, HTML) | Sofía Maldonado | Finance | — | Sebastián | Mensual, antes de generar el HTML |
| NPS snapshot | Sebastián (vía sesión de Claude + Amplitude) | *a confirmar* | — | Mayra | Mensual, mes anterior completo |
| Tasas de cambio (`tb_trm_banrep`, Redshift) | *(por confirmar)* | — | Luis Caro (avisa/escala si no está al día) | Sebastián | Antes de correr el flujo del mes |
| Segmentos de CAC (`fact_cac_version_segments`, Redshift) | Santiago González | — | — | Sebastián | Antes de correr el flujo del mes |
| Aprobación final del board (antes de publicar) | — | **Sin dueño único definido todavía — pendiente** | Luis Caro | Equipo Board | Antes de la fecha del board |

**Pendiente de definir contigo:** quién es el Accountable (aprobador final) de cada fila, y confirmar
si Luis/Mayra son los dueños reales de Discussion Topics o solo los que más lo piden. Esto se ajusta
en la reunión de revisión de este Playbook.

---

## 4. Cómo proponer un cambio en GitHub (para no-técnicos)

1. Pídele a Claude Code (con acceso al repo `board-agent`) que haga el cambio por ti — decirle en
   lenguaje simple qué quieres (ej. "agrega este discussion topic sobre X").
2. Claude arma el cambio en una rama nueva y abre un **Pull Request** (PR) — es una propuesta de
   cambio, no se publica sola.
3. Alguien revisa el PR en GitHub (por ahora, Sebastián) y lo aprueba o pide ajustes.
4. Una vez aprobado, se mergea a la rama principal — ahí sí queda oficial.

No hace falta escribir código a mano ni entender Git — el flujo completo se puede hacer conversando
con Claude Code.

---

## 5. Cómo usar la skill de Discussion Topics

Ya existe una skill (`Board Agent/skills/discussion-topic/SKILL.md`) que sabe el diseño exacto de las
slides de discussion topics — no hace falta que Sebastián las escriba a mano.

**Para usarla:** decirle a Claude Code algo como *"quiero agregar un discussion topic sobre [tema],
tengo estos bullets/esta imagen/estos datos"* — Claude te va a preguntar qué layout encaja mejor (hay
5 disponibles) y arma el HTML solo, respetando el diseño de las slides existentes.

No hace falta llenar ningún YAML ni tocar CSS — la skill se encarga de eso.

---

## 6. Troubleshooting

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El board sale con datos de un mes viejo | Fase 1 (Data Freshness) no se corrió o falló | Avisar a Sebastián y correr el flujo completo (`run.py --month YYYY-MM`, sin flags) — `--validate-only` NO revisa Fase 1, solo re-valida el HTML que ya existe |
| Un discussion topic tiene la imagen rota | Imagen no se embebió en base64 al crearla | Ver Regla de oro #4 de la skill de discussion topics |
| No tengo acceso a GitHub | No te han invitado al repo todavía | Pedir a Sebastián que te agregue con tu usuario de GitHub |
| Un número del board no cuadra con otro | El Validator (Fase 4) debería haberlo bloqueado | Avisar — puede ser una regla nueva que hace falta agregar |

---

## Próximos pasos de este borrador

1. Revisar con Sebastián las filas "a confirmar" del RACI (sección 3).
2. Decidir quién es el Accountable de la aprobación final del board.
3. Una vez validado, publicar como documento en la wiki de Alegra, colección **"Board"** (nueva).
