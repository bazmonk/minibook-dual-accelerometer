#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+

# Screen hinge angle detection service for 2-in-1 'yoga' style laptops with
# dual-accelerometer hinge angle sensors.
#
# Copyright 2024, Richard Halkyard <rhalkyard@gmail.com>

import argparse
import datetime
import enum
import logging
import numpy as np
import os
import pyudev
import re
import shlex
import signal
import subprocess
import sys
import time

from typing import Optional


logger = logging.getLogger(os.path.split(sys.argv[0])[-1])


# https://stackoverflow.com/questions/18499497/how-to-process-sigterm-signal-gracefully
class GracefulKiller:
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.kill_now = False

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


class TabletState(enum.Enum):
    UNKNOWN = 0
    CLOSED = 1
    LAPTOP = 2
#    TENT = 3    # TODO
    TABLET = 4


def angle_within(theta: float, target: float, tolerance: float):
    """
    Determine whether angle theta is within +-tolerance degrees of angle
    target.
    """
    delta = abs(theta - target)
    return min(delta, 360-delta) <= tolerance


def magnitude(v):
    """Return magnitude of vector v"""
    return np.sqrt(np.dot(v,v))


class Accel:
    @classmethod
    def parse_mount_matrix(cls, mountmatrix: str):
        """Parse a udev-style accelerometer mount matrix string. Returns a Numpy
        matrix"""
        return np.array([[int(val) for val in row.split(',')]
                        for row in mountmatrix.split(';')])

    @classmethod
    def get(cls, pyudev_ctx: pyudev.Context, location: str,
            device_file: Optional[str] = None,
            transform_string: Optional[str] = None):
        """
        Find an accelerometer in a given location
        """

        if device_file is None:
            devices = list(pyudev_ctx.list_devices(ACCEL_LOCATION=location))
            if len(devices) < 1:
                raise Exception(f'Could not find any accelerometers in udev '
                                f'with ACCEL_LOCATION={location}.')
            if len(devices) > 1:
                logger.warning(f'Found {len(devices)} accelerometers in udev '
                            f'with ACCEL_LOCATION={location}:')
                for device in devices:
                    logger.warning(f'\t\t{device.sys_path}')
                logger.warning(f'Using the first one.')
            device = devices[0]
        else:
            device = pyudev.Device.from_device_file(pyudev_ctx, device_file)

        logger.info(f'Using {device.sys_path} for accelerometer location '
                    f'\'{location}\'.')

        if transform_string is None:
            return cls(device)
        else:
            return cls(device, cls.parse_mount_matrix(transform_string))

    def __init__(self, dev: pyudev.Device, transform: Optional[str] = None):
        self.dev = dev

        if transform is None:
            try:
                mountmatrix = self.dev.properties['ACCEL_MOUNT_MATRIX']
                logger.info(f'Found ACCEL_MOUNT_MATRIX property for '
                            f'{self.dev.device_path}.')
                transform = self.parse_mount_matrix(mountmatrix)
            except KeyError:
                transform = None

        if transform is not None:
            logger.info(f'Accelerometer {self.dev.device_path} using '
                        f'transformation matrix:')
            for line in str(transform).splitlines():
                logger.info(f'\t\t{line}')

        self.transform = transform

    def read_attr(self, attr: str):
        with open(os.path.join(self.dev.sys_path, attr), 'r') as f:
            return f.read()

    def read_raw(self):
        x = int(self.read_attr('in_accel_x_raw'))
        y = int(self.read_attr('in_accel_y_raw'))
        z = int(self.read_attr('in_accel_z_raw'))

        return (x,y,z)

    def read(self):
        scale = float(self.read_attr('in_accel_scale'))
        vec = np.array(tuple(v * scale for v in self.read_raw()))
        if self.transform is not None:
            vec = vec @ self.transform
        return vec


class LidSwitch:
    def __init__(self, path: str):
        self.path = os.path.join(path, 'state')

    @property
    def state(self):
        with open(self.path, 'r') as f:
            return re.match(r'state:\s+(\S+)', f.read()).group(1)


