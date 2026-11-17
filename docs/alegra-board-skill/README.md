# Skill `alegra-board` — documentación del proyecto

Última actualización: 2026-10-05. Escrito para el equipo BI Data (quien mantiene el board y la skill).

## 1. Qué es

Una skill del agente de data (repo `Alegra-Team/data-agent-selfservice`, carpeta `agent/skills/alegra-board/`) que responde en el chat con las cifras del board ejecutivo mensual: ARR y MRR por país (Colombia, México, República Dominicana, Costa Rica) y segmento (Core, Lite), ARR Walk, logos nuevos y netos, churn de logos, ARPA, inversión, CAC, payback y ARR total con Alanube. No cubre headcount, P&L, NPS ni budget.

Ejemplos de lo que responde: «¿cuánto fue el net new logos de Colombia Core en agosto?» (+247 en el board), «¿cuál fue el churn de Dominicana Core?» (2,0%), «¿cuál fue el CAC de México?».

## 2. Estado actual (2026-10-05)

| Qué | Dónde está | Qué lee |
|---|---|---|
| **Versión integrada** | `main` y `testing` (la integró Jhon; el manifest de `main` ya la lista) | `dm_board.board_published_monthly` (la foto del board v40) |
| **Versión nueva, sin liberar** | PR #64 abierto contra `testing`, rama `feature/alegra-board-skill` (commits `5b12138`, `5c453bf`) | `dm_board.arr_walk_general` + `dm_board.arr_walk_detalle` |

⚠️ Las dos versiones **no se pueden mezclar tal cual**: el PR #64 todavía trae los primeros commits (que ya están en `main` con otro hash) y habría que rebasarlo sobre `main` conservando los cambios de ruteo de Jhon (commit `a8de200`: «el modelo interno es el default de MRR y ARR; el board se ofrece después»).

**Decisión pendiente:** ¿se queda la versión de la foto (exacta con lo presentado, carga manual por board) o se reemplaza por general/detalle (cálculo automático, con diferencias pequeñas)? Ver §6.

## 3. Las tablas

Todas se crean en Redshift cluster-2 (schema `bi_board`) y se publican al clúster Viz (`dm_board`) con «Publicar tabla»; después se sincroniza Metabase. El replicador exige `DISTSTYLE` explícito (no `AUTO`): las dos tablas calculadas ya lo traen (`DISTSTYLE KEY DISTKEY (date_month)`).

| Tabla | Filas | Qué es | Archivo con el SQL |
|---|---:|---|---|
| `board_published_monthly` | 352 | **Foto** de los valores que usó el board v40, por `scope` (total y 4 países) × `segment` × mes, 2024-01 a 2026-08. Columna `board_version` | `sql/ddl_board_published_monthly.sql` (+ partes 1 y 2 de carga) |
| `arr_walk_general` | 96 | Walk **por empresa**: total, Core y Lite. Cálculo con historia desde 2022-10 | `sql/ddl_arr_walk_general.sql` |
| `arr_walk_detalle` | 352 | Walk **por producto y plan**: total, Core, Lite y 4 países. Es la consulta del propio board | `sql/ddl_arr_walk_detalle.sql` |
| `fact_arr_walk_monthly` | 1.135 | Primer recálculo (por empresa, historia completa, con churn marcado). Sin uso | `sql/ddl_fact_arr_walk_monthly.sql` |

Todas comparten las columnas `scope`, `segment`, `date_month`, `logos_*`, `mrr_*`, `churn_rate_pct`, `investment_usd`, `payback_months`. La inversión y el payback vienen de Redshift (`db_finance.fact_cac_version_segments`, `bi_strategic.payback_cohort_results`); las tablas equivalentes en Metabase llegan atrasadas (inversión solo hasta mayo-2026).

## 4. Por qué este diseño

- **El board no recalcula todo cada mes.** Calcula el mes nuevo y reutiliza como foto resultados guardados de meses anteriores. Un recálculo hoy da diferencias pequeñas contra lo enviado.
- **El board mezcla dos cálculos.** El walk del total, Core y Lite de enero-2024 a julio-2026 sale de un archivo guardado, calculado **por empresa** (la que llamamos «v2»). Agosto y todas las láminas por país se calculan **por producto y plan** («v1»). La causa en agosto: el estado de v2 ya figuraba en agosto pero el archivo histórico no lo tiene, y el control que evita sobrescribir meses cerrados hizo que las corridas siguientes se saltaran v2.
- **Qué cambia entre ambos.** El ARR de cierre es el mismo. Cambia el reparto entre altas, bajas y expansión (en agosto, total: Net Churn −1.054K con v1 y −1.100K con v2, y FX Impact 979K contra 1.024K; en Core y Lite la diferencia es mayor).
- **Decisión del usuario:** la skill debe dar lo mismo que se presentó. Por eso primero se guardó la foto (exacta) y después se armaron general y detalle (automáticas). La skill explica por qué una cifra puede no coincidir con un board ya enviado, sin nombrar versiones.

