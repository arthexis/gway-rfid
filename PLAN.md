# gway-rfid extraction and portable command-card plan

## Goal

Make `gway-rfid` the owner of generic RFID hardware, card-presence tracking,
portable command-card encoding, and command delivery to Gway.

A command card carries its complete Gway invocation. The UID is useful for
presence tracking and caching, but it is not an authoritative lookup key for a
command. A card can therefore move to another Gway system, or be copied to a
card with a different UID, without copying an ID-to-command database.

Authorization, balances, OCPP transaction policy, and other application state
remain in their owning projects.

## Design rules

- There is one command-reading path. Do not expose separate quick-read,
  deep-read, or hold-to-read modes.
- Run or durably enqueue a command as soon as its complete verified invocation
  is available, whether it came from cache or card blocks.
- Read one fixed header block to identify the current content. On a cache miss,
  read only the payload blocks required to construct the complete command and
  ignore the rest of the card.
- Execute a command at most once for each continuous card presence. Removing
  and presenting the card begins a new presence and permits another execution.
- Store an argument vector, never a shell command string. Dispatch without a
  shell through Gway's managed-command boundary.
- Keep project names and command paths literal. Sigils may occur in argument
  values and are resolved by Gway after card verification.
- Treat the card as the source of truth. UID and content caches are disposable
  accelerators and must never become required command mappings.
- Keep Raspberry Pi-only imports inside hardware backend modules so package
  import and tests remain hardware-independent.
- Only one service may own the physical RFID reader at a time.

## Phase 1 - package boundary and CI

- [x] Create the `src/gway_rfid` package.
- [x] Define a small reader-neutral `Reader` protocol.
- [x] Define normalized `Tag` values and UID conversion helpers.
- [x] Add a deterministic mock backend for CI and development.
- [x] Register `rfid` through `gway.toml`.
- [x] Add `status`, `scan`, `normalize`, and `doctor` command entry points.
- [x] Configure the shared `arthexis/ci-base` workflow.
- [x] Add hardware-free unit tests.

## Target command flow

```text
RFID card
  -> gway-rfid reader and presence tracker
  -> read fixed command header
  -> verified content cache, or exact-length payload read
  -> durable command queue
  -> Gway source-aware validation and dispatch
  -> managed project command, for example: gway device examine eth0
```

The queue record contains an immutable copy of the decoded command envelope.
The card may be removed after the envelope has been read. If another command is
already running, the new command is queued immediately rather than delayed
until card removal.

## Portable command-card format

### Header

Use a new `GWY1` layout so portable Gway commands cannot be confused with the
database-backed Arthexis `AXC1` layout.

The first implementation targets MIFARE Classic 1K cards. One fixed 16-byte
data block contains:

```text
magic (GWY1) | version | flags | payload length | 64-bit content ID
```

The content ID is derived from the complete canonical signed envelope. It is a
fast cache key and change detector; the envelope signature provides
authenticity. The payload length determines exactly how many ordered data
blocks to read. Readers reject impossible lengths before attempting additional
blocks.

Payload blocks are read in a documented order that skips the manufacturer
block and sector trailers. Reading stops after `ceil(payload_length / 16)`
payload blocks. The runtime must not scan unused command sectors, result
sectors, or the remainder of the card.

Command sectors use a deterministic read profile available to every compatible
Gway reader. Writer credentials remain separately provisioned. MIFARE Classic
access keys alone are not treated as proof that a command is trusted.

### Envelope

The command remains logically textual and structured: `argv` is an argument
vector of literal strings, never a shell command and never an opcode table.
Human-facing tools represent an envelope as JSON, for example:

```json
{
  "v": 1,
  "argv": ["device", "examine", "eth0"],
  "label": "AUTO EXAM",
  "issuer": "operations",
  "sig": "..."
}
```

The on-card and signed representation is deterministic canonical CBOR, not
JSON text. JSON is the diagnostic and interchange representation used by tools
such as `inspect`; it is not part of the wire format. The wire contract is the
canonical CBOR byte sequence itself. This keeps commands readable at the
tooling boundary while reducing card usage and eliminating JSON whitespace,
escaping, and key-order ambiguity from signatures.

