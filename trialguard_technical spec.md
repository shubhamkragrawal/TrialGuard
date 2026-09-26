# TrialGuard — Technical Spec

> **Status: exploratory draft, superseded for the hackathon by [TrialGuard Hackathon Product Spec v2](</Users/shubhamagrawal/Documents/ChatGPT/healthcare_ai/trialguard_hackathon_spec_v2.md>).** This earlier draft describes a much larger implementation than is realistic for a solo event-day build. Use v2 as the current product and scope; retain this file only as a source of later portfolio ideas.

Sep 26, 2026 · @SKA

TrialGuard is a one-day, solo-built agent that predicts whether a clinical trial will be terminated or withdrawn, finds similar trials that already failed, and recommends cited design changes, all on free public ClinicalTrials.gov data.

## 1. Scope

One person, one day, one end-to-end flow: a trial goes in, a cited risk report comes out, and a backtest number proves it works.

**Ships on the day**

- Calibrated termination-risk model for interventional Phase 2, 2/3 and 3 trials, trained on a temporal split
- Precedent search over stopped trials, using their free-text `why_stopped` reasons
- Cohort statistics: base termination rate and top stop reasons for trials like this one
- What-if rescoring: change one design field, see the risk move
- LangGraph agent that combines the four tools into a report where every recommendation cites real trials
- Verifier step that rejects uncited or unresolvable claims
- Streamlit UI plus a FastAPI endpoint
- Backtest on trials that started after the training cutoff and whose outcome is now known

**Out of scope (say so in the demo)**

- Any patient-level data or PHI — registry data only
- Causal claims: what-if shows how the model's score moves, not what would happen in reality
- Drift monitoring, retraining, Kubernetes, guardrail classifiers, MCP — portfolio work for later
- Phase 1 and observational studies (different failure dynamics)

## 2. User and demo flow

The user is a clinical operations lead or trial designer reviewing a protocol before it launches, when design changes are still cheap.

1. Enter an NCT ID, or paste a draft protocol synopsis (title, phase, condition, intervention, sponsor type, eligibility criteria, planned enrollment, countries).
2. Intake turns it into the model's feature schema. For pasted text, the LLM extracts fields into a typed Pydantic object, and the user confirms them.
3. Risk panel: calibrated probability of termination or withdrawal, the cohort's base rate beside it, and the top 5 SHAP drivers in plain English.
4. Precedents panel: 5–10 similar trials that stopped, with phase, sponsor type, start year, their stop reason verbatim, the reason category and a link to ClinicalTrials.gov.
5. Recommendations: 3–5 concrete design changes. Each names the risk driver it addresses and cites at least one precedent NCT ID.
6. What-if: change a field (for example add 2 countries or loosen an age limit), rescore, and see the risk move. The UI labels this model sensitivity, not a causal effect.
7. Agent trace: an expandable log of every tool call and its output, so judges can see it is not one prompt.

## 3. Architecture

A single LangGraph agent calls four deterministic tools, and a verifier gates the final report. The LLM never computes a number itself.

&#91;embedded content: TrialGuard architecture · 4 tools, 1 verification loop\]

Every number in the report comes from a tool. The LLM only plans, extracts and writes.

| Component | Responsibility | Built with |
| --- | --- | --- |
| Intake | NCT ID → row from DuckDB (live ClinicalTrials.gov API as fallback); pasted text → LLM structured extraction into `TrialFeatures` | Pydantic, LLM with JSON schema |
| Risk model | Calibrated probability plus top SHAP drivers | LightGBM, isotonic calibration, SHAP TreeExplainer |
| Precedent search | k nearest stopped trials, filtered by phase and condition | Chroma, bge-small-en-v1.5 embeddings |
| Cohort stats | Base rate and stop-reason mix for the trial's cohort | DuckDB, parameterized read-only queries |
| What-if rescoring | Rescore with one or more fields changed | Same model, feature diff |
| Recommender | Turns tool outputs into 3–5 cited recommendations | LLM, strict JSON output |
| Verifier | Every cited NCT ID was retrieved this run; every recommendation maps to a SHAP driver or cohort statistic | Python checks, one LLM retry |
| Report | UI and API | Streamlit, FastAPI |

