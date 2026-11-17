"""Verifica que la foto (snapshot_rows.json) reproduce lo publicado en un board (metrics.yaml de la versión).

Uso:  uv run --with pyyaml python verify_snapshot_vs_board.py snapshot_rows.json \
          "Board Agent/boards/2026-08/board_Aug_2026_v40.metrics.yaml" 2026-08

Compara, celda por celda, la tabla del ARR Walk (total, Core y Lite, últimos 5 meses) y las láminas
por país del mes de corte (ARR, logos, New Logos, New ARR, Net New ARR, ARPA, Investment, CAC, Payback, Churn).
Fórmulas: las del board (ver references/formulas.md de la skill).
"""
import sys, json, re, yaml

rows = json.load(open(sys.argv[1])); b = yaml.safe_load(open(sys.argv[2])); cutoff = sys.argv[3]
idx = {(r['scope'], r['segment'], r['date_month'][:7]): r for r in rows}


def prevm(m):
    y, mo = int(m[:4]), int(m[5:]) - 1
    return f"{y - 1:04d}-12" if mo == 0 else f"{y:04d}-{mo:02d}"


def g(sc, sg, m, k):
    return (idx.get((sc, sg, m)) or {}).get(k) or 0.0


def num(s):
    s = str(s).strip()
    if s in ('—', 'N/A', ''):
        return None
    t = re.sub(r'[^0-9.]', '', s)
    return None if t == '' else (-float(t) if s.startswith(('(', '-')) else float(t))


def walk(sc, sg, m):
    p = prevm(m)
    G = lambda k, mm=m: g(sc, sg, mm, k)
    bop_l, eop_l, new, rec = G('logos_eop', p), G('logos_eop'), G('logos_new'), G('logos_recov')
    bop, eop = G('mrr_eop', p), G('mrr_eop')
    nb, nc, rc, ra, ch = G('mrr_new_base_t0'), G('mrr_new_cross_t0'), G('mrr_recov'), G('mrr_react'), G('mrr_churn')
    up, dn, pr, cn, cr, cd = (G('mrr_upsell'), G('mrr_downsell'), G('mrr_pricing_others'),
                              G('mrr_cross_new_t1plus'), G('mrr_cross_readop'), G('mrr_cross_down'))
    fx = eop - (bop + nb + nc + rc + ra - ch + up + dn + pr + cn + cr - cd)
    na = ((new + rec) / (((bop_l + eop_l) / 2) or 1) * 100) if sg == 'all' else ((new / bop_l * 100) if bop_l else 0)
    return {'Total EoP': eop_l / 1e3, 'Logo Monthly New Adds %': na, 'Logo Monthly Churn %': G('churn_rate_pct'),
            'ARR BoP': bop * 12 / 1e6, 'Additions': (nb + nc) * 12 / 1e6, 'Recovered': rc * 12 / 1e6,
            'Net Churn': (ra - ch) * 12 / 1e6, 'Net Expansion': (up + dn + pr + cn + cr - cd) * 12 / 1e6,
            '(+/−) FX Impact': fx * 12 / 1e6, 'ARR EoP': eop * 12 / 1e6,
            'ARR EoP (Constant Currency)': G('mrr_eop_cc') * 12 / 1e6, 'S&M Total Spend ($K)': G('investment_usd') / 1e3,
            'CAC Payback (meses)': G('payback_months') or 0,
            'ARPA Adds': ((nb + nc) / new if new > 0 else 0), 'ARPA Churn': (ch / G('logos_churn') if G('logos_churn') > 0 else 0)}


months5 = [cutoff]
for _ in range(4):
    months5.insert(0, prevm(months5[0]))
tot_ok = tot_bad = 0
for name, seg, table in [('Total', 'all', b['arr_walk_table'])] + [(p['name'], p['name'], p['arr_walk_table']) for p in b['arr_walk_products']]:
    bt = {r['label']: r['cells'] for sec in table['sections'] for r in sec['rows']}
    ok = bad = 0; det = []
    for i, m in enumerate(months5):
        for lab, val in walk('total', seg, m).items():
            bv = num(bt[lab][i]) if lab in bt else None
            if bv is None:
                continue
            small = lab.startswith(('S&M', 'ARPA'))
            mine = round(val) if small else round(val, 1)
            if abs(mine - bv) < (1.01 if small else 0.051):
                ok += 1
            else:
                bad += 1; det.append((m, lab, round(val, 3), bt[lab][i]))
    tot_ok += ok; tot_bad += bad
    print(f"walk {name:<6} celdas ok {ok}, difieren {bad}", det[:5])
print("TOTAL walk:", tot_ok, "ok /", tot_bad, "difieren")
