"""Routing and batching alerts: now / daily / weekly, one problem once with a count, repeats flagged."""

import pandas as pd

from pipeline_doctor import digest as dg


def _alert(subject, sev, cls="credential_expiry", pipeline=None, days=5, owner="repo owner", kind="credential",
           date="2026-11-03", action="fix_setting"):
    return {"subject_name": subject, "subject_kind_code": kind, "pipeline_name": pipeline,
            "predicted_failure_class_code": cls, "predicted_date": date, "days_until_count": days,
            "severity_code": sev, "recommended_action_code": action, "owner_name": owner,
            "evidence_text": f"{subject} evidence"}


def test_route_follows_the_severity_ladder():
    a = pd.DataFrame([_alert("a", "SEV1"), _alert("b", "SEV2"), _alert("c", "SEV3"), _alert("d", "SEV4"),
                      _alert("e", "SEV9")])
    r = dg.route(a).set_index("subject_name")["route_code"]
    assert r.to_dict() == {"a": "now", "b": "now", "c": "daily", "d": "weekly", "e": "weekly"}


def test_dedupe_keeps_one_row_per_problem_with_a_count_and_the_pipelines():
    a = pd.DataFrame([_alert("ci-secret", "SEV2", pipeline="medgemma_reader"),
                      _alert("ci-secret", "SEV2", pipeline="encoder_gpu"),
                      _alert("ci-secret", "SEV3", pipeline="load_results", days=20)])
    d = dg.dedupe(a)
    assert len(d) == 1
    row = d.iloc[0]
    assert row["alert_count"] == 3 and row["severity_code"] == "SEV2"
    assert row["pipeline_names_text"] == "encoder_gpu, load_results, medgemma_reader"


def test_daily_digest_holds_sev3_only_and_carries_open_items_as_repeats():
    today = pd.DataFrame([_alert("pat", "SEV3", days=20), _alert("x", "SEV4", days=60), _alert("y", "SEV2")])
    earlier = pd.DataFrame([_alert("old", "SEV3", days=10), _alert("pat", "SEV3", days=21)])
    d = dg.digest(today, "daily", open_since=earlier)
    assert set(d["subject_name"]) == {"pat", "old"}
    assert bool(d.set_index("subject_name").loc["old", "is_repeat"]) is True
    assert bool(d.set_index("subject_name").loc["pat", "is_repeat"]) is False   # present today: not a carry-over


def test_a_repeating_sev2_is_flagged_for_level_review():
    """A SEV2 goes out now; one still open at the next digest is carried in, flagged: fix the cause or lower
    the level (AGENTS-common.md, Alerts and severity)."""
    now = dg.immediate(pd.DataFrame([_alert("flaky", "SEV2", cls="platform")]))
    assert len(now) == 1 and now.iloc[0]["severity_code"] == "SEV2"
    earlier = pd.DataFrame([_alert("flaky", "SEV2", cls="platform")])
    d = dg.digest(pd.DataFrame(columns=dg.ALERT_COLUMNS), "daily", open_since=earlier)
    assert len(d) == 1 and bool(d.iloc[0]["is_repeat"]) and bool(d.iloc[0]["is_level_review"])
    assert "fix the cause or lower the level" in dg.render(d, "daily")["repo owner"]


def test_render_groups_by_owner_severity_and_kind():
    a = pd.DataFrame([_alert("pat", "SEV3", days=13, date="2026-11-11"),
                      _alert("medgemma v1", "SEV4", cls="deprecation", kind="model", days=47, date="2026-12-15",
                             action="hold_downstream", pipeline="medgemma_reader"),
                      _alert("other", "SEV4", owner="someone else", days=80, date="2027-01-17")])
    text = dg.render(dg.digest(a, "weekly"), "weekly")
    assert set(text) == {"repo owner", "someone else"}
    mine = text["repo owner"]
    assert "weekly digest for repo owner: 1 open item(s)" in mine        # pat is SEV3 → daily, not weekly
    assert "model" in mine and "medgemma v1 [medgemma_reader]: deprecation by 2026-12-15 → hold_downstream" in mine
