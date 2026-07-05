#!/bin/bash
# HQ → Oracle annex hourly sync — never lose or forget
# Ross 2026-07-05: every hour
set -e
KEY=/vaults/nvme0/qsb_tower_v1/data/runtime/ssh/oracle_vm_ross_ed25519
KH=/vaults/nvme0/qsb_tower_v1/data/runtime/ssh/known_hosts
LOG=/vaults/nvme0/qsb_tower_v1/data/registries/qsb_annex_sync.log
SSH_OPTS="-i $KEY -o BatchMode=yes -o UserKnownHostsFile=$KH -o ConnectTimeout=15"

started=$(date -u +%FT%TZ)
echo "══ $started ══" >> $LOG

# 1. Memory (small + critical)
rsync -az --delete -e "ssh $SSH_OPTS" \
  /home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/ \
  ubuntu@145.241.225.163:~/skyscraper/memory/ >> $LOG 2>&1

# 2. Core data (excludes vault + venvs + weights)
timeout 1800 rsync -az --delete -e "ssh $SSH_OPTS" \
  --exclude '.venv/' --exclude 'venv/' --exclude '__pycache__/' \
  --exclude 'floors/floor_28_security_department/vault/' \
  --exclude '.env*' --exclude '.git/' \
  --exclude 'data/registries/wren_rag/' \
  --exclude 'data/screenshots/' --exclude '_archive/' \
  --exclude '*.gguf' --exclude '*.safetensors' --exclude '*.bin' \
  --exclude 'external/' --exclude 'hf_downloads/' \
  /vaults/nvme0/qsb_tower_v1/data/ \
  ubuntu@145.241.225.163:~/skyscraper/data/ >> $LOG 2>&1

# 3. Pitstops separately (smaller, always want them fresh)
rsync -az -e "ssh $SSH_OPTS" \
  /vaults/nvme0/qsb_tower_v1/data/registries/pitstops/ \
  ubuntu@145.241.225.163:~/skyscraper/pitstops/ >> $LOG 2>&1

finished=$(date -u +%FT%TZ)
echo "$finished done" >> $LOG
