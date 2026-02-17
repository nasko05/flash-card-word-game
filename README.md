# Flash Card Word Game (Spanish -> Bulgarian)

MVP full-stack app for studying Spanish vocabulary with:
- Cognito authentication (register/login)
- Upload Spanish words with Bulgarian translations
- Four practice modes:
  - flash cards (normal flip cards)
  - quiz Bulgarian -> Spanish
  - quiz Spanish -> Bulgarian
  - sentence practice Bulgarian -> Spanish (natural day-to-day prompts)
- Spanish checks ignore vowel accent-only mismatches, still requiring correct `ñ`
- Mini-game mode (within flash cards): draw 20 cards, flip, and go next

## Stack

- Frontend app: React + Vite (`frontend/`)
- Frontend hosting: S3 + CloudFront
- Auth: Amazon Cognito User Pool
- API: API Gateway HTTP API (JWT auth with Cognito)
- Backend: AWS Lambda in Python (`backend/functions/`)
- Data:
  - words table: DynamoDB (`userId` + `wordId` primary key, plus `RandomPoolRandKeyIndex` GSI)
  - sentence table: DynamoDB (`sentenceId` primary key, plus `StatusRandKeyIndex` GSI)
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
  --profile adonev-login \
  --seed-sentences
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
- `GET /words/random?limit=20`
  - returns random set from DynamoDB
- `GET /words/export`
  - returns all authenticated user words for XLSX export/bulk editing
- `GET /sentences/next`
  - returns one random approved Bulgarian prompt for sentence translation
- `POST /sentences/check`
  - body: `{ "sentenceId": "...", "answer": "..." }`
  - returns `exact | warning | wrong` with canonical answer

## Notes

- Cognito sign-up requires email confirmation code.
- `POST /words` upserts by lowercase Spanish word id within the authenticated user scope.
- Bulk upload is supported via XLSX in the UI (download template, fill rows, upload file).
- You can export all words for the authenticated user as XLSX, edit them, and upload back in bulk.
- Quiz answer checks are case-insensitive; near-miss answers (accent/case only) are counted as correct with a warning and the canonical word shown.
- Quiz/sentence Spanish checks ignore vowel accents while keeping `ñ` strict.
- Random draw is user-scoped and uses indexed query by `randKey` in normal operation.
- Sentence exercises use a separate pool and are not constrained to uploaded word pairs.

## Sentence Pool Pipeline (Beyond MVP)

Full sentence creation/curation documentation:
- `/Users/adonev/workspace/flash-card-word-game/docs/SENTENCE_CREATION.md`

Generate deterministic rule-based natural sentence pool:

```bash
python3 /Users/adonev/workspace/flash-card-word-game/scripts/generate-sentence-pool.py \
  --output /Users/adonev/workspace/flash-card-word-game/docs/sentence-pool.generated.json
```

Import an existing open-source BG/ES corpus (TSV/CSV) into pool format:

```bash
python3 /Users/adonev/workspace/flash-card-word-game/scripts/import-open-sentence-dataset.py \
  --input /path/to/corpus.tsv \
  --delimiter $'\t' \
  --output /Users/adonev/workspace/flash-card-word-game/docs/sentence-pool.imported.json
```

Publish generated/imported pool to DynamoDB:

```bash
python3 /Users/adonev/workspace/flash-card-word-game/scripts/publish-sentence-pool.py \
  --input /Users/adonev/workspace/flash-card-word-game/docs/sentence-pool.generated.json \
  --stack-name flash-card-word-game \
  --region eu-central-1 \
  --profile adonev-login
```

Review and moderate pending exercises:

```bash
python3 /Users/adonev/workspace/flash-card-word-game/scripts/review-sentence-pool.py \
  --action list \
  --status PENDING_REVIEW
```
