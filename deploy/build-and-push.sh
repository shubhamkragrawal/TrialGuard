#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
: "${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID to the 12-digit target account ID.}"
: "${ECR_REPOSITORY:?Set ECR_REPOSITORY to the provisioned repository name.}"
: "${IMAGE_TAG:?Set IMAGE_TAG to a unique immutable tag, such as git-<sha>.}"

if [[ ! "${AWS_ACCOUNT_ID}" =~ ^[0-9]{12}$ ]]; then
  echo "AWS_ACCOUNT_ID must contain exactly 12 digits." >&2
  exit 2
fi

if [[ ! "${AWS_REGION}" =~ ^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$ ]]; then
  echo "AWS_REGION does not look like an AWS Region." >&2
  exit 2
fi

if [[ ! "${ECR_REPOSITORY}" =~ ^[a-z0-9]+([._/-][a-z0-9]+)*$ ]]; then
  echo "ECR_REPOSITORY contains unsupported characters." >&2
  exit 2
fi

if [[ ! "${IMAGE_TAG}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo "IMAGE_TAG is not a valid container image tag." >&2
  exit 2
fi

caller_account_id="$(
  aws sts get-caller-identity --query Account --output text
)"

if [[ "${caller_account_id}" != "${AWS_ACCOUNT_ID}" ]]; then
  echo "The active AWS session belongs to a different account; refusing to push." >&2
  exit 3
fi

registry="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
image_uri="${registry}/${ECR_REPOSITORY}:${IMAGE_TAG}"

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${registry}"

docker build \
  --pull \
  --platform linux/amd64 \
  --tag "${image_uri}" \
  .

docker push "${image_uri}"

image_digest="$(
  aws ecr describe-images \
    --region "${AWS_REGION}" \
    --repository-name "${ECR_REPOSITORY}" \
    --image-ids imageTag="${IMAGE_TAG}" \
    --query 'imageDetails[0].imageDigest' \
    --output text
)"

if [[ ! "${image_digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "ECR did not return a valid image digest." >&2
  exit 4
fi

printf 'Image identifier: %s@%s\n' "${registry}/${ECR_REPOSITORY}" "${image_digest}"
