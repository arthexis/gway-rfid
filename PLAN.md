# gway-rfid extraction plan

## Goal

Extract RFID hardware access and generic tag handling into `gway-rfid` while leaving authorization, balances, OCPP transaction policy, and application state in their owning projects.

## Phase 1 — package boundary and CI

- [x] Create `src/gway_rfid` package.
- [x] Define a small reader-neutral `Reader` protocol.
- [x] Define normalized `Tag` values and UID conversion helpers.
- [x] Add deterministic mock backend for CI/development.
- [x] Register `rfid` through `gway.toml`.
- [x] Add `status`, `scan`, `normalize`, and `doctor` command entry points.
- [x] Configure `arthexis/ci-base` reusable CI workflow.
- [x] Add hardware-free unit tests.

## Phase 2 — inventory and extraction

Locate the deployed RFID scanner implementation and classify each piece before moving it:

1. Reader transport / GPIO / SPI / serial access -> move to `gway-rfid` backend.
2. UID parsing, formatting, duplicate suppression, card-present/card-removed handling -> move to `gway-rfid` core/runtime.
3. Reader diagnostics and recovery -> move to `gway-rfid doctor` or backend status.
4. Service loop whose sole responsibility is scanning -> replace with a generic `gway-rfid` runtime/service.
5. OCPP Authorize/StartTransaction/StopTransaction behavior -> keep in `gway-ocpp`.
6. Allowlists, balances, customer/card records, and business policy -> keep outside `gway-rfid`.

The first concrete hardware backend should preserve the behavior of the reader currently deployed on Gway boxes rather than redesigning it during extraction.

## Phase 3 — hardware backend

Add the existing reader as a backend under `gway_rfid.backends` with optional hardware dependencies. Requirements:

- importing `gway_rfid` must not import Raspberry Pi-only modules;
- construction should fail with a clear diagnostic when required hardware/dependencies are missing;
- backend settings should be explicit arguments/config (bus, device, pins, polling interval as applicable);
- `status()` should report enough information for field diagnostics;
- tests should mock the transport boundary, not physical GPIO/SPI modules globally.

## Phase 4 — runtime behavior

Extract generic scanner-loop behavior without OCPP knowledge:

- configurable polling;
- duplicate/re-read suppression;
- optional wait-for-tag behavior;
- card-present and card-removed semantics if the deployed reader supports them reliably;
- clean shutdown;
- structured result/event values suitable for Gway composition.

Avoid building authorization semantics into this layer. `gway-rfid` reports what the reader saw; callers decide what the tag means.

## Phase 5 — consumers

Update consumers to depend on `gway-rfid`:

- migrate the OCPP RFID path to the public API;
- remove copied reader/UID helpers after parity is proven;
- preserve existing behavior during rollout;
- use the mock backend for consumer CI;
- remove the legacy scanner service only after the new service is verified on the deployed Raspberry Pi.

## Proposed public API

```python
from gway_rfid import Tag
from gway_rfid.backends import MockReader

reader = MockReader(["04:A1:B2:C3"])
tag: Tag | None = reader.scan()
```

The public model intentionally does not expose MFRC522, SPI, GPIO, OCPP, or database concepts.

## Proposed Gway surface

```console
gway rfid status
gway rfid doctor
gway rfid scan
gway rfid normalize --uid 04:A1:B2:C3
```

Backend-specific options should remain arguments to these generic commands rather than becoming separate projects.

## Definition of extraction complete

The extraction is complete when the deployed scanner works through `gway rfid`, OCPP consumes the new package without direct hardware imports, the old reader implementation is deleted from its original project, and CI passes without access to RFID hardware.
