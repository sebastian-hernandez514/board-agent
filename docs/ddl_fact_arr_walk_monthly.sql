-- fact_arr_walk_monthly — flujos del ARR Walk del board (clasificación por compañía)
-- Esquema: bi_board (Metabase: dm_board). Grano: date_month x segment ('all' | 'Core' | 'Lite') x app_version.
-- Historia: se mira TODA la historia de cada compañía para decidir si es nueva o recuperada; la salida va desde 2024-01.
-- Montos en USD a la tasa FX del propio mes (dwh_dimensions.tb_trm_banrep, redondeo del board). Solo meses cerrados.
--
-- Columnas de churn de logos — son dos medidas distintas, no mezclar:
--   logos_churn / usd_churn          = empresas que tenían MRR el mes anterior y este mes ya no (pasan a MRR 0).
--                                      Incluye las que el warehouse aún no marca como churn. Sirve para que el ARR cierre.
--   logos_churn_marked               = empresas marcadas CHURN por el warehouse (churn oficial; coincide con dm_retention).
--   logos_reactivated_marked         = empresas marcadas REACTIVATED por el warehouse con los filtros del board.
-- usd_churn y usd_downsell son NEGATIVOS.
--
-- Cambios respecto de la tabla actual:
--   1) Historia completa (antes desde 2022-10): una empresa que pagó antes de esa fecha y vuelve ahora es recuperada, no nueva.
--   2) Columnas nuevas: logos_reactivated_marked y logos_churn_marked.
--   3) date_month pasa a tipo DATE (antes timestamp).
-- Validado (solo lectura, 2026-10-02): New, Recovered, Reactivated marcado y Churn marcado coinciden con los eventos
-- del warehouse en mayo a agosto-2026 (agosto: 2.076 / 693 / 1.126 / 3.448).
--
-- Lo corre el dueño del DDL (no Claude). Reconstruir completa cada mes.
-- Paso 1: borrar la tabla actual.
DROP TABLE bi_board.fact_arr_walk_monthly;

