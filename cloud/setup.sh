#!/bin/bash
# GCP リソースのセットアップスクリプト
# 使い方: ./setup.sh <project-id> [region] [docai-region]
set -euo pipefail

PROJECT_ID="${1:?Usage: ./setup.sh <project-id> [region] [docai-region]}"
REGION="${2:-asia-northeast1}"
DOCAI_REGION="${3:-us}"
BUCKET="${PROJECT_ID}-pdf-converter"
SA_NAME="pdf-converter-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
JOB_NAME="pdf-converter"
IMAGE="gcr.io/${PROJECT_ID}/${JOB_NAME}"

echo "=== 1. API 有効化 ==="
gcloud services enable \
  documentai.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  --project="${PROJECT_ID}"

echo "=== 2. GCS バケット作成 ==="
gsutil mb -l "${REGION}" -p "${PROJECT_ID}" "gs://${BUCKET}" || true

echo "=== 3. サービスアカウント作成 ==="
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="PDF Converter Service Account" \
  --project="${PROJECT_ID}" || true

# 必要な IAM ロールを付与
for role in \
  roles/documentai.apiUser \
  roles/storage.objectAdmin \
  roles/run.invoker; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}"
done

echo "=== 4. Document AI プロセッサ ==="
echo "コンソールから手動で作成してください:"
echo "  https://console.cloud.google.com/ai/document-ai/processors"
echo "  プロセッサタイプ: Document OCR または Layout Parser"
echo "  リージョン: ${DOCAI_REGION}"
echo "  作成後、プロセッサ ID を環境変数 DOCUMENT_AI_PROCESSOR_ID に設定してください"
echo ""
read -rp "プロセッサ ID を入力してください: " PROCESSOR_ID

echo "=== 5. Cloud Run イメージのビルド・デプロイ ==="
gcloud builds submit \
  --tag "${IMAGE}" \
  --project="${PROJECT_ID}" \
  "$(dirname "$0")"

gcloud run jobs create "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},DOCUMENT_AI_PROCESSOR_ID=${PROCESSOR_ID},DOCUMENT_AI_REGION=${DOCAI_REGION},GCS_BUCKET_NAME=${BUCKET}" \
  --project="${PROJECT_ID}" || \
gcloud run jobs update "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},DOCUMENT_AI_PROCESSOR_ID=${PROCESSOR_ID},DOCUMENT_AI_REGION=${DOCAI_REGION},GCS_BUCKET_NAME=${BUCKET}" \
  --project="${PROJECT_ID}"

echo "=== 6. Cloud Scheduler 設定 ==="
JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

gcloud scheduler jobs create http "${JOB_NAME}-trigger" \
  --schedule="0 * * * *" \
  --uri="${JOB_URI}" \
  --oauth-service-account-email="${SA_EMAIL}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" || true

echo ""
echo "=== セットアップ完了 ==="
echo "GCS バケット : gs://${BUCKET}"
echo "Cloud Run ジョブ: ${JOB_NAME} (${REGION})"
echo "Cloud Scheduler : 毎時 0 分に自動実行"
echo ""
echo "PDF を gs://${BUCKET}/input/ にアップロードすると次の実行時に変換されます。"
echo "手動実行: gcloud run jobs execute ${JOB_NAME} --region=${REGION} --project=${PROJECT_ID}"
