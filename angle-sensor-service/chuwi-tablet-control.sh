#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0+

errecho() {
	echo "$@" >&2
}

usage() {
	errecho "$(basename "$0") [old-state] new-state"
	errecho -e "\tChange tablet-mode state on Chuwi MiniBook X convertible laptop"
	errecho -e "\tValid states are: CLOSED, LAPTOP, TENT, TABLET"
}

TABLET_MODE_TRIGGER_LOCATIONS=(
	"/sys/devices/platform/MDA6655:00/chuwi_dual_accel_tablet_mode"
	"/sys/bus/acpi/devices/MDA6655:00/chuwi_ltsm_hack"
)

if [ $# -eq 1 ]; then
	old_state=""
	new_state="$1"
elif [ $# -eq 2 ]; then
	old_state="$1"
	new_state="$2"
else
	usage
	exit 1
fi

for f in "${TABLET_MODE_TRIGGER_LOCATIONS[@]}"; do
	if [ -w $f ]; then
		TABLET_MODE_TRIGGER="$f"
		break
	fi
done

if [ -z ${TABLET_MODE_TRIGGER+x} ]; then
	errecho "Tablet mode trigger file not found in sysfs"
	exit 1
fi

case "$new_state" in
	"CLOSED"|"LAPTOP")
		echo 0 > "${TABLET_MODE_TRIGGER}"
		;; 
	"TENT"|"TABLET")
		echo 1 > "${TABLET_MODE_TRIGGER}"
		;;
	*)
		errecho "Invalid tablet mode '$new_state'!"
		usage
		exit 1
		;;
esac

exit 0
