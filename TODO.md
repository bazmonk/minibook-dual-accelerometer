# To-do

In roughly sequential order:

- [ ] Further testing on how tablet mode interacts with the system. In
  particular:
    
    - Standby and hibernation.

    - Dual-booting with Windows.

    - Buttons held down while switching in and out of tablet mode.

    - External displays and input devices.

    - Rapid 'flapping' of mode switch.

- [ ] Tune `angle-sensor` to be maximally responsive and reliable. Ensure
  coverage of extreme cases such as:
  
    - Odd orientations (upside down, on its side, folded flat, etc.),
  
    - Usage in motion (in a moving vehicle, on unstable surfaces, handheld,
      etc.)

- [ ] Submit driver and kernel patches for review and inclusion in the mainline
  kernel.

- [ ] Rewrite `angle-sensor` in something more lightweight than Python.

- [ ] Make RPM and deb packages for `angle-sensor` and supporting components.

- [ ] Detect intermediate 'tent' state (hinge position past 180 degrees but not
  folded into tablet position).

- [ ] Figure out what `GMTR` ACPI data (see DSDT section below) is, and make use
  of it if appropriate.

- [ ] Allow characterisation of, and compensation for, Z-axis offset observed on
  some devices.
