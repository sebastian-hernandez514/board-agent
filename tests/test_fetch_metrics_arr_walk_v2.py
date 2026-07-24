"""Tests de ARR Walk v2 (2026-07-22) — clasificación New/Churn/Reactivated/Recovered/
Upsell/Downsell a nivel de entidad (compañía, o compañía+segmento), metodología validada
en vivo contra el Excel real de Finance (ver memory/project_board_agent.md). Cubre
_classify_arr_walk_entities() y _months_between() de scripts/fetch_metrics.py.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_metrics as fm  # noqa: E402


def _rate_one(app_version, month):
    """Sin conversión FX — simplifica los tests que no necesitan verificar la revalorización."""
    return 1.0


def test_months_between_same_year():
    assert fm._months_between("2026-03", "2026-06") == 3


def test_months_between_year_rollover():
    assert fm._months_between("2025-11", "2026-02") == 3


def test_new_company_no_prior_history():
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 100.0}]
    history = {}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_new"] == 1
    assert out["usd_new"] == 100.0
    assert history["c1"] == {"last_month": "2026-06", "last_local_mrr": 100.0, "app_version": "colombia"}


def test_continuing_company_upsell():
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 150.0}]
    history = {"c1": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["usd_upsell"] == 50.0
    assert out["usd_downsell"] == 0.0
    assert out["logos_new"] == 0


def test_continuing_company_downsell():
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 80.0}]
    history = {"c1": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["usd_downsell"] == -20.0
    assert out["usd_upsell"] == 0.0


def test_continuing_company_flat_contributes_nothing():
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 100.0}]
    history = {"c1": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["usd_upsell"] == 0.0
    assert out["usd_downsell"] == 0.0


def test_reactivated_gap_of_two_months():
    """Tenía MRR en abril, nada en mayo (habría sido churn de mayo), vuelve en junio —
    exactamente el mes siguiente a churnear."""
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 120.0}]
    history = {"c1": {"last_month": "2026-04", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_reactivated"] == 1
    assert out["usd_reactivated"] == 120.0
    assert out["usd_upsell"] == 0.0  # no es upsell, es reactivación


def test_recovered_gap_of_three_or_more_months():
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 90.0}]
    history = {"c1": {"last_month": "2026-01", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_recovered"] == 1
    assert out["usd_recovered"] == 90.0


def test_rerun_same_month_is_a_noop_not_recovered():
    """Bug encontrado en vivo (2026-07-24): re-correr el mismo mes de corte ya persistido
    (gap == 0) caía en el branch 'else' (pensado para gap>=3) y contaba el MRR completo
    como Recovered. Debe ser un no-op — el mes ya está reflejado en el historial."""
    rows = [{"key": "c1", "app_version": "colombia", "local_mrr": 100.0}]
    history = {"c1": {"last_month": "2026-06", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_recovered"] == 0
    assert out["usd_recovered"] == 0.0
    assert out["logos_new"] == 0


def test_churn_derives_app_version_from_key_when_missing():
    """Bug encontrado en vivo (2026-07-24): ~2/3 de las entradas del bootstrap no tenían
    'app_version' guardado -> rate_lookup(None, ...) caía a 1.0 y dejaba MRR en moneda
    local (ej. COP) sin convertir a USD en el bucket de Churn. Debe derivarse de la key."""
    rows = []  # c1 churneó, no aparece este mes
    history = {"c1|colombia": {"last_month": "2026-05", "last_local_mrr": 400000.0}}  # sin app_version

    def _rate_4000(app_version, month):
        assert app_version == "colombia"  # se derivó de la key "c1|colombia" -- no de None
        return 4000.0

    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_4000)
    assert out["logos_churn"] == 1
    assert out["usd_churn"] == -100.0  # 400000/4000, no -400000 (que sería sin convertir)


def test_churn_detected_for_company_absent_this_month():
    rows = []  # c1 no aparece en el pull de este mes
    history = {"c1": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_churn"] == 1
    assert out["usd_churn"] == -100.0
    # el estado de la compañía churneada NO se toca — sigue apuntando a mayo, para que el
    # gap se siga midiendo bien si reaparece más adelante
    assert history["c1"]["last_month"] == "2026-05"


def test_churn_not_re_flagged_for_company_absent_longer_than_one_month():
    """Ya churneó el mes pasado (detectado en una corrida anterior) — no debe volver a
    contar como churn cada mes que sigue ausente."""
    rows = []
    history = {"c1": {"last_month": "2026-03", "last_local_mrr": 100.0, "app_version": "colombia"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _rate_one)
    assert out["logos_churn"] == 0


def test_rate_lookup_applied_to_current_month_not_historical():
    """Confirma que la clasificación usa la tasa del mes DE CORTE (rate_lookup), no una
    tasa histórica — la revalorización de FX depende de esto (ver docstring de
    _classify_arr_walk_entities)."""
    calls = []

    def _tracking_rate(app_version, month):
        calls.append((app_version, month))
        return 2.0

    rows = [{"key": "c1", "app_version": "mexico", "local_mrr": 200.0}]
    history = {"c1": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "mexico"}}
    out = fm._classify_arr_walk_entities(rows, history, "2026-06", _tracking_rate)
    # (200-100)/2.0 = 50 de upsell, no (200-100)=100 -- confirma que se dividió por la tasa
    assert out["usd_upsell"] == 50.0
    assert ("mexico", "2026-06") in calls


def test_bucket_row_shape_matches_existing_schema():
    bucket = {
        "logos_new": 2, "logos_recovered": 1, "logos_reactivated": 0, "logos_churn": 3,
        "usd_new": 500.0, "usd_recovered": 200.0, "usd_reactivated": 0.0, "usd_churn": -300.0,
        "usd_upsell": 150.0, "usd_downsell": -80.0,
    }
    row = fm._arr_walk_v2_bucket_row(bucket, "2026-06", "Core")
    assert row["m"] == "2026-06"
    assert row["seg"] == "Core"
    assert row["mrr_new_base_t0"] == 500.0
    assert row["mrr_new_cross_t0"] == 0.0
    assert row["mrr_churn"] == 300.0  # se guarda positivo (magnitud), igual que la convención vieja
    assert row["mrr_upsell"] == 150.0
    assert row["mrr_downsell"] == -80.0
    # cross-sell/pricing ya no existen como buckets separados en esta metodología
    assert row["mrr_pricing_others"] == 0.0
    assert row["mrr_cross_new_t1plus"] == 0.0
    assert row["mrr_cross_readop"] == 0.0
    assert row["mrr_cross_down"] == 0.0


def test_apply_arr_walk_v2_overrides_only_cutoff_month(monkeypatch, tmp_path):
    """Verifica el contrato completo: segs_raw/seg_metrics del mes de corte quedan
    sobreescritos con la nueva metodología, los meses históricos NO se tocan, y "all"
    (GLO) usa su propia clasificación a nivel de compañía (no la suma de Core+Lite)."""
    history_file = tmp_path / ".company_mrr_history.json"
    monkeypatch.setattr(fm, "COMPANY_MRR_HISTORY_FILE", history_file)
    monkeypatch.setattr(fm, "ARR_WALK_V2_HISTORY_FILE", tmp_path / "arr_walk_v2_monthly_history.json")
    monkeypatch.setattr(fm, "load_fx", lambda: {})

    # Compañía c1: tiene Core Y Lite a la vez, ambos continuando desde mayo con distinto
    # signo — a nivel de compañía combinada, su MRR total sube (upsell en GLO), aunque a
    # nivel Core baje (downsell) — exactamente el caso que justifica clasificar GLO aparte.
    company_mrr_v2_rows = [
        {"id_company": "1", "app_version": "colombia", "segment_type_def": "Core", "local_mrr": 80.0},
        {"id_company": "1", "app_version": "colombia", "segment_type_def": "Lite", "local_mrr": 100.0},
    ]
    history_file.write_text(fm.json.dumps({
        "as_of_month": "2026-05",
        "by_segment": {
            "1|Core|colombia": {"last_month": "2026-05", "last_local_mrr": 100.0, "app_version": "colombia"},
            "1|Lite|colombia": {"last_month": "2026-05", "last_local_mrr": 50.0, "app_version": "colombia"},
        },
        "by_company": {
            "1|colombia": {"last_month": "2026-05", "last_local_mrr": 150.0, "app_version": "colombia"},
        },
    }))

    segs_raw = {
        "Core": {"2026-05": {"m": "2026-05", "seg": "Core", "mrr_eop": 999}},
        "Lite": {"2026-05": {"m": "2026-05", "seg": "Lite", "mrr_eop": 999}},
        "all":  {"2026-05": {"m": "2026-05", "seg": "all",  "mrr_eop": 999}},
    }
    seg_metrics = {}
    all_months = ["2026-05", "2026-06"]

    fm._apply_arr_walk_v2(segs_raw, seg_metrics, all_months, "06", "2026-06", company_mrr_v2_rows)

    # Mes histórico intacto
    assert segs_raw["Core"]["2026-05"]["mrr_eop"] == 999

    # Core: 80 vs 100 -> downsell de 20
    assert segs_raw["Core"]["2026-06"]["mrr_downsell"] == -20.0
    # Lite: 100 vs 50 -> upsell de 50
    assert segs_raw["Lite"]["2026-06"]["mrr_upsell"] == 50.0
    # GLO: 180 vs 150 -> upsell de 30 (NO downsell de 20 + upsell de 50 sumados por separado)
    assert segs_raw["all"]["2026-06"]["mrr_upsell"] == 30.0
    assert segs_raw["all"]["2026-06"]["mrr_downsell"] == 0.0

    # Estado persistido actualizado
    saved = fm.json.loads(history_file.read_text())
    assert saved["by_company"]["1|colombia"]["last_local_mrr"] == 180.0
    assert saved["as_of_month"] == "2026-06"

    # El mes de corte queda agregado al store histórico permanente (2026-07-24) — así
    # julio en adelante no necesita volver a tocar Redshift para ver junio como histórico.
    arr_walk_history = fm._load_arr_walk_v2_history()
    assert arr_walk_history["months"]["2026-06"]["all"]["mrr_upsell"] == 30.0


def test_apply_arr_walk_v2_is_noop_when_month_already_processed(monkeypatch, tmp_path):
    """Bug real encontrado en vivo (2026-07-24): re-correr un mes ya reflejado en
    `as_of_month` no debe tocar nada -- ni segs_raw, ni el estado rodante, ni el store
    histórico permanente. Antes de este fix, el gap<=0 (no-op de clasificación) igual se
    agregaba al store histórico, pisando con ceros un valor real ya calculado (ej. por un
    backfill) para ese mismo mes."""
    history_file = tmp_path / ".company_mrr_history.json"
    arr_walk_history_file = tmp_path / "arr_walk_v2_monthly_history.json"
    monkeypatch.setattr(fm, "COMPANY_MRR_HISTORY_FILE", history_file)
    monkeypatch.setattr(fm, "ARR_WALK_V2_HISTORY_FILE", arr_walk_history_file)
    monkeypatch.setattr(fm, "load_fx", lambda: {})

    history_file.write_text(fm.json.dumps({
        "as_of_month": "2026-06",  # ya procesado
        "by_segment": {"1|Core|colombia": {"last_month": "2026-06", "last_local_mrr": 100.0, "app_version": "colombia"}},
        "by_company": {"1|colombia": {"last_month": "2026-06", "last_local_mrr": 100.0, "app_version": "colombia"}},
    }))
    # El store histórico ya tiene un valor real para junio (ej. de un backfill) -- no debe
    # pisarse con el resultado (en cero) de re-clasificar un mes con gap<=0.
    arr_walk_history_file.write_text(fm.json.dumps({
        "months": {"2026-06": {"all": {"mrr_upsell": 12345.0}}},
    }))

    segs_raw = {"Core": {"2026-06": {"m": "2026-06", "seg": "Core", "mrr_eop": 999}},
                "Lite": {}, "all": {"2026-06": {"m": "2026-06", "seg": "all", "mrr_eop": 999}}}
    seg_metrics = {}
    company_mrr_v2_rows = [
        {"id_company": "1", "app_version": "colombia", "segment_type_def": "Core", "local_mrr": 100.0},
    ]

    fm._apply_arr_walk_v2(segs_raw, seg_metrics, ["2026-06"], "06", "2026-06", company_mrr_v2_rows)

    # segs_raw no se tocó (seguiría teniendo solo m/seg/mrr_eop, sin buckets de flujo)
    assert "mrr_upsell" not in segs_raw["all"]["2026-06"]
    # el store histórico permanente sigue con el valor real, no se pisó con ceros
    saved_history = fm.json.loads(arr_walk_history_file.read_text())
    assert saved_history["months"]["2026-06"]["all"]["mrr_upsell"] == 12345.0
    # el estado rodante tampoco se tocó
    saved_state = fm.json.loads(history_file.read_text())
    assert saved_state["by_company"]["1|colombia"]["last_local_mrr"] == 100.0


def test_historical_overrides_replace_flow_but_not_stock(monkeypatch, tmp_path):
    """_apply_arr_walk_v2_historical_overrides() debe sobreescribir los buckets de flujo
    de un mes ya presente en el store permanente, sin tocar los campos de stock
    (mrr_eop/mrr_eop_cc/logos_eop), y dejar intacto cualquier mes ausente del store."""
    history_file = tmp_path / "arr_walk_v2_monthly_history.json"
    monkeypatch.setattr(fm, "ARR_WALK_V2_HISTORY_FILE", history_file)
    history_file.write_text(fm.json.dumps({
        "months": {
            "2025-01": {"all": {"mrr_upsell": 500.0, "mrr_downsell": 0.0, "logos_new": 3}},
        }
    }))

    segs_raw = {
        "all": {
            "2025-01": {"m": "2025-01", "seg": "all", "mrr_eop": 999.0, "mrr_upsell": 111.0},
            "2025-02": {"m": "2025-02", "seg": "all", "mrr_eop": 888.0, "mrr_upsell": 222.0},
        }
    }
    fm._apply_arr_walk_v2_historical_overrides(segs_raw)

    # Mes presente en el store -> flujo sobreescrito, stock intacto
    assert segs_raw["all"]["2025-01"]["mrr_upsell"] == 500.0
    assert segs_raw["all"]["2025-01"]["logos_new"] == 3
    assert segs_raw["all"]["2025-01"]["mrr_eop"] == 999.0

    # Mes ausente del store -> ni se toca
    assert segs_raw["all"]["2025-02"]["mrr_upsell"] == 222.0
    assert segs_raw["all"]["2025-02"]["mrr_eop"] == 888.0


def test_historical_overrides_noop_when_store_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "ARR_WALK_V2_HISTORY_FILE", tmp_path / "does_not_exist.json")
    segs_raw = {"all": {"2025-01": {"m": "2025-01", "seg": "all", "mrr_upsell": 111.0}}}
    fm._apply_arr_walk_v2_historical_overrides(segs_raw)
    assert segs_raw["all"]["2025-01"]["mrr_upsell"] == 111.0
