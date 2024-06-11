# Installation Overview

CACE currently supports two primary methods of installation: using **Nix** and the
**Python-only** method.

## Nix (Recommended)

Nix is a build system for Linux and macOS allowing for _cachable_ and
_reproducible_ builds, and is the primary build system for CACE.

Compared to the Docker method, Nix offers:

* **Native Execution on macOS:** CACE is built natively for both Intel and
  Apple Silicon-based Macs, unlike Docker which uses a Virtual Machine, and
  thus requires more resources.
* **Filesystem integration:** No need to worry about which folders are being
  mounted like in the Docker containers- Nix apps run natively in your userspace.
* **Smaller deltas:** if one tool is updated, you do not need to re-download
  everything, which is not the case with Docker.
* **Dead-simple customization:** You can modify any tool versions and/or any
  CACE code and all you need to do is re-invoke `nix-shell`. Nix's smart
  cache-substitution feature will automatically figure out whether your build is
  cached or not, and if not, will automatically attempt to build any tools that
  have been changed.

Because of the advantages afforded by Nix, we recommend trying to install using
Nix first. Follow the installation guide here:
{ref}`nix-based-installation`

## Python-only

This method installs CACE with PIP from [PyPI](https://pypi.org/project/cace/). But you will need to _bring your own tools_, which means that you have to manually compile and install each of the design tools and manage their versions.

You'll need the following:

- [Python 3.8 or higher](https://www.python.org/) with PIP and Tkinter

Install CACE with PIP:

```console
$ python3 -m pip install --upgrade cace
```

Non-exhaustive list of the required design tools:

* [XSCHEM](https://github.com/stefanschippers/xschem)
* [KLayout](https://klayout.de)
* [Magic](http://opencircuitdesign.com/magic/)
* [Netgen](http://opencircuitdesign.com/netgen/)
* [ngspice](https://ngspice.sourceforge.io/)

Some of the measurements require:

- [GNU Octave](https://octave.org/)

However, as the versions will likely not match those packaged with CACE,
some incompatibilities may arise, and we might not be able to support them.