`argv` contains the managed project, command path, and arguments after the
`gway` executable name. The project and command components are literal.
Argument strings may contain Sigils for host-local resolution. Sigils remain
ordinary text inside the argument vector and are signed unresolved; Gway
resolves them only after card verification on the target host.

The signature covers the deterministic CBOR encoding of the envelope without
`sig`. It does not cover the UID, allowing the same command to be replicated on
a different physical card. Ed25519 is the preferred initial signature scheme.
Reader nodes receive trusted public keys; only card writers receive private
keys. Unsigned command execution is limited to an explicitly enabled
mock/development mode.

The complete signed envelope is then encoded as deterministic CBOR for card
storage. The content ID is derived from those canonical signed-envelope bytes,
so the same logical signed command produces the same content ID independent of
how a human-facing JSON view is formatted.

The first format does not reserve space for execution results. Results and
audit records remain local, preserving card capacity and avoiding repeated
writes to the card.

### Transactional writes

Writers prevent a reader from accepting a partially updated command:

1. Invalidate the header block.
2. Write the new payload blocks.
3. Read back and verify the payload.
4. Commit the final header containing the new length and content ID.
5. Read back and verify the committed header.

The writer fails before the first mutation if the envelope does not fit the
supported card layout.

## Unified read and execution path

For every newly observed presence:

1. Normalize the UID and create a presence generation for the reader.
2. Read and validate the fixed command header.
3. Look up the content ID in the verified content cache.
4. On a cache hit, recheck the cached signature and current Gway command policy
   as needed, then enqueue the cached invocation immediately.
5. On a cache miss, read only the declared payload blocks. Stop when the full
   envelope has been assembled.
6. Verify the content ID, decode the envelope, verify its signature, and ask
   Gway to validate the invocation for the `rfid` source.
7. Store the verified envelope in the cache and enqueue it immediately.
8. Mark the presence executed so polling cannot retrigger it while held.
9. End the presence after a reliable removal gap. A later presentation may run
   the command again.

There is no artificial delay before reading and no release-triggered delivery.
On a cache miss, execution begins as soon as the minimum required blocks have
been read and verified.

If the header cannot be read, retry it while the card remains present. Do not
fall back to a command selected by UID alone because the runtime cannot then
know whether the card was rewritten.

## Presence and content caches

Keep separate presence and content state:

```text
reader ID -> current UID, content ID, presence generation, execution state
UID -> last observed content ID
content ID -> canonical envelope, signature status, validation metadata
```

Suggested system paths are:

```text
/var/lib/gway-rfid/presence.json
/var/lib/gway-rfid/content/
/var/lib/gway-rfid/queue/{pending,processing,done,failed}/
/etc/gway/rfid/trusted-issuers.d/
```

UID-bearing state is local, mode `0600`, bounded by retention settings, and not
included in normal command output. The cache may be deleted and rebuilt by
reading cards; it is not a shared database.

Reread payload blocks when:

- the content ID differs from the value previously observed for the UID;
- the content entry is absent, corrupt, or uses an incompatible cache schema;
- a forced audit or configured maximum cache age requires physical
  revalidation; or
- the header declares a card-format version that requires another decoder.

A trusted-issuer or Gway policy change does not inherently require another
physical read because the cache retains the original signed envelope. Reverify
the cached signature and revalidate the invocation instead.

## Gway command legality

`gway-rfid` must not decide command legality by maintaining its own command
catalog. A card invocation is executable only when:

1. the target is an installed, registered Gway managed project;
2. Gway discovers the exact managed command path;
3. all card arguments bind successfully to the command parameters;
4. the project manifest permits invocation from the `rfid` source;
5. the card signature is trusted; and
6. the RFID service account has the required operating-system permissions.

Gway lifecycle operations such as `install`, `upgrade`, and `service` are not
managed project commands and must never be accepted from cards.

Both card writing and card execution validate the invocation. Write-time
validation gives the operator immediate feedback; execution-time validation
protects a target whose installed projects or policies differ from the writer.

## Hardware backend

