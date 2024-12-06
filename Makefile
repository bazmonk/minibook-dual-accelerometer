KDIR := /usr/lib/modules/$(shell uname -r)/build

.PHONY: install uninstall module clean

module: chuwi-dual-accel.ko

chuwi-dual-accel.ko: chuwi-dual-accel.c
	$(MAKE) -C $(KDIR) M=$(PWD)

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install:
	install -m 644 -D udev/60-sensor-chuwi.rules /etc/udev/rules.d/60-sensor-chuwi.rules
	install -m 644 -D angle-sensor-service/angle-sensor.sysconfig /etc/sysconfig/angle-sensor
	install -m 644 -D angle-sensor-service/angle-sensor.service /etc/systemd/system/angle-sensor.service
	install -m 744 -D angle-sensor-service/angle-sensor.py /usr/local/sbin/angle-sensor
	install -m 744 -D angle-sensor-service/chuwi-tablet-control.sh /usr/local/sbin/chuwi-tablet-control
	systemctl daemon-reload
	dkms install .

uninstall:
	-systemctl stop angle-sensor.service
	-rm /etc/udev/rules.d/60-sensor-chuwi.rules
	-rm /etc/systemd/system/angle-sensor.service
	-rm /etc/sysconfig/angle-sensor
	-systemctl daemon-reload
	-rm /usr/local/sbin/angle-sensor
	-rm /usr/local/sbin/chuwi-tablet-control
	-rmmod chuwi-dual-accel
	-dkms remove chuwi-dual-accel/0.0.1
