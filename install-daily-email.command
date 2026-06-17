#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.ai-marketing-digest.daily.plist"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-marketing-digest.daily</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$PROJECT_DIR/run-daily-email.command</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>$LOG_DIR/daily.out.log</string>

  <key>StandardErrorPath</key>
  <string>$LOG_DIR/daily.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"

echo ""
echo "Schedulazione installata."
echo "Il digest verra' inviato ogni giorno alle 08:30 quando il Mac e' acceso."
echo ""
echo "Log:"
echo "$LOG_DIR/daily.out.log"
echo "$LOG_DIR/daily.err.log"
echo ""
read "unused?Premi Invio per chiudere..."
