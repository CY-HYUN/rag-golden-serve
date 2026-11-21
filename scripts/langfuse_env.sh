#!/usr/bin/env bash
# Writes the Langfuse settings to .env (ignored by git) without showing the keys on screen or in shell history.
#   bash scripts/langfuse_env.sh
# Keys: Langfuse project > Settings > API Keys. Region EU = https://cloud.langfuse.com
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -p "Langfuse base URL [https://cloud.langfuse.com]: " base
base="${base:-https://cloud.langfuse.com}"
read -r -s -p "Public key (pk-lf-...), input hidden: " pk; echo
read -r -s -p "Secret key (sk-lf-...), input hidden: " sk; echo
case "$pk" in pk-lf-*) ;; *) echo "the public key should start with pk-lf-"; exit 1 ;; esac
case "$sk" in sk-lf-*) ;; *) echo "the secret key should start with sk-lf-"; exit 1 ;; esac
umask 177
{
  echo "LANGFUSE_BASE_URL=$base"
  echo "LANGFUSE_PUBLIC_KEY=$pk"
  echo "LANGFUSE_SECRET_KEY=$sk"
  echo "LANGFUSE_AUTH_B64=$(printf '%s:%s' "$pk" "$sk" | base64 -w 0)"
} > .env
echo ".env written ($(wc -l < .env) lines); the keys were not printed."
