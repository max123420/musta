#!/usr/bin/env sh
set -eu
: "${SUDANCARE_DB_PATH:=./sudancare.db}"
: "${SUDANCARE_BACKUP_KEY:?Set SUDANCARE_BACKUP_KEY before backing up}"
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
openssl enc -aes-256-cbc -pbkdf2 -salt -in "$SUDANCARE_DB_PATH" -out "backups/sudancare-$stamp.db.enc" -pass env:SUDANCARE_BACKUP_KEY
echo "Encrypted backup written to backups/sudancare-$stamp.db.enc"
