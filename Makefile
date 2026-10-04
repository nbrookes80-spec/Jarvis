# Shortcuts for common tasks. Each target is a thin wrapper around a script
# documented in README.md.

.PHONY: install gui run window test lint

install:        ## Install Jarvis and the Claude plugin (Debian / Ubuntu / Zorin)
	./bootstrap.sh

gui:            ## Install the desktop window with offline voice
	./scripts/install-gui.sh

run:            ## Start Jarvis in this terminal
	./Jarvis-AI

window:         ## Open the desktop window
	./jarvis-gui

test:           ## Lint and run the unit tests
	./test.sh

lint:           ## Lint only
	./env/bin/python -m flake8 --select E,W --max-line-length=140 --ignore E722,W503,W504,E128 jarviscli/ installer