Extract the deployed MFRC522 SPI/GPIO implementation from
[`arthexis/gway-ap-kiosk`](https://github.com/arthexis/gway-ap-kiosk) into a
backend under `gway_rfid.backends`.

The backend contract should distinguish:

- presence observation and UID normalization;
- reading one authenticated block;
- writing one authenticated block with readback;
- reader status and recovery; and
- clean shutdown and crypto-session cleanup.

Do not add a generic `deep_read()` operation. The command-card reader owns the
incremental algorithm and asks the backend only for the header and required
payload blocks. Tests mock the block transport boundary rather than importing
physical GPIO or SPI modules globally.

## Runtime and service

The `gway-rfid` service owns:

- configurable polling and removal detection;
- one execution per presence;
- header-first cache selection;
- incremental command assembly;
- signature and content verification;
- durable FIFO enqueue, claim, completion, and restart recovery;
- bounded UID-safe operational logging; and
- dispatch through Gway without a shell.

The runtime does not own OCPP authorization, customer records, balances,
device-specific implementation, or application databases.

Legacy multi-card navigation, `new.sh`, `hold.sh`, interrupt markers, and
next-card consumers are not translated into hidden scanner semantics. Each
retained behavior must become an explicit managed Gway command or remain on the
legacy runner until its behavior has been modeled and reviewed.

## Proposed Gway surface

Existing commands remain:

```console
gway rfid status
gway rfid doctor
gway rfid scan
gway rfid normalize --uid 04:A1:B2:C3
```

The portable command-card work adds commands along these lines:

```console
gway rfid inspect
gway rfid write-command --label "AUTO EXAM" -- device examine eth0
gway rfid cache-status
gway rfid queue-status
```

`inspect` reads and verifies a card without executing it. `write-command`
validates the target invocation through Gway before encoding it, writes the
payload transactionally, and verifies readback. Exact CLI spelling will be
settled with adapter tests before it becomes public API.

## Required pull requests

### This repository: `gway-rfid`

1. **Portable card format and codec**
   - Specify `GWY1`, deterministic canonical CBOR envelopes, signatures, exact
     block ordering, transactional writes, JSON inspection views, and capacity
     failures.
   - Add memory-card/mock transport tests covering cache IDs and incremental
     reads.
2. **MFRC522 backend and card tools**
   - Extract reader access from `gway-ap-kiosk`.
   - Add header/payload read, transactional write, inspect, and readback tests.
3. **Presence cache, durable queue, and service**
   - Add content-addressed caching, exactly-once-per-presence behavior,
     immediate enqueue, restart recovery, and Gway dispatch.
4. **Legacy migration tooling**
   - Inventory mappings without publishing UIDs, classify portable one-shot
     commands, guide physical reburning, and report behaviors that require new
     managed commands.

### [`arthexis/gway`](https://github.com/arthexis/gway)

Add one framework-neutral source-aware invocation PR:

- extend managed command metadata and `gway.toml` with allowed invocation
  sources;
- add a stable invocation object and validation API;
- provide an atomic `gway invoke --source rfid` path for validation and
  dispatch;
- ensure project and command resolution, argument binding, Sigil resolution,
  and execution use the normal dispatcher; and
- reject core lifecycle operations at this boundary.

The source name is opaque metadata to Gway core; RFID-specific trust,
signatures, caching, and presence behavior stay in `gway-rfid`.

### [`arthexis/gway-device`](https://github.com/arthexis/gway-device)

Use two reviewable PRs:

1. Move the evidence-acquisition engine and focused tests from
   `gway-field-usb` into an internal device module. Preserve read-only defaults
   and require explicit options for active discovery, protocol probes, serial
   reads, or USB gadget changes.
2. Expose a typed `examine()` function as `gway device examine`, return
   structured evidence, and declare the command eligible for the `rfid`
   invocation source.

A portable card can then contain a short invocation such as
`["device", "examine", "eth0"]` rather than a host-local script path.

### [`arthexis/sigils`](https://github.com/arthexis/sigils)

No initial PR is required. Gway already keeps project and command paths literal
and resolves Sigils in argument values. Sign the unresolved card envelope, then
let Gway resolve argument values on the target host. Cross-project coverage for
this behavior belongs in the Gway invocation PR.

Open a Sigils PR only if a future card-format version needs a new compact
structured-value encoding; the initial CBOR argument vector does not.

### [`arthexis/gway-field-usb`](https://github.com/arthexis/gway-field-usb)

After `gway device examine` reaches parity, replace the installed `examine`
implementation with a compatibility wrapper that delegates evidence
acquisition to `gway device examine`. Preserve necessary legacy report, LCD,
email, and saved-artifact behavior during the transition, then remove the
duplicate probe engine in a follow-up cleanup.

The local `rfid-examine-trigger` wrapper becomes unnecessary when cards invoke
the managed device command directly.

### [`arthexis/gway-ap-kiosk`](https://github.com/arthexis/gway-ap-kiosk)

After the new RFID service passes hardware validation:

- stop installing the legacy RFID publisher and UID-to-script runner;
- remove the artificial deep-read hold window, release-triggered delivery, and
  full-card scanning from the deployed path;
- retain the local mapping tree as rollback evidence until all wanted cards
  are migrated or intentionally retired; and
- delete copied RFID hardware code only after source/install parity and
  physical cutover are proven.

### [`arthexis/gway-box`](https://github.com/arthexis/gway-box)

Update appliance composition after the implementation PRs merge:

- install compatible `gway`, `gway-device`, and `gway-rfid` releases;
- install and verify the `gway-rfid` service;
- assert that exactly one service owns the reader;
- include source-ownership and command-surface checks; and
- keep legacy service rollback documented for one release cycle.

## Rollout sequence

1. Merge the portable format and Gway invocation contracts.
2. Land the `gway-device` examine engine and public command.
3. Validate format, cache, and dispatch behavior with mock readers and recorded
   redacted block fixtures.
4. Stop the legacy reader service for a controlled MFRC522 smoke test; never
   run both reader owners concurrently.
5. Write and verify a harmless portable device command card, followed by an
   `examine` card.
6. Prove cache miss and hit behavior, removal/rescan, held-card suppression,
   queue recovery, and restart behavior on the first node.
7. Present the same card on a second Gway node with the same trusted public key
   and required managed projects. Do not transfer a UID mapping or database.
8. Copy the same signed command to a card with another UID and prove equivalent
   behavior.
9. Verify rejection of tampered, unsigned, unknown, unavailable, and
   non-RFID-eligible commands.
10. Switch the live reader service, migrate retained one-shot cards, and leave
    the disabled legacy services and mappings available for rollback through
    one release cycle.
11. Merge legacy source-removal and appliance-composition PRs only after the
    physical and cross-node checks pass.

## Acceptance criteria

- A cache hit reads the UID/presence and one header block, then immediately
  enqueues the verified cached command.
- A cache miss reads the header plus exactly
  `ceil(payload_length / 16)` payload blocks.
- No sector trailer or block after the completed command is read.
- A changed content ID forces a payload reread even when the UID is unchanged.
- A missing, corrupt, incomplete, or digest-mismatched payload never falls back
  to stale UID-selected content.
- A held card executes once; removal and presentation permit another
  execution.
- Restart recovery does not duplicate an already queued command.
- A command copied to another UID executes without a shared database.
- Gway rejects unavailable commands, invalid arguments, disallowed invocation
  sources, and lifecycle operations.
- Tampered or untrusted command envelopes do not execute.
- Normal status and logs do not reveal raw UIDs, card keys, or signing keys.
- Hardware-free tests pass on CI, and physical validation covers the deployed
  MFRC522 reader before legacy service removal.

## Definition of extraction complete

The extraction is complete when:

- the deployed reader works through the `gway-rfid` service;
- command cards execute from their own verified content without UID mappings;
- cache hits and exact-length card reads follow this plan;
- `gway device examine` replaces host-local RFID examine sidecars;
- consumers use the public `gway-rfid` API without direct hardware imports;
- the old scanner/runner is disabled and then removed after the rollback
  window; and
- CI plus physical, restart, and cross-node portability checks pass.