## 5. Cómo se verificó (2026-10-02, contra el board de agosto v40)

| Qué | Resultado |
|---|---|
| Foto vs board: walk total, Core y Lite (abril a agosto), YTD, lámina global, láminas por país | 0 diferencias (225 celdas de walk, 88 de países) |
| Detalle vs foto, países, 32 meses | 99,4% dentro de tolerancia (5.185 de 5.216) |
| Detalle vs foto, total/Core/Lite de agosto | 47 de 63 dentro de 0,3%; el resto décimas de punto (churn de logos 3.448 contra 3.429) |
| General vs foto, total, enero-2024 a julio-2026 | Casi todo; difieren diciembre-2025, junio y julio-2026 (datos corregidos después del cierre) |
| General vs foto, Core y Lite | No coinciden: el board los calculó con una regla anterior |
| Ejemplo | Colombia Core agosto, net logo adds: foto +247, detalle +249 |

Las consultas MBQL de la skill se probaron en vivo contra Metabase con las tres tablas.

## 6. Qué hacer cada mes

### Si la skill lee la foto (versión integrada en `main`)

1. Correr el board del mes con el Board Agent (deja al día el cache de Metabase y el archivo histórico).
2. Copiar `scripts/`, `board_agent/`, `data/` y `csv/` del Board Agent a una carpeta temporal y correr `scripts/extract_board_snapshot.py <YYYY-MM> board_<YYYY-MM>_v<N>` (ver su encabezado). Genera `insert_<board_version>.sql`.
3. Verificar con `scripts/verify_snapshot_vs_board.py` contra el `metrics.yaml` del board enviado. Se esperan 0 diferencias.
4. El dueño del DDL corre el `INSERT` en Redshift (se agrega una versión; no se borra la anterior).
5. Sincronizar Metabase. La skill toma sola la `board_version` más alta de cada mes.

### Si la skill lee general y detalle (PR #64)

1. Editar en los dos `ddl_arr_walk_*.sql` el mes de corte (los literales `'2026-08-01'`, `'2026-09-01'` y `'2026-08'`).
2. El dueño del DDL corre cada archivo (`DROP` y `CREATE`), publica a `dm_board` y sincroniza Metabase.
3. Actualizar en la skill la regla de qué tabla usa cada mes (hoy: detalle para agosto-2026 y para países; general para el resto).

## 7. Hallazgos abiertos

1. **Agosto del board v40 se calculó con v1, no con v2.** Causa en §4. Arreglo: calcular agosto con v2, agregarlo al archivo histórico, regenerar como board v41 y agregar un control al Validator que falle si el archivo histórico no llega al mes de corte. Comunicar a quienes vieron el churn de 3,8%: con el mismo método en todos los meses daría ≈4,0%.
2. **Churn de logos en %.** Hay dos medidas: por ausencia (toda empresa que pasa a MRR 0, 3.541 en agosto) y por marca del warehouse (3.448). Con la fuente de hoy, agosto da 3,9% por marca y 4,0% por ausencia; el 3,8% publicado salió de una foto con 3.429. Falta definir cuál es la oficial.
3. **Core y Lite de meses anteriores** se calcularon con otra regla; v2 en Core y Lite también sobrestima la expansión por empresas que cambian de segmento.
4. **Tabla de inversión de Metabase atrasada** (llega a mayo-2026). Las tablas de la skill traen la inversión desde Redshift.
5. **La descripción que Metabase generó para `arr_walk_general`** dice «arrendadoras». Es automática y se puede corregir en los metadatos.

## 8. Archivos de esta carpeta

| Archivo | Para qué |
|---|---|
| `scripts/extract_board_snapshot.py` | Extrae la foto de un board y genera los `INSERT` |
| `scripts/verify_snapshot_vs_board.py` | Compara la foto contra el `metrics.yaml` del board |
| `sql/` | DDL de las cuatro tablas y los `INSERT` de la foto del board v40 |

Memoria de trabajo del asistente (no es parte del repo): `~/.claude/projects/-Users-sebastian-alegra-Alegra-IA/memory/project_alegra_board_skill.md` y `project_board_agosto_v1_en_vez_de_v2.md`.
