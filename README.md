# Dual-accelerometer tablet-mode switching for the Chuwi MiniBook X

## Introduction

A number of 2-in-1 convertible laptops today lack a hardware hinge-position
sensor, and instead use a pair of accelerometers to determine the relative
positions of the base and display. Some such laptops do this transparently in
firmware, but others (such as my Chuwi MiniBook X) require software to
interpret the accelerometer outputs and notify the firmware appropriately. In
the Windows 11 installation that the MiniBook X ships with, this appears to
all be handled inside the accelerometer driver (`mxc6655angle.dll`)

This repo is an attempt to implement a similar 'software angle sensor' for
Linux. Since floating-point math is frowned-upon inside the Linux kernel, we
cannot do this entirely inside a driver as in Windows. Instead, we have
separate driver and userspace components: the kernel exposes accelerometer
data to userspace, and provides a mechanism to notify the firmware of
tablet-mode changes. Meanwhile, on the userspace side, a service interprets
the accelerometer data, and notifies the driver (which in turn notifies the
firmware) of any mode changes.

When the driver triggers a switch into or out tablet mode, the firmware
disables or enables the keyboard and touchpad, and issues an HID
tablet-mode-switch event, just as would happen if there was a physical
switch. Most desktop environments recognise these events, and enable or
disable screen rotation, and change UI elements as appropriate.

## Why reinvent the wheel?

