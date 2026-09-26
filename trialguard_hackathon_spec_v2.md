# TrialGuard — Hackathon Product Spec

**Version:** 2.1 · **Event:** Healthcare AI Hackathon · **Build constraint:** solo, approximately four hours remaining at the time of this revision

**Session transfer update:** read `HANDOFF.md` first. It was prepared at approximately 11:46 a.m. Pacific, contains the actual planning-only workspace state, and supersedes this document's earlier 11:05 starting milestones. The 2 p.m. feature freeze, 2:40 target submission, and 3 p.m. hard deadline still apply.

**Hard submission deadline:** September 26, 2026, **3:00 p.m. Pacific**, supplied by the user. Target submission at **2:40 p.m.**; freeze features at **2:00 p.m.** This deadline supersedes the earlier event-wide 10 a.m.–5 p.m. schedule. The planning clock was checked at 11:05 a.m. Pacific.

**Confirmed resources:** the user has access to the Amazon Bedrock environment and Codex through that platform for the day. Direct OpenAI access is pending. This document sets the plan; implementation has not been authorized or started in this chat. If implementation starts later than these times, compress the build scope and preserve the submission buffer.

## Product in one sentence

TrialGuard is a multi-agent, evidence-grounded second review for a clinical-trial protocol: it brings trial-specific registry signals, comparable past trials, and carefully bounded review questions into one decision-support brief for a human clinical-operations reviewer.

## The problem and the user

Clinical operations and feasibility teams have to assess whether a proposed study is likely to encounter avoidable execution problems. Relevant history is spread across trial records, free-text stop reasons, and cohort patterns. TrialGuard makes that history easier to review before a protocol launches.

The primary user is a clinical operations or trial-feasibility reviewer at a sponsor or CRO. The user remains responsible for protocol decisions. The product does not diagnose, recommend treatment, approve a protocol, or claim that changing a design feature will prevent failure.

## User input and output

**Primary input:** a ClinicalTrials.gov NCT ID. Select one phase/condition group for the main demo, preferably Phase 2 drug studies in a condition with enough comparable records. Confirm the example during the first data milestone. A trial that has not yet started can receive a prospective evidence review; historical examples must be labeled retrospective.

**Submission scope:** one NCT-ID input path. Protocol synopsis extraction and document uploads are deferred until after submission.

**Output:** a review brief containing:

- A trial status and registry-data freshness check.
- Descriptive cohort context: filters, sample size, outcome counts, and data timestamp. There is no personalized risk probability in today's version.
- A historical stop-rate only when the complete matched cohort has been retrieved and the denominator can be explained. If retrieval is partial, show the available counts and explicitly label the sample incomplete.
- Up to five similar stopped trials, each linking directly to its public registry record and showing its stated stop reason.
- Up to three **review questions** tied to retrieved evidence and observed signals. Phrase them as questions for a qualified reviewer, not as design instructions.
- A compact audit trace: which data records and tools were used, what each agent concluded, and which checks passed or blocked the result.
- A limitations note: registry data are incomplete and self-reported; association is not causation; the brief is not clinical or regulatory advice.

## Why this is a multi-agent product

Use three distinct roles with separate responsibilities. Keep numeric analysis and safety gates deterministic; agents may organize, compare, and explain evidence but may not invent measurements.

| Role | Platform | Responsibility | Cannot do |
|---|---|---|---|
| **Coordinator / Intake Agent** | Model enabled in the provided Bedrock environment | Resolve the requested trial, call the evidence and cohort tools, and assemble a structured review brief. | Invent missing trial fields, calculate statistics, or bypass a failed check. |
| **Registry Evidence Agent** | Model enabled in the provided Bedrock environment | Find and summarize a small set of relevant stopped trials from retrieved public records. Return record IDs and source-linked reasons with each claim. | Make clinical recommendations or use sources that were not returned by the retrieval tool. |
| **Challenge Agent** | Model enabled in the provided Bedrock environment; direct OpenAI may be added before freeze if access arrives | Review the draft for unsupported claims, weak comparisons, causal language, and overly prescriptive advice. It can approve, request revision, or block the brief. | Change source facts, alter numbers, or approve a brief with failed deterministic checks. |

