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
 * (chuwi_dual_accel_tablet_mode) that userspace can use to trigger the LTSM
 * method.
 */

#define pr_fmt(fmt) "%s:%s: " fmt, KBUILD_MODNAME, __func__

#include <linux/acpi.h>
#include <linux/bits.h>
#include <linux/dmi.h>
#include <linux/i2c.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/sysfs.h>
#include <linux/types.h>

struct chuwi_dual_accel {
	struct i2c_client *lid_mxc6655;
	struct i2c_client *base_mxc6655;
	acpi_handle handle;
};

static const struct dmi_system_id chuwi_dual_accel_dmi_ids[] = {
	{
		.matches = {
			DMI_MATCH(DMI_SYS_VENDOR, "CHUWI"),
			DMI_MATCH(DMI_PRODUCT_NAME, "MiniBook X"),
		},
	},
	{ }
};
MODULE_DEVICE_TABLE(dmi, chuwi_dual_accel_dmi_ids);

static acpi_status chuwi_dual_accel_call_ltsm(struct chuwi_dual_accel *data,
					      int val)
{
	acpi_status ret;
	struct acpi_object_list args;
	union acpi_object mode_arg;

	args.count = 1;
	args.pointer = &mode_arg;

	mode_arg.type = ACPI_TYPE_INTEGER;
	mode_arg.integer.value = val;

	ret = acpi_evaluate_object(data->handle, "LTSM", &args, NULL);
	return ret;
}

static ssize_t chuwi_dual_accel_tablet_mode_store(struct device *dev,
						  struct device_attribute *attr,
						  const char *buf, size_t count)
{
	struct chuwi_dual_accel *data = dev_get_drvdata(dev);
	int ret;

	switch (buf[0]) {
	case '0':
		ret = chuwi_dual_accel_call_ltsm(data, 0);
		break;
	case '1':
		ret = chuwi_dual_accel_call_ltsm(data, 1);
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
static DEVICE_ATTR_WO(chuwi_dual_accel_tablet_mode);

static int chuwi_dual_accel_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct acpi_device *adev = ACPI_COMPANION(dev);
	struct chuwi_dual_accel *data;
	struct i2c_board_info board_info;
	char name[32];
	int ret;

	if (!dmi_check_system(chuwi_dual_accel_dmi_ids))
		return -ENODEV;

	data = devm_kzalloc(dev, sizeof(*data), GFP_KERNEL);
	if (!data)
		return -ENOMEM;

	memset(&board_info, 0, sizeof(board_info));
	strscpy(board_info.type, "mxc4005");
	snprintf(name, sizeof(name), "%s-%s.display", dev_name(dev),
		 board_info.type);
	board_info.dev_name = name;
	data->lid_mxc6655 = i2c_acpi_new_device(dev, 0, &board_info);

	if (IS_ERR(data->lid_mxc6655)) {
		ret = PTR_ERR(data->lid_mxc6655);
		goto out;
	}

	memset(&board_info, 0, sizeof(board_info));
	strscpy(board_info.type, "mxc4005");
	snprintf(name, sizeof(name), "%s-%s.base", dev_name(dev),
		 board_info.type);
	board_info.dev_name = name;
	data->base_mxc6655 = i2c_acpi_new_device(dev, 1, &board_info);

	if (IS_ERR(data->base_mxc6655)) {
		ret = PTR_ERR(data->base_mxc6655);
		goto out_unregister_display;
	}

	data->handle = adev->handle;
	if (chuwi_dual_accel_call_ltsm(data, 0) != AE_OK) {
		ret = -ENODEV;
		goto out_unregister_base;
	}

	platform_set_drvdata(pdev, data);
	device_create_file(dev, &(dev_attr_chuwi_dual_accel_tablet_mode));
	return 0;

out_unregister_base:
	i2c_unregister_device(data->base_mxc6655);

out_unregister_display:
	i2c_unregister_device(data->lid_mxc6655);
out:
	return ret;
}

static void chuwi_dual_accel_remove(struct platform_device *pdev)
{
	struct chuwi_dual_accel *data = platform_get_drvdata(pdev);
	
	device_remove_file(&pdev->dev, &(dev_attr_chuwi_dual_accel_tablet_mode));
	chuwi_dual_accel_call_ltsm(data, 0);

	if (data->lid_mxc6655)
		i2c_unregister_device(data->lid_mxc6655);
	if (data->base_mxc6655)
		i2c_unregister_device(data->base_mxc6655);
}

/*
 * Device ID must also be added to ignore_serial_bus_ids in
 * drivers/acpi/scan.c:acpi_device_enumeration_by_parent().
 */
static const struct acpi_device_id chuwi_dual_accel_acpi_ids[] = {
	{ "MDA6655", },
	{ }
};
MODULE_DEVICE_TABLE(acpi, chuwi_dual_accel_acpi_ids);

static struct platform_driver chuwi_dual_accel_driver = {
	.driver	= {
		.name = "Chuwi Dual Accelerometer device driver",
		.acpi_match_table = chuwi_dual_accel_acpi_ids,
	},
	.probe = chuwi_dual_accel_probe,
	.remove = chuwi_dual_accel_remove,
};
module_platform_driver(chuwi_dual_accel_driver);

MODULE_DESCRIPTION("Chuwi Dual Accelerometer device driver");
MODULE_AUTHOR("Richard Halkyard <rhalkyard@gmail.com>");
MODULE_LICENSE("GPL");
