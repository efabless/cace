init:
	pip install -r requirements.txt

test:
	py.test tests

lint:
	black --check cace/

format:
	black cace/

build:
	python -m build

install:
	pip install -e .

.PHONY: init test
