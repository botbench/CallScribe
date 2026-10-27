#!/bin/bash
# Run a shell command inside Terminal.app (for System Audio Recording permission).
# Usage: run_in_terminal.app.sh <log-file> <command...>
set -euo pipefail

LOG="${1:?log file}"
shift
CMD="$*"

# Absolute paths in the command help when Terminal starts with a different cwd.
mkdir -p "$(dirname "$LOG")"
: >"$LOG"

# Escape for AppleScript string.
ESC=$(printf '%s' "$CMD" | sed 's/\\/\\\\/g; s/"/\\"/g')

osascript <<EOF
tell application "Terminal"
  activate
  set w to do script "($ESC) > \"$LOG\" 2>&1; echo EXIT:\$? >> \"$LOG\"; exit"
end tell
EOF

echo "Launched in Terminal.app; logging to $LOG"
