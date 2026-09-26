# TrialGuard — handoff to the Bedrock Codex session

Prepared September 26, 2026, at approximately **11:46 a.m. Pacific / 18:46 UTC**. Check the actual time when opening this document.

## 1. Read this first

**Continue with TrialGuard.** The user asked for a choice between TrialGuard and PilotBench; TrialGuard was recommended for its stronger fit with the user's AI/data science career, pharma research assistant work, public evidence, and a concrete healthcare workflow.

**Hard submission deadline: today, September 26, at 3:00 p.m. Pacific.** Target submission at **2:40 p.m.**, preserving twenty minutes for submission problems. Freeze features at **2:00 p.m.** There were approximately **3 hours 14 minutes remaining** when this handoff was prepared. The earlier 10 a.m.–5 p.m. event-wide schedule is not the submission deadline.

**Current state: planning documents only.** No application code, dataset, selected demo IDs, configured API client, model, UI, deployment, or evaluation results have been created in this workspace. No coding sessions or agents have been dispatched. Do not describe planned checks as passed or planned integrations as working.

**Authorization:** the user's original instruction was “DO NOT WRITE ANY CODE, JUST PLANNING NOW.” Their latest request was to write this handoff before switching accounts. This handoff itself does not authorize implementation. If the user's opening instruction in the new session says to start building or implementing, that supersedes the earlier planning-only instruction; proceed without asking for the same permission again.

## 2. User context and available resources

- The user is participating solo and does not currently have a teammate.
- Career priorities: AI, data science, and AI in pharma; currently works as a research assistant in this area.
- They want a genuinely agentic application with multiple roles, healthcare-relevant guardrails, and visible evaluation.
- They have confirmed access to the **Amazon Bedrock environment** and **Codex through the Bedrock platform for the day**. Record this as user-provided access information. The exact offering, interface, enabled models, and permissions have not been inspected.
- Direct OpenAI API access remains **pending**; the user will provide an update. It must not block the working application.
- The user also mentioned ChatGPT Plus and two Claude Pro subscriptions as possible development assistance. No work has been assigned to those sessions. Those subscriptions have not been established as application API credentials.
- Day-only environment access makes exporting the source and final artifacts important.

Do not spend time debating the user's description of Codex access. Inspect the provided environment and use its actual supported interfaces. Access to a coding assistant does not by itself establish which application inference APIs or managed Guardrails are enabled.

## 3. Where the files are

Original workspace on the user's Mac:

`/Users/shubhamagrawal/Documents/ChatGPT/healthcare_ai`

| File | Status and purpose |
|---|---|
| `HANDOFF.md` | Read first. Latest session state, deadline, and revised starting schedule. |
| `trialguard_hackathon_spec_v2.md` | Current product spec, version 2.1. Read after this handoff. Its old 11:05 starting milestones are superseded by the schedule below. |
| `trialguard_technical spec.md` | Superseded, ambitious exploratory draft. Includes training, AACT, SHAP, FastAPI, and other work excluded from today's scope. Do not use it as the implementation checklist. |
| `why this?.md` | Original rationale, career alignment, and alternatives. Historical claims and original feasibility estimates are not all independently verified. |
| `pilotbench_product_spec.md` | Alternative startup-facing evaluation product. Preserve it as an alternative; it is not the selected build. |

An earlier Git inspection reported that the workspace was not a Git repository. No repository, remote, branch, or commits were created in this session. Inspect the destination workspace before making Git changes.

If the Bedrock environment uses another machine or checkout, the Mac path will not automatically exist there. Transfer at least **this handoff and `trialguard_hackathon_spec_v2.md`**, preferably the whole small planning folder. Resolve filenames relative to the destination workspace.

## 4. Product definition

**TrialGuard helps a clinical-operations or feasibility reviewer examine a trial using comparable public studies, documented stop reasons, and evidence-linked questions for human review.**

Target user: a clinical operations or feasibility reviewer at a sponsor or CRO.

The entire submission should demonstrate this path:

**NCT ID → source trial → comparable trial evidence and cohort context → up to three review questions → challenge-agent findings → checked report.**

A trial that has not yet started can receive a prospective evidence review. A trial with a known outcome is shown in a clearly labeled retrospective view. Today's application makes no historical forecasting claim.

The user should see:

1. Trial identity, public registry link, status, and retrieval timestamp.
2. The phase/condition filters and available cohort counts.
3. Three to five relevant terminated or withdrawn studies when available, with real NCT IDs, original stated stop reasons, and links. Return fewer when evidence is scarce.
4. Up to three concrete questions a qualified reviewer should investigate, each tied to identified evidence. For example, an enrollment-related stop reason could motivate asking whether recruitment assumptions have been checked with sites. Do not prescribe removing eligibility criteria or changing treatment.
5. A compact execution trace showing tools, evidence IDs, agent outputs, review findings, corrections, and final check status. No hidden chain-of-thought display is needed.
6. Honest missing-data and evidence limitations.

