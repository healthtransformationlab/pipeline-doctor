# %% [markdown]
# # PipelineDoctorBench on Kaggle Benchmarks
#
# Incident triage for data pipelines. The model under test is the on-call agent: it is shown the rows a
# platform keeps about one failed run (the run, the pipeline's last ok runs, its configuration, lineage one
# hop, the runbook) and must name the failure class, the first allowed runbook action, and the root cause.
# Scored against what the owner actually decided. Every incident is run under every condition of the
# switch-off test (`doctor.ABLATIONS`), so the result says what each convention buys each model.
#
# Push (from the repo root, after `kaggle b init -y`):
#
#     kaggle b t push pipeline-doctor-triage -f kaggle/pipeline_doctor_task.py --wait
#     kaggle b t run  pipeline-doctor-triage -m gemma-4-4b-it -m gemini-3.5-flash --wait
#
# Without Kaggle credentials this file runs end to end on a scripted model and prints a SIMULATED result,
# never a number to report. The rules' own row (`RulesReader`) is printed too: that one is real.

# %%
import json
import subprocess
import sys

import kaggle_benchmarks as kbench

# %%
try:
    from pipeline_doctor import kbench as triage
except ImportError:  # pragma: no cover - the Kaggle kernel path
    PACKAGE = "pipeline-doctor[kbench] @ git+https://github.com/healthtransformationlab/pipeline-doctor"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", PACKAGE], check=True)
    from pipeline_doctor import kbench as triage

# %%
df = triage.eval_frame()                     # every incident under every condition

# %%
if kbench.kaggle.is_configured():
    llm, judge_llm = kbench.llm, kbench.judge_llm
else:
    llm = triage.ScriptedReader(triage.answer_key_script(df, wrong_every=4))
    judge_llm = triage.ScriptedReader(triage.judge_script(), name="sim:scripted-judge")

# %%
rules = triage.pipeline_doctor_triage.run(triage.RulesReader(), df)
print("PipelineDoctorBench [rules:doctor]")
print(json.dumps(rules.result, indent=2))

# %%
run = triage.pipeline_doctor_triage.run(llm, df, judge_llm=judge_llm)
label = "SIMULATED (scripted model, not a result)" if run.result.get("is_simulated") else run.result["reader_name"]
print(f"PipelineDoctorBench [{label}]")
print(json.dumps(run.result, indent=2))
run  # noqa: B018 - the SDK renders the run object in a notebook cell
