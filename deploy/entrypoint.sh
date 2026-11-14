#!/bin/sh
# scheduler  -> cron runs the daily job (deploy/crontab)
# run        -> one run right now
# dashboard  -> Streamlit on port 8501
set -e
python -m tracker init-db

case "$1" in
  scheduler)
    # cron starts jobs with an empty environment; pass ours through /etc/environment.
    printenv | grep -E '^(DATABASE_URL|TELEGRAM_|SMTP_|EMAIL_|PRICE_|PROXY_LIST|USER_AGENT|BROWSER_CHANNEL|TZ|MAX_RETRIES|EXPORT_DIR|LOG_DIR)=' > /etc/environment
    crontab /app/deploy/crontab
    echo "scheduler ready: $(grep -v '^#' /app/deploy/crontab | head -1)"
    exec cron -f
    ;;
  run)
    exec python -m tracker run
    ;;
  dashboard)
    exec streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
    ;;
  *)
    exec "$@"
    ;;
esac
