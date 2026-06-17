#!/bin/zsh
set -e

PLIST_PATH="$HOME/Library/LaunchAgents/com.ai-marketing-digest.daily.plist"

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "Schedulazione giornaliera rimossa."
read "unused?Premi Invio per chiudere..."
