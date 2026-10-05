PYTHON ?= python3
APP_ID := io.github.averagenative.thr2
APPS := $(HOME)/.local/share/applications
ICONS := $(HOME)/.local/share/icons/hicolor/scalable/apps

VERSION = $(shell $(PYTHON) -c 'import thr2; print(thr2.__version__)')
APPIMAGE = dist/0xTHR-II-$(VERSION)-x86_64.AppImage

.PHONY: check test compile gui install uninstall appimage release-appimage dist release screenshots

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

appimage: check
	packaging/build-appimage.sh

dist: check
	rm -f dist/thr2-$(VERSION)*
	$(PYTHON) -m pip wheel . --no-deps --no-build-isolation -w dist -q
	$(PYTHON) -c "from setuptools import build_meta; build_meta.build_sdist('dist')"
	rm -rf thr2.egg-info build/lib build/bdist*

release: dist appimage
	packaging/release.sh $(VERSION)

screenshots:
	packaging/screenshots.sh
