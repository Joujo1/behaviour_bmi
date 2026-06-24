# Changing Resolution

Camera resolution and all other camera parameters are defined in one place: [bmi_closed_loop/RPi_main/config.py](../../RPi_main/config.py). No other file needs to be edited to change resolution.

---

## The relevant constants

```python
CAMERA_WIDTH       = 480          # pixels
CAMERA_HEIGHT      = 320          # pixels
CAMERA_FPS         = 60           # frames per second
CAMERA_BITRATE     = 2_000_000    # bits per second (H264 encoder target)
CAMERA_H264_IPERIOD = 60          # keyframe interval in frames (1 keyframe per second at 60 fps)
CAMERA_EXPOSURE_US = 6000         # shutter time in microseconds
CAMERA_GAIN        = 4.0          # analogue gain
```

---

## What each setting affects

**`CAMERA_WIDTH` / `CAMERA_HEIGHT`**: The encoded frame size. Smaller resolution means smaller frame bytes. This is the main lever for reducing UDP packet size.

**`CAMERA_BITRATE`**: The H264 encoder's target output rate. Higher bitrate improves image quality but increases frame size. Combined with resolution, this determines the actual bytes per frame.

**`CAMERA_H264_IPERIOD`**: How often the encoder emits a full keyframe. At 60 fps a value of 60 means one keyframe per second. Lower values give you more seeking points in recordings but increase average frame size.

**`CAMERA_FPS`**: Capture and encode rate. Changing this also changes the effective keyframe interval in wall-clock time.

**`CAMERA_EXPOSURE_US`**: Controls motion blur. The current value of 6000 µs is chosen to freeze rat movement at 60 fps. Increasing it brightens the image but blurs fast movement.

---

## The UDP size constraint

Each H264 frame is sent in a single UDP datagram. The maximum payload for a UDP packet is **65,507 bytes**. If a frame (header + events JSON + H264 frame bytes) exceeds this limit, the packet is silently dropped in `UDPSender._pack_and_send()` in [RPi_main/udp_sender_pi.py](../../RPi_main/udp_sender_pi.py).

Dropped frames show up as sequence-number gaps detected by the acquisition process on the PC. If you increase resolution or bitrate and start seeing frequent frame drops, reduce `CAMERA_BITRATE` first before reducing resolution.

A rough check: at `CAMERA_BITRATE = 2_000_000` bps and 60 fps, the average frame is about 4 kB, well under the 65 kB limit. Raising to 8 Mbps pushes average frame size to ~17 kB — still safe. At very high bitrates or resolutions, P-frames are small but the occasional large I-frame can exceed the limit.

---

## How to change resolution

1. Edit `CAMERA_WIDTH` and `CAMERA_HEIGHT` in [RPi_main/config.py](../../RPi_main/config.py).
2. Restart the Pi service (`sudo systemctl restart pi_bmi_rig`) for the change to take effect — the camera is initialised at startup.
3. If frame drops appear in the acquisition logs, lower `CAMERA_BITRATE` proportionally.

No changes are needed on the PC side: the packet parser reads `jpeg_size` from the header and extracts exactly that many bytes regardless of resolution.
