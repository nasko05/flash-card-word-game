#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

STACK_NAME=${1:-flash-card-word-game}
REGION=${2:-eu-central-1}
AWS_PROFILE_NAME=${3:-adonev-login}
FRONTEND_ENV_FILE="${REPO_ROOT}/frontend/.env.local"

if [[ -z "${REGION}" ]]; then
  echo "AWS region is missing. Pass it as the second argument."
  exit 1
fi

if ! aws configure list-profiles | grep -qx "${AWS_PROFILE_NAME}"; then
  echo "AWS profile '${AWS_PROFILE_NAME}' not found. Configure it first (see .aws/config.example)."
  exit 1
fi

if ! aws sts get-caller-identity --profile "${AWS_PROFILE_NAME}" >/dev/null 2>&1; then
  echo "AWS credentials for profile '${AWS_PROFILE_NAME}' are missing or expired. Logging in via SSO..."
  aws sso login --profile "${AWS_PROFILE_NAME}"
fi

get_output() {
  local key=$1
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --profile "${AWS_PROFILE_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='${key}'].OutputValue" \
    --output text
}

require_output() {
  local key=$1
  local value
  value=$(get_output "${key}")

  if [[ -z "${value}" || "${value}" == "None" ]]; then
    echo "Missing stack output '${key}' from ${STACK_NAME} in ${REGION}."
    exit 1
  fi

  echo "${value}"
}

API_BASE_URL=$(require_output ApiBaseUrl)
USER_POOL_ID=$(require_output CognitoUserPoolId)
USER_POOL_CLIENT_ID=$(require_output CognitoUserPoolClientId)
AWS_REGION=$(require_output AwsRegion)

mkdir -p "$(dirname "${FRONTEND_ENV_FILE}")"

cat > "${FRONTEND_ENV_FILE}" <<ENV
VITE_API_BASE_URL=${API_BASE_URL}
VITE_AWS_REGION=${AWS_REGION}
VITE_COGNITO_USER_POOL_ID=${USER_POOL_ID}
VITE_COGNITO_USER_POOL_CLIENT_ID=${USER_POOL_CLIENT_ID}
ENV

echo "Created ${FRONTEND_ENV_FILE} from stack outputs."
