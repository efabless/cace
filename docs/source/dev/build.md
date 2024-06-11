# Build CACE

If you are using nix, the package will be builded when you run `nix-shell`.

---

If not, you may need to set up a Python [virtual environment](https://docs.python.org/3/library/venv.html).

To install the dependencies for CACE, run:

```
$ make dependencies
```

To build the Python package, run:

```
$ make build
```

To install the package, run:

```
$ make install
```

To install the package in editable mode, run:

```
$ make editable
```
