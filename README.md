# bindmc

[![PyPI version](https://badge.fury.io/py/bindmc.svg)](https://badge.fury.io/py/bindmc)
[![Python Version](https://img.shields.io/pypi/pyversions/bindmc.svg)](https://pypi.org/project/bindmc/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23652775.svg)](https://doi.org/10.5281/zenodo.23652775)

`bindmc` is a tool for calculating binding constants, built on top of [bindtools](https://github.com/martinp23/bindtools).

## Installation

### Pre-built Binary
Download the latest executable for your platform from the [Releases](https://github.com/martinp23/bindmc/releases) page.

### uv

Make sure you have [installed uv](https://docs.astral.sh/uv/getting-started/installation/).

In an empty directory:
```bash
uv init --python 3.14
uv add bindmc
```

### Pip
```bash
pip install bindmc
```



## Upgrades

### Pre-built Binary
Re-download from the link above. 

### uv
```bash
uv add --upgrade bindmc
```

### Pip
```bash
pip install --upgrade bindmc
```



## Usage

If using the pre-built binary, run the downloaded executable.

### uv
```bash
uv run python -m bindmc
```

### Pip
```bash
python -m bindmc
```

