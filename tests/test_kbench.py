"""PipelineDoctorBench (pipeline_doctor.kbench): incident triage as a Kaggle Benchmarks task, run here on
scripted models and on the rules themselves. No credentials, no network."""

import importlib.util
import json

import pandas as pd
import pytest

pytest.importorskip("kaggle_benchmarks")

from pipeline_doctor import doctor, kbench

REPO = doctor.EXAMPLES.parents[1]
TASK_FILE = REPO / "kaggle" / "pipeline_doctor_task.py"


@pytest.fixture(autouse=True)
def run_files_in_tmp(tmp_path, monkeypatch):
    """The SDK writes a `*.run.json` per run into the working directory and reuses any it finds there
    under `enable_cache()`: keep each test's files in its own folder and out of the repo."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def df():
    return kbench.eval_frame()


@pytest.fixture(scope="module")
def full(df):
    return df[df["condition"] == "full"].reset_index(drop=True)


# ---------------------------------------------------------------- data and context
def test_eval_frame_is_every_incident_under_every_condition(df):
    n_inc = len(doctor.load_incidents())
    assert len(df) == n_inc * len(doctor.ABLATIONS) and list(df["condition"].unique()) == list(doctor.ABLATIONS)
    assert {"incident_id", "run_id", "failure_class_code", "decided_action_code", "recorded_in_text"} <= set(df)


def test_context_shows_the_four_tables_rows_for_the_incident(full):
    config, runbook, lineage, history = kbench._tables()
    inc = full.iloc[0].to_dict()
    ctx = kbench.context_for(inc, "full", config, runbook, lineage, history)
    assert ctx["run"]["run_id"] == inc["run_id"] and ctx["run"]["error_type_name"] == inc["error_type_name"]
    assert len(ctx["trailing_ok_runs"]) == doctor.TRAILING_RUNS
    assert ctx["pipeline"]["pipeline_name"] == inc["pipeline_name"]
    assert {r["failure_class_code"] for r in ctx["runbook"]} == set(runbook["failure_class_code"])
    assert "failure_class_code" not in ctx["run"] and "recorded_in_text" not in json.dumps(ctx)   # no answer leaks


@pytest.mark.parametrize("condition, gone", [
    ("no_conventions", lambda ctx: ctx["run"]["error_type_name"] is None and ctx["run"]["cost_usd"] is None),
    ("no_history", lambda ctx: ctx["trailing_ok_runs"] == []),
    ("no_lineage", lambda ctx: ctx["lineage"] == []),
    ("no_metrics", lambda ctx: ctx["run"]["duration_seconds"] is None),
    ("no_config", lambda ctx: ctx["pipeline"]["sla_seconds"] is None),
])
def test_each_condition_switches_one_convention_off(full, condition, gone):
    config, runbook, lineage, history = kbench._tables()
    inc = full.iloc[0].to_dict()
    assert gone(kbench.context_for(inc, condition, config, runbook, lineage, history))
    with pytest.raises(ValueError):
        kbench.context_for(inc, "no_such_condition", config, runbook, lineage, history)


# ---------------------------------------------------------------- one incident
def test_triage_one_passes_the_owner_decision(full):
    r = full.iloc[0].to_dict()
    reader = kbench.ScriptedReader(kbench.answer_key_script(full))
    run = kbench.triage_one.run(reader, **r)
    assert run.passed and run.result["is_class_ok"] and run.result["is_action_ok"] and run.result["is_parsed"]
    assert [a.passed for a in run.assertion_results] == [True, True, True]
    assert "verdict_code" not in run.result                                  # no judge given


def test_triage_one_fails_an_action_off_the_runbook_list(full):
    r = full.iloc[0].to_dict()
    answer = json.dumps({"failure_class_code": r["failure_class_code"], "action_code": "reboot_everything",
                         "root_cause_text": "x"})
    run = kbench.triage_one.run(kbench.ScriptedReader(lambda _: answer), **r)
    assert run.result["is_class_ok"] and not run.result["is_action_on_list"] and not run.passed


def test_triage_one_records_an_unparseable_answer_instead_of_raising(full):
    run = kbench.triage_one.run(kbench.ScriptedReader(lambda _: "no idea"), **full.iloc[0].to_dict())
    assert not run.result["is_parsed"] and run.result["error_text"].startswith("parse:")
    assert run.result["predicted_class_code"] is None


def test_triage_one_with_a_judge_checks_the_root_cause(full):
    r = full.iloc[0].to_dict()
    judge = kbench.ScriptedReader(kbench.judge_script(), name="sim:scripted-judge")
    run = kbench.triage_one.run(kbench.ScriptedReader(kbench.answer_key_script(full)), judge_llm=judge, **r)
    assert run.result["verdict_code"] == "agrees" and run.result["is_root_cause_ok"]
    assert r["recorded_in_text"] in judge.prompts[0]


# ---------------------------------------------------------------- the rules as a model
def test_rules_reader_matches_doctor_evaluate_under_every_condition(df):
    """The deterministic rung on the leaderboard says what `doctor.ablation` says: same class accuracy per
    condition, since both see the same switched-off rows."""
    out = kbench.pipeline_doctor_triage.run(kbench.RulesReader(), df, n_jobs=1).result
    config, runbook, lineage, history = kbench._tables()
    ab = doctor.ablation(doctor.load_incidents(), config, runbook, lineage, history).set_index("condition_name")
    for cond in doctor.ABLATIONS:
        got = out["by_condition"][cond]
        assert got["class_ok_ratio"] == pytest.approx(ab.loc[cond, "class_accuracy_ratio"]), cond
        assert got["action_ok_ratio"] == pytest.approx(ab.loc[cond, "action_agreement_ratio"]), cond
    assert out["reader_name"] == "rules:doctor" and not out["is_simulated"]


# ---------------------------------------------------------------- the whole task
def test_pipeline_doctor_triage_scores_every_condition(df):
    reader = kbench.ScriptedReader(kbench.answer_key_script(df, wrong_every=3))
    out = kbench.pipeline_doctor_triage.run(reader, df, n_jobs=1).result
    assert out["n"] == len(df) and out["errored_count"] == 0 and 0 < out["class_ok_ratio"] < 1
    assert out["is_simulated"] and set(out["by_condition"]) == set(doctor.ABLATIONS)
    assert out["action_ok_ratio"] == 1.0                                     # the script copies the action
    single = kbench.pipeline_doctor_class_accuracy.run(reader, df).result
    assert single == pytest.approx(out["class_ok_ratio"])


def test_score_rows_leaves_an_empty_share_blank():
    rows = pd.DataFrame({"condition": ["full"], "is_class_ok": [True], "is_action_ok": [False],
                         "is_action_on_list": [True], "is_parsed": [True]})
    out = kbench.score_rows(rows)
    assert out["class_ok_ratio"] == 1.0 and out["action_ok_ratio"] == 0.0 and "root_cause_ok_ratio" not in out
    assert out["by_condition"]["full"]["class_ok_ratio"] == 1.0


# ---------------------------------------------------------------- the task file Kaggle runs
def test_task_file_follows_the_sdk_rules():
    text = TASK_FILE.read_text()
    assert text.startswith("# %%") and "import kaggle_benchmarks as kbench" in text
    assert "pipeline_doctor_triage.run(" in text and "SIMULATED" in text


def test_task_file_dry_runs_on_a_scripted_model(capsys):
    spec = importlib.util.spec_from_file_location("pipeline_doctor_task", TASK_FILE)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "by_condition" in out