## 4. Data

The AACT snapshot of ClinicalTrials.gov is the only data you need: free, no login and about 2.1 GB as pipe-delimited flat files, which load straight into DuckDB.

| Source | Used for | Access |
| --- | --- | --- |
| [AACT flat files](https://aact.ctti-clinicaltrials.org/downloads) | Training data, cohort stats, precedent corpus | Download zip, \`read\_csv(..., delim=' |
| [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) | Live lookup of an NCT ID missing from the snapshot | `GET /api/v2/studies/{nctId}`, JSON, no key |
| [Open Targets stop-reason classifications](https://opentargets.org/news/clinical-trial-stop-reasons-Jul24.html) | Optional labels for stop-reason categories (28,842 stopped trials, 17 classes) | Download if the file is reachable; otherwise the LLM classifies on the fly |

**AACT tables used**

| Table | Columns taken |
| --- | --- |
| `studies` | `nct_id`, `study_type`, `overall_status`, `phase`, `start_date`, `why_stopped`, `number_of_arms`, `has_dmc`, `enrollment`, `enrollment_type`, `brief_title` |
| `sponsors` | `lead_or_collaborator`, `agency_class`, `name` |
| `designs` | `allocation`, `intervention_model`, `masking`, `primary_purpose` |
| `eligibilities` | `criteria`, `gender`, `minimum_age`, `maximum_age`, `healthy_volunteers` |
| `conditions` / `browse_conditions` | Condition names and MeSH terms for cohort and filtering |
| `interventions` | `intervention_type` |
| `countries`, `calculated_values` | Country count, `number_of_facilities`, `has_us_facility` |
| `design_outcomes` | Count of primary and secondary outcomes |
| `brief_summaries` | Text for the precedent embeddings |

**Label.** `y = 1` if `overall_status` is TERMINATED, WITHDRAWN or SUSPENDED; `y = 0` if COMPLETED. Every other status is excluded (still running, so no outcome yet).

**Filters.** `study_type = INTERVENTIONAL`, phase in {PHASE2, PHASE2/PHASE3, PHASE3}, `start_date` from 2005 to 2020.

**Temporal split (by `start_date`)**

| Split | Start years | Purpose |
| --- | --- | --- |
| Train | 2005–2015 | Fit the model |
| Calibration | 2016–2017 | Isotonic calibration, threshold choice |
| Backtest | 2018–2020 | Headline numbers — "trained on the past, scored on the future" |

Trials started after 2020 are left out because many have no final outcome yet. Even 2018–2020 is slightly skewed toward terminations, which resolve faster than completions. State that in the eval slide.

**Leakage trap to avoid.** AACT overwrites `enrollment` with the actual number when a trial closes, and terminated trials enroll few patients, so using it is a label leak. Filtering to `enrollment_type = 'ANTICIPATED'` doesn't help, because closed trials almost always report actual enrollment. Drop `enrollment` from the model. The planned figure only exists in each record's first registered version on ClinicalTrials.gov, which is a stretch goal. `number_of_facilities` and the country count can also shrink after registration: run the model with and without them, and report the difference. This is a strong interview talking point.

## 5. Risk model

A gradient-boosted classifier on about 25 features, all known at registration. It is calibrated on a later time window, and the target is ROC-AUC of about 0.70 or better on the backtest. Published models on similar data reach [0.73](https://www.nature.com/articles/s41598-021-82840-x) to [0.80](https://www.nature.com/articles/s41598-023-27416-7).

**Features (all known at registration)**

| Group | Features |
| --- | --- |
| Design | phase, allocation, intervention model, masking level (0–4), primary purpose, number of arms, has DMC, intervention type (drug, biologic, device, other) |
| Outcomes | count of primary outcomes, count of secondary outcomes |
| Eligibility | inclusion count, exclusion count, criteria length in words, age span, accepts healthy volunteers, gender restriction |
| Sponsor | agency class (industry, NIH, other); sponsor's prior trial count and prior termination rate, computed only over trials that started before this one |
| Condition | therapeutic area from the top MeSH tree branch, condition trial count (rarity) |
| Geography (ablate) | country count, US site present, facility count |
| Time | start year |

**Training**

1. Baselines: the base rate, and logistic regression on the same features.
2. LightGBM with `is_unbalance` or class weights. Optuna with 30 trials, optimizing PR-AUC with time-ordered cross-validation on the train years only.
3. Isotonic calibration on the 2016–2017 calibration years. Report the Brier score and ECE before and after.
4. Threshold for the HIGH / MEDIUM / LOW band: set by cost on the calibration years, with a missed termination costing 5× a false alarm.
5. SHAP TreeExplainer: global importance for the slide, local top 5 per trial for the report.
6. Plain-English template: each SHAP driver becomes a sentence with the trial's value and the cohort's typical value, for example "12 exclusion criteria, versus a median of 7 for Phase 2 oncology."
7. Log the run to MLflow with a `feature_pipeline_version` tag (the git hash). This costs 10 minutes and matches the portfolio contract.

**Stretch: conformal interval.** A split-conformal interval from MAPIE on the calibration years. If there's no time, return `null` in `conformal_interval` and keep the field.

## 6. Retrieval

The precedent index holds only stopped trials that give a reason: roughly 25,000–30,000 documents, small enough to embed on a laptop CPU.

**Corpus.** Interventional trials with status TERMINATED, WITHDRAWN or SUSPENDED and a non-empty `why_stopped`, all phases and years. The backtest excludes precedents that started after the trial being scored.

**Document text** (one per trial, about 300 tokens):

```text
{brief_title}
Phase: {phase} | Sponsor type: {agency_class} | Started: {start_year}
Conditions: {conditions}
Interventions: {intervention_types}: {intervention_names}
Summary: {brief_summary[:600]}
Why stopped: {why_stopped}
```

**Metadata for filtering:** `phase`, `start_year`, `agency_class`, `therapeutic_area`, `stop_category`, `nct_id`.

**Embeddings.** `BAAI/bge-small-en-v1.5` (384 dimensions) through sentence-transformers, run locally with no API cost. Budget 10–20 minutes on CPU for the full corpus. Build it before the event if the rules allow; otherwise embed only Phase 2–3 stopped trials.

**Query.** Built from the input trial's title, conditions, interventions and phase.

1. Filtered search: same phase group and therapeutic area, k = 20.
2. If fewer than 5 hits, drop the therapeutic-area filter.
3. Rerank by cosine similarity plus 0.1 × (same sponsor class) and keep the top 8.

**Stop categories.** Use the Open Targets labels if downloaded. Otherwise, one batched LLM call per query classifies the 8 retrieved reasons into: enrollment, business or strategic, funding, safety, efficacy or futility, investigator or site logistics, regulatory, other.

## 7. Agent

A LangGraph state machine with 6 nodes. The planner chooses tool calls; deterministic Python does everything numeric. Each report is capped at 8 tool calls and 2 recommender attempts.

**Graph (in order)**

1. `intake` — resolve the NCT ID, or extract `TrialFeatures` from pasted text. Missing fields are marked `unknown`, never guessed.
2. `planner` — always calls `predict_risk`, `find_precedents` and `cohort_stats`. It then calls `what_if` for the top 1–2 changeable SHAP drivers (for example exclusion count or country count).
3. `tools` — runs the calls in parallel where possible and writes results into state.
4. `recommender` — writes 3–5 recommendations as strict JSON.
5. `verifier` — Python checks. On failure it loops back to `recommender` once with the error list; on a second failure it drops the bad items.
6. `report` — renders the UI payload and saves the full trace to `runs/{run_id}.json`.

**Tools**

| Tool | Input | Output |
| --- | --- | --- |
| `predict_risk` | `TrialFeatures` | `proba`, `band`, `top_shap` \[feature, value, cohort\_median, contribution\], `plain_english_summary` |
| `find_precedents` | `TrialFeatures`, `k` | list of {`nct_id`, `title`, `phase`, `start_year`, `agency_class`, `why_stopped`, `stop_category`, `similarity`} |
| `cohort_stats` | phase group, therapeutic area, sponsor class | `n_trials`, `termination_rate`, stop-category shares, median exclusion count, median country count |
| `what_if` | `TrialFeatures`, `{field: new_value}` | `proba_before`, `proba_after`, `delta` |

**Recommendation JSON (per item)**

```json
{
  "change": "Reduce exclusion criteria from 14 to about 8",
  "addresses_driver": "exclusion_count",
  "evidence": {
    "precedents": ["NCT01234567", "NCT02345678"],
    "cohort_stat": "median exclusion count in cohort = 7",
    "what_if_delta": -0.06
  },
  "rationale": "3 of 8 similar stopped trials cite slow accrual; ...",
  "confidence": "medium"
}
```

**Verifier rules**

- Every NCT ID in `evidence.precedents` is in this run's retrieved set.
- `addresses_driver` is in `top_shap`, or the item cites a `cohort_stat`.
- Any `what_if_delta` matches a `what_if` result exactly.
- No number in `rationale` is missing from the tool outputs (regex over numbers, compared against the state).

**Prompt rules (system prompt, short):** use only numbers from tool outputs; say "insufficient evidence" rather than invent; never call a what-if result a causal effect; each change must be doable before launch.

**LLM.** One model-agnostic client through LiteLLM. Use OpenAI (a sponsor) or AWS Bedrock on the day, with Gemini or Ollama as fallback. A report takes about 3 LLM calls: intake (pasted text only), recommender and one optional retry.

## 8. API and output schema

The `/predict` response keeps exactly the field set locked in the TrialOutcome spec, so this code later drops into the portfolio unchanged.

| Method | Route | Returns |
| --- | --- | --- |
| POST | `/api/v1/predict` | `TrialFeatures` in → `{proba, conformal_interval, threshold_decision, top_shap, plain_english_summary, feature_pipeline_version}` |
| POST | `/api/v1/predict/nct/{nct_id}` | Same response, features looked up from DuckDB |
| POST | `/api/v1/assess` | `{nct_id}` or `{protocol_text}` → full agent report (below) |
| POST | `/api/v1/whatif` | `{features, changes}` → `{proba_before, proba_after, delta}` |
| GET | `/api/v1/model/info` | model version, train window, backtest ROC-AUC, PR-AUC, ECE |
| GET | `/health` | liveness |

**`/assess` response**

```json
{
  "run_id": "...",
  "trial": {"nct_id": "NCT...", "title": "...", "features": {...}},
  "risk": {"proba": 0.31, "band": "HIGH", "cohort_base_rate": 0.14,
           "top_shap": [...], "plain_english_summary": "..."},
  "cohort": {"n_trials": 412, "termination_rate": 0.14, "stop_mix": {"enrollment": 0.41, ...}},
  "precedents": [{"nct_id": "...", "why_stopped": "...", "stop_category": "enrollment", "similarity": 0.82}],
  "recommendations": [ ... Section 7 format ... ],
  "verification": {"passed": true, "retries": 0, "dropped": 0},
  "trace": [{"tool": "predict_risk", "ms": 42}, ...],
  "disclaimer": "Model estimate from registry data; what-if deltas are not causal."
}
```

The numbers above are placeholders showing the shape, not results.

## 9. Evaluation

Three layers of evaluation, each producing one number for the eval slide: the model, the precedents and the recommendations.

| Layer | Metric | How | Slide line |
| --- | --- | --- | --- |
| Model | ROC-AUC, PR-AUC, Brier, ECE on backtest years 2018–2020 | Score every backtest trial once | "ROC-AUC X on trials it never saw, from a later period" |
| Model | Lift in top decile | Termination rate in the riskiest 10% ÷ overall rate | "Top 10% flagged terminated at N× the base rate" |
| Model | Leakage delta | Same model with raw `enrollment` included vs dropped | "Naive version scores X; it's cheating, here's why" |
| Precedents | Reason-match@8 | For terminated backtest trials, does the most common category among the 8 precedents equal the trial's own stop category? | "Precedents predicted the actual reason in X% of cases" |
| Recommendations | Grounding rate | Share of recommendations that pass the verifier on first try, over 30 backtest trials | "X% fully grounded first time; 100% after verification" |
| Recommendations | Human spot-check | You rate 10 reports on a 1–3 scale (specific, doable, supported) | Show 1 good and 1 bad example honestly |
| System | Latency and cost | Median seconds and tokens per report | "\~N s, \~$0.0X per report" |

**Rules for honest numbers:** precedents for a backtest trial only include trials that started before it, the calibration and backtest years are never touched during tuning, and every number on the slide comes from `eval/run_eval.py` output saved to `eval/results.json`.

## 10. Tech stack and repo layout

Everything runs on one laptop without a database server: DuckDB replaces Postgres and Chroma runs embedded.

| Layer | Choice | Why |
| --- | --- | --- |
| Environment | Python 3.12, `uv`, `ruff` | Matches portfolio conventions |
| Storage | DuckDB file (`data/aact.duckdb`) | Reads AACT pipe files directly; no server to babysit |
| ML | LightGBM, scikit-learn, Optuna, SHAP, MLflow (local) | Fast on tabular data; SHAP TreeExplainer is exact and fast |
| Retrieval | Chroma (persistent, embedded), sentence-transformers `bge-small-en-v1.5` | Local, free, CPU-friendly |
| Agent | LangGraph, Pydantic v2, LiteLLM | Explicit graph for the demo trace; swappable LLM |
| Serving | FastAPI, Streamlit | Streamlit calls the FastAPI endpoints, so both are real |
| Packaging | Docker Compose (api + ui) | One-command run for judges and the GitHub README |

```text
trialguard/
├── core/                      # domain-agnostic
│   ├── model/                 # train.py, calibrate.py, explain.py, whatif.py
│   ├── retrieval/             # index.py, search.py
│   ├── agent/                 # graph.py, verifier.py, llm.py (LiteLLM wrapper)
│   └── api/                   # app.py, schemas.py (locked /predict contract)
├── domains/pharma/
│   ├── load_aact.py           # flat files -> DuckDB
│   ├── features.sql           # point-in-time feature build
│   ├── features.py            # TrialFeatures model + text features
│   ├── cohort.py              # cohort_stats queries
│   └── prompts/               # intake.md, recommender.md
├── ui/streamlit_app.py
├── eval/run_eval.py           # writes eval/results.json
├── docker-compose.yml
├── Makefile                   # data, train, index, serve, eval
└── decisions.md
```

## 11. Build plan

Plan for about 8 hours of build time with hard cut-lines. The Luma page didn't show the schedule, so shift the clock once you know the start and demo times.

**Before the event (check the rules on pre-written code first)**

- [ ] Download the AACT flat-file zip (about 2.1 GB) and load it into DuckDB; check row counts for `studies`, `sponsors`, `eligibilities`
- [ ] `uv` project with all dependencies locked; download the `bge-small-en-v1.5` weights
- [ ] API keys for OpenAI or Bedrock (sponsor credits) and one fallback LLM; test one call each
- [ ] If allowed: build the Chroma index of stopped trials (10–20 min)
- [ ] Pick 3 demo trials: one high-risk that later terminated, one low-risk completed, one live protocol pasted as text
- [ ] Offline fallback: saved JSON reports for the 3 demo trials in case the venue Wi-Fi fails

**On the day (clock from start of hacking)**

| Time | Build | Done when |
| --- | --- | --- |
| 0:00–0:30 | Repo skeleton, Makefile, DuckDB check | `make data` passes |
| 0:30–2:00 | `features.sql` + `features.py`, point-in-time sponsor history, temporal split | Feature table with no nulls in required fields; split counts logged |
| 2:00–3:00 | Baselines, LightGBM + Optuna, calibration, SHAP, backtest metrics | `eval/results.json` has ROC-AUC, PR-AUC, lift. **Lock the model here.** |
| 3:00–3:45 | Chroma index (if not prebuilt), `find_precedents`, `cohort_stats`, `what_if` | Each tool returns sane output for the 3 demo trials |
| 3:45–5:15 | LangGraph agent: intake, planner, recommender, verifier | `/assess` returns a verified report for all 3 demo trials |
| 5:15–6:15 | FastAPI routes + Streamlit UI (risk, precedents, recommendations, what-if slider, trace) | Full flow in the browser |
| 6:15–7:00 | Run the eval on 30 backtest trials: reason-match, grounding rate, latency | Eval slide numbers filled |
| 7:00–8:00 | README with architecture image, 4 slides, rehearse demo twice, push to GitHub | 3-minute run-through under time |

**Cut-lines if you fall behind**

1. At 3:00 without a model: drop Optuna, use default LightGBM, keep calibration.
2. At 5:15 without an agent: drop what-if and pasted-text intake; NCT ID input only.
3. At 6:15 without a UI: drop FastAPI and have Streamlit call Python directly.
4. Never cut: the backtest number and the verifier. They are what separate this from a demo.

## 12. Risks and fallbacks

The biggest risk is a leak that makes the model look better than it is. A judge who spots it sinks the project, so check for it first.

| Risk | Likelihood | Mitigation | Fallback |
| --- | --- | --- | --- |
| Label leakage (actual enrollment, post-hoc site counts, sponsor history computed on the future) | High | Drop `enrollment`; ablate geography; point-in-time sponsor features | Show the leakage delta as a feature of the talk |
| Model scores only about 0.65 ROC-AUC | Medium | Frame as calibrated risk plus precedent evidence; cite the 0.73–0.80 literature range | Lead with lift in the top decile and reason-match |
| AACT snapshot is old | Medium | Check the date on the downloads page | Live ClinicalTrials.gov API for any NCT ID not in the snapshot |
| Embedding the corpus takes too long | Low–medium | Prebuild if allowed; restrict to Phase 2–3 | Filter by condition in SQL, embed only on demand |
| LLM invents numbers or trials | Medium | Verifier, numbers only from tools, strict JSON | Drop failing items rather than show them |
| Venue Wi-Fi or LLM outage | Medium | Local models and data; LiteLLM fallback chain | Cached JSON reports for the 3 demo trials |
| What-if read as causal | High (by judges) | UI label and disclaimer in every report | Say it out loud in the demo |
| Scope creep | High (solo) | Cut-lines in Section 11 | Freeze features at 7:00 and ship what works |

## 13. Three-minute demo script

Open with the problem, run the product live once, then prove it with the backtest. End by showing restraint: what it won't claim.

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:20 | Title slide | "Roughly 1 in 8 trials that report results were terminated, and the top reason isn't the drug. It's the trial can't enroll patients. That's often a design problem, visible before launch." |
| 0:20–1:30 | Live: enter the high-risk demo NCT ID | Walk through risk vs cohort base rate, top drivers, 2 precedents with their own stop reasons, 1 recommendation and its citation, then drag the what-if slider |
| 1:30–1:50 | Expand the agent trace | "Four tools, one verifier. The LLM never produces a number itself. A recommendation without a real citation is rejected." |
| 1:50–2:30 | Eval slide | Backtest ROC-AUC, top-decile lift, reason-match@8, grounding rate. "Trained on trials that started through 2015, tested on 2018–2020." |
| 2:30–2:50 | Limits slide | Registry data only, not causal, a human decides. "It's a second reviewer for the protocol, not a replacement." |
| 2:50–3:00 | Close | "Built today, open source, runs on a laptop." |

Don't use the high-risk demo trial anywhere in tuning, and say so if asked.

## 14. Sources

- [AACT downloads](https://aact.ctti-clinicaltrials.org/downloads) — flat files and Postgres dump, about 2.1 GB
- [AACT data dictionary](https://aact.ctti-clinicaltrials.org/data_dictionary) — tables `studies`, `sponsors`, `designs`, `eligibilities`, `calculated_values`
- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api)
- [Williams et al., PLOS ONE 2015](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0127242) — 12% of trials with results were terminated; insufficient accrual was the top reason
- [Elkin & Zhu, Scientific Reports 2021](https://www.nature.com/articles/s41598-021-82840-x) — termination prediction, ensemble AUC above 0.73
- [Scientific Reports 2023](https://www.nature.com/articles/s41598-023-27416-7) — interpretable XGBoost for early termination, ROC-AUC 0.80
- [Open Targets: why clinical trials stop](https://opentargets.org/news/clinical-trial-stop-reasons-Jul24.html) — 28,842 stop reasons classified into 17 categories