**Cohort statistics, retrieval filters, citation validation, and the final release gate are deterministic tools.** Agent roles have separate instructions and outputs. Using multiple roles or models does not establish independent clinical validation. Bound each report to at most eight model calls, one revision cycle, and a 90-second end-to-end timeout. These are execution limits to implement, not measured performance claims.

## Platform use

- **Confirmed access:** use the provided Bedrock environment as the application baseline and the day's Codex access for development assistance. During the first ten minutes of implementation, identify the actual runtime endpoint, enabled model IDs, permissions, region, and limits. Do not assume that access to one service enables every Bedrock feature.
- **Runtime interface:** use the inference interface supported by the supplied environment; the earlier Converse proposal remains an option, not an assumed entitlement. Keep the three agent roles separate even if they initially use the same model.
- **AWS Guardrails:** use prompt-attack and contextual-grounding checks if permission and setup are available quickly. Record whether each check ran. Deterministic citation and numeric gates are required regardless of managed-service availability.
- **Direct OpenAI access:** pending. If it arrives early enough, integrate it as the challenge model through the same input/output contract. Keep the working Bedrock path while integrating. Freeze provider changes at 2:00 p.m.
- **Hosting:** use the fastest submission-compatible option. The submission form's live-URL requirement is still unknown; local operation, a recording, and a repository may or may not meet the rules. Confirm required assets before choosing deployment work.
- **Temporary access:** export the source, dependency information, public-data cache, evaluation results, and demo recording before the day's environment expires. Store credentials separately and exclude them from submitted artifacts.

## Data and modeling boundary

Use ClinicalTrials.gov public records for a bounded phase/condition cohort. Cache fetched records with their retrieval timestamps. Full AACT ingestion, embeddings infrastructure, and predictive model training are deferred. Never use PHI or patient-level data.

For a descriptive resolved-study rate, count TERMINATED and WITHDRAWN in the numerator and those statuses plus COMPLETED in the denominator. Display SUSPENDED and ongoing studies separately because their final outcomes are unresolved. Show all applied filters and status counts. These registry statuses describe study operations and do not establish drug efficacy. Resolved-only comparisons can favor outcomes that resolve sooner; show this limitation with the statistic.

Today's report uses evidence available at retrieval time. It makes no claim to have predicted a historical outcome. A future historical backtest must reconstruct both trial features and precedent outcomes as they were publicly available at the decision date; filtering only by trial start date is insufficient. Personalized prediction and sensitivity analysis require this additional work after submission.

## Guardrails and release policy

1. **Public-data-only boundary:** no patient records, PHI, or identifiable protocol attachments. Reject or remove sensitive input before model calls; do not retain raw free-text input in demo logs.
2. **Read-only tools:** agents can query the registry snapshot/API and local cohort tables only. No external actions, protocol edits, trial recommendations, or tool calls chosen from retrieved text.
3. **Evidence required:** every trial-specific statement cites a registry record in the current evidence bundle, including any timestamped cached records. Every number must match a deterministic tool output. Show direct record links and source passages. Citation validity alone does not prove that a passage supports a claim; semantic support is reviewed separately.
4. **No causal wording:** prohibit claims that a change will reduce termination risk. If a sensitivity view is added later, label it as model-score sensitivity, not an intervention effect.
5. **Human decision boundary:** output review questions and evidence for a qualified person. Do not issue go/no-go decisions or clinical, regulatory, or patient-care advice.
6. **Review gate:** the challenge agent reviews the draft, while deterministic citation and numeric checks enforce release conditions. Permit one visible revision cycle, then recheck. Any unresolved failure blocks the affected section or the whole brief. Display review findings and revision status.
7. **Prompt-injection handling:** treat registry text as untrusted evidence, never as instructions. Test malicious-looking text in free-text fields and verify it cannot change tool permissions or the system rules.
8. **Honest uncertainty:** surface missing or stale data, cohort size, low retrieval confidence, and model uncertainty. Return “insufficient evidence” when support is weak.

## Evaluation plan

Evaluation is part of the demo, not an afterthought. Maintain a small fixed set of representative public trial IDs and edge cases; record the inputs, expected evidence, checks, and outputs so a run is reproducible.

