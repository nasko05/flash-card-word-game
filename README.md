# Flash Card Word Game (Spanish -> Bulgarian)

MVP full-stack app for studying Spanish vocabulary with:
- Cognito authentication (register/login)
- Upload Spanish words with Bulgarian translations
- Draw random flash cards (up to 50)
- Two study modes: Spanish -> Bulgarian and Bulgarian -> Spanish
- Mini-game mode: draw 20 cards, flip, and go next

## Stack

- Frontend app: React + Vite (`frontend/`)
- Frontend hosting: S3 + CloudFront
- Auth: Amazon Cognito User Pool
- API: API Gateway HTTP API (JWT auth with Cognito)
- Backend: AWS Lambda in Python (`backend/functions/`)
- Data: DynamoDB (`wordId` partition key + `RandomPoolRandKeyIndex` GSI for random draws)
- IaC: AWS SAM (`template.yaml`)

## Region

All deployments are configured for **`eu-central-1`**.

## Prerequisites

- AWS account with credentials configured
- AWS CLI
- AWS SAM CLI
- Python 3.12 (for SAM Python runtime/build)
- Node.js 16+ (for frontend build)

## AWS SSO profile setup

Deploy scripts use profile **`adonev-login`** by default.

1. Copy `/Users/adonev/workspace/flash-card-word-game/.aws/config.example` into your `~/.aws/config` (or append its profile block).
2. Replace placeholders (`sso_start_url`, `sso_account_id`, `sso_role_name`).
3. Optional first login:

```bash
aws sso login --profile adonev-login
```

`/Users/adonev/workspace/flash-card-word-game/scripts/deploy.sh` auto-runs SSO login if session is missing/expired.

## Deploy (single entrypoint)

From repo root:

```bash
cd /Users/adonev/workspace/flash-card-word-game
./scripts/deploy.sh
```

This command:
- deploys backend infrastructure and code
- generates `/Users/adonev/workspace/flash-card-word-game/frontend/.env.local`
- builds frontend
- uploads frontend build to S3
- invalidates CloudFront cache

### Deploy options

```bash
./scripts/deploy.sh \
  --stack-name flash-card-word-game \
  --stage-name v1 \
  --allowed-origin '*' \
  --profile adonev-login
```

Backend-only deploy:

```bash
./scripts/deploy.sh --skip-frontend
```

## Regenerate frontend env only

```bash
/Users/adonev/workspace/flash-card-word-game/scripts/generate-frontend-env.sh
```

You can run this from any working directory.
This script is kept specifically for local development workflow.

## Local frontend dev

```bash
cd /Users/adonev/workspace/flash-card-word-game/frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Backend API (authenticated)

- `POST /words`
  - body: `{ "spanish": "aprender", "bulgarian": "уча" }`
- `POST /words/bulk`
  - body: `{ "items": [{ "spanish": "aprender", "bulgarian": "уча" }] }`
- `GET /words/random?limit=50`
  - returns random set from DynamoDB

## Notes

- Cognito sign-up requires email confirmation code.
- `POST /words` upserts by lowercase Spanish word id.
- Bulk upload is supported via XLSX in the UI (download template, fill rows, upload file).
- Flashcards and mini-game follow the currently selected study mode direction.
- Random draw uses indexed query by `randKey` and does not scan the full table in normal operation.