There already exist a couple of userspace solutions for tablet mode on the
MiniBook X, both [manual](https://github.com/lschans/chuwi-tablet) and
[accelerometer-based](https://github.com/petitstrawberry/minibook-support).
However, the manual solution is Gnome-specific and does not make use of the
accelerometers, and the accelerometer-based solution is rather complex (three
separate daemons, and virtual input devices that intercept the built-in
keyboard and touchpad), did not work reliably for me, and essentially
duplicates functionality that already exists to support devices with 'real'
tablet switches.

By leveraging the MiniBook's own firmware to do the tablet-mode switching, we
eliminate this complexity and duplication of effort - userspace sees the same
tablet-mode-switch input events that it would if it had a 'real'
hinge-position sensor, and the firmware handles disabling the keyboard and
trackpad when in tablet mode without needing awkward interception of inputs.

## Status

(see also: [`TODO.md`](TODO.md))

While the driver and angle-sensor service are both currently functional, **I
would consider them to be at the proof-of-concept stage**. Do **not** expect
them to be reliable or stable (or safe) at present. I am notably bad at both
signal-processing and trigonometry, which is basically everything that the
angle-sensor service has to do! I would welcome any suggestions as to how to
do a better job of it.

Once the driver and angle-sensor service have seen a bit more testing and
been proven to work reliably, I would like to try to get the platform driver
into the mainline Linux kernel, and package up the angle sensor service for
easy installation.

This repo contains two different drivers - `platform-driver` contains my
attempt at a proper driver for eventual inclusion in the mainline kernel.
This driver allows both accelerometers to be detected automatically, and
registers a platform device to which it adds a sysfs property for triggering
tablet-mode switching. However, to do this it requires some supporting
patches elsewhere in the kernel, so while it can be built out-of-tree, it
isn't any use without a rebuilt kernel anyway.

`hack-driver` is a quick and dirty hack that simply exposes the tablet-mode
switching method to userspace, without the accelerometer detection feature.
This driver can be built out-of-tree on any kernel, so while it isn't a
complete solution, it's more immediately useful, and its lack of
accelerometer detection can be worked around in user space.

## Supported hardware and software

I run this on my MiniBook X N100 under OpenSUSE Tumbleweed, and don't have the
time or extra hardware to do much testing beyond that. I would very much
appreciate anyone willing to test on other distros, or other similar hardware
(e.g. the earlier N5100 MiniBook X, the 8" MiniBook, other Chuwi convertible
laptops).

## How to install and use

If you've got this far and haven't been scared off yet, the following steps
should get you set up using the 'hack driver' on your existing kernel:

1. Install DKMS, Python 3, and the `numpy` and `pyudev` Python packages.

2. As root, run `make install`, or manually:

    - Install [`hack-driver/60-sensor-chuwi.rules`](udev/60-sensor-chuwi.rules) into
      `/etc/udev/rules.d`.

    - Install [`hack-driver/chuwi-ltsm-hack.rules`](udev/60-sensor-chuwi.rules) into
      `/etc/udev/rules.d`.

    - Install [`angle-sensor-service/angle-sensor.py`](angle-sensor-service/angle-sensor.py)
      to `/usr/local/sbin/angle-sensor` with execute permissions.

    - Install [`angle-sensor-service/chuwi-tablet-control.sh`](angle-sensor-service/chuwi-tablet-control.sh)
      to `/usr/local/sbin/chuwi-tablet-control` with execute permissions.

    - Install [`angle-sensor-service/angle-sensor.sysconfig`](angle-sensor-service/angle-sensor.sysconfig)
      to `/etc/sysconfig/angle-sensor`.

    - Install [`angle-sensor-service/angle-sensor.service`](angle-sensor-service/angle-sensor.service)
      to `/etc/systemd/system/angle-sensor.service`.

    - Build and install the `chuwi-ltsm-hack` kernel module by running 
      `dkms install hack-driver` in this directory.

Running `make uninstall` will uninstall everything and (hopefully) bring your
system back to how it was before.

## Software info

### [Platform Driver](platform-driver/)

#### [Kernel patch](platform-driver/0001-platform-x86-support-for-out-of-tree-MDA6655-dual-ac.patch)

While the dual-accelerometer driver is buildable out-of-tree, supporting changes
are required in the kernel:

`drivers/acpi/scan.c`: Add `MDA6655` to list of device IDs ignored during device
enumeration. This is necessary to allow our driver to instantiate both
accelerometers specified in its hardware resources, instead of one. Note that
this gets built into the kernel itself, rather than a module (otherwise we could
just build and load modified versions of of the `mxc4005` and `intel-hid`
modules rather than rebuilding the whole kernel).

`drivers/iio/accel/mxc4005.c`: Remove `MDA6655` from ACPI ID list. The change
above renders it redundant.

`drivers/platform/x86/intel/hid.c`: Add MiniBook X product and vendor IDs to
`VGBS` method allowlist. This allows the MiniBook X's firmware to send
tablet-state HID events.

#### [`chuwi-dual-accel` kernel module](platform-driver/chuwi-dual-accel.c)

The `chuwi-dual-accel` module is a platform driver that matches the `MDA6655`
device ID. It instantiates two `mxc4005` IIO accelerometer devices, named
`MDA6655-mxc4005.display` and `MDA6655-mxc4005.base`, and creates a write-only
sysfs property named `chuwi_dual_accel_tablet_mode` triggers the `LTSM` ACPI
method - write a single character '`1`' to this property to enter tablet mode,
'`0`' to enter laptop mode (any following characters, and characters other that
'`0`' and '`1`', are ignored).

As a safety measure (since keyboard inputs are disabled in tablet mode), the
driver forces a transition to laptop mode when it is loaded and unloaded.

### [Hack driver](hack-driver/)

The `chuwi-ltsm-hack` module simply adds a `chuwi_ltsm_hack` sysfs file to
`/sys/bus/acpi/MDA6655:00`, that triggers the `LTSM` ACPI method in the same
way as the `chuwi-dual-accel` driver.

The included udev rule takes care of adding the second accelerometer and
loading the hack driver when the first accelerometer is detected, and a
modprobe configuration file is used to allow the `intel-hid` module to
recognise tablet-mode switch events.

### [`angle-sensor`](angle-sensor-service/angle-sensor.py)

`angle-sensor` is a Python script that polls the accelerometers (and lid
switch), and calls a configurable command (e.g. `chuwi-tablet-control`) to take
action when it determines that a tablet-mode change has occurred, based on
accelerometer and lid-switch inputs.

For convenience, the angle sensor service uses the terms 'hinge axis' and 'tilt
axis' when talking about orientation. When looking at the laptop in normal 'in
your lap' orientation, 'hinge axis' rotation is back and forth (in the axis of
the hinge), and 'tilt axis' is left to right, perpendicular to the hinge.

Its basic logic for determining state is:

- If the lid switch is closed, ignore accelerometers and report `CLOSED` state.

- If the change in acceleration since the last poll exceeds more than a certain
  threshold (configurable by `--jerk-threshold`), do nothing, since erratic
  motion will render hinge angle calculations unreliable.

- If the base acceleration vector is off-horizontal on the tilt axis by more
  than a certain amount (configurable by `--tilt-threshold`), do nothing, since
  hinge angle calculation becomes less reliable as the Z component diminshes
  (like how rotation sensing becomes unreliable the further the device is from
  vertical).

- Otherwise, report `LAPTOP` or `TABLET` state based on the hinge-axis angle
  between the display and base acceleration vectors. The criteria for state
  changes can be tuned with `--threshold` and `--hysteresis`.

An additional `TENT` state is defined, but not detected or reported at present.
This state is intended to represent when the hinge is open further than 180
degrees but not fully folded back into 'tablet' position, allowing the laptop to
stand vertically in a portrait orientation.

### [`chuwi-tablet-control`](chuwi-tablet-control/chuwi-tablet-control.sh)

`chuwi-tablet-control` is a simple shell script, designed to be called by
`angle-sensor`, to set the tablet state. It takes a single argument, which can
be one of `CLOSED`, `LAPTOP`, `TENT`, or `TABLET`, and writes `0` or `1` to
`/sys/devices/platform/MDA6655:00/chuwi_dual_accel_tablet_mode` as appropriate.

States are translated to `chuwi_dual_accel_tablet_mode` writes as follows:

| State     | Value written | Comment
|-----------|---------------|--------
| `CLOSED`  | `0`           | Safety measure - always enter laptop mode when lid is closed
| `LAPTOP`  | `0`           |
| `TENT`    | `1`           | Not implemented in `angle-sensor` yet
| `TABLET`  | `1`           |

## Hardware info

Both accelerometers are MEMSIC MXC6655 devices, using a thermal sensing element.
The accelerometer inside the display is at address `0x15` on I<sup>2</sup>C bus
1, and the base accelerometer is at the same address on I<sup>2</sup>C bus 0.

The accelerometers are oriented so that in tablet mode, their
vectors should be roughly pointing in the same direction. Since I can't draw
worth a damn, this table is an attempt to explain the orientation of the
accelerometers while in tablet mode.

|    | + direction                                |
|----|--------------------------------------------|
| X  | In plane of screen, towards camera         |
| Y  | In plane of screen, towards fan            |
| Z  | Normal to keyboard (i.e. away from viewer) |

These orientations do NOT match the suggested orientation given in the kernel
IIO documentation, which suggests for a handheld device with the camera at the
top of the screen:

|    | + direction                                           |
|----|-------------------------------------------------------|
| X  | In plane of screen, towards right hand edge of screen |
| Y  | In plane of screen, towards front-facing camera       |
| Z  | Normal to screen, (i.e. towards viewer)               |

[`udev/60-sensor-chuwi.rules`](udev/60-sensor-chuwi.rules) defines
`ACCEL_MOUNT_MATRIX` properties that transform their vectors into the
IIO-recommended orientation while also compensating for the inherent 90
degree rotation of the MiniBook X's physical display. No suggested
orientation exists for a sensor in the keyboard, but using the same
`ACCEL_MOUNT_MATRIX` as the display is convenient, since this maintains the
property of the vectors being equal when in tablet mode. This information
should really be in the hwdb, but hwdb entries are keyed off of `modalias`
values, which in our case is the same for both sensors, so dedicated rules
based on device path and name are necessary here.

Interestingly both accelerometers on my MiniBook X have a significant, but
stable offset (approximately -6 kg/m<sup>2</sup>) in the Z axis. This impacts
the accuracy of the hinge angle measurement, though not unusably so. This has
also been observed on another unit, so it is likely a design quirk rather than a
fault.

### DSDT

The relevant bits from a disassembly of my MiniBook X N100's DSDT are below.
Note the two `I2cSerialBusV2` resources for the two accelerometers, and the
`LTSM` method that updates the HID switch state and generates 'standard'
tablet-mode and laptop-mode events.

The `GMTR` method looks interesting too - it returns 24 bytes of data (always
`PARB` on my machine). At a guess, it looks to be two 3x3 matrices of signed
8-bit values (almost certainly orientations of the two sensors?), followed by
6 bytes - either a 3-element vector of 16-bit values applying to both
sensors, or two 3-element vectors of 8-bit values, one for each sensor. The
orientation matrices don't look immediately useful to us, and the purpose of
the following data isn't clear - it doesn't make sense as zero-offset
calibration values.

```asl
Device (_SB)
{
    /* ... */

    Device (ACMK)
    {
        Name (_ADR, Zero)  // _ADR: Address
        Name (_HID, "MDA6655")  // _HID: Hardware ID
        Name (_CID, "MDA6655")  // _CID: Compatible ID
        Name (_DDN, "Accelerometer with Angle Calculation")  // _DDN: DOS Device Name
        Name (_UID, One)  // _UID: Unique ID
        Name (_DEP, Package (0x02)  // _DEP: Dependencies
        {
            ^PC00.I2C0, 
            ^PC00.I2C1
        })
        Method (_CRS, 0, NotSerialized)  // _CRS: Current Resource Settings
        {
            Name (RBUF, ResourceTemplate ()
            {
                I2cSerialBusV2 (0x0015, ControllerInitiated, 0x00061A80,
                    AddressingMode7Bit, "\\_SB.PC00.I2C1",
                    0x00, ResourceConsumer, , Exclusive,
                    )
                I2cSerialBusV2 (0x0015, ControllerInitiated, 0x00061A80,
                    AddressingMode7Bit, "\\_SB.PC00.I2C0",
                    0x00, ResourceConsumer, , Exclusive,
                    )
            })
            Return (RBUF) /* \_SB_.ACMK._CRS.RBUF */
        }

        Method (GMTR, 0, Serialized)
        {
            Name (PARA, Buffer (0x18)
            {
                /* 0000 */  0x00, 0xFF, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,  // ........
                /* 0008 */  0x01, 0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00,  // ........
                /* 0010 */  0x00, 0xFF, 0xB9, 0xAF, 0x1E, 0x05, 0x14, 0x10   // ........
            })
            Name (PARB, Buffer (0x18)
            {
                /* 0000 */  0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,  // ........
                /* 0008 */  0x01, 0x01, 0x00, 0x00, 0x00, 0xFF, 0x00, 0x00,  // ........
                /* 0010 */  0x00, 0xFF, 0xB9, 0xAF, 0x1E, 0x05, 0x14, 0x13   // ........
            })
            Name (PARC, Buffer (0x18)
            {
                /* 0000 */  0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00,  // ........
                /* 0008 */  0xFF, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,  // ........
                /* 0010 */  0x00, 0xFF, 0xB9, 0xAF, 0x1E, 0x05, 0x14, 0x10   // ........
            })
            Name (PARD, Buffer (0x18)
            {
                /* 0000 */  0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00,  // ........
                /* 0008 */  0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00,  // ........
                /* 0010 */  0x00, 0xFF, 0xB9, 0xAF, 0x1E, 0x05, 0x14, 0x10   // ........
            })
            If (Ones)
            {
                Return (PARB) /* \_SB_.ACMK.GMTR.PARB */
            }
            Else
            {
                Local0 = 0x0D
                Switch (ToInteger (Local0))
                {
                    Case (0x10)
                    {
                        Return (PARC) /* \_SB_.ACMK.GMTR.PARC */
                    }
                    Case (0x05)
                    {
                        Return (PARD) /* \_SB_.ACMK.GMTR.PARD */
                    }
                    Default
                    {
                        Return (PARA) /* \_SB_.ACMK.GMTR.PARA */
                    }

                }
            }
        }

        Method (_STA, 0, NotSerialized)  // _STA: Status
        {
            If (Ones)
            {
                If ((GGIV (0x09080011) == Zero))
                {
                    Return (0x0F)
                }

                Return (Zero)
            }

            If (Ones)
            {
                If (Ones)
                {
                    Return (0x0F)
                }

                Return (Zero)
            }

            Return (Zero)
        }

        Method (PRIM, 0, NotSerialized)
        {
            Name (RBUF, Buffer (One)
            {
                    0x01                                             // .
            })
            Return (RBUF) /* \_SB_.ACMK.PRIM.RBUF */
        }

        Method (LTSM, 1, NotSerialized)
        {
            If ((Arg0 == Zero))
            {
                ^^PC00.LPCB.H_EC.KBCD = Zero
                PB1E |= 0x08
                ADBG ("UPBT(LTSM) Laptop Start")
                ^^PC00.LPCB.H_EC.UPBT (0x06, One)
                Notify (HIDD, 0xCD) // Hardware-Specific
            }
            Else
            {
                ^^PC00.LPCB.H_EC.KBCD = 0x03
                PB1E &= 0xF7
                ADBG ("UPBT(LTSM) Slate Start")
                ^^PC00.LPCB.H_EC.UPBT (0x06, Zero)
                Notify (HIDD, 0xCC) // Hardware-Specific
            }
        }
    }
}
```
