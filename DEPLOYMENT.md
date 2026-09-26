# TrialGuard deployment

This package supports two public FastAPI container paths:

- Render, using `render.yaml`, defaults to credential-free checked-demo
  generation while still retrieving live public ClinicalTrials.gov data.
- AWS App Runner stores the image in private Amazon ECR and can call Amazon
  Bedrock with an App Runner instance role.

No AWS access key, secret key, session token, model payload, or application
secret belongs in the image, repository, Blueprint, plain Render environment
configuration, App Runner configuration, or logs.

The ECR image path is authoritative. `apprunner.yaml` is only a source-based
fallback because App Runner does not consume that file for image-based
services.

## Render deployment

The checked-in `render.yaml` creates one Docker web service with:

- Render region `virginia`;
- application AWS region `us-east-1`;
- a `/health` liveness check;
- checked-demo generation by default (`TRIALGUARD_LIVE_BEDROCK_ENABLED=false`);
- the current structural maximum of five model-role calls;
- a configured allowance of 15 shared live assessment/chat operations per UTC
  day if live generation is deliberately enabled; and
- six requests per minute per client.

To deploy:

1. In Render, create a **Blueprint** and connect this GitHub repository.
2. Review the generated service. Do not add AWS credentials.
3. Deploy and wait for `/health` to pass.
4. Open `/api/v1/runtime` and confirm the provider is
   `checked_offline_demo`, the Region is `us-east-1`, and the model-call value
   is `5`.
5. Run the two prepared NCT IDs and one arbitrary valid NCT ID before sharing
   the URL.

The default service makes no Bedrock calls and therefore needs no AWS identity.
It still depends on outbound HTTPS access to ClinicalTrials.gov, so verify one
uncached NCT ID from the deployed service.

### Enabling live Bedrock on Render

Do **not** store the temporary workshop role's credentials on Render. Workshop
access keys and session tokens are short-lived, often broad, and will expire;
they are unsuitable for a public service. They must not be committed, placed
in `render.yaml`, pasted into build arguments, or added as plain configuration.

Enable live mode only after supplying a durable, revocable, least-privilege AWS
identity created specifically for TrialGuard. Its policy should allow only the
required `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`
resources in `us-east-1` (including each required inference-profile destination
resource). Store credential material only in Render's secret environment
settings, never in this repository. Then set these non-secret values in the
Render dashboard:

```text
TRIALGUARD_LIVE_BEDROCK_ENABLED=true
TRIALGUARD_AWS_REGION=us-east-1
TRIALGUARD_BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
TRIALGUARD_BEDROCK_NATIVE_JSON_SCHEMA=true
TRIALGUARD_DAILY_LIVE_RUN_LIMIT=15
```

Redeploy and confirm `/api/v1/runtime` reports the live provider. Revert
`TRIALGUARD_LIVE_BEDROCK_ENABLED` to `false` immediately if authentication,
throttling, cost, or abuse controls behave unexpectedly.

The 15-operation control is an in-memory, per-process UTC-day counter shared by
live assessments and model-backed report-chat turns. It resets when
the process restarts and would multiply across instances, so it is appropriate
only as a hackathon safety control on one instance—not as a durable account
budget or billing guarantee. Keep the Render service at one instance and use
AWS quotas, billing alerts, and metadata-only monitoring as additional
controls. Render hosting and outbound traffic may have separate costs and free
plan limits; check the current Render plan before publishing.

## AWS App Runner prerequisites

- AWS CLI v2 and Docker.
- An AWS account with Bedrock model access in the deployment Region.
- A short-lived AWS IAM Identity Center (SSO) session for manual deployment, or
  GitHub Actions OIDC for later CI/CD.
- Permission to manage ECR, CloudFormation, App Runner, IAM roles, and,
  optionally, AWS Budgets.

Do not create an IAM user or export long-lived `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` values. For a manual deployment, use a named SSO
profile:

```bash
aws sso login --profile trialguard-deployer
export AWS_PROFILE=trialguard-deployer
export AWS_REGION=us-east-1
```

TrialGuard is configured for `us-east-1`. Confirm that the required Bedrock
model or inference profile is available there before deployment. The
application uses App Runner's default outbound networking to reach
ClinicalTrials.gov and Bedrock.

## Deployment files

- `deploy/ecr.yaml` creates a private, encrypted, scan-on-push ECR repository
  with immutable tags.
- `deploy/apprunner-service.yaml` creates the App Runner service, ECR access
  role, least-privilege runtime instance role, health check, and bounded
  autoscaling.
