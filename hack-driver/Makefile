KDIR := /usr/lib/modules/$(shell uname -r)/build

.PHONY: module clean

module: chuwi-ltsm-hack.ko

chuwi-ltsm-hack.ko: chuwi-ltsm-hack.c
	$(MAKE) -C $(KDIR) M=$(PWD)

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install:
	install -m 644 -D 60-sensor-chuwi.rules /etc/udev/rules.d/60-sensor-chuwi.rules
	install -m 644 -D chuwi-ltsm-hack.conf /etc/modprobe.d/chuwi-ltsm-hack.conf
	dkms install .
	rmmod intel-hid
	modprobe intel-hid
	udevadm trigger -w /dev/iio:device0
	udevadm trigger -w /dev/iio:device1

uninstall:
	-rm -rf /etc/udev/rules.d/60-sensor-chuwi.rules
	-rm -rf /etc/modprobe.d/chuwi-ltsm-hack.conf
	-rmmod intel-hid
	-modprobe intel-hid
	-rmmod chuwi-ltsm-hack
	-dkms remove chuwi-ltsm-hack/0.0.1