class Tablet:
    def __init__(self, base_accel: Accel, display_accel: Accel,
                 lid_switch: LidSwitch, threshold: float = 45,
                 hysteresis: float = 20, tilt_threshold: float = 20,
                 jerk_threshold: float = 6,
                 trigger_command: Optional[str] = None):
        self.base_accel = base_accel
        self.display_accel = display_accel
        self.lid_switch = lid_switch
        self.trigger_command = trigger_command
        self.threshold = threshold
        self.hysteresis = hysteresis
        self.tilt_threshold = tilt_threshold
        self.jerk_threshold = jerk_threshold

        # Timestamp of last poll
        self.last_poll = None

        # Current tablet mode state
        self.tablet_state = TabletState.UNKNOWN

        # Acceleration vector of the base and display at last poll
        self.base_vector = None
        self.display_vector = None

        # Jerk (rate of acceleration change) vector of the base
        self.base_jerk = None

        # Angle (relative to horizontal) of the display and base in the hinge
        # (X-Z) axis
        self.base_angle = None
        self.display_angle = None

        # Angle (relative to horizontal) of the base in the tilt (Y-Z) axis
        self.base_tilt = None

    def poll(self):
        """Poll the accelerometers and record current vectors and angles"""
        now = datetime.datetime.now()

        self.display_vector = self.display_accel.read()

        new_base_vector = self.base_accel.read()
        if self.base_vector is None or self.last_poll is None:
            self.base_jerk = (0, 0, 0)
        else:
            delta = self.base_vector - new_base_vector
            self.base_jerk = delta / (now - self.last_poll).total_seconds()
        self.base_vector = new_base_vector

        self.display_angle = np.degrees(np.atan2(self.display_vector[1],
                                                 self.display_vector[2]))

        self.base_angle = np.degrees(np.atan2(self.base_vector[1],
                                              self.base_vector[2]))
        self.hinge_angle = self.base_angle - self.display_angle

        self.base_tilt = np.degrees(np.atan2(self.base_vector[0],
                                              self.base_vector[2]))

        self.last_poll = now

    def evaluate(self):
        """Determine hinge state from current accelerometer vectors and hinge
        angle"""
        if self.lid_switch.state == 'closed':
            # The lid switch won't lie to us (we hope!)
            return TabletState.CLOSED
        else:
            # Otherwise, switch between tablet and laptop state based on
            # calculated hinge angle. TODO: detect 'tent' mode
            if self.tablet_state != TabletState.TABLET:
                if angle_within(self.hinge_angle, 0, self.threshold):
                    return TabletState.TABLET
                else:
                    return TabletState.LAPTOP
            else:
                if angle_within(self.hinge_angle, 0, self.threshold +
                                self.hysteresis):
                    return TabletState.TABLET
                else:
                    return TabletState.LAPTOP

    def update(self, state: TabletState):
        """Update the hinge state"""

        if self.tablet_state != state:
            logger.info(f'State changed: {self.tablet_state.name}->'
                        f'{state.name}')
            old_state = self.tablet_state
            self.tablet_state = state
            if self.trigger_command is not None:
                command = self.trigger_command + [old_state.name, state.name]
                logger.debug(f'Running trigger command: {command}')
                try:
                    subprocess.run(command, check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(e)

    def run(self):
        self.poll()
        logger.debug(f'Display vector: '
                     f'{" ".join(f"{val:9.4f}" for val in self.display_vector)}        '
                     f'|{magnitude(self.display_vector):9.4f}|')
        logger.debug(f'Base vector:    '
                     f'{" ".join(f"{val:9.4f}" for val in self.base_vector)}        '
                     f'|{magnitude(self.base_vector):9.4f}|')
        logger.debug(f'Jerk vector:    '
                     f'{" ".join(f"{val:9.4f}" for val in self.base_jerk)}        '
                     f'|{magnitude(self.base_jerk):9.4f}|')

        logger.debug(f'Display yz:     {self.display_angle:9.4f}')
        logger.debug(f'Base yz:        {self.base_angle:9.4f}')
        logger.debug(f'Base xz (tilt): {self.base_tilt:9.4f}')
        logger.debug(f'Hinge angle:    {self.hinge_angle:9.4f}')

        if abs(magnitude(self.base_jerk)) > self.jerk_threshold:
            # If our vectors have changed significantly since last time,
            # we're being jostled around, and angle calculations may not be
            # reliable.
            logger.debug('Too much jerk, update skipped.')
        elif not (angle_within(self.base_tilt, 180, self.tilt_threshold) or \
                  angle_within(self.base_tilt, 0, self.tilt_threshold)):
            # The farther we are off-horizontal (Y-Z axis on the base), the
            # smaller our X and Z components will be, rendering our
            # opening-angle calculation unreliable.
            logger.debug('Too much tilt, update skipped')
        else:
            state = self.evaluate()
            logger.debug(f'Tablet state: {state.name}')

            self.update(state)
        logger.debug('')


def main():
    parser = argparse.ArgumentParser(description='Tablet-mode trigger '
                                     'daemon for dual-accelerometer '
                                     'convertible tablets.')

    tunables = parser.add_argument_group(title='Tuning parameters')
    tunables.add_argument('--interval', type=float, default=0.5,
                          metavar='SECONDS',
                          help='Interval between sensor polls.')
    tunables.add_argument('--threshold', type=float, default=45,
                          metavar='DEGREES',
                          help='Angle threshold for entering tablet mode '
                          '(default: 45 degrees)')
    tunables.add_argument('--hysteresis', type=float, default=20,
                          metavar='DEGREES',
                          help='Hysteresis for leaving tablet mode (default: '
                          '20 degrees)')
    tunables.add_argument('--tilt-threshold', type=float, default=20,
                          metavar='DEGREES',
                          help='Angle threshold for off-horizontal lockout '
                          '(default: 20 degrees)')
    tunables.add_argument('--jerk-threshold', type=float, default=6,
                          metavar='M/S^3',
                          help='Acceleration rate-of-change threshold for '
                          'erratic-motion lockout (default: 6 m/s^3)')

    hwconfig = parser.add_argument_group(title='Hardware configuration')
    hwconfig.add_argument('--display-accel', default=None, metavar='PATH',
                          help='Path to display accelerometer device (default: '
                          'autodetect from udev, or "1,0,0;0,1,0;0,0,1" if '
                          'ACCEL_MOUNT_MATRIX property not defined)')
    hwconfig.add_argument('--display-transform', default=None,
                          metavar='MATRIX',
                          help='Transformation matrix to apply to display '
                          'accelerometer data (default: autodetect from udev)')
    hwconfig.add_argument('--base-accel', default=None, metavar='PATH',
                          help='Path to base accelerometer device (default: '
                          'autodetect from udev, or "1,0,0;0,1,0;0,0,1" if '
                          'ACCEL_MOUNT_MATRIX property not defined)')
    hwconfig.add_argument('--base-transform', default=None, metavar='MATRIX',
                          help='Transformation matrix to apply to base '
                          'accelerometer data (default: autodetect from udev)')
    hwconfig.add_argument('--lid-switch', default='/proc/acpi/button/lid/LID0',
                          metavar='PATH',
                          help='Path to lid switch procfs entry (default: '
                          '/proc/acpi/button/lid/LID0)')

    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('trigger_command', nargs='?',
                        help=f'Command to run on stage change. Old and new '
                        f'states (one of {TabletState._member_names_}) are '
                        f'given in first and second arguments.')

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    pyudev_ctx = pyudev.Context()

    display_accel = Accel.get(pyudev_ctx, 'display', args.display_accel,
                              args.display_transform)
    base_accel = Accel.get(pyudev_ctx, 'base', args.base_accel,
                           args.base_transform)
    lid_switch = LidSwitch(args.lid_switch)

    if args.trigger_command is not None:
        trigger_command = shlex.split(args.trigger_command)
    else:
        trigger_command = None

    t = Tablet(base_accel, display_accel, lid_switch, threshold=args.threshold,
               hysteresis=args.hysteresis, tilt_threshold=args.tilt_threshold,
               jerk_threshold=args.jerk_threshold,
               trigger_command=trigger_command)

    killer = GracefulKiller()
    try:
        while not killer.kill_now:
            t.run()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        # Always switch to laptop state when we exit, this is a safety measure
        # since keyboard and trackpad input are disabled at the firmware level
        # while in tablet mode.
        t.update(TabletState.LAPTOP)


if __name__ == '__main__':
    main()