## 5. Submission scope is locked

**Required:** one NCT-ID input path; a bounded public-data retrieval flow; three agent roles; evidence-linked review questions; deterministic citation and numeric checks; an inspectable report; a small fixed evaluation set; and whatever assets the actual submission form requires.

**Deferred until after submission:** predictive model training, individualized failure probabilities, SHAP, calibration, historical backtesting, what-if scores, full AACT ingestion, vector database setup, protocol uploads, patient matching, extra agents, production authentication, and elaborate cloud deployment.

A descriptive cohort rate is optional. A smaller honest evidence report is acceptable when the denominator cannot be established. Do not manufacture a risk score to make the dashboard appear complete.

The fastest reasonable implementation is likely a small Python application with a simple UI, a few data/tools modules, a runtime adapter, and explicit agent steps. The earlier Streamlit idea is available; a separate FastAPI service, LangGraph, Docker Compose, and multiple databases are not requirements. Choose the smallest architecture that works with the actual supplied environment and submission format.

## 6. Agent responsibilities and runtime plan

| Role | Responsibility | Required output |
|---|---|---|
| Coordinator | Resolve the input, request evidence and statistics, and assemble the brief | Structured report using supplied facts and evidence references |
| Registry Evidence Agent | Select and summarize relevant records; request a bounded broader search when appropriate | Ranked precedents, source passages, reasons for relevance, and uncertainty |
| Challenge Agent | Check support for claims, comparability, causal overreach, and missing evidence | Approve, request one revision, or flag/block affected findings with reasons |

Use the models enabled in the provided Bedrock environment for all roles initially. Separate instructions, tool permissions, and outputs make these distinct roles even if the same model serves them. Agreement among roles is not independent clinical validation.

If direct OpenAI access arrives early enough, it can become the challenge model through the same contract. Keep the working provider path and freeze provider changes at 2 p.m.

Application control limits from the spec: **at most eight model calls, one revision cycle, and a 90-second report timeout**. These are proposed caps, not measured latency promises. Return a useful partial report with explicit missing-check status if a service times out.

Managed Bedrock Guardrails are optional within today's setup budget. Confirm permissions before promising them in the demo. Local evidence checks are mandatory. Always distinguish passed, failed, and not-run checks.

## 7. Data plan and correctness constraints

Use public ClinicalTrials.gov records. API documentation starting point:

[ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api)

The expected API-v2 routes from the plan are `/api/v2/studies/{nctId}` for a record and `/api/v2/studies` for searching. Verify current query parameters, pagination, and returned fields before implementation; no API response has been fetched in this session.

Select one phase/condition group for a coherent demo, preferably Phase 2 drug studies with enough comparable records. No condition or demo NCT ID has yet been selected. Choose IDs from fetched records rather than inventing placeholders.

Cache public records and their timestamps. Preserve original source fields and stop-reason text. Cached responses are useful for repeatable evaluation and venue connectivity problems; show cache status honestly.

For cohort statistics:

- Compute statistics from the whole matched cohort if it was fully retrieved. The few retrieved stopped precedents are not the denominator for a general stop-rate.
- For a resolved-study stop-rate, the numerator is TERMINATED plus WITHDRAWN; the denominator is those statuses plus COMPLETED.
- Show SUSPENDED and ongoing studies separately. They have unresolved final outcomes.
- Display the filter, date boundaries if any, sample sizes, and completeness status with the statistic.
- If pagination, limits, or sampling prevent complete retrieval, show clearly labeled sample counts and omit the overall stop-rate.
- These are current registry descriptions. Even complete resolved-study cohorts can be biased toward outcomes that resolve sooner.

Source citation existence and factual support are different checks. Matching a cited NCT ID to the evidence bundle does not prove that its passage supports the claim.

Numeric facts should be computed by tools and rendered using their specific fact reference, units, and denominator. Matching a generated number to any number somewhere in the evidence is insufficient validation.

## 8. Shared contracts to settle before dividing implementation

Keep these conceptual objects consistent across the data, orchestration, UI, and evaluation work. No schema code has been written.

| Object | Required information |
|---|---|
| Trial record | NCT ID, title, phase, conditions, status, relevant design fields, original source URL, timestamp, missing fields |
| Evidence item | NCT ID, field/passage reference, original stop reason, source URL, similarity rationale, retrieval timestamp |
| Cohort result | Filters, status counts, total retrieved, completeness, denominator, optional descriptive rate, limitations |
| Review question | Question, cited evidence references, supporting explanation, uncertainty, reviewer finding |
| Check result | Check name, passed/failed/not-run state, affected item, reason, tool evidence |
| Report | Trial, cohort, precedents, questions, checks, source freshness, execution trace, revision count |