- `deploy/budget.yaml` optionally creates an account-wide monthly cost alert.
- `deploy/build-and-push.sh` builds and pushes one Linux/AMD64 image.
- `deploy/deploy-service.sh` creates or updates the App Runner service.

The ECR access role can only read the specified repository. The runtime
instance role can only invoke the Bedrock resource ARNs supplied during stack
deployment. It grants no IAM mutation, S3 wildcard, Bedrock Agents, Knowledge
Bases, training, customization, or general `bedrock:*` permission.

For a cross-Region Bedrock inference profile, supply the inference-profile ARN
and every destination foundation-model ARN required by that profile. For a
single-Region model, supply only the exact model or provisioned-throughput ARN
that the application invokes.

## Runtime environment contract

These values are configuration, not credentials:

| Variable | Required | Purpose |
|---|---:|---|
| `TRIALGUARD_ENV` | yes | Must be `production` for the public service. |
| `TRIALGUARD_AWS_REGION` | yes | Bedrock client Region; configured as `us-east-1`. |
| `TRIALGUARD_BEDROCK_MODEL_ID` | yes | Primary model or inference-profile ID used by Evidence and Coordinator. |
| `TRIALGUARD_BEDROCK_CHALLENGE_MODEL_ID` | no | Optional separate Challenge model; defaults to the primary model. |
| `TRIALGUARD_BEDROCK_GUARDRAIL_ID` | no | Optional managed guardrail ID; empty means disabled. |
| `TRIALGUARD_BEDROCK_GUARDRAIL_VERSION` | no | Required when a guardrail ID is set. |
| `TRIALGUARD_BEDROCK_NATIVE_JSON_SCHEMA` | yes | Enables Bedrock native structured output for compatible models. |
| `TRIALGUARD_LIVE_BEDROCK_ENABLED` | yes | Must be `true` for live generation. |
| `TRIALGUARD_CLOUDWATCH_METRICS_ENABLED` | no | Publishes low-cardinality, metadata-only custom metrics when `true`. |
| `TRIALGUARD_CLOUDWATCH_LOGS_ENABLED` | no | Publishes metadata-only events to `/trialguard/demo` when `true`. |
| `TRIALGUARD_REGISTRY_BASE_URL` | yes | Fixed to `https://clinicaltrials.gov`. |
| `TRIALGUARD_MODEL_CALL_LIMIT` | yes | Configured as `5`, matching the fixed graph's structural maximum of at most five role calls. |
| `TRIALGUARD_MAX_REVISIONS` | yes | Hard revision ceiling; configured as `1`. |
| `TRIALGUARD_REPORT_TIMEOUT_SECONDS` | yes | End-to-end ceiling; configured as `90`. |
| `TRIALGUARD_MODEL_TIMEOUT_SECONDS` | yes | Per-model call ceiling. |
| `TRIALGUARD_RATE_LIMIT_REQUESTS_PER_MINUTE` | yes | Per-IP public request cap. |
| `TRIALGUARD_DAILY_LIVE_RUN_LIMIT` | yes | Configured as `15`; in-memory per process and reset at restart. |
| `TRIALGUARD_ALLOW_CACHED_DEMOS` | yes | Keeps frozen demo runs available after the live cap. |
| `TRIALGUARD_LOG_PAYLOADS` | yes | Must remain `false` in a public environment. |
| `TRIALGUARD_CACHE_DIR` | yes | Writable ephemeral cache path in the container. |
| `TRIALGUARD_RUNS_DIR` | yes | Writable ephemeral checked-run path in the container. |

Model IDs and guardrail IDs are not secrets. If a future feature needs a
secret, store it in AWS Secrets Manager and grant access to only that secret;
do not add it as a CloudFormation parameter or plain runtime variable.

The container filesystem is ephemeral. Only allowlisted registry fields may be
written to the runtime cache. Checked fallback demos intended to survive
restarts must be reviewed and included as non-sensitive build assets.

## Public-demo application gates

Do not publish the URL until the application enforces all of these controls:

1. Accept only `^NCT\d{8}$`; do not accept user-provided URLs or free text.
2. Keep the fixed graph at no more than five role calls, one revision, and 90
   seconds.
3. Rate-limit by the App Runner-provided client IP and enforce a shared daily
   live-operation limit across assessments and report chat.
4. Switch to credential-free checked-demo generation when the live cap is
   reached.
5. Limit request body size and concurrent assessments.
6. Escape all registry and generated text before HTML rendering.
7. Treat registry text as untrusted evidence, never as instructions.
8. Log metadata only: run ID, NCT ID, stage, status, duration, cache status,
   model ID, token counts, and deterministic check results.
9. Never log request headers, raw prompts, model responses, full registry
   payloads, contact fields, credentials, or chain-of-thought.
