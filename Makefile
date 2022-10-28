# OBO Purls Makefile
# 2015-11-06
# James A. Overton <james@overton.ca>
#
# Last major modification: 2019-02-10, Michael Cuffaro <consulting@michaelcuffaro.com>
#
# This file contains code for working with
# Open Biomedical Ontoloiges (OBO)
# Persistent Uniform Resource Locators (PURLs).
#
# WARNING: This file contains significant whitespace!
# Make sure that your text editor distinguishes tabs from spaces.
#
# Required software:
#
# - [GNU Make](http://www.gnu.org/software/make/) to run this file
# - [Python 3](https://www.python.org/downloads/) to run scripts
# - [PyYAML](http://pyyaml.org/wiki/PyYAML) for translation to Apache


### Configuration
#
# You can override these defaults with environment variables:
#
#     export DEVELOPMENT=172.16.100.10; make all test
#

# List of ontology IDs to work with, as file names (lowercase).
# Defaults to the list of config/*.yml files.
ONTOLOGY_IDS ?= $(patsubst config/%.yml,%,$(wildcard config/*.yml))

# Local development server.
DEVELOPMENT ?= localhost

# Production server.
PRODUCTION ?= purl.obolibrary.org


### Boilerplate
#
# Recommended defaults: http://clarkgrubb.com/makefile-style-guide

MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
.DEFAULT_GOAL := all
.SUFFIXES:


### Basic Operations

# Default goal: Remove generated files and regenerate.
.PHONY: all
all: clean build

# Remove directories with generated files and tests.
.PHONY: clean
clean:
	rm -rf temp tests


### Build recipe for a single project.
#
# Convert the YAML file of a single project to a .htaccess file and place it
# in the temp/ directory.
.PHONY: build-%
build-%:
	tools/translate_yaml.py --input_files config/$*.yml --output_dir temp
	@echo "Built files in temp/$*"


# Build recipe for all projects
#
# Convert the YAML files of every project to .htaccess files and place them
# in the www/obo directory.

# Final output directory:
www/obo/:
	mkdir -p $@

# When a new build is created, the old build's files are moved here, in a subdirectory
# whose name is generated in a portable way using python (see the target-specific
# variable BACKUP below).
backup/:
	mkdir $@

# The main build target:
.PHONY: build
build: BACKUP = backup/obo-$(shell python -c "import time,os;print(time.strftime('%Y%m%d-%H%M%S',time.gmtime(os.path.getmtime('www/obo'))))")
build: | backup/ www/obo/
	tools/translate_yaml.py --input_dir config --output_dir temp/obo
	rm -rf temp/obo/obo temp/obo/OBO
	rm -rf temp/taxonomy
	rm -rf temp/ontology
	rm -rf temp/data
	-test -e www/obo && mv www/obo $(BACKUP)
	cp -R temp/obo www/taxonomy
	cp -R temp/obo www/ontology
	cp -R temp/obo www/data
	mv temp/obo www/obo
	rmdir temp


### Test Development Apache Config
#
# Make HTTP HEAD requests quickly against the DEVELOPMENT server
# to ensure that redirects are working properly.
# Fail if any FAIL line is found in any of them.
.PHONY: test
test:
	tools/test.py --delay=0.01 --output=tests/development --domain=$(DEVELOPMENT) config/*.yml


### Test Production Apache Config
#
# Make HTTP HEAD requests slowly against the PRODUCTION server
# to ensure that redirects are working properly.
.PHONY: test-production
test-production:
	tools/test.py --delay=1 --output=tests/production --domain=$(PRODUCTION) config/*.yml


### Test Tools
#
# Test our tools on files in examples/ directory.
.PHONY: test-example1
test-example1:
	tools/migrate.py test1 tools/examples/test1/test1.xml tests/examples/test1/test1.yml
	diff tools/examples/test1/test1.yml tests/examples/test1/test1.yml

.PHONY: test-example2
test-example2:
	tools/translate_yaml.py --input_dir tools/examples/test2/ --output_dir tests/examples/test2/
	diff tools/examples/test2/test2.htaccess tests/examples/test2/.htaccess
	diff tools/examples/test2/obo/obo.htaccess tests/examples/test2/obo/.htaccess
	diff tools/examples/test2/test2/test2.htaccess tests/examples/test2/test2/.htaccess	

.PHONY: test-examples
test-examples: test-example1 test-example2


### Update Repository
#
# Run the safe-update.py script which does the following:
# - Check Travis-CI for the last build.
# - If it did not pass, or if it is the same as the current build, then do nothing.
# - Otherwise replace .current_build, pull from git, and run a new `make`.
safe-update:
	tools/safe-update.py


### Code style and lint checks for python source files.
#
# Note that `|| true` is appended to force make to ignore the exit code in both cases
.PHONY: style
style:
	pep8 --max-line-length=100 --ignore E129,E126,E121,E111,E114 tools/*.py || true

.PHONY: delint
delint:
	python3 -m pyflakes tools/*.py || true
