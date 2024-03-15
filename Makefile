.PHONY: dependencies
dependencies:
	pip3 install -r requirements.txt
	pip3 install -r requirements_dev.txt
	pip3 install -r requirements_docs.txt

.PHONY: test
test:
	py.test tests

.PHONY: lint
lint:
	blue --check .

.PHONY: format
format:
	blue .

.PHONY: build
build:
	python3 -m build

.PHONY: install
install:
	pip3 install .

.PHONY: editable
editable:
	pip3 install -e .

.PHONY: upload
upload:
	python3 -m twine upload --repository pypi dist/*

.PHONY: docs
docs:
	$(MAKE) -C docs html

.PHONY: host-docs
host-docs:
	python3 -m http.server --directory ./docs/build/html

.PHONY: auto-docs
auto-docs:
	sphinx-autobuild docs/source docs/build/html

.PHONY: clean
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
