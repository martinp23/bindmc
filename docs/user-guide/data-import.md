# Data Import & Schemas

`bindmc` supports importing experimental titration data from CSV (`.csv`) and Excel (`.xlsx`, `.xls`) files.

---

## File Layout Standards

Your data file should structure data in columns where each row represents a single titration point (e.g. single tube or addition step).

### Example Data Table (NMR Titration)

| Host_conc (M) | Guest_conc (M) | H1_shift (ppm) | H2_shift (ppm) |
|---|---|---|---|
| 0.001 | 0.000 | 7.420 | 8.105 |
| 0.001 | 0.0005 | 7.395 | 8.120 |
| 0.001 | 0.001 | 7.360 | 8.145 |
| 0.001 | 0.002 | 7.310 | 8.180 |

---

## Experimental Data Types

When assigning columns in the **Data Import** tab, select the correct **Experimental Data Type**:

### 1. NMR Chemical Shifts (`deltaH` / `deltaF`)
- **Fast Exchange**: Observed chemical shift $\delta_{\text{obs}}$ is the mole-fraction weighted average of free species and complexes:
  $$\delta_{\text{obs}} = \sum_{i} x_i \cdot \delta_i$$
  where $x_i = \frac{c_i}{C_{\text{total\_host}}}$ is the fraction of host present in species $i$.
- **Parametric Binding Constants**: Each species $i$ has an associated chemical shift parameter $\delta_i$.

### 2. UV-Vis / Fluorescence Absorbance (`absorbance` / `fluorescence`)
- Linear concentration-weighted observables (Beer-Lambert law):
  $$A_{\text{obs}} = \sum_{i} \varepsilon_i \cdot c_i \cdot l$$
  where $\varepsilon_i$ is the molar extinction coefficient / fluorescence intensity factor for species $i$.

### 3. Peak Integrations (`integration`)
- Peak integration areas proportional to concentrations of specific species (slow exchange NMR or HPLC peak areas).

---

## Mapping Columns in `bindmc`

1. Click **Choose File** in the **Data Import** tab.
2. Select your CSV or Excel file.
3. For each component defined in your model (e.g. `H`, `G`), select the corresponding dataset column for total concentration ($[\text{H}]_{\text{tot}}$, $[\text{G}]_{\text{tot}}$).
4. Add dependent variable series, giving each a name (e.g., `Peak H1`) and assigning its data column and observable type.
