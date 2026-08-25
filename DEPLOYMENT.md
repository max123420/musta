# Deployment and recovery

For a pilot clinic, install Docker Engine, copy `.env.example` to `.env`, set a random `SUDANCARE_SECRET`, and start `docker compose --profile clinic up --build -d`. Bind the service only to a trusted clinic LAN and place it behind TLS before processing any sensitive data.

Backup: `SUDANCARE_DB_PATH=./sudancare.db SUDANCARE_BACKUP_KEY='long random passphrase' sh scripts/backup.sh`.

Restore into a stopped test instance first: `SUDANCARE_DB_PATH=./restored.db SUDANCARE_BACKUP_KEY='long random passphrase' sh scripts/restore.sh backups/FILE.db.enc`.

Before a real rollout, use PostgreSQL, a managed encrypted backup target, reverse proxy TLS, monitoring, tested rollback, access reviews, and a documented incident response process.
