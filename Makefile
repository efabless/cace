init:
	pip3 install -r requirements.txt

test:
	py.test tests

lint:
	black --check cace/

format:
	black cace/

build:
	python3 -m build

install:
	pip3 install -e .

.PHONY: init test
