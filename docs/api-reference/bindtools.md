# `bindtools` Core API Reference

The `bindtools.binding` module contains Numba-compiled speciation solvers, analytical equilibrium functions, `lmfit` optimization wrappers, and `emcee` MCMC sampling interfaces.

---

## 1. High-Level `bindingModel` Class

The primary class managing binding equilibria, parameters, data mapping, and minimization routines.

::: bindtools.binding.bindingModel
    options:
      show_root_heading: true
      members:
        - __init__
        - prepModel
        - runModel
        - calcSpeciation
        - plotSpeciation

---

## 2. Low-Level Speciation Solvers

::: bindtools.binding.getConcs
    options:
      show_root_heading: true

::: bindtools.binding.getConcsScipy
    options:
      show_root_heading: true

::: bindtools.binding.DoNR
    options:
      show_root_heading: true

::: bindtools.binding.calc_analytical_speciation
    options:
      show_root_heading: true

---

## 3. Fitting & Objective Functions

::: bindtools.binding.fitfun
    options:
      show_root_heading: true

---

## 4. Simulation & Visualization Utilities

::: bindtools.binding.simulateModel
    options:
      show_root_heading: true

::: bindtools.binding.makeFitResidPlot
    options:
      show_root_heading: true

::: bindtools.binding.saveFitCSV
    options:
      show_root_heading: true
