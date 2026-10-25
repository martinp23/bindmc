# Example Datasets & Tutorials

This page provides example titration datasets and step-by-step walkthroughs for common supramolecular binding experiments.

---

## 1. NMR 1:1 Host-Guest Titration Data

### Sample Description
- **Host (H)**: $1.0 \text{ mM}$ total concentration ($0.001 \text{ M}$).
- **Guest (G)**: Added incrementally from $0.0 \text{ M}$ to $0.010 \text{ M}$ ($10.0 \text{ mM}$).
- **Observable**: Chemical shift $\delta_{\text{H}}$ of Host proton H1 (ppm).

### CSV Data Format

Copy and save the code block below as `nmr_1to1_titration.csv`:

```csv
Host_tot_M,Guest_tot_M,H1_ppm
0.001,0.0000,7.420
0.001,0.0002,7.408
0.001,0.0005,7.391
0.001,0.0008,7.375
0.001,0.0010,7.365
0.001,0.0015,7.342
0.001,0.0020,7.324
0.001,0.0030,7.298
0.001,0.0040,7.279
0.001,0.0060,7.255
0.001,0.0080,7.240
0.001,0.0100,7.230
```

### Walkthrough Steps

1. Launch `bindmc`.
2. In **Binding Model**, select **1:1 Fast Exchange** (or type `H + G <=> HG`).
3. In **Data Import**, click **Choose File** and select `nmr_1to1_titration.csv`.
4. Map `Host_tot_M` $\rightarrow$ `H` total conc, `Guest_tot_M` $\rightarrow$ `G` total conc.
5. Map `H1_ppm` $\rightarrow$ Dependent Variable (type: `deltaH`).
6. In **Fitting**, set initial guess $\log_{10} K = 3.5$ and click **Run Fit**.
7. Observe fitted parameters: $\log_{10} K \approx 3.0$ ($K \approx 1,000 \text{ M}^{-1}$) and $\delta_{\text{HG}} \approx 7.20 \text{ ppm}$.

---

## 2. UV-Vis 1:2 Stepwise Binding Titration Data

### CSV Data Format

Copy and save the code block below as `uvvis_1to2_titration.csv`:

```csv
Host_tot_M,Guest_tot_M,Abs_350nm
0.0001,0.0000,0.850
0.0001,0.0001,0.782
0.0001,0.0002,0.695
0.0001,0.0003,0.612
0.0001,0.0004,0.540
0.0001,0.0006,0.435
0.0001,0.0008,0.365
0.0001,0.0010,0.315
0.0001,0.0015,0.240
0.0001,0.0020,0.205
```

### Model Setup
Equilibrium equations:
```text
H + G <=> HG
H + 2G <=> HG2
```
Select observable type `absorbance` for `Abs_350nm`.
