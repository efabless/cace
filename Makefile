.PHONY: init
init:
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

venv: venv/manifest.txt
venv/manifest.txt: ./requirements_docs.txt ./requirements_dev.txt ./requirements.txt
	rm -rf venv
	python3 -m venv ./venv
	PYTHONPATH= ./venv/bin/python3 -m pip install --upgrade pip
	PYTHONPATH= ./venv/bin/python3 -m pip install --upgrade -r ./requirements_docs.txt
	PYTHONPATH= ./venv/bin/python3 -m pip install --upgrade -r ./requirements_dev.txt
	PYTHONPATH= ./venv/bin/python3 -m pip install --upgrade -r ./requirements.txt
	PYTHONPATH= ./venv/bin/python3 -m pip freeze > $@
	@echo ">> Venv prepared."

.PHONY: docs
docs: venv
	. venv/bin/activate; $(MAKE) -C docs html

.PHONY: host-docs
host-docs: venv
	. venv/bin/activate; python3 -m http.server --directory ./docs/build/html

.PHONY: clean
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
