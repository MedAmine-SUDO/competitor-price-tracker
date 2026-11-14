#!/bin/sh
# Install the daily timer for the current user: sh deploy/systemd/install.sh [postgres-container]
set -e
PROJECT_DIR=$(cd "$(dirname "$0")/../.." && pwd)
DB_CONTAINER=${1:-cpt-postgres}
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
sed -e "s|@PROJECT_DIR@|$PROJECT_DIR|g" -e "s|@DB_CONTAINER@|$DB_CONTAINER|g" \
    "$PROJECT_DIR/deploy/systemd/price-tracker.service" > "$UNIT_DIR/price-tracker.service"
cp "$PROJECT_DIR/deploy/systemd/price-tracker.timer" "$UNIT_DIR/"
docker update --restart unless-stopped "$DB_CONTAINER" >/dev/null
# Lingering lets user timers fire without an open login session.
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now price-tracker.timer
systemctl --user list-timers price-tracker.timer
