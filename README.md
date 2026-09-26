# TrialGuard

TrialGuard is an evidence-linked second reviewer for clinical-trial planning. Give
it a ClinicalTrials.gov NCT ID and it finds comparable stopped trials, preserves
their documented registry reasons, drafts operational questions, and refuses to
release unsupported claims.

It does **not** predict efficacy, recommend protocol changes, or make clinical,
regulatory, or go/no-go decisions. Its output is for qualified human review.

Public checked showcase:
[shubhamkragrawal.github.io/TrialGuard](https://shubhamkragrawal.github.io/TrialGuard/).
Visitors can use its **Find more NCT IDs** link to browse the public
ClinicalTrials.gov search; arbitrary live reviews require the full application.

## What happens in a review

1. TrialGuard accepts only an NCT ID and fetches allowlisted public registry
   fields from ClinicalTrials.gov.
2. Deterministic code builds a comparison cohort and ranks stopped precedents.
3. Three bounded Amazon Bedrock roles select evidence, draft questions, and
   challenge the draft.
4. Code—not a model—checks citation membership, exact source passages, numbers,
   prohibited wording, and release status.
5. The report exposes its sources, checks, limitations, token usage, and
   execution trace.

Prepared examples:

- `NCT06860815`: active Phase 2 prospective review.
- `NCT06513364`: stopped Phase 2 retrospective review.

## Architecture

```mermaid
flowchart LR
    U[Reviewer browser] --> A[FastAPI UI and API<br/>AWS App Runner target]
    A --> O[Bounded orchestrator<br/>90 s, 8-call ceiling, 1 revision]
    O --> R[ClinicalTrials.gov<br/>allowlisted public fields]
    O --> E[Evidence role]
    O --> C[Coordinator role]
    O --> H[Challenge role]
    E --> B[Amazon Bedrock<br/>Nova Lite · us-east-1]
    C --> B
    H --> B
    O --> G[Deterministic release gates<br/>citations · passages · numbers · language]
    G --> P[Evidence-linked report]
    I[IAM workload role<br/>no embedded credentials] -.-> A
    A -. metadata-only logs .-> L[Operational trace]
```

The repository includes a production-oriented private-ECR/App Runner package.
The current AWS workshop role can invoke Bedrock but explicitly denies
CloudFormation, ECR, App Runner, Lambda, and Lightsail hosting actions. A static
checked showcase is therefore used for the public presentation fallback; the
full application runs locally and can deploy unchanged from an AWS account with
the permissions documented in [DEPLOYMENT.md](DEPLOYMENT.md).

## Run locally

Python 3.10 or newer is recommended; the container uses Python 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Offline checked-demo mode is the default and still
uses live public registry retrieval.

For live Bedrock generation, authenticate through the normal AWS SDK credential
chain or an IAM workload role—never copy credentials into this repository:

```bash
export TRIALGUARD_AWS_REGION=us-east-1
export TRIALGUARD_BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0
export TRIALGUARD_LIVE_BEDROCK_ENABLED=true
.venv/bin/uvicorn app.main:app --reload
```

Copy the non-secret defaults from `.env.example` if useful. The application
does not load or persist AWS access keys.

## Verification

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app tests eval
.venv/bin/python -m eval.run_eval --output eval/results.json
docker build --check .
```

Current build:

- 52/52 automated tests pass.
- 7/7 fixed synthetic offline release behaviors match expectations.
- A live `NCT06860815` smoke test reached full release with 14/14 checks.

The synthetic suite checks software boundaries; it is not a clinical validation
or a model-quality benchmark.

## Cost metric

TrialGuard records actual Bedrock input/output tokens for each run and computes:

```text
estimated model cost =
  input tokens × input rate / 1,000,000
  + output tokens × output rate / 1,000,000
```

One live smoke test on 2026-09-26 used three Nova Lite calls, 10,821 input
tokens, and 1,758 output tokens. At the Amazon Bedrock Standard-tier rates
verified for `us-east-1` that day—$0.06 per million input tokens and $0.24 per
million output tokens—the estimated model cost was **$0.001071**. The run took
11.77 seconds; one observation is not a latency benchmark.

Rates can change. Re-check the
[official Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/)
before deployment. Hosting, logs, networking, taxes, and free-tier effects are
excluded. The machine-readable observation is in
[`eval/live_metrics.json`](eval/live_metrics.json).

## Security and privacy

- Only public ClinicalTrials.gov fields are accepted; there is no patient or
  protocol upload path.
- NCT IDs must match `^NCT\d{8}$`; URLs and free text are rejected.
- Registry text is treated as untrusted data and scanned for instruction-like
  content before any model call.
- Requests, concurrency, model calls, revisions, and live daily usage are
  bounded.
- Credentials, `.env` files, private keys, runtime caches, and generated runs
  are ignored by Git.
- Deployment uses IAM roles and metadata-only operational traces; prompts,
  model responses, request headers, and credentials are not logged.

Before every public push, run the tests and the repository credential scan
described in [DEPLOYMENT.md](DEPLOYMENT.md).

## Repository map

- `app/`: FastAPI application, registry client, bounded roles, and release gates.
- `eval/`: seven fixed synthetic evaluations and one live smoke-test metric.
- `tests/`: unit, integration, orchestration, and UI-route tests.
- `deploy/`: ECR, App Runner, least-privilege IAM, and optional budget templates.
- `slides/`: editable presentation source, deck, and product screenshot.
- `docs/`: static public showcase for GitHub Pages.

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for scope and milestone rationale.
