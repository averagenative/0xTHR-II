PYTHON ?= python3
APP_ID := io.github.averagenative.thr2
APPS := $(HOME)/.local/share/applications
ICONS := $(HOME)/.local/share/icons/hicolor/scalable/apps

.PHONY: check test compile gui install uninstall

check: compile test

compile:
	$(PYTHON) -m compileall -q thr2 tests

test:
	$(PYTHON) -m unittest discover -s tests -t .

gui:
	$(PYTHON) -m thr2.gui

install:
	install -Dm644 data/$(APP_ID).svg $(ICONS)/$(APP_ID).svg
	sed 's|@REPO@|$(CURDIR)|' data/$(APP_ID).desktop.in > $(APPS)/$(APP_ID).desktop
	-update-desktop-database $(APPS) 2>/dev/null
	-gtk-update-icon-cache -q -t $(HOME)/.local/share/icons/hicolor 2>/dev/null

uninstall:
	rm -f $(APPS)/$(APP_ID).desktop $(ICONS)/$(APP_ID).svg