-- Paso 2: crearla de nuevo.
CREATE TABLE bi_board.fact_arr_walk_monthly AS
SELECT t.*, GETDATE() AS last_update
FROM (
WITH fx_raw AS (
  SELECT LEFT(month::varchar, 7) AS ym, 'colombia'  AS app_version, ROUND(cop_usd::float8, 0) AS rate FROM dwh_dimensions.tb_trm_banrep WHERE cop_usd IS NOT NULL
  UNION ALL SELECT LEFT(month::varchar, 7), 'argentina', ROUND(ars_usd::float8, 0) FROM dwh_dimensions.tb_trm_banrep WHERE ars_usd IS NOT NULL
  UNION ALL SELECT LEFT(month::varchar, 7), 'spain',     ROUND(eur_usd::float8, 3) FROM dwh_dimensions.tb_trm_banrep WHERE eur_usd IS NOT NULL
  UNION ALL SELECT LEFT(month::varchar, 7), 'mexico',    ROUND(mex_usd::float8, 1) FROM dwh_dimensions.tb_trm_banrep WHERE mex_usd IS NOT NULL
  UNION ALL SELECT LEFT(month::varchar, 7), 'peru',      ROUND(pen_usd::float8, 1) FROM dwh_dimensions.tb_trm_banrep WHERE pen_usd IS NOT NULL
),
fx_latest AS (
  SELECT app_version, rate FROM (
    SELECT app_version, rate, ROW_NUMBER() OVER (PARTITION BY app_version ORDER BY ym DESC) AS rn FROM fx_raw
  ) WHERE rn = 1
),
seg_month AS (
  SELECT id_company, app_version, segment_type_def AS segment, date_month,
         SUM(CASE WHEN app_version IN ('colombia','mexico','argentina','peru','spain')
                  THEN amount_mrr ELSE COALESCE(amount_usd_real_mrr, amount_usd_mrr) END) AS local_mrr
  FROM dwh_facts.fact_customers_mrr
  WHERE segment_type_def IN ('Core','Lite')
    AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
    AND amount_usd_mrr > 0
    AND plan_name IS NOT NULL AND plan_name <> ''
    AND date_month < DATE_TRUNC('month', CURRENT_DATE)
  GROUP BY 1,2,3,4
  HAVING SUM(CASE WHEN app_version IN ('colombia','mexico','argentina','peru','spain')
                  THEN amount_mrr ELSE COALESCE(amount_usd_real_mrr, amount_usd_mrr) END) > 0
),
co_month AS (
  SELECT id_company, app_version, date_month, SUM(local_mrr) AS local_mrr
  FROM seg_month GROUP BY 1,2,3
),
co_seq AS (
  SELECT id_company, app_version, date_month, local_mrr,
         LAG(date_month)  OVER (PARTITION BY id_company, app_version ORDER BY date_month) AS prev_m,
         LAG(local_mrr)   OVER (PARTITION BY id_company, app_version ORDER BY date_month) AS prev_local,
         LEAD(date_month) OVER (PARTITION BY id_company, app_version ORDER BY date_month) AS next_m
  FROM co_month
),
co_flag AS (
  SELECT *,
    CASE WHEN prev_m IS NULL THEN 'new'
         WHEN DATEDIFF(month, prev_m, date_month) = 1 THEN 'delta'
         WHEN DATEDIFF(month, prev_m, date_month) = 2 THEN 'reactivated'
         ELSE 'recovered' END AS status,
    CASE WHEN (next_m IS NULL OR DATEDIFF(month, date_month, next_m) <> 1)
          AND DATEADD(month, 1, date_month) < DATE_TRUNC('month', CURRENT_DATE)
         THEN 1 ELSE 0 END AS churns_next_month
  FROM co_seq
),
seg_seq AS (
  SELECT id_company, app_version, segment, date_month, local_mrr,
         LAG(local_mrr) OVER (PARTITION BY id_company, app_version, segment ORDER BY date_month) AS prev_seg_local
  FROM seg_month
),
ev AS (
  -- GLO ('all'): clasificación a nivel compañía completa
  SELECT c.date_month, 'all' AS segment, c.app_version, c.status AS kind,
         CASE WHEN c.status IN ('new','reactivated','recovered') THEN 1 ELSE 0 END AS logos,
         CASE WHEN c.status = 'delta' THEN (c.local_mrr - c.prev_local) ELSE c.local_mrr END
           / COALESCE(fx.rate, fl.rate, 1.0) AS usd
  FROM co_flag c
  LEFT JOIN fx_raw fx ON fx.app_version = c.app_version AND fx.ym = LEFT(c.date_month::varchar, 7)
  LEFT JOIN fx_latest fl ON fl.app_version = c.app_version
  UNION ALL
  SELECT DATEADD(month, 1, c.date_month), 'all', c.app_version, 'churn', 1,
         -c.local_mrr / COALESCE(fx.rate, fl.rate, 1.0)
  FROM co_flag c
  LEFT JOIN fx_raw fx ON fx.app_version = c.app_version AND fx.ym = LEFT(DATEADD(month, 1, c.date_month)::varchar, 7)
  LEFT JOIN fx_latest fl ON fl.app_version = c.app_version
  WHERE c.churns_next_month = 1
  UNION ALL
  -- Core / Lite: misma decisión que GLO, monto del segmento
  SELECT s.date_month, s.segment, s.app_version, c.status,
         CASE WHEN c.status IN ('new','reactivated','recovered') THEN 1 ELSE 0 END,
         CASE WHEN c.status = 'delta' THEN (s.local_mrr - COALESCE(s.prev_seg_local, 0)) ELSE s.local_mrr END
           / COALESCE(fx.rate, fl.rate, 1.0)
  FROM seg_seq s
  JOIN co_flag c ON c.id_company = s.id_company AND c.app_version = s.app_version AND c.date_month = s.date_month
  LEFT JOIN fx_raw fx ON fx.app_version = s.app_version AND fx.ym = LEFT(s.date_month::varchar, 7)
  LEFT JOIN fx_latest fl ON fl.app_version = s.app_version
  UNION ALL
  SELECT DATEADD(month, 1, s.date_month), s.segment, s.app_version, 'churn', 1,
         -s.local_mrr / COALESCE(fx.rate, fl.rate, 1.0)
  FROM seg_seq s
  JOIN co_flag c ON c.id_company = s.id_company AND c.app_version = s.app_version AND c.date_month = s.date_month
  LEFT JOIN fx_raw fx ON fx.app_version = s.app_version AND fx.ym = LEFT(DATEADD(month, 1, s.date_month)::varchar, 7)
  LEFT JOIN fx_latest fl ON fl.app_version = s.app_version
  WHERE c.churns_next_month = 1
),
flows AS (
SELECT date_month, segment, app_version,
       SUM(CASE WHEN kind = 'new'         THEN logos ELSE 0 END) AS logos_new,
       SUM(CASE WHEN kind = 'recovered'   THEN logos ELSE 0 END) AS logos_recovered,
       SUM(CASE WHEN kind = 'reactivated' THEN logos ELSE 0 END) AS logos_reactivated,
       SUM(CASE WHEN kind = 'churn'       THEN logos ELSE 0 END) AS logos_churn,
       SUM(CASE WHEN kind = 'new'         THEN usd ELSE 0 END) AS usd_new,
       SUM(CASE WHEN kind = 'recovered'   THEN usd ELSE 0 END) AS usd_recovered,
       SUM(CASE WHEN kind = 'reactivated' THEN usd ELSE 0 END) AS usd_reactivated,
       SUM(CASE WHEN kind = 'churn'       THEN usd ELSE 0 END) AS usd_churn,
       SUM(CASE WHEN kind = 'delta' AND usd > 0 THEN usd ELSE 0 END) AS usd_upsell,
       SUM(CASE WHEN kind = 'delta' AND usd < 0 THEN usd ELSE 0 END) AS usd_downsell
FROM ev
WHERE date_month >= '2024-01-01'
GROUP BY 1,2,3
),
marked AS (
  -- Churn y reactivados MARCADOS por el warehouse (los eventos oficiales de churn de logos).
  SELECT date_month, segment_type_def AS segment, app_version,
         COUNT(DISTINCT CASE WHEN event_logo = 'CHURN' THEN id_company END) AS logos_churn_marked,
         COUNT(DISTINCT CASE WHEN event_logo = 'REACTIVATED'
                              AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
                              AND amount_usd_mrr > 0
                              AND plan_name IS NOT NULL AND plan_name <> '' THEN id_company END) AS logos_reactivated_marked
  FROM dwh_facts.fact_customers_mrr
  WHERE segment_type_def IN ('Core','Lite')
    AND date_month >= '2024-01-01' AND date_month < DATE_TRUNC('month', CURRENT_DATE)
  GROUP BY 1,2,3
  UNION ALL
  SELECT date_month, 'all', app_version,
         COUNT(DISTINCT CASE WHEN event_logo = 'CHURN' THEN id_company END),
         COUNT(DISTINCT CASE WHEN event_logo = 'REACTIVATED'
                              AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
                              AND amount_usd_mrr > 0
                              AND plan_name IS NOT NULL AND plan_name <> '' THEN id_company END)
  FROM dwh_facts.fact_customers_mrr
  WHERE segment_type_def IN ('Core','Lite')
    AND date_month >= '2024-01-01' AND date_month < DATE_TRUNC('month', CURRENT_DATE)
  GROUP BY 1,3
)
SELECT COALESCE(f.date_month, m.date_month)::date AS date_month,
       COALESCE(f.segment, m.segment)             AS segment,
       COALESCE(f.app_version, m.app_version)     AS app_version,
       COALESCE(f.logos_new, 0)                   AS logos_new,
       COALESCE(f.logos_recovered, 0)             AS logos_recovered,
       COALESCE(f.logos_reactivated, 0)           AS logos_reactivated,
       COALESCE(f.logos_churn, 0)                 AS logos_churn,
       COALESCE(m.logos_reactivated_marked, 0)    AS logos_reactivated_marked,
       COALESCE(m.logos_churn_marked, 0)          AS logos_churn_marked,
       COALESCE(f.usd_new, 0)                     AS usd_new,
       COALESCE(f.usd_recovered, 0)               AS usd_recovered,
       COALESCE(f.usd_reactivated, 0)             AS usd_reactivated,
       COALESCE(f.usd_churn, 0)                   AS usd_churn,
       COALESCE(f.usd_upsell, 0)                  AS usd_upsell,
       COALESCE(f.usd_downsell, 0)                AS usd_downsell
FROM flows f
FULL OUTER JOIN marked m
  ON m.date_month = f.date_month AND m.segment = f.segment AND m.app_version = f.app_version
) t;