| Area | Hackathon measure | Pass condition for the demo |
|---|---|---|
| Data and retrieval | Correct lookup; relevant precedent precision at 5; every result links to the right public record | No broken or mismatched NCT IDs in the demo set |
| Grounding | Citation validity; recomputed numeric facts; human spot-check of claim support | All displayed citation IDs and numbers pass checks; report the count and findings of human-reviewed claims separately |
| Safety | Test cases for PHI-like input, prompt injection in registry text, unsupported causal claims, and missing data | Unsafe or unsupported output is blocked or downgraded; no fabricated evidence reaches the user |
| Agent behavior | Tool-call success, reviewer block/revision rate, end-to-end completion, and latency on fixed cases | Show at least one successful run and one intentionally blocked case |
| Human usefulness | Quick review of a few outputs for relevance and clarity | Present as informal feedback, not clinical validation |

Do not claim the small demo set proves clinical safety or clinical utility. Show the evaluation boundary and the failures found.

**Minimum fixed evaluation set:** one evidence-rich trial; one sparse-evidence trial; an invalid NCT ID; a resolved trial requested in prospective mode; an injected instruction in retrieved text; a fabricated citation; and a numeric claim that disagrees with the tool result. Keep adversarial fixtures clearly labeled and outside the real public-data cache. Freeze expected outcomes before the final run, show counts, and inspect semantic support in at least two real reports. Evaluation is planned here and has not yet run.

## Solo-day scope

**Must ship:** one NCT-ID workflow; public record lookup; three to five sourced precedents when available; descriptive cohort context; three Bedrock-backed agent roles; deterministic citation/number checks; seven fixed evaluation cases; an inspectable review trace; and the required submission assets.

**Optional only before the feature freeze:** managed Bedrock Guardrails integration, a direct OpenAI challenge model if access arrives, and descriptive rates for fully retrieved cohorts. No individualized probability, what-if scoring, protocol upload, or model training before submission.

**Remaining time budget — all times Pacific, September 26:**

| Time | Deliverable | Cut decision |
|---|---|---|
| 11:05–11:15 | Lock runtime access, submission requirements, and shared tool/report contracts | Keep provider integration to the working supplied environment |
| 11:15–12:00 | Select demo IDs; retrieve and cache the bounded public cohort; return cited precedents | If the full cohort is unavailable, show sample counts and omit the rate |
| 12:00–1:00 | Connect the three agent roles and deterministic release checks to one working report | Preserve cited evidence, review questions, and block behavior; reduce optional statistics |
| 1:00–2:00 | Integrate UI, run the fixed cases, inspect real reports, fix failures, capture a backup demo | Cut provider switching and extra infrastructure first |
| **2:00** | **Feature freeze** | Only fix issues that prevent a correct demo or submission |
| 2:00–2:25 | Final evaluation record, concise README, required video/slides or app link | Use the actual submission form to prioritize assets |
| 2:25–2:40 | Package, export from temporary environment, and submit | Confirm submission receipt |
| 2:40–3:00 | Submission contingency buffer | Resolve upload, permission, and broken-link issues |

These are planning milestones, not elapsed work. If implementation begins after 11:15, reduce scope rather than moving the 2:40 target. Additional coding sessions should take bounded tasks with shared contracts: data/retrieval, UI, and evaluation review. One session owns orchestration and integration; avoid several sessions editing the same files.

**Explicitly cut for this submission:** full AACT ingestion, predictive model training, what-if scoring, protocol uploads, patient matching, autonomous protocol edits, production authentication, persistent PHI storage, and additional agent roles.

**Demo acceptance test:** for a selected public trial, a judge can see the source record, cohort context, comparable stopped trials, evidence-linked review questions, the independent review result, and the checks that controlled release. A second test intentionally triggers a block, such as an unsupported claim or prompt injection.

## Positioning

“TrialGuard gives clinical-operations reviewers a second, evidence-grounded look at a trial before launch. It combines public trial history, transparent cohort signals, and a multi-agent review gate. It helps people ask better questions; it does not decide whether a study should proceed.”

This is a clinical-development and trial-execution product in the hackathon's AI × Life Sciences area. Today's version organizes public evidence and descriptive cohort signals for human review. Predictive modeling remains future portfolio work.
