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

The repository includes mock and lazy-import MFRC522 backends, an observation-only service, and signed portable card codecs. The legacy Gway adapter commands above still select the mock backend.

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

PR1 also adds the portable `GWY1` command-card codec, including canonical CBOR envelopes, Ed25519 signatures, and MIFARE Classic 1K block layout helpers.

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

## Standalone shell command cards

`gway-rfid command write`, `command inspect`, and explicit `command run` store
and use complete signed POSIX shell programs on cards. The program is portable
without a UID-to-script mapping. Inspection never executes; execution requires
an explicit trusted-issuer directory and refuses root. The scanner service
remains observation-only.

See [shell-card format, examples and execution contract](docs/shell-cards.md)
and `man gway-rfid`. Existing managed-argv cards and label printing are unchanged.
