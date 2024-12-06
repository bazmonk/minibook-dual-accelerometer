// SPDX-License-Identifier: GPL-2.0+

/* 
 * Dual accelerometer driver for Chuwi MiniBook X
 *
 * Copyright 2024, Richard Halkyard <rhalkyard@gmail.com>
 * 
 * The Chuwi MiniBook X is a 'yoga' style laptop/tablet that uses a dual
 * accelerometer setup to determine the angle of its hinge. The Windows driver
 * uses an undocumented ACPI method ('LTSM') to communicate tablet vs. laptop
 * state to the firmware, which in turn issues standard tablet HID events. This
 * driver exposes both MXC6655 accelerometers, and a write-only sysfs property
 * (chuwi_ltsm_hack_tablet_mode) that userspace can use to trigger the LTSM
 * method.
 */

#define pr_fmt(fmt) "%s:%s: " fmt, KBUILD_MODNAME, __func__

#include <linux/acpi.h>
#include <linux/bits.h>
#include <linux/dmi.h>
#include <linux/iio/iio.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/property.h>
#include <linux/sysfs.h>
#include <linux/types.h>

acpi_handle mda6655_handle;
struct device * mda6655_dev;

static acpi_status chuwi_ltsm_hack_call_ltsm(int val)
{
	acpi_status ret;
	struct acpi_object_list args;
	union acpi_object mode_arg;

	args.count = 1;
	args.pointer = &mode_arg;

	mode_arg.type = ACPI_TYPE_INTEGER;
	mode_arg.integer.value = val;

	ret = acpi_evaluate_object(mda6655_handle, "LTSM", &args, NULL);
	return ret;
}

static ssize_t chuwi_ltsm_hack_store(struct device *dev,
				     struct device_attribute *attr,
				     const char *buf, size_t count)
{
	int ret;

	switch (buf[0]) {
	case '0':
		ret = chuwi_ltsm_hack_call_ltsm(0);
		break;
	case '1':
		ret = chuwi_ltsm_hack_call_ltsm(1);
		break;
	default:
		break;
	}

	if (ret == AE_OK)
		return count;

	dev_err(dev, "Could not call LTSM method: %s\n",
		acpi_format_exception(ret));
	return -EINVAL;
}
static DEVICE_ATTR_WO(chuwi_ltsm_hack);

static int __init chuwi_ltsm_hack_init(void)
{
	struct acpi_device *mda6655_adev;

	mda6655_adev = acpi_dev_get_first_match_dev("MDA6655", NULL, -1);

	if (!mda6655_adev) {
		return -ENODEV;
	}

	mda6655_handle = acpi_device_handle(mda6655_adev);
	mda6655_dev = get_device(&mda6655_adev->dev);

	device_create_file(mda6655_dev, &dev_attr_chuwi_ltsm_hack);

	return 0;
}

static void __exit chuwi_ltsm_hack_exit(void)
{
	device_remove_file(mda6655_dev, &dev_attr_chuwi_ltsm_hack);
	put_device(mda6655_dev);
}


module_init(chuwi_ltsm_hack_init);
module_exit(chuwi_ltsm_hack_exit);
MODULE_DESCRIPTION("Chuwi Dual Accelerometer device driver");
MODULE_AUTHOR("Richard Halkyard <rhalkyard@gmail.com>");
MODULE_LICENSE("GPL");
