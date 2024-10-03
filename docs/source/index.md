# The Documentation for CACE

## Circuit Automatic Characterization Engine

<br>

CACE is a framework for analog and mixed-signal circuits that enables automatic characterization under various conditions and with Monte Carlo and mismatch analysis. After all parameters have been run under the given conditions, CACE produces a summary showing the circuit performance. CACE requires the designer to create a specification, called the _datasheet_ in CACE jargon, which contains the parameters, their conditions and limits. In addition, the designer must set up the directory structure of the design in a regular way and create template testbenches for the parameters. 

Setting up CACE requires some additional effort, but the benefits of using CACE are clear.

- **Specification and project structure** Each circuit design requires a datasheet that serves both as documentation for the specifiation and also as input for CACE. Designs must adhere to a regular directory structure, thus other designs using CACE feel familiar.

- **Reproducibility and re-use** Designs that have the CACE system set up can be fully and automatically characterized. This makes it easy to verify the correctness and completeness of analog circuits, facilitating the reuse of designs.

- **Good design practices** Finally, CACE encourages good analog design practices, fostering trust in open source analog design.

Follow the navigation element below (or check the sidebar on the left) to get started.

```{toctree}
:glob:
:hidden:
:maxdepth: 3

getting_started/index
usage/index
reference_manual/index
tutorials/index
examples/index
dev/index
```
