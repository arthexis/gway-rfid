#!/bin/sh
set -eu
if [ "$(id -u)" -eq 0 ]; then
  echo "Run deployment as the appliance account, not root." >&2
  exit 1
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Skip only when the active immutable release matches HEAD and is healthy.
if [ "$#" -eq 0 ]; then
  revision=$(git -C "$ROOT" rev-parse --verify HEAD)
  prefix="$HOME/.local/share/gway-rfid"
  release="$prefix/releases/$revision"
  if [ "$(readlink "$prefix/current" 2>/dev/null || true)" = "$release" ] &&
     [ -x "$release/venv/bin/python" ] &&
     "$release/venv/bin/python" -c "import gway_rfid; from importlib.metadata import version; assert version('gway-rfid')" >/dev/null 2>&1 &&
     systemctl is-enabled --quiet gway-rfid.service &&
     systemctl is-active --quiet gway-rfid.service; then
    printf 'RFID revision %s already installed and healthy; skipped Ansible.\n' "$revision"
    exit 0
  fi
fi
# Print per-task durations without exposing task inputs or results.
export ANSIBLE_CALLBACK_PLUGINS="$ROOT/ansible/callback_plugins${ANSIBLE_CALLBACK_PLUGINS:+:$ANSIBLE_CALLBACK_PLUGINS}"
export ANSIBLE_CALLBACKS_ENABLED="rfid_task_timing${ANSIBLE_CALLBACKS_ENABLED:+,$ANSIBLE_CALLBACKS_ENABLED}"
exec ansible-playbook "$ROOT/ansible/playbooks/install.yml" -i localhost, -c local "$@"
