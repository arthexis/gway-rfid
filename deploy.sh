#!/bin/sh
set -eu
if [ "$(id -u)" -eq 0 ]; then
  echo "Run deployment as the appliance account, not root." >&2
  exit 1
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec ansible-playbook "$ROOT/ansible/playbooks/install.yml" -i localhost, -c local "$@"
