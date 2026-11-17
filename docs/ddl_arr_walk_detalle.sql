-- arr_walk_detalle — walk calculado por producto y plan (total, Core, Lite y los 4 países; 2024-01 a 2026-08)
-- scope = 'total' o colombia | mexico | republicaDominicana | costaRica (países solo Core y Lite). Es la consulta que el board usa para las láminas por país.
-- Se usa para los países en todos los meses y para el total, Core y Lite de agosto-2026.
-- Mismas columnas que board_published_monthly (scope, segment, date_month, logos_*, mrr_*, churn_rate_pct, investment_usd, payback_months).
-- Montos en USD (MRR mensual; ARR = MRR x 12). mrr_churn positivo; mrr_downsell negativo. Corte: agosto-2026 (se reconstruye completa en cada board).
-- Lo corre el dueño del DDL (no Claude).
DROP TABLE IF EXISTS bi_board.arr_walk_detalle;

CREATE TABLE bi_board.arr_walk_detalle
DISTSTYLE KEY DISTKEY (date_month)
AS
SELECT t.*, GETDATE() AS last_update
FROM (
WITH mrr_base AS (
  SELECT id_company, app_version, segment_type_def, date_month,
         id_product, plan_name, amount_usd_mrr, event_product, event_logo,
         CASE app_version
           WHEN 'colombia'  THEN amount_mrr
           WHEN 'mexico'    THEN amount_mrr
           WHEN 'argentina' THEN amount_mrr
           WHEN 'peru'      THEN amount_mrr
           WHEN 'spain'     THEN amount_mrr
           ELSE COALESCE(amount_usd_real_mrr, amount_usd_mrr)
         END AS amount_conv
  FROM dwh_facts.fact_customers_mrr
  WHERE date_month <= '2026-08-01'
    AND segment_type_def IN ('Core', 'Lite')
    AND event_product NOT IN ('AWAITING PAYMENT', 'CHURN')
    AND amount_usd_mrr > 0
    AND plan_name IS NOT NULL
    AND plan_name <> ''
),
flm AS (
  SELECT id_company, app_version, MIN(date_month) AS logo_first_month
  FROM mrr_base GROUP BY 1,2
),
fpm AS (
  SELECT id_company, app_version, id_product, MIN(date_month) AS prod_first_month
  FROM mrr_base GROUP BY 1,2,3
),
t0_products AS (
  SELECT DISTINCT m.id_company, m.app_version, m.id_product,
    CASE m.id_product WHEN 1 THEN 1 WHEN 4 THEN 2 WHEN 2 THEN 3
                      WHEN 3 THEN 4 WHEN 11 THEN 5 ELSE 99 END AS rk
  FROM mrr_base m
  JOIN flm ON m.id_company=flm.id_company AND m.app_version=flm.app_version
          AND m.date_month=flm.logo_first_month
),
base_product_per_logo AS (
  SELECT id_company, app_version, id_product AS base_id_product
  FROM (
    SELECT id_company, app_version, id_product,
           ROW_NUMBER() OVER (PARTITION BY id_company, app_version ORDER BY rk, id_product) AS rn
    FROM t0_products
  ) WHERE rn=1
),
mrr_eop AS (
  SELECT date_month, app_version, segment_type_def,
         SUM(amount_conv)      AS mrr_usd_eop,
         SUM(amount_conv)      AS mrr_usd_eop_cc
  FROM mrr_base GROUP BY 1,2,3
),
logo_metrics AS (
  SELECT date_month, app_version, segment_type_def,
         COUNT(DISTINCT id_company)                                             AS logos_eop,
         COUNT(DISTINCT CASE WHEN event_logo='NEW'         THEN id_company END) AS logos_new,
         COUNT(DISTINCT CASE WHEN event_logo='RECOVERED'   THEN id_company END) AS logos_recov,
         COUNT(DISTINCT CASE WHEN event_logo='REACTIVATED' THEN id_company END) AS logos_react
  FROM mrr_base GROUP BY 1,2,3
),
logo_churn AS (
  SELECT date_month, app_version, segment_type_def,
         COUNT(DISTINCT id_company) AS logos_churn
  FROM dwh_facts.fact_customers_mrr
  WHERE date_month <= '2026-08-01'
    AND segment_type_def IN ('Core', 'Lite')
    AND event_logo = 'CHURN'
  GROUP BY 1,2,3
),
logo_inflows AS (
  SELECT m.date_month, m.app_version, m.segment_type_def,
    SUM(CASE WHEN m.event_logo='NEW'
              AND (bpl.base_id_product IS NULL OR m.id_product <> bpl.base_id_product)
             THEN m.amount_conv ELSE 0 END)                       AS mrr_usd_new_cross_t0,
    SUM(CASE WHEN m.event_logo='NEW'
              AND bpl.base_id_product IS NOT NULL
              AND m.id_product = bpl.base_id_product
             THEN m.amount_conv ELSE 0 END)                       AS mrr_usd_new_base_t0,
    SUM(CASE WHEN m.event_logo='RECOVERED'   THEN m.amount_conv ELSE 0 END) AS mrr_usd_recov,
    SUM(CASE WHEN m.event_logo='REACTIVATED' THEN m.amount_conv ELSE 0 END) AS mrr_usd_react
  FROM mrr_base m
  LEFT JOIN base_product_per_logo bpl
    ON m.id_company=bpl.id_company AND m.app_version=bpl.app_version
  WHERE m.event_logo IN ('NEW','RECOVERED','REACTIVATED')
  GROUP BY 1,2,3
),
churn_outflows AS (
  SELECT cur.date_month, cur.app_version, cur.segment_type_def,
         SUM(prev.amount_conv) AS mrr_usd_churn
  FROM dwh_facts.fact_customers_mrr cur
  JOIN mrr_base prev
    ON cur.id_company=prev.id_company AND cur.app_version=prev.app_version
   AND cur.id_product=prev.id_product
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
  WHERE cur.date_month <= '2026-08-01'
    AND cur.segment_type_def IN ('Core','Lite')
    AND cur.event_logo = 'CHURN'
  GROUP BY 1,2,3
),
companies_in_both AS (
  SELECT DISTINCT cur.id_company, cur.app_version, cur.date_month
  FROM mrr_base cur
  JOIN mrr_base prev
    ON cur.id_company=prev.id_company AND cur.app_version=prev.app_version
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
),
products_added AS (
  SELECT cpe.date_month, cpe.app_version, cpe.segment_type_def, cpe.amount_conv,
         CASE WHEN fpm.prod_first_month=cpe.date_month THEN 1 ELSE 0 END AS is_first_adoption
  FROM mrr_base cpe
  JOIN companies_in_both cib
    ON cib.id_company=cpe.id_company AND cib.app_version=cpe.app_version
   AND cib.date_month=cpe.date_month
  LEFT JOIN mrr_base cpb
    ON cpb.id_company=cpe.id_company AND cpb.app_version=cpe.app_version
   AND cpb.id_product=cpe.id_product
   AND cpb.date_month=DATEADD('month',-1,cpe.date_month)
  JOIN fpm
    ON fpm.id_company=cpe.id_company AND fpm.app_version=cpe.app_version
   AND fpm.id_product=cpe.id_product
  WHERE cpb.id_company IS NULL
),
products_removed AS (
  SELECT DATEADD('month',1,cpb.date_month) AS date_month,
         cpb.app_version, cpb.segment_type_def, cpb.amount_conv
  FROM mrr_base cpb
  JOIN companies_in_both cib
    ON cib.id_company=cpb.id_company AND cib.app_version=cpb.app_version
   AND cib.date_month=DATEADD('month',1,cpb.date_month)
  LEFT JOIN mrr_base cpe
    ON cpe.id_company=cpb.id_company AND cpe.app_version=cpb.app_version
   AND cpe.id_product=cpb.id_product
   AND cpe.date_month=DATEADD('month',1,cpb.date_month)
  WHERE cpe.id_company IS NULL
),
cross_agg AS (
  SELECT date_month, app_version, segment_type_def,
    SUM(CASE WHEN is_first_adoption=1 THEN amount_conv ELSE 0 END) AS mrr_usd_cross_new_t1plus,
    SUM(CASE WHEN is_first_adoption=0 THEN amount_conv ELSE 0 END) AS mrr_usd_cross_readop,
    0::numeric AS mrr_usd_cross_down
  FROM products_added GROUP BY 1,2,3
  UNION ALL
  SELECT date_month, app_version, segment_type_def, 0, 0, SUM(amount_conv)
  FROM products_removed GROUP BY 1,2,3
),
cross_final AS (
  SELECT date_month, app_version, segment_type_def,
         SUM(mrr_usd_cross_new_t1plus) AS mrr_usd_cross_new_t1plus,
         SUM(mrr_usd_cross_readop)     AS mrr_usd_cross_readop,
         SUM(mrr_usd_cross_down)       AS mrr_usd_cross_down
  FROM cross_agg GROUP BY 1,2,3
),
plan_agg AS (
  SELECT cur.date_month, cur.app_version, cur.segment_type_def,
    SUM(CASE WHEN prev.plan_name <> cur.plan_name AND (cur.amount_conv-prev.amount_conv) > 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_upsell,
    SUM(CASE WHEN prev.plan_name <> cur.plan_name AND (cur.amount_conv-prev.amount_conv) < 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_downsell,
    SUM(CASE WHEN prev.plan_name  = cur.plan_name AND (cur.amount_conv-prev.amount_conv) <> 0
             THEN cur.amount_conv-prev.amount_conv ELSE 0 END) AS mrr_usd_pricing_others
  FROM mrr_base cur
  JOIN mrr_base prev
    ON prev.id_company=cur.id_company AND prev.app_version=cur.app_version
   AND prev.id_product=cur.id_product
   AND prev.date_month=DATEADD('month',-1,cur.date_month)
  GROUP BY 1,2,3
),
summary AS (
SELECT
  e.date_month,
  e.segment_type_def                            AS segment,
  e.app_version,
  COALESCE(lm.logos_eop,0)                      AS logos_eop,
  COALESCE(lm.logos_new,0)                      AS logos_new,
  COALESCE(lm.logos_recov,0)                    AS logos_recov,
  COALESCE(lm.logos_react,0)                    AS logos_react,
  COALESCE(lc.logos_churn,0)                    AS logos_churn,
  e.mrr_usd_eop                                 AS mrr_usd_eop,
  e.mrr_usd_eop_cc                              AS mrr_usd_eop_cc,
  COALESCE(li.mrr_usd_new_base_t0,0)            AS mrr_usd_new_base_t0,
  COALESCE(li.mrr_usd_new_cross_t0,0)           AS mrr_usd_new_cross_t0,
  COALESCE(li.mrr_usd_recov,0)                  AS mrr_usd_recov,
  COALESCE(li.mrr_usd_react,0)                  AS mrr_usd_react,
  COALESCE(co.mrr_usd_churn,0)                  AS mrr_usd_churn,
  COALESCE(pa.mrr_usd_upsell,0)                 AS mrr_usd_upsell,
  COALESCE(pa.mrr_usd_downsell,0)               AS mrr_usd_downsell,
  COALESCE(pa.mrr_usd_pricing_others,0)         AS mrr_usd_pricing_others,
  COALESCE(cf.mrr_usd_cross_new_t1plus,0)       AS mrr_usd_cross_new_t1plus,
  COALESCE(cf.mrr_usd_cross_readop,0)           AS mrr_usd_cross_readop,
  COALESCE(cf.mrr_usd_cross_down,0)             AS mrr_usd_cross_down
FROM mrr_eop e
LEFT JOIN logo_metrics   lm USING (date_month, app_version, segment_type_def)
LEFT JOIN logo_churn     lc USING (date_month, app_version, segment_type_def)
LEFT JOIN logo_inflows   li USING (date_month, app_version, segment_type_def)
LEFT JOIN churn_outflows co USING (date_month, app_version, segment_type_def)
LEFT JOIN plan_agg       pa USING (date_month, app_version, segment_type_def)
LEFT JOIN cross_final    cf USING (date_month, app_version, segment_type_def)
),

fx_raw AS (
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
conv AS (
  -- conversión a USD como el board: moneda local / tasa del mes (constant currency: tasa del mes de corte)
  SELECT s.date_month, s.segment, s.app_version,
         s.logos_eop, s.logos_new, s.logos_recov, s.logos_react, s.logos_churn,
         s.mrr_usd_eop            / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_eop,
         s.mrr_usd_eop_cc         / COALESCE(fc.rate, fl.rate, 1.0) AS mrr_eop_cc,
         s.mrr_usd_new_base_t0    / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_new_base_t0,
         s.mrr_usd_new_cross_t0   / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_new_cross_t0,
         s.mrr_usd_recov          / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_recov,
         s.mrr_usd_react          / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_react,
         s.mrr_usd_churn          / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_churn,
         s.mrr_usd_upsell         / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_upsell,
         s.mrr_usd_downsell       / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_downsell,
         s.mrr_usd_pricing_others / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_pricing_others,
         s.mrr_usd_cross_new_t1plus / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_cross_new_t1plus,
         s.mrr_usd_cross_readop   / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_cross_readop,
         s.mrr_usd_cross_down     / COALESCE(fx.rate, fl.rate, 1.0) AS mrr_cross_down
  FROM summary s
  LEFT JOIN fx_raw fx ON fx.app_version = s.app_version AND fx.ym = LEFT(s.date_month::varchar, 7)
  LEFT JOIN fx_raw fc ON fc.app_version = s.app_version AND fc.ym = '2026-08'
  LEFT JOIN fx_latest fl ON fl.app_version = s.app_version
  WHERE s.date_month >= '2023-12-01'
),
logos_all AS (
  SELECT date_month,
         COUNT(DISTINCT CASE WHEN event_logo NOT IN ('CHURN','AWAITING PAYMENT') THEN id_company END) AS logos_eop,
         COUNT(DISTINCT CASE WHEN event_logo = 'NEW'         THEN id_company END) AS logos_new,
         COUNT(DISTINCT CASE WHEN event_logo = 'RECOVERED'   THEN id_company END) AS logos_recov,
         COUNT(DISTINCT CASE WHEN event_logo = 'REACTIVATED' THEN id_company END) AS logos_react
  FROM dwh_facts.fact_customers_mrr
  WHERE date_month >= '2023-12-01' AND date_month <= '2026-08-01'
    AND segment_type_def IN ('Core','Lite') AND amount_usd_mrr > 0 AND plan_name IS NOT NULL AND plan_name <> ''
  GROUP BY 1
),
inv AS (
  SELECT cohortmonth AS date_month, app_version, segment_type AS segment,
         SUM(general_expenses_usd + paid_media_expenses_usd + publicidad_no_web_expenses_usd
             + software_and_tools_expenses_usd + team_expenses_usd + freelance_expenses_usd
             + payroll_expenses_usd + travel_expenses_usd) AS investment_usd
  FROM db_finance.fact_cac_version_segments
  WHERE segment_type IN ('Core','Lite') AND cohortmonth >= '2023-12-01' AND cohortmonth <= '2026-08-01'
  GROUP BY 1,2,3
),
pb AS (
  SELECT cohort_month AS date_month, dimension, pb_base AS payback_months
  FROM bi_strategic.payback_cohort_results
  WHERE model = 'nc' AND cohort_month >= '2023-12-01' AND cohort_month <= '2026-08-01'
),
-- filas por país (los 4 del board)
country_rows AS (
  SELECT c.date_month, c.app_version AS scope, c.segment,
         c.logos_eop, c.logos_new, c.logos_recov, c.logos_react, c.logos_churn,
         c.mrr_eop, c.mrr_eop_cc, c.mrr_new_base_t0, c.mrr_new_cross_t0,
         c.mrr_new_base_t0 + c.mrr_new_cross_t0 AS mrr_new,
         c.mrr_recov, c.mrr_react, c.mrr_churn, c.mrr_upsell, c.mrr_downsell,
         c.mrr_pricing_others, c.mrr_cross_new_t1plus, c.mrr_cross_readop, c.mrr_cross_down,
         i.investment_usd,
         p.payback_months
  FROM conv c
  LEFT JOIN inv i ON i.date_month = c.date_month AND i.app_version = c.app_version AND i.segment = c.segment
  LEFT JOIN pb p ON p.date_month = c.date_month AND p.dimension =
       (CASE c.app_version WHEN 'colombia' THEN 'colombia' WHEN 'mexico' THEN 'mexico'
                           WHEN 'republicaDominicana' THEN 'rd' WHEN 'costaRica' THEN 'cr' END) || '_' || LOWER(c.segment)
  WHERE c.app_version IN ('colombia','mexico','republicaDominicana','costaRica')
),
-- total por segmento: suma de todos los países
tot_seg AS (
  SELECT date_month, 'total' AS scope, segment,
         SUM(logos_eop) AS logos_eop, SUM(logos_new) AS logos_new, SUM(logos_recov) AS logos_recov,
         SUM(logos_react) AS logos_react, SUM(logos_churn) AS logos_churn,
         SUM(mrr_eop) AS mrr_eop, SUM(mrr_eop_cc) AS mrr_eop_cc,
         SUM(mrr_new_base_t0) AS mrr_new_base_t0, SUM(mrr_new_cross_t0) AS mrr_new_cross_t0,
         SUM(mrr_new_base_t0 + mrr_new_cross_t0) AS mrr_new,
         SUM(mrr_recov) AS mrr_recov, SUM(mrr_react) AS mrr_react, SUM(mrr_churn) AS mrr_churn,
         SUM(mrr_upsell) AS mrr_upsell, SUM(mrr_downsell) AS mrr_downsell,
         SUM(mrr_pricing_others) AS mrr_pricing_others, SUM(mrr_cross_new_t1plus) AS mrr_cross_new_t1plus,
         SUM(mrr_cross_readop) AS mrr_cross_readop, SUM(mrr_cross_down) AS mrr_cross_down
  FROM conv GROUP BY 1,3
),
tot_all AS (
  SELECT t.date_month, 'total' AS scope, 'all' AS segment,
         la.logos_eop, la.logos_new, la.logos_recov, la.logos_react, SUM(t.logos_churn) AS logos_churn,
         SUM(t.mrr_eop), SUM(t.mrr_eop_cc), SUM(t.mrr_new_base_t0), SUM(t.mrr_new_cross_t0), SUM(t.mrr_new),
         SUM(t.mrr_recov), SUM(t.mrr_react), SUM(t.mrr_churn), SUM(t.mrr_upsell), SUM(t.mrr_downsell),
         SUM(t.mrr_pricing_others), SUM(t.mrr_cross_new_t1plus), SUM(t.mrr_cross_readop), SUM(t.mrr_cross_down)
  FROM tot_seg t JOIN logos_all la ON la.date_month = t.date_month
  GROUP BY t.date_month, la.logos_eop, la.logos_new, la.logos_recov, la.logos_react
),
tot AS (
  SELECT t.*, i.investment_usd, p.payback_months
  FROM (SELECT * FROM tot_seg UNION ALL SELECT * FROM tot_all) t
  LEFT JOIN (SELECT date_month, segment, SUM(investment_usd) AS investment_usd FROM inv GROUP BY 1,2
             UNION ALL SELECT date_month, 'all', SUM(investment_usd) FROM inv GROUP BY 1) i
         ON i.date_month = t.date_month AND i.segment = t.segment
  LEFT JOIN pb p ON p.date_month = t.date_month
       AND p.dimension = CASE t.segment WHEN 'all' THEN 'global' WHEN 'Core' THEN 'global_core' ELSE 'global_lite' END
),
allrows AS (
  SELECT * FROM country_rows UNION ALL SELECT * FROM tot
)
SELECT date_month::date AS date_month, scope, segment,
       logos_eop, logos_new, logos_recov, logos_react, logos_churn,
       mrr_eop, mrr_eop_cc, mrr_new_base_t0, mrr_new_cross_t0, mrr_new,
       mrr_recov, mrr_react, mrr_churn, mrr_upsell, mrr_downsell,
       mrr_pricing_others, mrr_cross_new_t1plus, mrr_cross_readop, mrr_cross_down,
       CASE WHEN LAG(logos_eop) OVER (PARTITION BY scope, segment ORDER BY date_month) > 0
            THEN GREATEST(logos_churn - logos_react, 0)::float8
                 / LAG(logos_eop) OVER (PARTITION BY scope, segment ORDER BY date_month) * 100 END AS churn_rate_pct,
       investment_usd, payback_months
FROM allrows
WHERE date_month >= '2024-01-01'
) t;
