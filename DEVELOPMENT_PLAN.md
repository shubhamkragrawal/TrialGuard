# TrialGuard Development Plan

**Prepared:** September 26, 2026  
**Target:** presentation-ready hackathon MVP with a public URL and slide deck  
**Feature freeze:** 2:00 p.m. Pacific  
**Submission target:** 2:40 p.m. Pacific  
**Hard deadline:** 3:00 p.m. Pacific

## 1. Product decision

The first release is an evidence-grounded review assistant for clinical-trial operations.

The user enters a ClinicalTrials.gov NCT ID. TrialGuard retrieves the public trial record, builds a bounded comparison cohort, identifies relevant stopped trials, and produces up to three evidence-linked questions for a qualified reviewer. A challenge agent and deterministic checks approve, revise, partially block, or fully block the report.

`trialguard_hackathon_spec_v2.md` and `HANDOFF.md` are the governing specifications. The predictive model, SHAP explanations, what-if scoring, protocol uploads, AACT ingestion, vector database, and design recommendations in the exploratory technical draft are deferred.

### Intended public description

> TrialGuard uses selected public ClinicalTrials.gov fields to produce evidence-linked operational review questions. It is a hackathon decision-support demonstration, not clinical, regulatory, legal, or medical advice.

## 2. What “presentation-ready MVP” means

The result must be more than a local prototype. The submission package should contain:

1. A stable public HTTPS URL.
2. A polished NCT-ID workflow that works without setup by a judge.
3. One evidence-rich live or cached success example.
4. One adversarial example that visibly triggers a release block.
5. A compact execution trace showing agent roles, source IDs, and check results.
6. A six-slide editable PowerPoint deck.
7. A concise public README with architecture, setup, safety limits, and screenshots.
8. A backup screen recording or cached replay for network or Bedrock failure.
9. Recorded evaluation results from the seven fixed cases.

This is suitable for a hackathon presentation and portfolio demonstration. It is not a production clinical system. It will not support PHI, confidential protocols, medical decisions, or unrestricted public usage.

## 3. Release scope

### Must ship

- One input: an NCT ID matching `^NCT\d{8}$`.
- Current trial identity, status, registry URL, retrieval time, and cache status.
- Public ClinicalTrials.gov API v2 retrieval.
- An allowlisted normalized record that excludes names, email addresses, phone numbers, site contacts, and arbitrary registry sections.
- A bounded cohort with visible filters, outcome counts, retrieval completeness, and timestamp.
- A resolved-study stop rate only when every cohort page was retrieved.
- Three to five comparable stopped trials when evidence is available.
- Original stop-reason text, source field, NCT ID, and registry link for each precedent.
- Up to three evidence-linked operational review questions.
- Three distinct Bedrock-backed roles: Evidence, Coordinator, and Challenge.
- Deterministic citation, passage, numeric, schema, and wording checks.
- One revision cycle at most.
- Full, partial, or blocked release states.
- Seven fixed evaluation cases.
- Public URL, slides, README, and fallback demo.

### Ship if the core flow is already stable

- Bedrock Guardrails with the result shown as passed, failed, or not run.
- Downloadable checked report.
- Token, latency, and model-call counters.
- A stronger Bedrock model for the Challenge role.
- Better lexical reranking such as BM25 or TF-IDF.

### Explicitly defer

- Trial termination probabilities or risk bands.
- Predictive-model training, calibration, SHAP, and backtesting.
- What-if scoring and causal or prescriptive design advice.
- Protocol text or document uploads.
- Patient matching or patient-level data.
- Full AACT download and ingestion.
- Embeddings, OpenSearch, Bedrock Knowledge Bases, or a vector database.
- Bedrock Agents, LangGraph, Step Functions, and SQS.
- Production authentication, multitenancy, or long-term data retention.

## 4. User and demo flow

1. A judge opens the public URL.
2. The landing page explains the intended use and provides a known demo NCT ID.
3. TrialGuard validates the ID before any model call.
4. It loads the target record from the cache or ClinicalTrials.gov.
5. It labels a resolved study as retrospective rather than implying a historical forecast.
6. It retrieves the bounded cohort and records whether pagination completed.
7. Deterministic code computes status counts and any eligible resolved-study rate.
8. A deterministic ranker creates a candidate evidence bundle.
9. The Evidence Agent selects and explains up to five precedents from that bundle.
10. Citation and passage checks validate the evidence selection.
11. The Coordinator drafts up to three review questions using evidence and numeric fact references.
12. Deterministic checks validate the draft.
13. The Challenge Agent approves, requests one revision, or blocks unsupported content.
14. After an optional single revision, every deterministic check runs again.
15. The UI displays the released report, blocked sections, limitations, and execution trace.

A normal run should use three Bedrock calls. A revision run should use four. The hard ceiling remains eight calls and 90 seconds.

