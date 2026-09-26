# TrialGuard — Why This Project

> **Current concept:** use [TrialGuard Hackathon Product Spec v2](</Users/shubhamagrawal/Documents/ChatGPT/healthcare_ai/trialguard_hackathon_spec_v2.md>) as the concrete product definition. The event-day version is a multi-agent, evidence-grounded second review for trial operations, with human decision-making, deterministic evidence checks, a temporal evaluation boundary, OpenAI orchestration, and an independent AWS Bedrock challenge agent. The alternatives and career-fit notes below explain the choice; the older technical scope is not the event-day commitment.

Sep 26, 2026 · @SKA

Build TrialGuard: it targets a real, costly, well-documented failure in drug development and matches the hackathon's AI × Life Sciences brief almost word for word. It runs entirely on free public data, and one person can take it past MVP in a day.

## The problem

Many clinical trials stop early, and most stop for reasons that have nothing to do with whether the drug works.

- About **12%** of trials with results on ClinicalTrials.gov were terminated (905 of 7,646) ([PLOS ONE, 2015](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0127242)).
- **68%** of those terminations were for reasons other than the trial's own data. Insufficient accrual was the single largest cause, at 39% of all terminated trials.
- Across 28,842 stopped trials, **over a third** stopped for insufficient enrollment, and only **12.7%** for safety or efficacy ([Open Targets, 2024](https://opentargets.org/news/clinical-trial-stop-reasons-Jul24.html)).

Enrollment failure is largely a design and planning problem: eligibility too narrow, too few sites or countries, unrealistic targets. It can be seen before launch, when fixing it costs a protocol amendment rather than a failed study. Yet the evidence sits scattered across hundreds of thousands of registry records that nobody reads side by side.

## The idea

TrialGuard is a second reviewer for a trial protocol. Give it an NCT ID or a draft synopsis and it answers three questions, each backed by evidence:

1. **How likely is this trial to stop early?** A calibrated probability from a model trained on past trials, compared with the base rate for similar trials.
2. **Who has tried something like this and failed, and why?** The closest stopped trials, with their own stated stop reasons.
3. **What should change before launch?** 3–5 specific design changes, each tied to a risk driver and cited to real precedent trials, with a what-if score showing how the model's estimate moves.

An agent coordinates four deterministic tools, and a verifier rejects any recommendation whose citations or numbers don't trace back to tool output.

## Fit with the hackathon themes

The AI × Life Sciences brief names clinical trial endpoints as a target, and TrialGuard predicts exactly that.

| What the organizers wrote | How TrialGuard answers it |
| --- | --- |
| "Build AI that better predicts what will actually happen in biology … real-world outcomes such as … clinical trial endpoints" | Predicts whether a trial completes or stops, validated on later years it never saw |
| "AI is creating new ways to compress the traditional drug development cycle" | Catches enrollment and design failures before launch instead of years in |
| "We're less interested in incremental AI wrappers" | A trained model, a retrieval index and an agent with verification; the LLM is one component, not the product |
| "Build something that meaningfully improves health" | Trials that finish get drugs to patients; stopped trials waste participants' time and exposure |
| Care Delivery theme: "clinical trials" named as an area | Also touches trial access: failed enrollment is patients never reached |

## Why it lands with these judges

The sponsors and likely judges span AI platforms, a bank, a law firm, VCs and clinicians; the event page doesn't name the judging panel. TrialGuard gives each group something specific to judge it on.

| Judge group | What they look for | What TrialGuard shows them |
| --- | --- | --- |
| OpenAI, AWS | Real agentic use of their platforms, not a single prompt | Tool-calling agent with a verifier loop and a visible trace; runs on their models through one client |
| Pear VC, NEA, Cathay Innovation | A market and a buyer | Sponsors and CROs lose money on trials that fail to enroll; a pre-launch risk review is a clear product wedge |
| J.P. Morgan | Quantified risk and evidence | Calibrated probabilities, backtested lift, not just scores |
| Troutman Pepper | Defensibility and honesty | Every claim cited to a public record; explicit "not causal" disclaimer |
| Clinicians and researchers | Clinical plausibility | Recommendations about eligibility, sites and endpoints, the levers trial designers actually pull |

The backtest is the differentiator. Most hackathon demos show one example; this one shows a number on trials from years the model never saw.

## Why it's buildable solo in one day

Every hard dependency is either free and downloadable or runs on a laptop, so the day goes into the product, not setup.

| Constraint | TrialGuard |
| --- | --- |
| Data access | AACT snapshot, free with no login, about 2.1 GB; ClinicalTrials.gov API needs no key |
| Labels | Built into the registry: trial status plus free-text stop reasons; no annotation needed |
| Privacy | Registry data only; no PHI, no data-use agreement, no IRB |
| Compute | LightGBM trains in minutes on CPU; about 30,000 short documents embed on CPU in minutes |
| Clinical partner | Not needed; the stop reasons were written by the trial teams themselves |
| Evaluation | Ground truth already exists for any past period, so the backtest is automatic |
| Scope control | Clear cut-lines; each layer (model, search, agent, UI) demos on its own if a later one slips |

It also matches skills you have already shown: FDA-document RAG in your research role, and tabular ML with MLflow and FastAPI in your churn project.

## Alternatives considered

Seven ideas were compared on data access, solo feasibility, demo strength and theme fit. TrialGuard is the only one strong on all four.

| Idea | Theme | Data | Why it lost |
| --- | --- | --- | --- |
| **TrialGuard** (chosen) | AI × Life Sciences | AACT, ClinicalTrials.gov | Chosen: strong on all four |
| SignalScout: FAERS drug-safety signal detection | AI × Life Sciences | openFDA, FDA label-change database | Strong statistics story but a less visual demo; messy drug-name normalization eats hours |
| TrialMatch: patient-to-trial matching | Care Delivery | ClinicalTrials.gov, TREC Clinical Trials benchmark, Synthea | Parsing eligibility criteria into rules is fiddly and can consume the whole day |
| Prior-auth denial appeal agent | Infrastructure & Financing | Public payer policies, MTSamples | Real denial letters are scarce, so evaluation is weak |
| Multi-agent tumor board | Care Delivery | Published case reports | Clinical judges spot thin oncology reasoning fast; hard to evaluate |
| Continuity-of-care agent | Care Delivery | FHIR sandbox, Synthea | Hours of FHIR setup before any AI work |
| Multi-compartment molecule outcome predictor | AI × Life Sciences | ChEMBL, ADMET models | Needs GPUs and several model setups; a team project |

## Portfolio fit

The hackathon build doubles as the first shipped piece of your pharma portfolio. The risk model follows the TrialOutcome `/predict` contract, and the retrieval and agent code seed RegIntel. It also answers the main gap in your own portfolio review: working code, judged by outside people, rather than another spec.

## Honest limitations

Saying these limits out loud in the demo builds credibility with a technical and clinical panel.

- **Registry data is thin.** No site-level recruitment data, budgets or competitor timelines, and those drive enrollment too. Expect an ROC-AUC around 0.70–0.80, not near-perfect.
- **Not causal.** What-if shows how the model's estimate moves; it doesn't prove a design change would save a trial.
- **Stop reasons are self-reported.** "Business decision" can hide other reasons.
- **Recent trials are unresolved.** The backtest stops at trials that started in 2020, and faster-resolving terminations slightly skew it.
- **A reviewer, not a decider.** The output supports a protocol review by people; it doesn't approve or reject a trial.

## Sources

- [Healthcare AI Hackathon event page](https://luma.com/e9z9vuxz) — themes and sponsors quoted above
- [Williams et al., PLOS ONE 2015](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0127242) — termination rate and reasons
- [Open Targets: why clinical trials stop](https://opentargets.org/news/clinical-trial-stop-reasons-Jul24.html) — 28,842 stop reasons classified
- [Elkin & Zhu, Scientific Reports 2021](https://www.nature.com/articles/s41598-021-82840-x) and [Scientific Reports 2023](https://www.nature.com/articles/s41598-023-27416-7) — published termination-prediction performance
- [AACT downloads](https://aact.ctti-clinicaltrials.org/downloads) — data size and formats