One session should own these contracts and integration. If parallel development is used within the user's authorizations and environment capabilities, assign separate files/modules: data/retrieval, UI, and evaluation review. Keep orchestration with the integration owner. No parallel work has already been started.

## 9. Evaluation and guardrails

Freeze expected outcomes for seven small cases before the final run:

| Case | Expected behavior |
|---|---|
| Real trial with enough evidence | Resolve real sources and produce supported questions |
| Real trial with sparse evidence | State the gap and return fewer questions or precedents |
| Invalid NCT ID | Report invalid input or no record; never fabricate a trial |
| Resolved trial requested as prospective | Switch to labeled retrospective review or reject the prospective interpretation |
| Injected instruction in source text | Preserve task rules and read-only tool permissions |
| Fabricated citation in a candidate report | Block the affected content through the citation gate |
| Numeric claim inconsistent with tool result | Reject or correct it from the referenced fact |

Adversarial fixtures are synthetic and must stay distinguishable from the real registry cache. Display real test outcomes and counts; no evaluation has yet run. A deliberately seeded failure demonstrates the gate but is not evidence that a model naturally makes that error.

Inspect semantic support in at least two real reports. Report exactly who reviewed them; no clinician has been involved in this session. Do not claim clinical validation or “100% factual accuracy.”

Agent tools are read-only and limited to permitted registry/data operations. Registry text is untrusted evidence, not instructions. The app does not submit claims, contact sites, alter protocols, or make clinical decisions. No PHI is required for the NCT-ID flow.

## 10. Revised remaining schedule

This replaces the earlier 11:05 starting milestones in the spec. If the next session starts later, check the clock, reduce optional work, and preserve packaging/submission time.

| Pacific time | Deliverable |
|---|---|
| Approximately 11:50–12:00 | Read this handoff and the current spec; confirm actual inference access and submission format; lock the small contracts |
| 12:00–12:35 | Fetch and cache real trial examples and a bounded cohort; connect basic input and evidence display |
| 12:35–1:20 | Complete the three agent roles and deterministic release checks for one full report |
| 1:20–2:00 | Finish the UI, execute the fixed cases, inspect report support, and fix critical failures |
| **2:00** | **Freeze features and provider changes** |
| 2:00–2:25 | Prepare measured evaluation notes, README, and required demo recording/slides/live link |
| 2:25–2:40 | Export artifacts, submit, and verify receipt |
| 2:40–3:00 | Contingency for upload, permissions, or broken links |

Cut optional statistics and managed-service setup before cutting evidence provenance or the final gate. If full-cohort retrieval fails, retain sourced precedent review and labeled sample counts. If live inference or network access fails during the presentation, any replay must be labeled as a cached run.

## 11. Unknowns to resolve early

The previous session asked the user what the submission form requires; **no answer has arrived**. The submission URL is not known. Specifically confirm whether the deadline requires a public app URL, repository, video, slides, or a written description. Do not assume a local demo is sufficient, or spend time on hosting if it is unnecessary.

Other open items:

- Exact Bedrock/Codex environment, runtime endpoint, enabled models, credentials mechanism, region, and quotas.
- Whether managed Guardrails are enabled.
- Direct OpenAI availability, if the user supplies it.
- Event rules about pre-existing code/data and any required sponsor usage.
- Destination workspace, whether files were transferred, and repository ownership/visibility.

After implementation is authorized, resolve the essential unknowns while continuing independent work. Do not wait for optional OpenAI access.

## 12. Submission and session preservation

Export from the temporary environment before access ends:

- Source code, dependency information, and clear run instructions.
- Public-data cache with source URLs and timestamps.
- Evaluation inputs, expected behaviors, actual results, and known failures.
- A concise product description and architecture overview.
- Required submission assets and a backup demo recording.
- Submission receipt or confirmation once available.

Keep credentials outside source, prompts, screenshots, recordings, and exports. No secrets have been added to this folder or this handoff.

Event reference: [Healthcare AI Hackathon](https://luma.com/e9z9vuxz). The user's 3 p.m. submission deadline takes precedence over earlier schedule information.

## 13. Suggested message to begin implementation in the new session

The user can paste this if ready to end planning and authorize the build:

> Read HANDOFF.md and trialguard_hackathon_spec_v2.md in this project. Start implementing the scoped TrialGuard MVP now. The hard submission deadline is today at 3 p.m. Pacific; target submission at 2:40 and freeze features at 2. We have today's Codex access through the Bedrock environment. Direct OpenAI access is pending and must not block the build. Check the current time and actual environment, then deliver the smallest working evidence-review flow with three agent roles, citation/number checks, and the specified evaluation cases. Follow the handoff's scope cuts and preserve time for the actual submission requirements.

This is a suggested user message, not a claim that the user has already sent implementation authorization.
