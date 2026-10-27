# Standalone QR label printing

Label support is independent of the deprecated `gway` executable or project registry.
Install optional rendering dependencies with:

```sh
python -m pip install -e ".[printing,dev]"
```

Preview an explicit, non-secret QR payload:

```sh
gway-rfid label preview --text "CARD 001" --title "DEVICE" --output label.png
```

Generate the Phomemo M220 raster job without sending it:

```sh
gway-rfid label print --text "CARD 001" --title "DEVICE" --printer phomemo-m220 --dry-run
gway-rfid printer test
gway-rfid printer devices
```

On Windows only, physical USBPRINT delivery is available using an explicit USB path
(or a single discovered USBPRINT candidate):

```sh
gway-rfid label print --text "CARD 001" --printer phomemo-m220 --usb-path "<Windows USBPRINT interface path>"
```

The port retains the legacy M220 raw command format, including the raster packing,
speed and density settings, and chunked writes. The default label is 320×240 pixels
with a 160-pixel QR code. The contents are *only* what the operator specifies:
no RFID UID, GWY1 payload, command arguments, signatures, or secrets are read or
printed implicitly.

**Limitations:** Physical delivery currently uses the historical Windows USBPRINT
transport only. Linux/Raspberry Pi support requires a separately verified USB
backend and device permissions. A successful job-build or dry run does not
prove a printer is connected or will print correctly. No Gway runtime is
required by the label commands. The remaining legacy RFID command-card
workflow is a separate migration concern.

## Experimental Linux USB transport

Install the optional transport: `python -m pip install -e '.[printing,linux-printing]'`.
Only use after identifying the printer's real VID/PID, bulk OUT endpoint, bus, and USB device address. The inherited VID/PID (`0483:5740`) is not a unique printer identity; device matching alone is insufficient. For example, **after** confirming the device interface:

```sh
gway-rfid label print --text "CARD 001" --printer phomemo-m220 --transport linux --endpoint 0x01 --bus 1 --address 2
```

The example endpoint and address are placeholders, **not verified M220 settings**. Without `--endpoint`, Linux printing refuses to send data. If device selection is ambiguous, it fails rather than selecting a random USB device. It does not detach kernel drivers or change permissions. Check `lsusb` and USB descriptors on the target machine; Linux hardware smoke testing, access permissions, and label feed/alignment are still outstanding.
