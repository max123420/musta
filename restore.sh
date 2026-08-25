#!/usr/bin/env sh
set -eu
: "${SUDANCARE_DB_PATH:=./sudancare.db}"
: "${SUDANCARE_BACKUP_KEY:?Set SUDANCARE_BACKUP_KEY before restoring}"
[ "$#" -eq 1 ] || { echo "Usage: $0 BACKUP.db.enc"; exit 2; }
openssl enc -d -aes-256-cbc -pbkdf2 -in "$1" -out "$SUDANCARE_DB_PATH" -pass env:SUDANCARE_BACKUP_KEY
echo "Restored $SUDANCARE_DB_PATH. Start the service and validate before use."
