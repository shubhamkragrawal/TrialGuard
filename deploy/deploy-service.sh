#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
: "${IMAGE_IDENTIFIER:?Set IMAGE_IDENTIFIER to an ECR image pinned by digest.}"
: "${ECR_REPOSITORY_ARN:?Set ECR_REPOSITORY_ARN to the exact repository ARN.}"
: "${BEDROCK_RESOURCE_ARNS:?Set BEDROCK_RESOURCE_ARNS to approved ARNs separated by commas.}"
: "${BEDROCK_MODEL_ID:?Set BEDROCK_MODEL_ID.}"

stack_name="${STACK_NAME:-trialguard-app}"
service_name="${SERVICE_NAME:-trialguard}"
daily_limit="${DAILY_LIVE_ASSESSMENT_LIMIT:-50}"
rate_limit="${RATE_LIMIT_REQUESTS_PER_MINUTE:-5}"
model_timeout="${MODEL_TIMEOUT_SECONDS:-30}"
challenge_model_id="${BEDROCK_CHALLENGE_MODEL_ID:-${BEDROCK_MODEL_ID}}"
guardrail_id="${BEDROCK_GUARDRAIL_ID:-}"
guardrail_version="${BEDROCK_GUARDRAIL_VERSION:-}"

if [[ "${IMAGE_IDENTIFIER}" != *@sha256:* ]]; then
  echo "IMAGE_IDENTIFIER must be pinned with an @sha256 digest." >&2
  exit 2
fi

if [[ -n "${guardrail_id}" && -z "${guardrail_version}" ]]; then
  echo "BEDROCK_GUARDRAIL_VERSION is required when BEDROCK_GUARDRAIL_ID is set." >&2
  exit 2
fi

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --template-file deploy/apprunner-service.yaml \
  --stack-name "${stack_name}" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    ServiceName="${service_name}" \
    ImageIdentifier="${IMAGE_IDENTIFIER}" \
    EcrRepositoryArn="${ECR_REPOSITORY_ARN}" \
    BedrockResourceArns="${BEDROCK_RESOURCE_ARNS}" \
    BedrockModelId="${BEDROCK_MODEL_ID}" \
    BedrockChallengeModelId="${challenge_model_id}" \
    BedrockGuardrailId="${guardrail_id}" \
    BedrockGuardrailVersion="${guardrail_version}" \
    DailyLiveAssessmentLimit="${daily_limit}" \
    RateLimitRequestsPerMinute="${rate_limit}" \
    ModelTimeoutSeconds="${model_timeout}"

service_url="$(
  aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "${stack_name}" \
    --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue | [0]" \
    --output text
)"

printf 'Service URL: https://%s\n' "${service_url}"
