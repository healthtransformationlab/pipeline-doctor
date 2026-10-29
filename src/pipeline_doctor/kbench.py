"""PipelineDoctorBench: incident triage as a Kaggle Benchmarks task (`import kaggle_benchmarks as kbench`).

The model under test is the triage agent. It gets what the doctor gets, the four tables' rows for one
failed run (the run row, the pipeline's trailing ok runs, its config row, lineage one hop, the runbook),
and must answer with JSON: the failure class, the first allowed runbook action, and the root cause in a
sentence. Scored against what the owner actually decided (`incident.csv`): class exact, action exact and
on the runbook's list, root cause by a judge model against the owner's own note.

The thesis this measures: conventions do the thinking a small model is too small to do. So the task
takes a `condition` from `doctor.ABLATIONS`: `full`, or one convention switched off (`no_conventions`
hides the typed signal columns, `no_history` the trailing runs, `no_lineage` the edges, `no_metrics`
duration and cost, `no_config` the SLA and retry policy). Run every model under every condition and the
leaderboard shows, per model size, what each convention buys. The rules are a model too
(`RulesReader`), so the deterministic rung has its own row.

Install with `pip install -e ".[kbench]"`. The SDK imports without credentials; tests run on scripted
models. Simulated readers are named `sim:` and results carry `is_simulated` (never a number to report).
"""

# No `from __future__ import annotations`: the SDK reads each task's real return annotation to pick how
# the leaderboard scores it.
import functools
import json
from collections.abc import Callable

import kaggle_benchmarks as kbench
import pandas as pd
import pydantic
from kaggle_benchmarks import actors
from kaggle_benchmarks.llm_messages import LLMMessage

from . import doctor
from ._tracing import traced

CONDITIONS = tuple(doctor.ABLATIONS)
TASK_VERSION = 1
ANSWER = """Answer with JSON only:
{"failure_class_code": one of the runbook's failure classes,
 "action_code": the first allowed action for that class, from the runbook entry,
 "root_cause_text": "one sentence naming what failed and why, from the rows above"}"""


class Triage(pydantic.BaseModel):
    """The agent's answer."""

    failure_class_code: str
    action_code: str
    root_cause_text: str = ""


class RootCauseVerdict(pydantic.BaseModel):
    """The judge's answer: does the agent's root cause say what the owner's note says?"""

    verdict: str  # agrees | disagrees | not_determinable
    rationale: str = ""


# ---------------------------------------------------------------- context (what the agent sees)
def _records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.loads(out.to_json(orient="records", date_format="iso"))


@traced
def context_for(incident: dict, condition: str, config: pd.DataFrame, runbook: pd.DataFrame,
                lineage: pd.DataFrame, history: pd.DataFrame) -> dict:
    """The rows the agent is shown for one incident, with the condition's convention switched off the same
    way `doctor.ablation` does it, so the agent and the rules see the same thing."""
    if condition not in doctor.ABLATIONS:
        raise ValueError(f"condition must be one of {list(doctor.ABLATIONS)}, got {condition!r}")
    inc = pd.DataFrame([{c: incident.get(c) for c in doctor.RUN_COLUMNS}])
    inc, cfg, lin, hist = doctor._ablate(condition, inc, config, lineage, history)
    name = incident["pipeline_name"]
    return {
        "run": _records(inc)[0],
        "trailing_ok_runs": _records(hist[hist["pipeline_name"] == name]),
        "pipeline": (_records(cfg[cfg["pipeline_name"] == name]) or [{}])[0],
        "lineage": _records(lin[lin["pipeline_name"] == name]) if "pipeline_name" in lin else [],
        "runbook": _records(runbook[["failure_class_code", "description_text", "allowed_action_codes",
                                     "severity_code"]]),
    }


@traced
def triage_prompt(ctx: dict) -> str:
    """The single string `llm.prompt()` takes: the rows, then the answer format."""
    return ("You are on call for a data platform. One run failed. Below are the rows the platform keeps about "
            "it: the failed run, the pipeline's last ok runs, its configuration, what reads its output, and the "
            "runbook (one entry per failure class, actions in the order they are tried). Classify the failure, "
            "pick the first allowed action for that class, and say the root cause.\n\n"
            + json.dumps(ctx, indent=1, default=str) + "\n\n" + ANSWER)


@traced
def judge_prompt(criteria, response_text: str) -> str:
    """`prompt_fn` for `assess_response_with_judge`: `criteria` carries the owner's note (one item),
    `response_text` the agent's root cause."""
    (recorded,) = tuple(criteria)
    return ("You audit an on-call agent. The pipeline owner recorded this root cause and fix:\n"
            f"<<<\n{recorded}\n>>>\n\nThe agent said:\n<<<\n{response_text}\n>>>\n\n"
            "Does the agent's sentence name the same failure as the owner's note? Answer with JSON only:\n"
            '{"verdict": "agrees" | "disagrees" | "not_determinable", "rationale": "one sentence"}')


