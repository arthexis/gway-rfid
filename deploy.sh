#!/bin/sh
set -eu
if [ "$(id -u)" -eq 0 ]; then
  echo "Run deployment as the appliance account, not root." >&2
  exit 1
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Print per-task durations without exposing task inputs or results.
export ANSIBLE_CALLBACK_PLUGINS="$ROOT/ansible/callback_plugins${ANSIBLE_CALLBACK_PLUGINS:+:$ANSIBLE_CALLBACK_PLUGINS}"
export ANSIBLE_CALLBACKS_ENABLED="rfid_task_timing${ANSIBLE_CALLBACKS_ENABLED:+,$ANSIBLE_CALLBACKS_ENABLED}"
exec ansible-playbook "$ROOT/ansible/playbooks/install.yml" -i localhost, -c local "$@"
