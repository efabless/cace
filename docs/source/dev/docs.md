# Documentation

If you are using nix, you can get the environmen to build the docs by running `nix develop .#docs`. Otherwise, you will need to install the dependencies via:

```
$ make dependencies
```

---

To build the documentation, run:

```
$ make docs
```

To host the docs, run:

```
$ make host-docs
```

To automatically refresh the docs upon changes, run:

```
$ make auto-docs
```