10. Return no secret or infrastructure detail from `/health`, `/ready`, or
    `/api/v1/runtime`.
11. Require every model-bearing endpoint, including report chat, to consume a
    shared invocation budget before enabling public live Bedrock.

App Runner terminates HTTPS and forwards traffic to port 8000. `/health` must
be a cheap liveness check that performs no external call. `/ready` may report
dependency readiness but must not invoke a model on every probe.

The stack bounds App Runner at two instances, but application-level limits are
still required because App Runner does not provide the desired per-IP and
per-day policies by itself. CloudFront, WAF, authentication, durable storage,
and private networking belong in the post-hackathon ECS hardening path.

## Provision, build, and deploy

Set shell variables for non-secret deployment identifiers:

```bash
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=us-east-1
export ECR_REPOSITORY=trialguard
export IMAGE_TAG=git-abcdef123456
```

Create the repository:

```bash
aws cloudformation deploy \
  --template-file deploy/ecr.yaml \
  --stack-name trialguard-ecr \
  --parameter-overrides RepositoryName="$ECR_REPOSITORY"
```

Build and push the image:

```bash
deploy/build-and-push.sh
```

The script prints an immutable image identifier containing a digest. Use that
digest, not a mutable tag, to deploy the service.

Supply exact Bedrock resources as a comma-separated list. This example is
deliberately non-runnable; replace every placeholder with identifiers verified
in the target account:

```bash
export IMAGE_IDENTIFIER='<account>.dkr.ecr.<region>.amazonaws.com/trialguard@sha256:<digest>'
export ECR_REPOSITORY_ARN='arn:aws:ecr:<region>:<account>:repository/trialguard'
export BEDROCK_RESOURCE_ARNS='arn:aws:bedrock:<region>::foundation-model/<model>'
export BEDROCK_MODEL_ID='<model-or-inference-profile-id>'
export BEDROCK_CHALLENGE_MODEL_ID='<optional-separate-model-or-profile-id>'
deploy/deploy-service.sh
```

CloudFormation outputs the App Runner service URL. Confirm it over HTTPS:

```bash
curl --fail --show-error --silent "https://<service-url>/health"
curl --fail --show-error --silent "https://<service-url>/ready"
```

Then run one cached demo, one live evidence-rich demo, one deliberately blocked
fixture, and the seven fixed evaluations. A healthy process alone is not a
release signal.

## Budget and usage controls

App Runner keeps at least one instance active, so it continues to incur cost
even without traffic. Before publishing:

- Set `TRIALGUARD_DAILY_LIVE_RUN_LIMIT=15` and treat it as an in-process demo
  safeguard, not a durable billing limit.
- Keep App Runner `MaxSize` at 2 and review Bedrock service quotas.
- Disable Bedrock model-invocation payload logging.
- Deploy `deploy/budget.yaml` with a monitored email address if the account
  does not already have an appropriate budget.
- Add a calendar reminder for the teardown date.

The supplied budget is account-wide so it cannot create a false sense that all
TrialGuard costs are isolated. Budget alerts are delayed and do not stop
resources automatically.

```bash
aws cloudformation deploy \
  --template-file deploy/budget.yaml \
  --stack-name trialguard-budget \
  --parameter-overrides \
    BudgetName=trialguard-hackathon \
    MonthlyLimitUsd=25 \
    NotificationEmail='<monitored-email>'
```

## Teardown

Save any reviewed, non-sensitive evaluation output first. Then delete the
service stack, budget stack if it was created only for this demo, and finally
the ECR stack:

```bash
aws cloudformation delete-stack --stack-name trialguard-app
aws cloudformation wait stack-delete-complete --stack-name trialguard-app
aws cloudformation delete-stack --stack-name trialguard-budget
aws cloudformation delete-stack --stack-name trialguard-ecr
```

Deleting `trialguard-ecr` removes all images because the repository is
configured with `EmptyOnDelete`. Confirm the account and stack names before
running teardown. Also remove any separately configured alarms, custom domains,
guardrails, or log groups that were not created by these templates.

## Validation

These checks require no AWS credentials:

```bash
bash -n deploy/build-and-push.sh deploy/deploy-service.sh
ruby -e 'require "yaml"; ARGV.each { |f| YAML.parse_file(f) }' \
  apprunner.yaml deploy/ecr.yaml deploy/apprunner-service.yaml deploy/budget.yaml
docker build --check .
```

Run an actual image build only after `pyproject.toml` and `app/main.py` land
from their owning workstreams. Before any push, scan the full Git history for
secrets and scan the built image for vulnerabilities.
