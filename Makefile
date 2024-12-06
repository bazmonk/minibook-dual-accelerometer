.PHONY: install uninstall

install:
	install -m 644 -D angle-sensor-service/angle-sensor.sysconfig /etc/sysconfig/angle-sensor
	install -m 644 -D angle-sensor-service/angle-sensor.service /etc/systemd/system/angle-sensor.service
	install -m 744 -D angle-sensor-service/angle-sensor.py /usr/local/sbin/angle-sensor
	install -m 744 -D angle-sensor-service/chuwi-tablet-control.sh /usr/local/sbin/chuwi-tablet-control
	systemctl daemon-reload
	$(MAKE) -C ./hack-driver install

uninstall:
	-systemctl stop angle-sensor.service
	-rm /etc/udev/rules.d/60-sensor-chuwi.rules
	-rm /etc/systemd/system/angle-sensor.service
	-rm /etc/sysconfig/angle-sensor
	-systemctl daemon-reload
	-rm /usr/local/sbin/angle-sensor
	-rm /usr/local/sbin/chuwi-tablet-control
	-rmmod chuwi-dual-accel
	-$(MAKE) -C ./hack-driver uninstall