## 5. Technical architecture

Use a modular Python monolith in one container.

```text
Browser
  |
  v
FastAPI application with server-rendered HTML
  |
  v
Explicit orchestration state machine
  |-- ClinicalTrials.gov client
  |-- allowlist normalizer and local JSON cache
  |-- cohort calculator
  |-- deterministic precedent ranker
  |-- Bedrock Evidence role
  |-- Bedrock Coordinator role
  |-- Bedrock Challenge role
  |-- citation, numeric, language, and release gates
  `-- metadata-only trace
```

FastAPI with Jinja templates and light HTMX enhancement is the preferred UI because it produces one deployable service and a conventional public URL. Streamlit is the fallback if UI integration threatens the feature freeze.

### Core dependencies

- Python 3.12
- FastAPI and Uvicorn
- Jinja2 and optional HTMX
- Pydantic v2
- `httpx`
- `boto3`
- `pytest`
- Ruff

Use JSON files for the small hackathon cache and recorded fixtures. DuckDB can be added later if the bounded cohort becomes awkward to calculate in memory. A database service is unnecessary for the first release.

## 6. Shared contracts

The integration owner defines these contracts before parallel implementation begins:

| Object | Required fields |
|---|---|
| `TrialRecord` | NCT ID, title, phase, conditions, intervention types, status, design fields, stop reason, source URL, retrieval time, missing fields |
| `EvidenceItem` | Evidence ID, NCT ID, field path, source passage, stop reason, source URL, relevance features, retrieval time |
| `CohortResult` | Applied filters, status counts, records retrieved, pagination complete, denominator, optional rate, limitations |
| `NumericFact` | Fact ID, label, value, unit, numerator, denominator, derivation |
| `ReviewQuestion` | Question, evidence IDs, numeric fact IDs, explanation, uncertainty |
| `ChallengeDecision` | Approve/revise/block, findings, affected question IDs, requested corrections |
| `CheckResult` | Check name, passed/failed/not-run, affected item, reason |
| `AssessmentReport` | Trial, cohort, precedents, questions, challenge decision, checks, release state, trace |
| `TraceEvent` | Stage, status, duration, cache hit, model ID, tokens, evidence IDs, check result |

Generated numbers must reference exact `NumericFact` IDs. Trial-specific claims must reference evidence IDs from the current run.

## 7. Deterministic and model responsibilities

| Deterministic application code | Bedrock roles |
|---|---|
| Validate the NCT ID | Select relevant evidence from a supplied candidate bundle |
| Build fixed API requests | Explain why selected records are comparable |
| Normalize allowlisted fields | Draft bounded questions for a qualified reviewer |
| Apply cohort filters and pagination | Identify weak support or causal overreach |
| Compute counts and rates | Request one revision when needed |
| Rank initial candidates | Return structured JSON only |
| Validate citations and source passages | Never calculate statistics |
| Match every number to a fact ID | Never retrieve arbitrary URLs |
| Detect prohibited wording | Never override a failed deterministic check |
| Decide final release state | Never issue clinical or go/no-go advice |

Retrieved registry text is untrusted data. It never becomes a system instruction and cannot select tools or endpoints.

## 8. AWS Bedrock plan

### Runtime

Use the Bedrock Runtime Converse interface if the enabled model supports it. Hide provider details behind:

```text
generate(role, messages, output_schema, timeout, metadata) -> LLMResult
```

`LLMResult` records parsed output, model ID, latency, token usage, stop reason, retries, and guardrail action. It must not expose chain-of-thought.

Implement two providers:

- `BedrockConverseProvider` for live operation.
- `FakeProvider` for deterministic tests and the offline demo.

Model IDs, inference profiles, AWS region, timeouts, and optional guardrail identifiers come from environment variables. Never put AWS credentials in source, images, logs, slides, or committed configuration.

Use the fastest enabled model that reliably returns the schemas for Evidence and Coordinator. Use a stronger model for Challenge only if measured latency leaves the total run under 90 seconds. Separate prompts and contracts establish distinct roles even when all roles use one model.

### Useful AWS services for the hackathon

- Bedrock Runtime for the three language roles.
- ECR for the container image.
- App Runner for the fastest public HTTPS deployment.
- An App Runner instance role with least-privilege Bedrock permissions.
- CloudWatch for metadata-only operational logs.
- AWS Budgets or a hard application-level usage cap.
- Bedrock Guardrails only if already available and quick to configure.

App Runner is preferred for speed. ECS Fargate behind an ALB is the post-hackathon hardening path. Lambda is not preferred for a synchronous workflow that may approach 90 seconds.

## 9. Public URL and abuse controls

The App Runner service should expose a public HTTPS URL by 1:50 p.m.

Hackathon controls:

- Allow only valid NCT IDs.
- Limit one assessment to eight model calls and one revision.
- Add per-IP throttling in the app.
- Cap total daily live Bedrock assessments.
- Provide selected cached demos after the live-call cap is reached.
- Set request, model, and end-to-end timeouts.
- Use an IAM role rather than long-lived AWS keys.
- Log metadata only. Do not log raw prompts, model responses, headers, full API responses, or contact data.
- Keep model invocation payload logging disabled.
- Configure a budget alert and a teardown date.

Post-hackathon hardening should put CloudFront and AWS WAF in front of an ECS service, add authentication, and use private S3 storage with lifecycle deletion.

## 10. API and pages

### API

- `POST /api/v1/assess` with `{nct_id, mode}`.
- `GET /api/v1/runs/{run_id}` for a checked cached report.
- `GET /api/v1/runtime` for non-secret provider availability.
- `GET /health` for liveness.
- `GET /ready` for registry-cache and Bedrock readiness.

### Pages

- `/` contains product positioning, limitations, NCT input, and demo examples.
- `/runs/{run_id}` contains the checked report.
- `/evaluation` contains the fixed evaluation summary and known limitations.

The report page shows:

- Trial summary and registry freshness.
- Cohort filters, counts, completeness, and optional resolved-study rate.
- Sourced precedents with direct links.
- Review questions with evidence references.
- Challenge findings and revision count.
- Passed, failed, and not-run checks.
- A compact trace with stage timing and model metadata.

## 11. Repository structure

```text
trialguard/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── registry/
│   │   ├── client.py
│   │   ├── normalize.py
│   │   ├── cohort.py
│   │   └── rank.py
│   ├── agents/
│   │   ├── provider.py
│   │   ├── evidence.py
│   │   ├── coordinator.py
│   │   └── challenge.py
│   ├── checks/
│   │   ├── citations.py
│   │   ├── numbers.py
│   │   ├── language.py
│   │   └── release.py
│   ├── orchestration.py
│   ├── templates/
│   └── static/
├── tests/
│   ├── fixtures/
│   ├── test_registry.py
│   ├── test_cohort.py
│   ├── test_checks.py
│   └── test_assessment.py
├── eval/
│   ├── cases.json
│   └── run_eval.py
├── demo/
│   └── checked_runs/
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