def _context_from_prompt(prompt_text: str) -> dict:
    """The context JSON back out of a triage prompt (for readers that answer from it)."""
    end = prompt_text.rindex("}", 0, prompt_text.index(ANSWER)) + 1
    return json.loads(prompt_text[prompt_text.index("{"): end])


# ---------------------------------------------------------------- data
@functools.lru_cache(maxsize=1)
def _tables() -> tuple:
    """The four tables, loaded once: config, runbook, lineage, and the simulated trailing ok runs."""
    config = doctor.load_config()
    return config, doctor.load_runbook(), doctor.load_lineage(), doctor.baseline_history(config)


@traced
def eval_frame(incidents_path=doctor.INCIDENT_CSV, conditions=CONDITIONS) -> pd.DataFrame:
    """One row per incident and condition: the columns become the task's keyword arguments."""
    inc = doctor.load_incidents(incidents_path)
    keep = ["incident_id", *doctor.RUN_COLUMNS, "failure_class_code", "decided_action_code", "recorded_in_text"]
    rows = [{"condition": cond, **r} for cond in conditions for r in _records(inc[keep])]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- tasks
@kbench.task(name="pipeline-doctor-triage-one", version=TASK_VERSION, store_task=False)
@traced
def triage_one(llm, condition: str, incident_id: str, failure_class_code: str, decided_action_code: str,
               recorded_in_text: str, judge_llm=None, **run_columns) -> dict:
    """Triage one failed run under one condition. Exact: class and action against the owner's decision,
    action on the runbook's list for the class the agent named. Judge: root cause against the owner's note."""
    config, runbook, lineage, history = _tables()
    incident = {"incident_id": incident_id, **run_columns}
    ctx = context_for(incident, condition, config, runbook, lineage, history)
    raw = llm.prompt(triage_prompt(ctx))
    out = _parse(raw)
    allowed = {r["failure_class_code"]: list(r["allowed_action_codes"]) for _, r in runbook.iterrows()}
    on_list = out["action_code"] in allowed.get(out["failure_class_code"], [])
    kbench.assertions.assert_equal(failure_class_code, out["failure_class_code"],
                                   expectation="failure class should match the owner's decision")
    kbench.assertions.assert_true(on_list, expectation="action should be on the runbook's list for that class")
    kbench.assertions.assert_equal(decided_action_code, out["action_code"],
                                   expectation="action should match the one the owner took")
    row = {
        "incident_id": incident_id, "condition": condition,
        "truth_class_code": failure_class_code, "predicted_class_code": out["failure_class_code"],
        "truth_action_code": decided_action_code, "predicted_action_code": out["action_code"],
        "is_class_ok": out["failure_class_code"] == failure_class_code,
        "is_action_on_list": on_list,
        "is_action_ok": out["action_code"] == decided_action_code,
        "is_parsed": out["is_parsed"],
        "error_text": out["error_text"],
    }
    if judge_llm is not None and out["root_cause_text"]:
        report = kbench.assertions.assess_response_with_judge(
            criteria=[recorded_in_text], response_text=out["root_cause_text"], judge_llm=judge_llm,
            prompt_fn=judge_prompt, output_schema=RootCauseVerdict)
        verdict = report.verdict if report is not None else "no_judge_answer"
        kbench.assertions.assert_equal("agrees", verdict, expectation="root cause should agree with the owner's note")
        row |= {"verdict_code": verdict, "is_root_cause_ok": verdict == "agrees"}
    return row


def _parse(raw) -> dict:
    out = {"failure_class_code": None, "action_code": None, "root_cause_text": "", "is_parsed": False,
           "error_text": ""}
    text = raw if isinstance(raw, str) else json.dumps(raw)
    try:
        d = json.loads(text[text.index("{"): text.rindex("}") + 1])
        t = Triage(**d)
    except (ValueError, pydantic.ValidationError) as e:
        out["error_text"] = f"parse: {type(e).__name__}"
        return out
    return out | t.model_dump() | {"is_parsed": True}


@traced
def score_rows(rows: pd.DataFrame) -> dict:
    """Per-condition and overall shares, the same columns as `doctor.evaluate` so the two agree:
    `class_ok_ratio`, `action_ok_ratio`, `action_on_list_ratio`, and `root_cause_ok_ratio` with a judge."""
    def share(df, col):
        return float(df[col].mean()) if col in df and len(df) else None

    names = {"is_class_ok": "class_ok_ratio", "is_action_ok": "action_ok_ratio",
             "is_action_on_list": "action_on_list_ratio", "is_parsed": "parsed_ratio",
             "is_root_cause_ok": "root_cause_ok_ratio"}

    def shares(df):
        return {name: share(df, col) for col, name in names.items() if col in df}

    out = shares(rows) | {"n": len(rows)}
    out["by_condition"] = {cond: shares(g) for cond, g in rows.groupby("condition", sort=False)}
    return out


