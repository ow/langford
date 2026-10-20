#!/usr/bin/env bash
# Render the *.plist.template files for this checkout/user into ~/Library/LaunchAgents.
# Usage: data/langford/install-launchd-workers.sh [--load]
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
dest="$HOME/Library/LaunchAgents"
mkdir -p "$dest" "$here/logs"
for tpl in "$here"/*.plist.template; do
  out="$dest/$(basename "${tpl%.template}")"
  sed -e "s#__REPO_ROOT__#$repo_root#g" -e "s#__HOME__#$HOME#g" "$tpl" > "$out"
  echo "wrote $out"
  [[ "${1:-}" == "--load" ]] && launchctl bootstrap "gui/$(id -u)" "$out"
done
