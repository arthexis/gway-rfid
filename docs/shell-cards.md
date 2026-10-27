# Shell programs stored on RFID cards

A shell card contains the complete UTF-8 POSIX shell program, not a UID lookup
or a reference to a host-local script. Pipelines, quoting, redirections and
multiple lines are preserved byte-for-byte. The card also carries its issuer,
label, timeout and Ed25519 signature. Copying those data blocks to a different
UID preserves the program and signature.

This opt-in capability implements issue #22. It is separate from the managed
`argv` envelope in codec.py and from observation-only scanner issues #9/#13.
The existing scanner service **does not execute shell cards**. This increment
provides explicit one-shot write, inspect and run tools; automatic presence,
queue and execution integration remains separate work.

## Format

The existing 16-byte `GWY1` header is unchanged. `flags=1` means a shell program;
all other flag values are rejected by the shell reader. The existing managed
`argv` decoder rejects the shell envelope's fields. Payload blocks begin at
block 2, skip sector trailers, and occupy only the declared length. The Classic
1K layout provides 736 bytes for the *entire signed envelope*. Script capacity
is lower and depends on the label and issuer lengths. Oversized programs fail
before image creation or physical-reader access. Programs are never silently
truncated or replaced with a local path.

Canonical CBOR map, shown here conceptually as JSON:

```json
{
  "v": 1,
  "kind": "shell",
  "script": "printf '%s\\n' 'hello world' | tr a-z A-Z\n",
  "issuer": "operations",
  "label": "HELLO",
  "timeout": 30,
  "sig": "64 binary Ed25519 signature bytes on the wire"
}
```

The signature covers `b"gway-rfid:shell:v1\x00"` followed by the canonical map
without `sig`. This domain separation prevents reuse of an ordinary managed
command signature. UID is deliberately excluded. Header content ID remains the
first 64 bits of SHA-256 over the complete signed payload; it is a corruption
check, never an authentication substitute. Version must be integer 1; timeout
must be an integer from 1 through 300 seconds. Unknown fields, malformed CBOR,
noncanonical representations, invalid UTF-8 and NUL-containing scripts fail.

Writes invalidate the header, write and verify each required data block, then
commit and verify the header. Manufacturer block 0 and sector trailers are
never written. Failures during payload writing leave an invalid header.
MFRC522 writes authenticate and read back each data block. A write is not a
whole-card backup; sector access keys are not changed.

## Writer and reader trust

Only writers need the private key. Reader nodes need an explicitly supplied
trust directory containing `<issuer>.pem` Ed25519 public keys. Issuer names are
restricted to 1–32 letters, digits, underscores or hyphens, starting with a
letter or digit. Revocation is removal of the public-key file: each explicit
run reloads trust and rechecks the signature; there is no trusted UID cache.

For a test writer, prepare keys outside the checkout (never put credentials or
private keys in a command program):

```sh
umask 077
mkdir -p ~/.config/gway-rfid/writer ~/.config/gway-rfid/trusted-shell-issuers
openssl genpkey -algorithm ED25519 -out ~/.config/gway-rfid/writer/operations.pem
openssl pkey -in ~/.config/gway-rfid/writer/operations.pem -pubout \
  -out ~/.config/gway-rfid/trusted-shell-issuers/operations.pem
```

Create `program.sh` containing the complete program you want to store, for
example `date -u > /tmp/gway-card-demo.txt`.

## Hardware-free image workflow

```sh
gway-rfid command write --image /tmp/command-card.bin \
  --script-file program.sh --issuer operations --label DEMO \
  --signing-key ~/.config/gway-rfid/writer/operations.pem

gway-rfid command inspect --image /tmp/command-card.bin \
  --trusted-issuers ~/.config/gway-rfid/trusted-shell-issuers

gway-rfid command run --image /tmp/command-card.bin \
  --trusted-issuers ~/.config/gway-rfid/trusted-shell-issuers
```

Images are exactly 1024 bytes and newly created with permissions `0600`.
Replacing an existing image requires `--overwrite`. Inspection reports metadata
and signature status; program text is hidden unless `--show-script` is supplied.
Unverified inspection is supported without a trust directory and explicitly
reports `verified: false`. Inspection never executes.

## Physical cards

During an approved exclusive-reader window, use a disposable Classic 1K card.
Replace `--image /tmp/command-card.bin` with `--reader mfrc522`. Physical writes
also require `--overwrite`. The existing SPI advisory lock prevents competing
cooperating readers; these tools never stop or restart another reader service.
There is one immediate card-selection attempt; no card present returns an error.
Remove the card only after successful write/readback.

Default block access uses the factory key A. For a different provisioned key,
use `--card-key-file /protected/path` containing exactly six raw bytes and
`--card-key-type A` or `B`. Access keys never appear in command arguments or
normal output. No key probing or access-bit rewriting is performed.

## Execution contract

`command run` is explicit trusted-code execution as the invoking non-root user.
It is **not a sandbox**. A trusted issuer may execute arbitrary code with that
account's filesystem and network permissions. Signature verification does not
prove a program is harmless. Keep the trust directory and writer key under
operator control; do not grant its keys to unknown writers.

Execution refuses root, verifies the current trust/signature, then starts fixed
`/bin/sh -s` with the program on stdin, a working directory of `/`, and only
`PATH=/usr/local/bin:/usr/bin:/bin` and `LANG=C.UTF-8` in the environment. Neither
program text nor caller credentials enter process arguments. Stdout and stderr
are discarded rather than retained in reports. Programs must write intended
artifacts explicitly. Exit status is returned as JSON and as the CLI status.

The effective timeout is the smaller of the signed timeout and the local
`--max-timeout` (default 30, maximum 300 seconds). On timeout or completion,
remaining children in the process group are killed and the shell is reaped.
This does not constrain a trusted program that deliberately creates a separate
session. Each explicit invocation may execute again; automatic once-per-presence
semantics and durable queueing are not claimed by these tools.

## Validation boundaries

CI uses generated test keys, memory transports, card images, fake MFRC522
hardware and harmless local shell programs. No test accesses live SPI, changes
services or writes a physical tag. Field acceptance still needs a disposable
card write/readback, trusted execution, tamper rejection and portability to a
second node. Do not infer those results from CI or merge status.
