-- arr_walk_general — walk calculado por empresa (total, Core y Lite; 2024-01 a 2026-08)
-- scope = 'total'; segment = all | Core | Lite. Clasifica cada empresa (id_company + país) con su historia desde 2022-10: nueva, recuperada, reactivada, perdida, o continua (sube/baja).
-- Core y Lite usan la misma decisión que el total, con el monto del segmento. Se usa para los meses publicados con este cálculo (hasta julio-2026).
-- Mismas columnas que board_published_monthly (scope, segment, date_month, logos_*, mrr_*, churn_rate_pct, investment_usd, payback_months).
-- Montos en USD (MRR mensual; ARR = MRR x 12). mrr_churn positivo; mrr_downsell negativo. Corte: agosto-2026 (se reconstruye completa en cada board).
-- Lo corre el dueño del DDL (no Claude).
DROP TABLE IF EXISTS bi_board.arr_walk_general;

CREATE TABLE bi_board.arr_walk_general
DISTSTYLE KEY DISTKEY (date_month)
AS
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
cutoff AS (
  SELECT '2026-08-01'::date AS m
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
    AND date_month >= '2022-10-01'
    AND date_month < '2026-09-01'::date
  GROUP BY 1,2,3,4
  HAVING SUM(CASE WHEN app_version IN ('colombia','mexico','argentina','peru','spain')
                  THEN amount_mrr ELSE COALESCE(amount_usd_real_mrr, amount_usd_mrr) END) > 0
),
co_month AS (
  SELECT id_company, app_version, date_month, SUM(local_mrr) AS local_mrr FROM seg_month GROUP BY 1,2,3
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
          AND DATEADD(month, 1, date_month) < '2026-09-01'::date
         THEN 1 ELSE 0 END AS churns_next_month
  FROM co_seq
),
seg_seq AS (
  SELECT id_company, app_version, segment, date_month, local_mrr,
         LAG(local_mrr) OVER (PARTITION BY id_company, app_version, segment ORDER BY date_month) AS prev_seg_local
  FROM seg_month
),
ev AS (
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
  SELECT date_month, segment,
         SUM(CASE WHEN kind = 'new'         THEN logos ELSE 0 END) AS logos_new,
         SUM(CASE WHEN kind = 'recovered'   THEN logos ELSE 0 END) AS logos_recov,
         SUM(CASE WHEN kind = 'reactivated' THEN logos ELSE 0 END) AS logos_react,
         SUM(CASE WHEN kind = 'churn'       THEN logos ELSE 0 END) AS logos_churn,
         SUM(CASE WHEN kind = 'new'         THEN usd ELSE 0 END) AS mrr_new,
         SUM(CASE WHEN kind = 'recovered'   THEN usd ELSE 0 END) AS mrr_recov,
         SUM(CASE WHEN kind = 'reactivated' THEN usd ELSE 0 END) AS mrr_react,
         SUM(CASE WHEN kind = 'churn'       THEN -usd ELSE 0 END) AS mrr_churn,
         SUM(CASE WHEN kind = 'delta' AND usd > 0 THEN usd ELSE 0 END) AS mrr_upsell,
         SUM(CASE WHEN kind = 'delta' AND usd < 0 THEN usd ELSE 0 END) AS mrr_downsell
  FROM ev WHERE date_month >= '2023-12-01' GROUP BY 1,2
),
stock_seg AS (
  -- MRR de cierre por segmento: moneda local / tasa del mes (y a la tasa del mes de corte para constant currency)
  SELECT s.date_month, s.segment,
         SUM(s.local_mrr / COALESCE(fx.rate, fl.rate, 1.0)) AS mrr_eop,
         SUM(s.local_mrr / COALESCE(fc.rate, fl.rate, 1.0)) AS mrr_eop_cc
  FROM seg_month s
  LEFT JOIN fx_raw fx ON fx.app_version = s.app_version AND fx.ym = LEFT(s.date_month::varchar, 7)
  LEFT JOIN fx_latest fl ON fl.app_version = s.app_version
  CROSS JOIN cutoff co
  LEFT JOIN fx_raw fc ON fc.app_version = s.app_version AND fc.ym = LEFT(co.m::varchar, 7)
  WHERE s.date_month >= '2023-12-01'
  GROUP BY 1,2
),
stock AS (
  SELECT date_month, segment, mrr_eop, mrr_eop_cc FROM stock_seg
  UNION ALL
  SELECT date_month, 'all', SUM(mrr_eop), SUM(mrr_eop_cc) FROM stock_seg GROUP BY 1
),
logos_seg AS (
  SELECT date_month, segment, SUM(n) AS logos_eop FROM (
    SELECT date_month, segment_type_def AS segment, app_version, COUNT(DISTINCT id_company) AS n
    FROM dwh_facts.fact_customers_mrr
    WHERE segment_type_def IN ('Core','Lite') AND event_product NOT IN ('AWAITING PAYMENT','CHURN')
      AND amount_usd_mrr > 0 AND plan_name IS NOT NULL AND plan_name <> ''
      AND date_month >= '2023-12-01' AND date_month < '2026-09-01'::date
    GROUP BY 1,2,3
  ) GROUP BY 1,2
),
logos_all AS (
  SELECT date_month, 'all' AS segment, COUNT(DISTINCT id_company) AS logos_eop
  FROM dwh_facts.fact_customers_mrr
  WHERE segment_type_def IN ('Core','Lite') AND event_logo NOT IN ('CHURN','AWAITING PAYMENT')
    AND amount_usd_mrr > 0 AND plan_name IS NOT NULL AND plan_name <> ''
    AND date_month >= '2023-12-01' AND date_month < '2026-09-01'::date
  GROUP BY 1
),
logos AS (
  SELECT date_month, segment, logos_eop FROM logos_seg
  UNION ALL SELECT date_month, segment, logos_eop FROM logos_all
),
inv AS (
  SELECT cohortmonth AS date_month, segment_type AS segment,
         SUM(general_expenses_usd + paid_media_expenses_usd + publicidad_no_web_expenses_usd
             + software_and_tools_expenses_usd + team_expenses_usd + freelance_expenses_usd
             + payroll_expenses_usd + travel_expenses_usd) AS investment_usd
  FROM db_finance.fact_cac_version_segments
  WHERE segment_type IN ('Core','Lite') AND cohortmonth >= '2023-12-01'
  GROUP BY 1,2
  UNION ALL
  SELECT cohortmonth, 'all',
         SUM(general_expenses_usd + paid_media_expenses_usd + publicidad_no_web_expenses_usd
             + software_and_tools_expenses_usd + team_expenses_usd + freelance_expenses_usd
             + payroll_expenses_usd + travel_expenses_usd)
  FROM db_finance.fact_cac_version_segments
  WHERE segment_type IN ('Core','Lite') AND cohortmonth >= '2023-12-01'
  GROUP BY 1
),
pb AS (
  SELECT cohort_month AS date_month,
         CASE dimension WHEN 'global' THEN 'all' WHEN 'global_core' THEN 'Core' WHEN 'global_lite' THEN 'Lite' END AS segment,
         pb_base AS payback_months
  FROM bi_strategic.payback_cohort_results
  WHERE model = 'nc' AND dimension IN ('global','global_core','global_lite') AND cohort_month >= '2023-12-01'
),
base AS (
  SELECT st.date_month, st.segment, st.mrr_eop, st.mrr_eop_cc, lg.logos_eop,
         COALESCE(f.logos_new,0) AS logos_new, COALESCE(f.logos_recov,0) AS logos_recov,
         COALESCE(f.logos_react,0) AS logos_react, COALESCE(f.logos_churn,0) AS logos_churn,
         COALESCE(f.mrr_new,0) AS mrr_new, COALESCE(f.mrr_recov,0) AS mrr_recov,
         COALESCE(f.mrr_react,0) AS mrr_react, COALESCE(f.mrr_churn,0) AS mrr_churn,
         COALESCE(f.mrr_upsell,0) AS mrr_upsell, COALESCE(f.mrr_downsell,0) AS mrr_downsell,
         i.investment_usd, p.payback_months
  FROM stock st
  JOIN logos lg ON lg.date_month = st.date_month AND lg.segment = st.segment
  LEFT JOIN flows f ON f.date_month = st.date_month AND f.segment = st.segment
  LEFT JOIN inv i ON i.date_month = st.date_month AND i.segment = st.segment
  LEFT JOIN pb p ON p.date_month = st.date_month AND p.segment = st.segment
)
SELECT date_month::date AS date_month, 'total' AS scope, segment,
       logos_eop, logos_new, logos_recov, logos_react, logos_churn,
       mrr_eop, mrr_eop_cc,
       mrr_new AS mrr_new_base_t0, 0::float8 AS mrr_new_cross_t0, mrr_new,
       mrr_recov, mrr_react, mrr_churn, mrr_upsell, mrr_downsell,
       0::float8 AS mrr_pricing_others, 0::float8 AS mrr_cross_new_t1plus,
       0::float8 AS mrr_cross_readop, 0::float8 AS mrr_cross_down,
       CASE WHEN LAG(logos_eop) OVER (PARTITION BY segment ORDER BY date_month) > 0
            THEN GREATEST(logos_churn - logos_react, 0)::float8
                 / LAG(logos_eop) OVER (PARTITION BY segment ORDER BY date_month) * 100 END AS churn_rate_pct,
       investment_usd, payback_months
FROM base
WHERE date_month >= '2024-01-01'
) t;
