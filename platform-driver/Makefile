KDIR := /usr/lib/modules/$(shell uname -r)/build

.PHONY: module clean

module: chuwi-dual-accel.ko

chuwi-dual-accel.ko: chuwi-dual-accel.c
	$(MAKE) -C $(KDIR) M=$(PWD)

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install:
	install -m 644 -D 60-sensor-chuwi.rules /etc/udev/rules.d/60-sensor-chuwi.rules
	dkms install .

uninstall:
	-rm -rf /etc/udev/rules.d/60-sensor-chuwi.rules
	-rmmod chuwi-dual-accel
	-dkms remove chuwi-dual-accel/0.0.1
