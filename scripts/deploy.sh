#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

STACK_NAME="flash-card-word-game"
STAGE_NAME="v1"
ALLOWED_ORIGIN="*"
AWS_REGION="eu-central-1"
AWS_PROFILE_NAME="adonev-login"
SKIP_FRONTEND_DEPLOY="false"

usage() {
  cat <<USAGE
Usage: ./scripts/deploy.sh [options]

Single entrypoint for backend + frontend deployments.
Defaults:
  region: eu-central-1
  profile: adonev-login
  stack:  flash-card-word-game
  stage:  v1
  allowed-origin: *

Options:
  --stack-name <name>       CloudFormation stack name
  --stage-name <stage>      API stage name
  --allowed-origin <url>    CORS origin for API
  --profile <name>          AWS profile override (default: adonev-login)
  --skip-frontend           Deploy backend only (skip S3/CloudFront frontend publish)
  --help                    Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack-name)
      STACK_NAME="$2"
      shift 2
      ;;
    --stage-name)
      STAGE_NAME="$2"
      shift 2
      ;;
    --allowed-origin)
      ALLOWED_ORIGIN="$2"
      shift 2
      ;;
    --profile)
      AWS_PROFILE_NAME="$2"
      shift 2
      ;;
    --skip-frontend)
      SKIP_FRONTEND_DEPLOY="true"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

require_command() {
  local command_name=$1
  local install_hint=$2

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} is required. Install with: ${install_hint}"
    exit 1
  fi
}

get_stack_output() {
  local key=$1

  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --profile "${AWS_PROFILE_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='${key}'].OutputValue" \
    --output text
}

require_stack_output() {
  local key=$1
  local value
  value=$(get_stack_output "${key}")

  if [[ -z "${value}" || "${value}" == "None" ]]; then
    echo "Missing stack output '${key}' from ${STACK_NAME} in ${AWS_REGION}."
    exit 1
  fi

  echo "${value}"
}

ensure_aws_session() {
  if ! aws configure list-profiles | grep -qx "${AWS_PROFILE_NAME}"; then
    echo "AWS profile '${AWS_PROFILE_NAME}' not found. Configure it first (see .aws/config.example)."
    exit 1
  fi

  if ! aws sts get-caller-identity --profile "${AWS_PROFILE_NAME}" >/dev/null 2>&1; then
    echo "AWS credentials for profile '${AWS_PROFILE_NAME}' are missing or expired. Logging in via SSO..."
    aws sso login --profile "${AWS_PROFILE_NAME}"
  fi
}

require_command aws "brew install awscli"
require_command sam "brew install aws-sam-cli"
require_command python3 "https://python.org/"

if [[ "${SKIP_FRONTEND_DEPLOY}" != "true" ]]; then
  require_command npm "https://nodejs.org/"
fi

ensure_aws_session

export AWS_PROFILE="${AWS_PROFILE_NAME}"

cd "${REPO_ROOT}"

echo "Deploying stack '${STACK_NAME}' to ${AWS_REGION} using profile '${AWS_PROFILE_NAME}'..."

sam build --template-file template.yaml

sam deploy \
  --stack-name "${STACK_NAME}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    StageName="${STAGE_NAME}" \
    AllowedOrigin="${ALLOWED_ORIGIN}"

"${SCRIPT_DIR}/generate-frontend-env.sh" "${STACK_NAME}" "${AWS_REGION}" "${AWS_PROFILE_NAME}"

if [[ "${SKIP_FRONTEND_DEPLOY}" == "true" ]]; then
  echo "Backend deployment complete. Frontend deployment skipped (--skip-frontend)."
  exit 0
fi

FRONTEND_BUCKET_NAME=$(require_stack_output FrontendBucketName)
FRONTEND_DISTRIBUTION_ID=$(require_stack_output FrontendDistributionId)
FRONTEND_APP_URL=$(require_stack_output FrontendAppUrl)

echo "Building frontend..."
cd "${REPO_ROOT}/frontend"
npm ci
npm run build

echo "Uploading frontend to s3://${FRONTEND_BUCKET_NAME}..."
aws s3 sync "${REPO_ROOT}/frontend/dist/" "s3://${FRONTEND_BUCKET_NAME}/" \
  --delete \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"

echo "Invalidating CloudFront cache (${FRONTEND_DISTRIBUTION_ID})..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "${FRONTEND_DISTRIBUTION_ID}" \
  --paths "/*" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'Invalidation.Id' \
  --output text)

echo "Deployment complete."
echo "Frontend URL: ${FRONTEND_APP_URL}"
echo "CloudFront invalidation ID: ${INVALIDATION_ID}"
