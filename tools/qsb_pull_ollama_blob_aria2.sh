#!/usr/bin/env bash
# qsb_pull_ollama_blob_aria2.sh — multi-stream + auto-resume Ollama blob pull.
#
# Authority: Ross 2026-06-21 — "split the download" + "we need auto resume in
# case it fails like it does". Ollama's built-in pull is single-stream (~3 MB/s
# from Cloudflare R2) and does NOT actually resume from partials (verified
# twice today). aria2c is multi-stream + truly resumes from .aria2 control file.
#
# Workflow:
#   1) Fetch signed Cloudflare R2 URL from Ollama registry.
#   2) aria2c -x16 -s16 -c into /tmp.
#   3) On exit-non-zero, refresh signed URL and retry (signed URLs expire
#      every 24h; aria2c -c picks up where it left off).
#   4) On success, prompt user to sudo-mv into Ollama blobs dir.
#
# Run:
#   bash tools/qsb_pull_ollama_blob_aria2.sh qwen2.5 32b \
#        eabc98a9bcbfce7fd70f3e07de599f8fda98120fefed5881934161ede8bd1a41 \
#        application/vnd.ollama.image.model
set -uo pipefail

MODEL="${1:?model name e.g. qwen2.5}"
TAG="${2:?tag e.g. 32b}"
DIGEST="${3:?blob digest hex e.g. eabc98a9...}"
MEDIA="${4:-application/vnd.ollama.image.model}"

REPO=/vaults/nvme0/qsb_tower_v1
LOG=$REPO/logs/qwen32b_aria2.log
F47=$REPO/data/registries/qsb_f47_team_records.jsonl
TMP_OUT="/tmp/${MODEL//[:\/]/_}_${TAG}_${DIGEST:0:12}.blob"
TARGET_NAME="sha256-${DIGEST}"
TARGET_PATH="/usr/share/ollama/.ollama/models/blobs/${TARGET_NAME}"
MAX_RETRIES=30
SLEEP_BETWEEN=8

stamp() {
    local kind="$1"; shift
    local detail="$*"
    python3 - <<PY
import json, datetime
with open("$F47", "a") as f:
    f.write(json.dumps({
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "$kind", "role": "claude",
        "subject": "aria2_pull:${MODEL}:${TAG}",
        "detail": "${detail}",
    }) + "\n")
PY
}

fetch_signed() {
    curl -s -o /dev/null -w '%{redirect_url}' -L --max-redirs 0 \
        -H "Accept: ${MEDIA}" \
        "https://registry.ollama.ai/v2/library/${MODEL}/blobs/sha256:${DIGEST}"
}

mkdir -p "$REPO/logs"
echo "[$(date -u +%FT%TZ)] aria2 pull start: ${MODEL}:${TAG} (${DIGEST:0:12})" \
    | tee -a "$LOG"
stamp aria2_pull_started "Multi-stream pull of ${MODEL}:${TAG}; tmp=$TMP_OUT; target=$TARGET_PATH"

attempt=0
while (( attempt < MAX_RETRIES )); do
    attempt=$((attempt+1))
    echo "[$(date -u +%FT%TZ)] attempt ${attempt}/${MAX_RETRIES}: fetching signed URL" | tee -a "$LOG"
    URL=$(fetch_signed)
    if [[ -z "$URL" || "$URL" != https://* ]]; then
        echo "[$(date -u +%FT%TZ)] ERROR: signed URL fetch failed: '${URL:0:60}'" | tee -a "$LOG"
        sleep "$SLEEP_BETWEEN"; continue
    fi

    aria2c \
        --max-connection-per-server=16 \
        --split=16 \
        --min-split-size=10M \
        --continue=true \
        --auto-file-renaming=false \
        --allow-overwrite=true \
        --summary-interval=15 \
        --console-log-level=warn \
        --show-console-readout=true \
        --dir=/tmp \
        --out="$(basename "$TMP_OUT")" \
        "$URL" 2>&1 | tee -a "$LOG"
    rc=$?

    if (( rc == 0 )) && [[ -f "$TMP_OUT" ]]; then
        actual_size=$(stat -c %s "$TMP_OUT")
        echo "[$(date -u +%FT%TZ)] aria2 done; size=${actual_size} B" | tee -a "$LOG"
        stamp aria2_pull_complete "tmp=$TMP_OUT size=${actual_size} attempts=${attempt}"
        break
    fi

    echo "[$(date -u +%FT%TZ)] aria2 exited rc=${rc}; auto-resume via -c after ${SLEEP_BETWEEN}s" | tee -a "$LOG"
    stamp aria2_pull_retry "attempt=${attempt} rc=${rc}; will refresh URL and resume"
    sleep "$SLEEP_BETWEEN"
done

if (( attempt >= MAX_RETRIES )); then
    echo "[$(date -u +%FT%TZ)] FAILED after ${MAX_RETRIES} attempts" | tee -a "$LOG"
    stamp aria2_pull_failed "exhausted ${MAX_RETRIES} attempts"
    exit 1
fi

echo ""
echo "==============================================================="
echo " Download complete. To install the blob into Ollama, run:"
echo ""
echo "   sudo cp $TMP_OUT $TARGET_PATH"
echo "   sudo chown ollama:ollama $TARGET_PATH"
echo "   ollama pull ${MODEL}:${TAG}   # verify + assemble metadata"
echo ""
echo " The 'ollama pull' step will detect the blob is present, skip"
echo " the download, and only fetch the tiny manifest + config layers."
echo "==============================================================="
stamp aria2_pull_awaiting_install "User needs sudo cp; one-line install printed."
