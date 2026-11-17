"""Extrae la «foto» de un board: los valores mensuales que el pipeline del Board Agent usó para
armar sus láminas (total, Core, Lite y los 4 países), con inversión y payback, y genera los INSERT
para bi_board.board_published_monthly.

Uso (desde una COPIA del Board Agent, para no alterar nada del original):
    cp -R "Board Agent/"{scripts,board_agent,data,csv} /tmp/ba && cd /tmp/ba
    uv run --with pyyaml python extract_board_snapshot.py 2026-08 board_2026-08_v40

Salidas: snapshot_rows.json y insert_<board_version>.sql. Los INSERT los corre el dueño del DDL en
Redshift (cluster-2, schema bi_board); luego se publica a Viz (dm_board) y se sincroniza Metabase.
"""
import sys, json
sys.path.insert(0, 'scripts')
import fetch_metrics as fm

cutoff, version = sys.argv[1], sys.argv[2]
summary, logos_all, country_raw, investment, funnel, product_perf, flywheel, sc, _ = fm.load_data(cutoff)
seg_metrics, segs_raw, all_months, latest_mm = fm.build_seg_metrics(summary, logos_all, sc=sc)

RAW = ['logos_eop', 'logos_new', 'logos_recov', 'logos_react', 'logos_churn', 'mrr_eop', 'mrr_eop_cc',
       'mrr_new_base_t0', 'mrr_new_cross_t0', 'mrr_recov', 'mrr_react', 'mrr_churn', 'mrr_upsell',
       'mrr_downsell', 'mrr_pricing_others', 'mrr_cross_new_t1plus', 'mrr_cross_readop', 'mrr_cross_down']
NUM = RAW + ['mrr_new', 'churn_rate_pct', 'investment_usd', 'payback_months']
months = [m for m in all_months if m >= '2024-01']
pb = fm.load_payback()
rc = (sc or {}).get('retention_churn', {}).get('by_seg_country', {})


def prev(m):
    return fm._prev_m(m)


def inv_of(scope, seg, m):
    if scope == 'total':
        return sum(sd.get(m, {}).get('total', 0) for ci in (investment or {}).values()
                   for sg, sd in ci.items() if seg == 'all' or sg == seg)
    return ((investment or {}).get(scope, {}).get(seg, {}).get(m, {}) or {}).get('total', 0.0)


def pb_of(scope, seg, m):
    v = pb.get(('Todos' if scope == 'total' else scope, 'Total' if seg == 'all' else seg), {}).get(m)
    return None if v is None else float(v)


rows = []
for seg in ('all', 'Core', 'Lite'):                       # total Alegra
    for m in months:
        d = segs_raw[seg].get(m)
        if not d:
            continue
        calc = seg_metrics[seg]['months'].get(fm._month_label(m), {})
        r = {'scope': 'total', 'segment': seg, 'date_month': m + '-01'}
        r.update({k: float(d.get(k, 0) or 0) for k in RAW})
        r['mrr_new'] = r['mrr_new_base_t0'] + r['mrr_new_cross_t0']
        r['churn_rate_pct'] = float(calc.get('l_churn_pct', 0)) * 100
        rows.append(r)
for m in months:                                          # países del board (solo Core y Lite)
    for ck, segd in (country_raw.get(m, {}) or {}).items():
        for seg, d in segd.items():
            if seg not in ('Core', 'Lite'):
                continue
            r = {'scope': ck, 'segment': seg, 'date_month': m + '-01'}
            r.update({k: float(d.get(k, 0) or 0) for k in RAW})
            r['mrr_new'] = float(d.get('mrr_new', 0) or 0)
            rd = rc.get(m, {}).get(ck, {}).get(seg)
            if rd and rd['bop'] > 0:
                r['churn_rate_pct'] = max(rd['churned'] - rd['reactivated'], 0) / rd['bop'] * 100
            else:
                bop = (country_raw.get(prev(m), {}).get(ck, {}).get(seg, {}) or {}).get('logos_eop', 0)
                r['churn_rate_pct'] = (max((d.get('logos_churn', 0) or 0) - (d.get('logos_react', 0) or 0), 0)
                                       / bop * 100) if bop else 0
            rows.append(r)
for r in rows:
    r['investment_usd'] = float(inv_of(r['scope'], r['segment'], r['date_month'][:7]))
    r['payback_months'] = pb_of(r['scope'], r['segment'], r['date_month'][:7])

json.dump(rows, open('snapshot_rows.json', 'w'))


def lit(v):
    if v is None:
        return 'NULL'
    s = repr(round(float(v), 6))
    return s[:-2] if s.endswith('.0') else s


cols = ['board_version', 'scope', 'segment', 'date_month'] + NUM
out = []
for i in range(0, len(rows), 60):
    vals = ",\n".join("('%s','%s','%s','%s',%s)" % (version, r['scope'], r['segment'], r['date_month'],
                                                    ",".join(lit(r.get(k)) for k in NUM)) for r in rows[i:i + 60])
    out.append(f"INSERT INTO bi_board.board_published_monthly ({', '.join(cols)}) VALUES\n{vals};\n")
open(f'insert_{version}.sql', 'w').write("\n".join(out))
print(len(rows), 'filas ->', f'insert_{version}.sql')
