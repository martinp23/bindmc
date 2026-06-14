TODO

- Enable choosing of graph elements:
  - What should be y-axis? Plot all species ideally
----- see also https://community.plotly.com/t/possible-to-have-nested-or-hierarchical-legends/2376/8 for potential way to toggle species vs group
- Fix GUI grossness

model.py:
overwrite model should delete all fits and simulations associated with it, and then clean up all orphaned expt_data.


- if chemical shift column has spaces in it then parameters are given invalid names. need to sanitize or just call them delta1, delta2, etc.




allow comments alongside equilibria
graphs - y/x log options

cannot have tooltip on a disabled element; would need to wrap it in a ui.element() and set tooltip on that. body.py:164


- if there are many dep variables but we do not fit them all, the fit graph does not work because m1.obslist (len(dep vars)) != fit.calc_obs (which ignores unfitted dep vars e.g. chemical shifts)

- multiple expdatas  -- need to implement load_data, delete_data
- check effect of changing a model on exptdata - it should be fine. but maybe we need to work in dict/uuids rather than indices. we should 'invalidate' expt_data when model changed but not necessarily delete it.
- fast exchange :'(

- statemanager, sim/fit deletions
 --- make sure that they always adjust the active_sim properly
 --- in the fit box, bind the inputs like in simulations (easy)

- quick data plotting for raw data
- saving calc data?
  - saving graphs?
  - save plots/data to png/pdf and csv

- mcmc
- allow expt_data selection on data page
- auto-title for fits
- check whether hasattr(..., "active_...") works as expected/is a good idea. probably not, because attr exists since it is a getter... we really want to be checking whether the value is None (or whatever the default is).
- add refresh-bindings as in model tab to other tabs.

- precompile numba (part done; do better)
- plot fit vs expt observables (not just speciation)

- chemical shifts/fast exchange
- fit graph seems to show lines from sim graph?




DONE:
component concs for simulation - also allow edits maybe to a preformed table (or upload csv!)
- automatically plot sim/fit results against a concentration that changes, not against H 
- overall it might be better to not have a default model.... -- actually how about a selection of fixed default models, e.g. 1:1, 2:1, 1:2.
- add packaging code, make it easily distributable
- annoying problem that components on LHS of equation is different to order of components in a species on RHS
- indicator to header
- make data dep/indep into radio buttons
- overwrite model should prompt to save as.
- show fit results (and parameters), somehow
- remove "s" from delete dropdowns
- Read binding constants from controls
- Add a spinning wheel to indicate processing
- Replace graph e.g. with a plotly graph
- Ability to overlay multiple different models?
- Model name should give a clue as to its use in the plot (e.g. encourage user to give a descriptive name).
- Model name should be used as legend title. 
- Enable selection of graph elements:
  - What should be x-axis? Any component, species, or ratio thereof.
  - What should be y-axis? Plot all species ideally
  ----- maybe give an option to disable plotting of [comp]_free.
----- use grouped legend <--- sadly, for now, this seems to make it impossible to toggle off single traces. :(
 - Do we remember line visibility? NO. we should.
 - default x-axis should be first varying component, notjust first component
-  When a simulation is run with one conc range, then more steps in the same conc range are added, the graph currently seems to show the original data (first simulation) on an incorrect x-axis.
- Download and upload project
- if model name is blah, then ask if we should overwrite results
- Model persistence: on simulation, save model params results to session state.
- Load and edit models (dropdown? + button).
  - so we should begin by instantiating a model with empty parameters and bind to/edit that.
  - needs some architecture changes:
        - model class
        - sd.currmodel (property? or int index?)
        - sd.models (list of models)
- Delete models.
- fix a bug where it seems like we cannot change the x-axis if "do not plot [comp]_free" is selected.
- plot loaded fit data (need to deal with compconcs sensibly -- re-calc via an expt_data_to_comp_concs function?)
