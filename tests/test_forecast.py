"""Forecasting failures from the same tables: credential expiry, deprecation, duration and cost trends."""

import pandas as pd
import pytest

from pipeline_doctor import doctor
from pipeline_doctor import forecast as fc

TODAY = "2026-10-29"


@pytest.fixture
def config():
    cfg = doctor.load_config()
    cfg["max_duration_seconds"] = 1800.0
    cfg["budget_usd"] = 5.0
    return cfg


@pytest.fixture
def register(tmp_path):
    p = tmp_path / "secrets_register.yaml"
    p.write_text("""credentials:
  - name: ci-secret
    expires: 2026-11-03
    owner: repo owner
    used_by: .github/workflows/deploy.yml (medgemma_reader, encoder_gpu)
    if_it_expires: deploys fail at sign-in
  - name: pat
    expires: 2026-11-20
    owner: repo owner
    used_by: judge_scorecard
    if_it_expires: the agent cannot read run outputs
  - name: hf token
    expires: unknown
    owner: repo owner
    used_by: medgemma_reader
    if_it_expires: model downloads fail
  - name: far away
    expires: 2027-06-01
    owner: repo owner
    used_by: nhanes_perio
    if_it_expires: nothing soon
  - name: expired
    expires: 2026-10-01
    owner: repo owner
    used_by: load_results
    if_it_expires: load fails
""")
    return fc.load_credential_register(p)


def test_register_loads_names_and_expiry_but_never_values(register):
    assert set(register["credential_name"]) == {"ci-secret", "pat", "hf token", "far away", "expired"}
    assert "value" not in " ".join(register.columns)


def test_credential_forecast_uses_the_days_ladder_and_names_the_pipelines(register, config):
    f = fc.credential_forecast(register, config, TODAY).set_index(["subject_name", "pipeline_name"])
    assert f.loc[("ci-secret", "medgemma_reader"), "severity_code"] == "SEV2"      # 5 days
    assert f.loc[("ci-secret", "encoder_gpu"), "days_until_count"] == 5
    assert f.loc[("pat", "judge_scorecard"), "severity_code"] == "SEV3"           # 22 days
    assert f.loc[("expired", "load_results"), "severity_code"] == "SEV1"          # already past
    assert ("far away", "nhanes_perio") not in f.index                              # beyond 90 days
    unknown = f.loc[("hf token", "medgemma_reader")]
    assert unknown["severity_code"] == "SEV4" and "unknown" in unknown["evidence_text"]
    assert (f["predicted_failure_class_code"] == "credential_expiry").all()
    assert (f["recommended_action_code"] == "fix_setting").all()


def test_deprecation_forecast_from_an_inventory(config):
    inv = pd.DataFrame([
        {"dependency_name": "medgemma-4b-it v1", "dependency_kind_code": "model", "end_of_support_date": "2026-12-15",
         "used_by_text": "medgemma_reader", "owner_name": "repo owner"},
        {"dependency_name": "pandas 2.2", "dependency_kind_code": "package", "end_of_support_date": "",
         "used_by_text": "all", "owner_name": "repo owner"},
    ])
    f = fc.deprecation_forecast(inv, config, TODAY)
    assert len(f) == 1
    row = f.iloc[0]
    assert row["predicted_failure_class_code"] == "deprecation" and row["pipeline_name"] == "medgemma_reader"
    assert row["severity_code"] == "SEV4" and row["days_until_count"] == 47


def _runs(pipeline, durations, costs, start="2026-10-01"):
    t0 = pd.Timestamp(start, tz="UTC")
    return pd.DataFrame([{"pipeline_name": pipeline, "run_status_code": "ok", "ended_ts": t0 + pd.Timedelta(days=i),
                          "duration_seconds": d, "cost_usd": c} for i, (d, c) in enumerate(zip(durations, costs))])


def test_trend_forecast_predicts_the_date_a_rising_cost_crosses_the_budget(config):
    h = _runs("judge_scorecard", [600] * 6, [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])   # +0.5 USD per daily run
    f = fc.trend_forecast(h, config, TODAY)
    cost = f[f["predicted_failure_class_code"] == "cost_anomaly"].iloc[0]
    assert cost["days_until_count"] == 3                        # (5.0 - 3.5) / 0.5 = 3 runs, one per day
    assert cost["severity_code"] == "SEV2" and "slope +0.5" in cost["evidence_text"]
    assert "source_late" not in set(f["predicted_failure_class_code"])   # duration is flat


def test_trend_forecast_is_quiet_when_nothing_is_rising(config):
    h = _runs("judge_scorecard", [600] * 6, [1.0] * 6)
    assert fc.trend_forecast(h, config, TODAY).empty


def test_forecast_combines_and_sorts_soonest_first(register, config):
    h = _runs("judge_scorecard", [600] * 6, [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
    f = fc.forecast_all(config, TODAY, register=register, history=h)
    assert list(f.columns) == fc.FORECAST_COLUMNS
    assert f.iloc[0]["subject_name"] == "expired"               # negative days first
    days = f["days_until_count"].dropna().tolist()
    assert days == sorted(days)


def test_a_dependency_marked_deprecated_without_a_date_is_a_sev3(config):
    inv = pd.DataFrame([{"dependency_name": "old endpoint", "dependency_kind_code": "endpoint", "end_of_support_date": "",
                         "support_status_code": "deprecated", "used_by_text": "llm_judge", "owner_name": "repo owner"}])
    f = fc.deprecation_forecast(inv, config, TODAY)
    assert len(f) == 1 and f.iloc[0]["severity_code"] == "SEV3" and f.iloc[0]["pipeline_name"] == "llm_judge"


def _vol(pipeline, counts, start="2026-10-01"):
    t0 = pd.Timestamp(start, tz="UTC")
    return pd.DataFrame([{"pipeline_name": pipeline, "run_status_code": "ok", "ended_ts": t0 + pd.Timedelta(days=i),
                          "row_out_count": c, "schema_sha256": "abc"} for i, c in enumerate(counts)])


def test_volume_forecast_sees_a_shrinking_feed_before_it_crosses_the_bound(config):
    h = _vol("load_results", [240, 240, 240, 240, 200, 180, 160, 140])   # heading for 120 (0.5 × 240)
    f = fc.volume_forecast(h, config, TODAY)
    assert len(f) == 1
    row = f.iloc[0]
    assert row["predicted_failure_class_code"] == "volume_anomaly" and row["days_until_count"] <= 2
    assert row["severity_code"] == "SEV2"


def test_volume_forecast_is_quiet_for_a_steady_feed(config):
    assert fc.volume_forecast(_vol("load_results", [240] * 8), config, TODAY).empty


def test_schema_change_forecast_flags_a_source_that_keeps_changing(config):
    h = _vol("load_results", [240] * 6)
    h["schema_sha256"] = ["a", "a", "b", "b", "c", "c"]
    f = fc.schema_change_forecast(h, config, TODAY)
    assert len(f) == 1 and f.iloc[0]["predicted_failure_class_code"] == "schema_drift"
    assert f.iloc[0]["severity_code"] == "SEV4" and "2 times" in f.iloc[0]["evidence_text"]
    h["schema_sha256"] = ["a", "a", "a", "a", "b", "b"]
    assert fc.schema_change_forecast(h, config, TODAY).empty          # one change is a change, not drift
