# This file is part of mkchromecast.
#
# Two sets of targets live here, and they do not mix:
#
#   Linux  -- run the tests, build a wheel, a .deb or a standalone binary, and
#             install into the virtualenv:
#                 make check wheel deb binary install develop uninstall run
#
#   macOS  -- build the .app bundle with py2app.  These targets rewrite
#             mkchromecast/__init__.py in place to force the tray on, and
#             `make clean` undoes that with a git checkout:
#                 make sed test debug deploy clean deepclean
#
# Each set refuses to run on the wrong platform instead of doing something
# surprising -- `make deploy` on Linux used to edit the source and then fail.
#
# `make` on its own prints the target list.  It used to run `sed`, which
# rewrote mkchromecast/__init__.py without being asked.
#
# What "binary" builds
# ====================
#     make binary  ->  dist/mkchromecast, one executable file that carries its
#                      own Python interpreter and every Python dependency, so
#                      it runs without the virtualenv and from any directory.
#
#     It does NOT carry the external programs mkchromecast drives: parec,
#     pactl, ffmpeg, lame and friends still have to come from the
#     distribution.  See the dependency list in README.md.
#
# The two .deb builds
# ===================
#     make deb   ->  dist/mkchromecast_X.Y.Z-1local1_all.deb, built with
#                    dpkg-deb by packaging/build-deb.sh.  Needs nothing beyond
#                    dpkg-dev, so it works on any machine; use it to try a
#                    change on the installed copy.
#
#     make dist  ->  ../mkchromecast_X.Y.Z_all.deb and the source package,
#                    built with dpkg-buildpackage from debian/.  This is the
#                    one to hand to somebody else: it carries a maintainer
#                    who can be reached, a DEP-5 copyright, and a source
#                    package anyone can rebuild.  Needs debhelper, dh-python
#                    and python3-all; make lint also needs lintian.
#
#     Both install the same files.  The Debian revision only differs so that
#     the two do not shadow each other in apt.
#
# Muammar El Khatib
#

UNAME_S := $(shell uname -s)

PYTHON      ?= .venv/bin/python
PIP         ?= $(PYTHON) -m pip
PYINSTALLER ?= .venv/bin/pyinstaller
DISTDIR     ?= dist
BUILDDIR    ?= build

# Extra arguments for `make run`, e.g. make run ARGS="-n Seminterrato -p 5001"
ARGS ?=

.DEFAULT_GOAL := help

.PHONY: help \
        require-linux \
        require-darwin \
        check \
        wheel \
        deb \
        dist \
        dist-source \
        lint \
        binary \
        install \
        develop \
        uninstall \
        run \
        clean-build \
        sed \
        sed_notray \
        test \
        debug \
        deploy \
        clean \
        deepclean

help:
	@echo "mkchromecast -- targets for $(UNAME_S)"
	@echo
	@echo "Linux:"
	@echo "  check        run the unit test suite"
	@echo "  wheel        build $(DISTDIR)/mkchromecast-*.whl"
	@echo "  deb          build $(DISTDIR)/mkchromecast_*_all.deb with dpkg-deb"
	@echo "  dist         build the distributable package from debian/"
	@echo "  dist-source  build only the source package from debian/"
	@echo "  lint         run lintian over what dist built"
	@echo "  binary       build $(DISTDIR)/mkchromecast, a standalone executable"
	@echo "  install      install into the virtualenv"
	@echo "  develop      install into the virtualenv, editable"
	@echo "  uninstall    remove it from the virtualenv"
	@echo "  run          run from the working tree: make run ARGS=\"--discover\""
	@echo "  clean-build  delete $(BUILDDIR)/, $(DISTDIR)/ and the caches"
	@echo
	@echo "macOS:"
	@echo "  sed sed_notray test debug deploy clean deepclean"
	@echo "               build the .app bundle with py2app; see the comments"
	@echo "               at the top of this file before using them"

require-linux:
	@test "$(UNAME_S)" = "Linux" || { \
	    echo "This target is for Linux; on $(UNAME_S) use the macOS targets."; \
	    exit 1; }

require-darwin:
	@test "$(UNAME_S)" = "Darwin" || { \
	    echo "This target builds the macOS .app and only runs on Darwin."; \
	    echo "On $(UNAME_S) try: make help"; \
	    exit 1; }

#
# Linux
#

check: require-linux
	$(PYTHON) -m unittest discover -s tests -v

wheel: require-linux
	$(PIP) wheel . --no-deps -w $(DISTDIR)

# Built with dpkg-deb rather than debhelper, so it needs nothing beyond
# dpkg-dev.  DEB_REVISION overrides the Debian revision.
deb: require-linux
	packaging/build-deb.sh $(DISTDIR)