Runtime cache and traces remain untracked.

## 12. Parallel development workstreams

Agents should work on disjoint paths. The integration owner alone edits shared schemas and orchestration.

| Workstream | Owner | Write scope | Done when |
|---|---|---|---|
| Integration | Main agent | `app/schemas.py`, `app/orchestration.py`, integration fixes | One success and one block run complete |
| Registry and cohort | Data agent | `app/registry/**`, registry fixtures, registry tests | Real record and bounded cohort normalize correctly |
| Bedrock roles | Agent-runtime agent | `app/agents/**`, prompt fixtures, provider tests | Three roles return valid structured objects |
| Checks and evaluation | Safety agent | `app/checks/**`, `eval/**`, check tests | Fabricated citations and wrong numbers are blocked |
| UI | UI agent | `app/templates/**`, `app/static/**`, page-level tests | Report reads clearly on laptop and phone widths |
| Deployment | Deployment agent | `Dockerfile`, deployment docs/IaC, health checks | Public URL returns healthy app |
| Presentation | Slides agent | `slides/**` and final `.pptx` | Six-slide deck renders cleanly and uses measured claims |

Agents must not change another workstream's files. Contract changes go through the integration owner.

## 13. Execution schedule

### Before 2:00 p.m. feature freeze

| Time | Parallel work | Gate |
|---|---|---|
| 12:15–12:25 | Lock schemas, test one Bedrock structured call, choose demo cohort and IDs, start deploy skeleton | Bedrock and registry access confirmed |
| 12:25–12:55 | Registry/cohort, agent adapter, checks, UI shell, and container proceed in parallel | Real trial plus sourced precedents render |
| 12:55–1:25 | Connect three roles, deterministic gates, and release states | One checked success and one deliberate block |
| 1:25–1:45 | Integrate report UI and trace; run fixed tests; deployment continues | Main demo passes end to end |
| 1:45–1:55 | Fix only critical failures; save checked fallback runs; verify public URL | URL and fallback both work |
| 1:55–2:00 | Secret scan and feature freeze | No unreviewed changes after freeze |

### Submission preparation

| Time | Work | Gate |
|---|---|---|
| 2:00–2:20 | Final evaluation record, README, screenshots, and slides | Claims match actual results |
| 2:20–2:30 | Record backup demo and rehearse the three-minute talk | Demo stays under three minutes |
| 2:30–2:40 | Upload, verify public links, and submit | Submission receipt saved |
| 2:40–3:00 | Contingency only | Broken links or upload issues resolved |

