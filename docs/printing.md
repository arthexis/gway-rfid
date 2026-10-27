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