# The distributable build.  dpkg-buildpackage writes to the parent directory,
# which is where every Debian tool expects to find its output.
dist: require-linux
	dpkg-buildpackage -us -uc -ui

dist-source: require-linux
	dpkg-buildpackage -us -uc -S

# --pedantic asks for everything lintian has an opinion about; -i explains
# each tag rather than only naming it.
lint: require-linux
	lintian -i --pedantic ../mkchromecast_*.changes

# The entry point puts the repo root on sys.path at runtime, which is too late
# for PyInstaller to follow: --paths says where the package is.  Most of the
# package is imported lazily inside functions, hence --collect-submodules.
# Only the tray icons are bundled -- images/ also holds the README screenshots.
# --add-data is resolved against --specpath, hence the absolute source path.
binary: require-linux
	@command -v $(PYINSTALLER) >/dev/null 2>&1 || { \
	    echo "pyinstaller not found at $(PYINSTALLER)."; \
	    echo "Install it with: $(PIP) install pyinstaller"; \
	    exit 1; }
	$(PYINSTALLER) --noconfirm --onefile --name mkchromecast \
	    --paths . \
	    --collect-submodules mkchromecast \
	    --add-data '$(CURDIR)/images/google*.png:images' \
	    --distpath $(DISTDIR) \
	    --workpath $(BUILDDIR) \
	    --specpath $(BUILDDIR) \
	    bin/mkchromecast
	@echo
	@echo "Built $(DISTDIR)/mkchromecast -- needs parec, pactl and the"
	@echo "encoders from the distribution; it only carries the Python side."

install: require-linux
	$(PIP) install .

develop: require-linux
	$(PIP) install -e .

uninstall: require-linux
	$(PIP) uninstall -y mkchromecast

run: require-linux
	$(PYTHON) bin/mkchromecast $(ARGS)

# Unlike `clean`, this touches only build products: no git clean, no checkout.
# The caches are hunted in the source directories only -- a bare `find .` would
# also churn through .venv/.
clean-build: require-linux
	rm -rf $(BUILDDIR) $(DISTDIR) *.egg-info .eggs
	find mkchromecast tests bin -name '__pycache__' -type d -prune -exec rm -rf {} +
	find mkchromecast tests bin -name '*.pyc' -delete

#
# macOS
#

# This target is used to test the start_tray.py script that is used to deploy
# the macOS app
sed: require-darwin
	sed -i -e  's/tray = args.tray/tray = True/g' mkchromecast/__init__.py
	sed -i -e  's/debug = args.debug/debug = True/g' mkchromecast/__init__.py

# This target is used when the tray should be disabled
sed_notray: require-darwin
	sed -i -e  's/tray = args.tray/tray = False/g' mkchromecast/__init__.py
	sed -i -e  's/debug = args.debug/debug = True/g' mkchromecast/__init__.py


# This target creates the app just to be used locally
test: require-darwin
	sed -i -e  's/tray = args.tray/tray = True/g' mkchromecast/__init__.py
	sed -i -e  's/debug = args.debug/debug = True/g' mkchromecast/__init__.py
	python3 setup.py py2app -A

# This target creates a standalone app with debugging enabled
debug: require-darwin
	sed -i -e  's/tray = args.tray/tray = True/g' mkchromecast/__init__.py
	sed -i -e  's/debug = args.debug/debug = True/g' mkchromecast/__init__.py
	python3 setup.py py2app
	cp -R /usr/local/Cellar/qt/5.15.1/plugins dist/Mkchromecast.app/Contents/PlugIns
	/usr/local/Cellar/qt/5.15.1/bin/macdeployqt dist/Mkchromecast.app

# This target creates a standalone app with debugging disabled
deploy: require-darwin
	sed -i -e  's/tray = args.tray/tray = True/g' mkchromecast/__init__.py
	sed -i -e  's/debug = args.debug/debug = False/g' mkchromecast/__init__.py
	python3 setup.py py2app
	cp -R /usr/local/Cellar/qt/5.15.1/plugins dist/Mkchromecast.app/Contents/PlugIns
	/usr/local/Cellar/qt/5.15.1/bin/macdeployqt dist/Mkchromecast.app -dmg

# This cleans
clean: require-darwin
	git clean -f -d
	git checkout mkchromecast/__init__.py
	rm -f mkchromecast/*.pyc
	rm -fr .eggs/

deepclean: require-darwin
	git clean -f -d
	git checkout mkchromecast/__init__.py
	rm -f mkchromecast/*.pyc
	rm -rf dist build
	rm -fr .eggs/
