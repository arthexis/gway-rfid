# gway-rfid

Gway-native RFID reader abstraction, diagnostics, and tag scanning.

`gway-rfid` owns generic RFID hardware access and normalized tag observations. It deliberately does **not** own OCPP authorization, balances, allowlists, customer records, or transaction policy.

## Install

For normal Gway installation:

```console
sudo gway install rfid
```

For development:

```console
python -m pip install -e ".[dev]"
```

## Gway project

`gway.toml` exposes this package as the `rfid` project through the Python adapter.

The initial command surface is:

```console
gway rfid status
gway rfid doctor
gway rfid scan
gway rfid normalize --uid 04:A1:B2:C3
```

The repository currently ships a mock backend only. This is intentional: the first milestone establishes the package boundary and CI contract before moving the deployed hardware implementation.

For a deterministic development scan:

```console
gway rfid scan --backend mock --uid 04:A1:B2:C3
```

## Python API

The public API is reader-neutral:

```python
from gway_rfid import Reader, Tag, normalize_uid
from gway_rfid.backends import MockReader

reader: Reader = MockReader(["04:A1:B2:C3"])
tag = reader.scan()

if tag:
    print(tag.uid_hex)
```

A backend needs only two basic operations: `scan()` and `status()`. Hardware-specific imports stay inside backend modules so importing the package remains safe on CI and non-Raspberry-Pi systems.

## Package boundary

Belongs in `gway-rfid`:

- reader transports and hardware backends;
- UID normalization;
- tag observations;
- duplicate/re-read suppression;
- generic scanner loops;
- reader diagnostics and recovery;
- mock/test readers.

Does not belong in `gway-rfid`:

- OCPP Authorize/StartTransaction/StopTransaction policy;
- card balances or customer records;
- charger state machines;
- application-specific allowlists;
- business rules attached to a scanned UID.

See `PLAN.md` for the staged extraction and migration plan.

## CI

The repository uses the shared `arthexis/ci-base` `v1` reusable workflow, matching the current Gway hardware-package pattern:

```yaml
jobs:
  python:
    uses: arthexis/ci-base/.github/workflows/consumer-ci.yml@v1
    with:
      install-command: python -m pip install -e ".[dev]"
```

All initial tests run against the mock backend and require no RFID hardware, GPIO, or SPI access.
