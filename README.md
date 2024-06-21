<h1 align="center">CACE</h1>
<h2 align="center">Circuit Automatic Characterization Engine</h2>
<p align="center">
    <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"/></a>
    <img src="https://github.com/efabless/cace/actions/workflows/ci.yaml/badge.svg?branch=main" alt="GitHub Actions Status Badge" />
    <a href="https://cace.readthedocs.io/"><img src="https://readthedocs.org/projects/cace/badge/?version=latest" alt="Documentation Build Status Badge"/></a>
    <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3.8-3776AB.svg?style=flat&logo=python&logoColor=white" alt="Python 3.8 or higher" /></a>
    <a href="https://github.com/grantjenks/blue"><img src="https://img.shields.io/badge/code%20style-blue-blue.svg" alt="Code Style: blue"/></a>
</p>
<p align="center">
    <a href="https://invite.skywater.tools"><img src="https://img.shields.io/badge/Community-Open%20Source%20Silicon%20Slack-ff69b4?logo=slack" alt="Invite to the Open Source Silicon Slack"/></a>
</p>

CACE is a framework for analog and mixed-signal circuits that enables automatic characterization under various conditions and with Monte Carlo and mismatch analysis. After all parameters have been run under the given conditions, CACE will generate a summary showing the circuit performance.

> [!NOTE]
> The latest documentation can be viewed online at [cace.readthedocs.io](https://cace.readthedocs.io/). 

## Installation

CACE currently supports two primary methods of installation for it and its dependencies.

Please read the installation instruction in the documentation under ["Installation Overview"](https://cace.readthedocs.io/en/latest/getting_started/index.html).

### Nix (Recommended)

Works for macOS and Linux (x86-64 and aarch64) as well for Windows via WSL2. Recommended, as it is more integrated with your filesystem and overall has less upload and download deltas.

See [Nix-based installation](https://cace.readthedocs.io/en/latest/getting_started/common/nix_installation/index.html) in the docs for more info.

### Python-only Installation

You'll need to bring your own compiled utilities, but otherwise, simply install CACE as follows:

```console
	python3 -m pip install --upgrade cace
```

## Usage

To invoke the CLI:

```console
cace [datasheet] [output] [options]
```

To invoke the GUI:

```console
cace-gui [datasheet] [options]
```

For more information about the usage of CACE with either the CLI or the GUI please have a look at ["Usage Guides"](https://cace.readthedocs.io/en/latest/usage_guides/index.html) in the documentation.

## Examples

There exist already numerous designs that use CACE. We have assembled a list of different designs that you can use as reference: [Example Designs](https://cace.readthedocs.io/en/latest/examples/index.html). 

## License

[The Apache License, version 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).
