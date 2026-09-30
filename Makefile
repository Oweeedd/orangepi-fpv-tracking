SHELL := /bin/bash

.PHONY: install verify run service-enable service-stop check

install:
	./scripts/install.sh

verify:
	./scripts/verify_system.sh

run:
	./scripts/start_tracking_fullscreen.sh

service-enable:
	systemctl --user enable --now tracking-stand.service

service-stop:
	systemctl --user stop tracking-stand.service

check:
	python3 -m py_compile tracking_crsf_lab.py tracking_crsf_lab_direct.py rknn_yolo_detector.py servo_pwm_sysfs.py
	bash -n scripts/*.sh
	python3 -m unittest discover -s tests -v