@kbench.task(name="pipeline-doctor-triage", version=TASK_VERSION)
@traced
def pipeline_doctor_triage(llm, df: pd.DataFrame, judge_llm=None, n_jobs: int = 2, timeout: float = 180) -> dict:
    """PipelineDoctorBench: every incident under every condition, scored as `doctor.evaluate` scores the
    rules. The `by_condition` block is the switch-off test: what each convention buys this model."""
    with kbench.client.enable_cache():
        runs = triage_one.evaluate(
            llm=[llm], judge_llm=[judge_llm], evaluation_data=df, n_jobs=n_jobs, timeout=timeout,
            on_failure="continue", max_attempts=2, retry_delay=5)
    rows = pd.DataFrame(list(runs.completed_runs.as_dataframe()["result"]))
    out = score_rows(rows)
    out["errored_count"] = len(runs.errored_runs)
    out["reader_name"] = getattr(llm, "name", "")
    out["is_simulated"] = bool(getattr(llm, "is_simulated", False))
    return out


@kbench.task(name="pipeline-doctor-class-accuracy", version=TASK_VERSION)
@traced
def pipeline_doctor_class_accuracy(llm, df: pd.DataFrame) -> float:
    """The one number for a leaderboard that scores one value: the share of failures classed as the
    owner classed them, over every condition."""
    return float(pipeline_doctor_triage(llm, df)["class_ok_ratio"] or 0.0)


# ---------------------------------------------------------------- readers for tests, dry runs and the rules rung
class ScriptedReader(actors.LLMChat):
    """A stand-in model: answers come from `script(prompt_text)`. Named `sim:` and flagged `is_simulated`."""

    is_simulated = True

    def __init__(self, script: Callable[[str], str], name: str = "sim:scripted-reader", **kw):
        super().__init__(name=name, **kw)
        self.script, self.prompts = script, []

    @traced
    def invoke(self, messages, tools=None, **kwargs):
        text = "\n".join(str(getattr(m, "content", m)) for m in messages)
        self.prompts.append(text)
        return LLMMessage(sender=self, content=self.script(text))


class RulesReader(ScriptedReader):
    """The doctor's own rules as a model: the deterministic rung's row on the leaderboard. It reads the
    same context the LLM reads (so the switched-off condition applies to it too) and answers with
    `doctor.classify` and `doctor.recommend`. Not simulated: it is the rules, named `rules:doctor`."""

    is_simulated = False

    def __init__(self, config=None, runbook=None, lineage=None, **kw):
        self.config = doctor.load_config() if config is None else config
        self.runbook = doctor.load_runbook() if runbook is None else runbook
        self.lineage = doctor.load_lineage() if lineage is None else lineage
        super().__init__(self._answer, name=kw.pop("name", "rules:doctor"), **kw)

    @traced
    def _answer(self, prompt_text: str) -> str:
        ctx = _context_from_prompt(prompt_text)
        history = pd.DataFrame(ctx["trailing_ok_runs"])
        for c in ("started_ts", "ended_ts"):
            if c in history:
                history[c] = pd.to_datetime(history[c], utc=True)
        cfg = self.config
        if ctx["pipeline"] and pd.isna(ctx["pipeline"].get("sla_seconds", 0)):   # no_config
            cfg = cfg.assign(sla_seconds=float("nan"), retry_max_count=0)
        lineage = pd.DataFrame(ctx["lineage"]) if ctx["lineage"] else self.lineage.iloc[0:0]
        cls = doctor.classify(ctx["run"], history, cfg)
        rec = doctor.recommend(ctx["run"], history, cfg, self.runbook, lineage,
                               failure_class_code=cls["failure_class_code"])
        return json.dumps({"failure_class_code": cls["failure_class_code"],
                           "action_code": rec["recommended_action_code"],
                           "root_cause_text": f"rule {cls['rule_name']} fired on the run row"})


@traced
def answer_key_script(df: pd.DataFrame, wrong_every: int = 0) -> Callable[[str], str]:
    """A script that answers from the owner's decisions (every `wrong_every`-th incident one class off),
    for dry runs of the whole task without a model."""
    classes = sorted(df["failure_class_code"].unique())
    by_run = {r.run_id: (r.failure_class_code, r.decided_action_code, r.recorded_in_text) for r in df.itertuples()}
    run_ids = list(by_run)

    def script(prompt_text: str) -> str:
        run = _context_from_prompt(prompt_text)["run"]
        cls, action, note = by_run[run["run_id"]]
        if wrong_every and run_ids.index(run["run_id"]) % wrong_every == wrong_every - 1:
            cls = classes[(classes.index(cls) + 1) % len(classes)]
        return json.dumps({"failure_class_code": cls, "action_code": action, "root_cause_text": note})

    return script


@traced
def judge_script() -> Callable[[str], str]:
    """A scripted judge for dry runs: `agrees` when the agent's sentence repeats the owner's note."""
    def script(prompt_text: str) -> str:
        recorded = prompt_text.split("<<<\n", 1)[1].split("\n>>>", 1)[0]
        said = prompt_text.rsplit("<<<\n", 1)[1].split("\n>>>", 1)[0]
        return json.dumps({"verdict": "agrees" if recorded.strip() == said.strip() else "disagrees",
                           "rationale": "simulated"})
    return script