If the schedule slips, cut managed Guardrails, downloadable reports, advanced ranking, and live arbitrary IDs before cutting provenance, deterministic gates, the public demo path, or slides.

## 14. Evaluation and release gates

### Fixed cases

1. Evidence-rich real trial.
2. Sparse-evidence real trial.
3. Invalid NCT ID.
4. Resolved trial requested as prospective.
5. Prompt injection embedded in synthetic registry text.
6. Fabricated citation in a synthetic candidate report.
7. Numeric claim that disagrees with a deterministic fact.

### Required automated checks

- Registry normalization handles missing fields.
- Pagination completeness controls whether a rate can appear.
- The stop-rate numerator and denominator are correct.
- Every displayed NCT ID exists in the current evidence bundle.
- Every cited passage matches its source field.
- Every displayed number matches its referenced fact.
- Prohibited causal, prescriptive, clinical, or go/no-go wording is blocked.
- A resolved trial cannot silently receive prospective framing.
- Retrieved text cannot modify instructions or tool permissions.
- Provider timeout and invalid JSON yield a useful partial or blocked result.
- HTML escapes all registry and generated text.
- Logs and caches exclude credentials and contact fields.

### Release criteria

- The evidence-rich case completes in under 90 seconds.
- All seven fixed cases match their frozen expected behavior.
- At least two real reports receive a manual semantic-support review.
- The success demo and blocked demo work from the public URL or checked cache.
- Slides contain only measured results.
- Full Git history passes a dedicated secret scan.
- The app uses no long-lived cloud credentials.
- The public URL displays source timestamps and intended-use limits.

## 15. Slide deck plan

Create a six-slide editable PowerPoint deck:

1. **TrialGuard**  
   One-sentence product definition and the target user.

2. **The trial review problem**  
   Explain why public evidence is hard to compare during operational review. Use only sourced statistics that survive final fact-checking.

3. **Product workflow**  
   Show the NCT input, cohort context, sourced precedents, review questions, and release result. Use a real screenshot from the finished app.

4. **System architecture**  
   Show deterministic retrieval and checks surrounding the three Bedrock roles. Make the human decision boundary explicit.

5. **Evaluation results**  
   Show the seven-case outcome summary, one blocked example, latency, and grounding results. Do not add placeholder metrics.

6. **Limits and next steps**  
   State the public-data boundary, no prediction or clinical advice, and the post-hackathon path toward evaluated retrieval and point-in-time predictive modeling.

The live demo should take about two minutes, leaving one minute for the architecture, evaluation, and limitations. The deck should support the demo rather than repeat every screen.

## 16. Demo script

- **0:00–0:20:** Define the user and the operational review problem.
- **0:20–1:30:** Enter the evidence-rich NCT ID and open one source precedent.
- **1:30–1:50:** Show the three roles and deterministic release checks.
- **1:50–2:15:** Trigger or replay the deliberately blocked case.
- **2:15–2:40:** Show measured evaluation results.
- **2:40–3:00:** State limitations and the human decision boundary.

## 17. Security and public-repository checklist

- Keep `.env`, AWS profiles, credentials, keys, Terraform state, caches, and runtime traces out of Git.
- Use GitHub Actions OIDC for later CI/CD rather than stored AWS keys.
- Run Gitleaks or an equivalent scanner against the working tree and full history.
- Enable GitHub secret scanning and push protection.
- Pin dependencies and scan the container.
- Run the container as a non-root user.
- Grant only the required Bedrock inference actions to the selected model or inference profile.
- Do not grant `bedrock:*`, `s3:*`, IAM mutation, model training, Agents, or Knowledge Base access.
- Do not log model payloads or full registry responses.
- Cache only allowlisted registry fields.
- Separate synthetic adversarial fixtures from real registry cache.
- Add cache and log retention limits plus an automatic teardown date.
- Remove local usernames, subscription details, and stale handoff logistics from public-facing README and slides.

## 18. Post-hackathon roadmap

### Phase 2: robust evidence product

- Measure precedent precision at five and improve ranking only when the evaluation supports it.
- Add async jobs, authentication, S3/DynamoDB persistence, CloudWatch dashboards, WAF, budgets, and Bedrock Guardrails.
- Add reviewer feedback and a formal claim-support rubric.
- Add report export and versioned evidence snapshots.

### Phase 3: carefully evaluated predictive research

- Reconstruct historical ClinicalTrials.gov records as they existed at registration time.
- Build leakage-resistant features and point-in-time sponsor history.
- Train and calibrate a temporal model.
- Report ROC-AUC, PR-AUC, Brier score, calibration error, and subgroup behavior.
- Keep prediction and what-if calculations deterministic.
- Treat any what-if output as score sensitivity, never as a causal effect.
- Complete a new privacy, security, clinical, and regulatory review before adding confidential protocols or patient data.
