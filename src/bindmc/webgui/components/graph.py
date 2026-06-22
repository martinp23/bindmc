import json

from nicegui import ui, app

from .base import BaseComponent
from ..classes import Simulation, FitResult
from ..utils import safe_filename, custom_download
import pandas as pd
import uuid

GRAPH_LEGEND_TITLE_W = 15
X_AXIS_ROW_INDEX = "Row index"


class Graph(BaseComponent):
    def __init__(self, state_manager, mode="sim", css_classes="h-[50vh]"):
        self.mode = mode
        self.sm = state_manager

        self.data_frames = (
            dict()
        )  # for now, make these DataFrames with sensible colnames, and which incorporate component concs.
        self.line_styles = dict()
        self.curr_x = None
        self._comp_names = set()  # set of all component names in the graph

        # Plotly's default color sequence for consistent coloring
        self.plotly_colors = [
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
            "#17becf",
        ]
        self._color_mapping = {}  # Maps column names to color indices

        self.css_classes = css_classes

        # set up sim_fig layout
        if mode == "sim":
            if not hasattr(self.sm, "sim_fig_data"):
                self.sm.sim_fig_data = {
                    "data": [],
                    "layout": {
                        "title": "Simulation Results",
                        "xaxis": {"title": {"text": X_AXIS_ROW_INDEX}},
                        "yaxis": {"title": {"text": "Concentration [M]"}},
                        "showlegend": True,
                    },
                }
            self.graph_data = self.sm.sim_fig_data

        if mode == "data_preview":
            if not hasattr(self.sm, "data_preview_fig_data"):
                self.sm.data_preview_fig_data = {
                    "data": [],
                    "layout": {
                        "title": "Data Preview",
                        "xaxis": {"title": {"text": X_AXIS_ROW_INDEX}},
                        "yaxis": {"title": {"text": "Y-axis"}},
                        "showlegend": True,
                    },
                }
            self.graph_data = self.sm.data_preview_fig_data

        if mode == "expt_preview":
            if not hasattr(self.sm, "expt_preview_fig_data"):
                self.sm.expt_preview_fig_data = {
                    "data": [],
                    "layout": {
                        "title": "Experimental Data Preview",
                        "xaxis": {"title": {"text": X_AXIS_ROW_INDEX}},
                        "yaxis": {"title": {"text": "Y-axis"}},
                        "showlegend": True,
                    },
                }
            self.graph_data = self.sm.expt_preview_fig_data

        # set up fit_fig layout
        if mode == "fit":
            if not hasattr(self.sm, "fit_fig_data"):
                self.sm.fit_fig_data = {
                    "data": [],
                    "layout": {
                        "title": "Fit Results",
                        "xaxis": {"title": {"text": X_AXIS_ROW_INDEX}},
                        "yaxis": {"title": {"text": "Y-axis"}},
                        "showlegend": True,
                    },
                }
            self.graph_data = self.sm.fit_fig_data

        if mode == "fit_speciation":
            if not hasattr(self.sm, "fit_speciation_fig_data"):
                self.sm.fit_speciation_fig_data = {
                    "data": [],
                    "layout": {
                        "title": "Fit Speciation",
                        "xaxis": {"title": {"text": X_AXIS_ROW_INDEX}},
                        "yaxis": {"title": {"text": "Y-axis"}},
                        "showlegend": True,
                    },
                }
            self.graph_data = self.sm.fit_speciation_fig_data

        # Plotly can render with a stale width when created inside hidden containers (e.g., inactive tabs).
        # Setting autosize helps it adapt to the parent element when it is (re)drawn.
        if isinstance(getattr(self, "graph_data", None), dict):
            self.graph_data.setdefault("layout", {})
            self.graph_data["layout"].setdefault("autosize", True)
        self._default_y_axis_title = (
            self.graph_data.get("layout", {}).get("yaxis", {}).get("title", {}).get("text", "Y-axis")
        )

        super().__init__(state_manager)

    def get_trimmed_cols(self, df, trimtail=2):
        """Get the trimmed columns of a DataFrame."""
        if df is None:
            return []
        return [col[:-trimtail] for col in df.columns]  # remove trailing _x

    @property
    def comp_names(self):
        """Get the component names for the graph."""
        return self._comp_names

    def add_comp_name(self, name):
        """Add a component name to the graph."""
        self._comp_names.add(name)

    def get_color_for_column(self, col_name: str) -> str:
        """Get a consistent color for a column name using Plotly's default color cycle."""
        if col_name not in self._color_mapping:
            # Assign next available color index
            next_index = len(self._color_mapping) % len(self.plotly_colors)
            self._color_mapping[col_name] = next_index

        color_index = self._color_mapping[col_name]
        return self.plotly_colors[color_index]

    def setup_nicegui(self):
        self._generate_graph()
        self._generate_options()

    def setup_bindings(self):
        super().setup_bindings()
        # if self.mode == "sim":
        #     self.sm.add_listener("simulation_completed", self._update_graph)
        # elif self.mode == 'fit':
        #     self.sm.add_listener('fit_results_updated', self._update_fit_results)

    def load_simulations_data(self):
        if len(self.sm.simulations) > 0:
            for sim in self.sm.simulations.values():
                self.add_graph_lines_xy(
                    sim.comp_concs,
                    sim.results[[c for c in sim.results.columns if c not in sim.comp_concs.columns]],
                    scatter="lines",
                    run_name=sim.name,
                    run_id=str(sim.id),
                )
            # self.add_graph_lines(sim.results, sim.name, sim.id)
            self._update_graph()

    def _update_graph(self, e=None):
        self.update_x_axis_selects()
        self.update_graph_x()
        self.graph.update()

    def update_graph(self):
        self._update_graph()

    # def add_line(self, x, y, name,mode='markers'):
    #     """Add a line to the graph."""
    #     self.graph_data["data"].append({
    #         "type": "scatter",
    #         "mode": mode,
    #         "x": x,
    #         "y": y,
    #         "name": name,
    #         "visible": True,
    #         "trace_id": name,  # Unique trace ID for this line
    #     })

    def add_graph_lines_xy(
        self,
        x: pd.DataFrame,
        y: pd.DataFrame,
        run_name: str = "",
        run_id: str | uuid.UUID = "",
        scatter: str = "lines",
        redraw: bool = False,
        color: str | None = None,
    ):
        """Add a set of lines from x and y to the graph.
        x and y should be dataframes of the same length.
        run_name and run_id are used to identify the simulation.
        scatter is the type of line to plot, e.g. 'lines', 'markers', etc.
        redraw is a boolean indicating whether to redraw the graph after adding the lines.
        color is an optional color specification for the traces.
        """

        if run_id is None:
            raise ValueError("run_id cannot be None")
            # run_id = str(uuid.uuid4())

        df_key = f"{run_id}-{scatter}"
        self.data_frames[df_key] = (x, y)  # Store the original x and y data for later use
        self.line_styles[df_key] = scatter

        for ii, col in enumerate(x.columns):
            self.add_comp_name(col)

        for ii, col in enumerate(y.columns):
            trace_data = {
                "type": "scatter",
                "mode": scatter,
                "x": x[x.columns[0]].tolist(),  # TODO clean up?
                "y": y[col].tolist(),
                "name": run_name[:GRAPH_LEGEND_TITLE_W] + " " + col,
                "species": col,
                "trace_id": str(run_id)  # is the uuid for the fit/etc
                + "-"
                + col,  # Unique trace ID for this simulation
                "df_key": df_key,
                "visible": True,
                #'legendgroup': self.sm.modelName,
                #'legendgrouptitle': dict(text=self.sm.modelName)
            }

            # Use consistent color based on column name, or provided color
            if color is not None:
                col_color = color
            else:
                # Use Plotly's default color cycle for consistency across calc/expt
                col_color = self.get_color_for_column(col)

            if scatter == "lines":
                trace_data["line"] = {"color": col_color}
            else:
                trace_data["marker"] = {"color": col_color}

            self.graph_data["data"].append(trace_data)
            if (
                col[:-5] in [d[:-4] for d in x.columns if d.endswith("_tot")]
                and hasattr(self, "chkNoComp")
                and self.chkNoComp.value is False
            ):
                self.graph_data["data"][-1]["visible"] = "legendonly"
        # elif, plot non-concentration data... TODO
        if redraw:
            self.graph.update()

    def add_graph_lines(self, df, run_name, run_id, scatter="lines", redraw=False):
        """Add a set of lines from a dataframe to the graph.
        Dataframe should have columns labelled _tot and _free for
        components and species respectively."""

        # Split df into x (component concentrations) and y (species concentrations) DataFrames
        # to maintain consistency with add_graph_lines_xy storage format
        comp_cols = [col for col in df.columns if col.endswith("_tot")]
        spec_cols = [col for col in df.columns if col.endswith("_free")]
        other_cols = [col for col in df.columns if not (col.endswith("_tot") or col.endswith("_free"))]

        # x DataFrame includes component concentrations and any other columns (like row index, time, etc.)
        x_df = df[comp_cols + other_cols] if comp_cols + other_cols else df[[df.columns[0]]]
        # y DataFrame includes species concentrations
        y_df = df[spec_cols] if spec_cols else pd.DataFrame()

        df_key = f"{run_id}-{scatter}"
        self.data_frames[df_key] = (x_df, y_df)
        self.line_styles[df_key] = scatter

        for ii, col in enumerate(df.columns):
            if col.endswith("_tot"):
                # this is a component concentration, so we skip it
                self.add_comp_name(col)
                continue
            elif col.endswith("_free"):
                # this is a species concentration, so we plot it
                col_color = self.get_color_for_column(col)
                trace_data = {
                    "type": "scatter",
                    "mode": scatter,
                    "x": df[df.columns[0]].tolist(),  # TODO clean up?
                    "y": df[col].tolist(),
                    "name": run_name[:GRAPH_LEGEND_TITLE_W] + " " + col,
                    "species": col,
                    "trace_id": str(run_id) + "-" + col,  # Unique trace ID for this simulation
                    "df_key": df_key,
                    "visible": True,
                    #'legendgroup': self.sm.modelName,
                    #'legendgrouptitle': dict(text=self.sm.modelName)
                }

                if scatter == "lines":
                    trace_data["line"] = {"color": col_color}
                else:
                    trace_data["marker"] = {"color": col_color}

                self.graph_data["data"].append(trace_data)
                if (
                    col[:-5] in [d[:-4] for d in df.columns if d.endswith("_tot")]
                    and hasattr(self, "chkNoComp")
                    and self.chkNoComp.value is False
                ):
                    self.graph_data["data"][-1]["visible"] = "legendonly"
            else:
                # assume it's a concentration
                col_color = self.get_color_for_column(col)
                trace_data = {
                    "type": "scatter",
                    "mode": scatter,
                    "x": df[df.columns[0]].tolist(),  # TODO clean up?
                    "y": df[col].tolist(),
                    "name": run_name[:GRAPH_LEGEND_TITLE_W] + " " + col,
                    "species": col,
                    "trace_id": str(run_id) + "-" + col,  # Unique trace ID for this simulation
                    "df_key": df_key,
                    "visible": True,
                    #'legendgroup': self.sm.modelName,
                    #'legendgrouptitle': dict(text=self.sm.modelName)
                }

                if scatter == "lines":
                    trace_data["line"] = {"color": col_color}
                else:
                    trace_data["marker"] = {"color": col_color}

                self.graph_data["data"].append(trace_data)

            # elif, plot non-concentration data... TODO
        if redraw:
            self.graph.update()

    def _generate_graph(self):
        """Generate the graph component."""

        self.graph = ui.plotly(self.graph_data).classes(f"w-full min-w-0 {self.css_classes}").style("width: 100%;")
        self.graph.on("plotly_restyle", self.plotly_restyle_handler)

    def _generate_options(self):
        """Generate the options for the graph."""
        with ui.card().classes("w-full mt-4"):
            with ui.row().classes("w-full items-center"):
                ui.label("Plotting options")
                ui.space()
                ui.button("Save", icon="save", on_click=self.download_graph_png).props("dense")
            with ui.row():
                ui.label("x-axis:")
                self.chkratio = ui.checkbox("Ratio?").on_value_change(
                    lambda e: self.xAxDenominatorSelect.set_value(1 if not e.value else self.xAxDenominatorSelect.value)
                )
                self.xAxNumeratorSelect = ui.select([1, 2, 3]).props("inline")
                ui.label("/").bind_visibility_from(self.chkratio, "value")
                self.xAxDenominatorSelect = (
                    ui.select([1, 2, 3]).props("inline").bind_visibility_from(self.chkratio, "value")
                )
                ui.button("Apply").on_click(self.update_graph_x)

            with ui.row():
                self.chkNormalizeY = ui.checkbox(
                    "Normalize Y per trace (0-1)",
                    value=False,
                    on_change=lambda e: self.update_graph_y(),
                )

            if self.mode != "expt_preview":
                with ui.row():
                    self.chkNoComp = ui.checkbox(
                        "Plot [Component]_free",
                        value=True,
                        on_change=(self.update_plot_compfree),
                    )

    def _default_export_filename(self) -> str:
        active_sim = self.sm.active_sim_or_none
        active_fit = self.sm.active_fit_or_none
        if self.mode == "sim":
            if active_sim is not None:
                return f"simulation_{safe_filename(active_sim.name, fallback='simulation')}_results"
            return "simulation_results"
        if self.mode == "fit":
            if active_fit is not None:
                return f"fit_{safe_filename(active_fit.name, fallback='fit')}_results"
            return "fit_results"
        if self.mode == "fit_speciation":
            if active_fit is not None:
                return f"fit_{safe_filename(active_fit.name, fallback='fit')}_speciation"
            return "fit_speciation"
        title = self.graph_data.get("layout", {}).get("title", "graph")
        title_text = title.get("text", "graph") if isinstance(title, dict) else str(title)
        return safe_filename(title_text, fallback="graph")

    async def download_graph_png(self) -> None:
        filename = self._default_export_filename()
        if not self.graph_data.get("data"):
            ui.notify(f"No plotted data available for {filename}.", type="warning")
            return

        is_native = False
        try:
            if getattr(app.native, "main_window", None) is not None:
                is_native = True
        except Exception:
            pass

        if is_native:
            js = f"""
const root = getElement({self.graph.id});
const container = root?.$el ?? root;
const plot = container?.querySelector('.js-plotly-plot') ?? container;
if (!plot || typeof Plotly === 'undefined') {{
    null;
}} else {{
    Plotly.toImage(plot, {{format: 'png', scale: 2}});
}}
"""
            data_url = await ui.run_javascript(js)
            if not data_url or not data_url.startswith("data:image/png;base64,"):
                ui.notify(f"Unable to export {filename}.png", type="negative")
                return

            try:
                import base64

                header, encoded = data_url.split(",", 1)
                image_bytes = base64.b64decode(encoded)
                await custom_download(image_bytes, filename=f"{filename}.png")
            except Exception as e:
                ui.notify(f"Failed to export {filename}.png: {str(e)}", type="negative")
        else:
            js = f"""
(() => {{
  const root = getElement({self.graph.id});
  const container = root?.$el ?? root;
  const plot = container?.querySelector('.js-plotly-plot') ?? container;
  if (!plot || typeof Plotly === 'undefined') return false;
  Plotly.downloadImage(plot, {{format: 'png', filename: {json.dumps(filename)}, scale: 2}});
  return true;
}})()
"""
            ok = await ui.run_javascript(js)
            if not ok:
                ui.notify(f"Unable to export {filename}.png", type="negative")

    def update_plot_compfree(self, e):
        """Update the plot to show or hide component free concentrations."""

        # comp_names = [d["species"][:-4] for d in self.graph_data["data"] if d["species"].endswith("_tot")]

        for d in self.graph_data["data"]:
            if d["species"].endswith("_free"):
                col = d["species"][:-5]  # Remove '_free' to get the component name
                col = col + "_tot"
                if col in self.comp_names:
                    if self.chkNoComp.value is False:
                        d["visible"] = "legendonly"
                    elif self.chkNoComp.value is True:
                        d["visible"] = True
        self.graph.update()

    def plotly_restyle_handler(self, e):
        # update is update item
        # trace is array of traces

        change = e.args["0"]
        traces = e.args["1"]

        # for multiples, we want to do if change.keys() == ['visible']
        # then for each item in change['visible'] (which will be a list)
        # change the corresponding trace
        if list(change.keys()) == ["visible"]:  # because if it's not just one entry, we don't want to mess things up.
            for ii, changeitem in enumerate(change["visible"]):
                if changeitem == "legendonly":
                    # if the trace is set to legendonly, we need to set this parameter in the  simFigData
                    # so that it persists if we add more traces
                    self.graph_data["data"][traces[ii]]["visible"] = "legendonly"

    def update_graph_x(self, e=None):
        numName = self.xAxNumeratorSelect.value
        deNomName = self.xAxDenominatorSelect.value if not None else 1
        # self.graph_data["data"] = []  # Clear existing data for the new plot

        throw_warning = False
        for d in self.graph_data["data"]:
            df_key = d.get("df_key")
            if df_key is None:
                run_id = "-".join(d["trace_id"].split("-", 5)[0:5])
                df_key = run_id

            if df_key not in self.data_frames:
                ui.notify("Data not found for trace: " + d.get("name", ""), type="warning")
                continue
            x_df = self.data_frames[df_key][0]
            x_cols = x_df.columns

            if numName == X_AXIS_ROW_INDEX:
                d["x"] = list(range(len(x_df)))
                continue
            if numName not in x_cols:
                ui.notify(
                    f"Numerator '{numName}' not found in simulation data for trace: {d.get('name', '')}",
                    type="warning",
                )
                continue

            if deNomName != 1 and deNomName not in x_cols:
                ui.notify(
                    f"Denomination '{deNomName}' not found in simulation data for trace: {d.get('name', '')}",
                    type="warning",
                )
                continue

            if deNomName == 1 or deNomName is None:
                d["x"] = self.data_frames[df_key][0][numName].tolist()
            else:
                d["x"] = (self.data_frames[df_key][0][numName] / self.data_frames[df_key][0][deNomName]).tolist()

        self.graph_data.setdefault("layout", {})
        self.graph_data["layout"].setdefault("xaxis", {})

        if numName == X_AXIS_ROW_INDEX:
            x_title_text = X_AXIS_ROW_INDEX
        elif isinstance(deNomName, int) and deNomName == 1:
            # if denominator is 1, we just plot the numerator
            x_title_text = f"[{numName}]"
        else:
            x_title_text = f"[{numName}] / [{deNomName}]"

        self.graph_data["layout"]["xaxis"]["title"] = {"text": x_title_text}

        if throw_warning:
            ui.notify(
                "Some lines could not be plotted because you have requested an x-axis which they do not support.",
                type="warning",
            )
        self.update_graph_y(update=False)
        self.graph.update()
        #  'x': (self.sd.compConcs['G']/self.sd.compConcs['H']).tolist(),

    def _normalize_trace_values(self, y_values):
        series = pd.to_numeric(pd.Series(y_values), errors="coerce")
        if series.notna().sum() == 0:
            return y_values

        y_min = series.min(skipna=True)
        y_max = series.max(skipna=True)
        if pd.isna(y_min) or pd.isna(y_max) or y_max == y_min:
            return [0.0 if pd.notna(v) else None for v in series.tolist()]

        return [
            None if pd.isna(v) else (float(v) - float(y_min)) / (float(y_max) - float(y_min)) for v in series.tolist()
        ]

    def update_graph_y(self, e=None, update=True):
        normalize = hasattr(self, "chkNormalizeY") and bool(self.chkNormalizeY.value)

        for d in self.graph_data["data"]:
            df_key = d.get("df_key")
            if df_key is None:
                trace_id = d.get("trace_id", "")
                run_id = "-".join(trace_id.split("-", 5)[0:5])
                df_key = run_id

            if df_key not in self.data_frames:
                continue

            x_df, y_df = self.data_frames[df_key]
            species = d.get("species")
            y_values = None
            if species in y_df.columns:
                y_values = y_df[species].tolist()
            elif species in x_df.columns:
                y_values = x_df[species].tolist()

            if y_values is None:
                continue

            d["y"] = self._normalize_trace_values(y_values) if normalize else y_values

        self.graph_data.setdefault("layout", {})
        self.graph_data["layout"].setdefault("yaxis", {})
        self.graph_data["layout"]["yaxis"]["title"] = {
            "text": "Normalized y (0-1)" if normalize else self._default_y_axis_title
        }

        if update:
            self.graph.update()

    def compspec_name_to_obj(self, name, sim):
        if name is None:
            return None
        if name == 1:
            return 1
        elif name.endswith("_tot"):
            # it's a component
            if name[:-4] in list(sim.comp_concs.columns):
                # i = self.sd.componentNames.index(name[:-4])
                return sim.comp_concs[name[:-4]]
        elif name.endswith("_free"):
            # s = name[:-5]  # remove '_free'
            # combo = [c.name for c in self.sd.components]+ [s for s in self.sd.species]
            if name in list(sim.results.columns):
                # i = self.sd.species.index(s)
                return sim.results[name]  # return the results for that species
        else:
            return None  # If the name does not match any known format, return None

    def update_x_axis_selects(self, e=None):
        # Prefer component-derived options for simulation workflows.
        # Fall back to x-dataframe columns only when no component names exist.
        x_axis_cols = [str(comp_name) for comp_name in self.comp_names]
        if len(x_axis_cols) == 0:
            for x_df, _ in self.data_frames.values():
                for col in x_df.columns:
                    col_name = str(col)
                    if col_name not in x_axis_cols:
                        x_axis_cols.append(col_name)

        uniq_opts = [X_AXIS_ROW_INDEX, *x_axis_cols]
        self.xAxNumeratorSelect.set_options(uniq_opts)
        self.xAxDenominatorSelect.set_options([1, *uniq_opts])

        if self.xAxNumeratorSelect.value is not None and self.xAxNumeratorSelect.value not in uniq_opts:
            self.xAxNumeratorSelect.value = X_AXIS_ROW_INDEX
            self.xAxDenominatorSelect.value = 1
            return

        if self.xAxNumeratorSelect.value is None:
            # first varying comp
            # would prefer to, for example, set this to the first varying component concentration
            # TODO
            if len(uniq_opts) > 1:  # because row index is always present but not a helpful option
                # look in the first dataframe and see which - if either - of these components vary
                first_x_data = next(iter(self.data_frames.values()))[0]
                # Find component with largest variation (max - min)
                variations = (first_x_data.max() - first_x_data.min()).sort_values(ascending=False)

                # Set to first component that has variation and is in options
                for comp_name in variations.index:
                    if str(comp_name) in uniq_opts:
                        self.xAxNumeratorSelect.value = str(comp_name)
                        self.xAxDenominatorSelect.value = 1
                        return

            self.xAxNumeratorSelect.value = (
                uniq_opts[1] if len(uniq_opts) > 1 else uniq_opts[0] if len(uniq_opts) > 0 else None
            )
            self.xAxDenominatorSelect.value = 1

    def clear_graph(self, e=None, update=True):
        """Clear the graph."""
        self.graph_data["data"] = []
        self.data_frames = {}
        self._comp_names = set()
        self._color_mapping = {}
        if update:
            self.graph.update()

    def remove_data(self, run_id: str):
        if isinstance(run_id, Simulation):
            run_id = str(run_id.id)
        if isinstance(run_id, uuid.UUID):
            run_id = str(run_id)
        if isinstance(run_id, FitResult):
            run_id = str(run_id.id)

        """Remove data for a specific run_id from the graph."""
        # Delete matching keys from data_frames and line_styles
        keys_to_delete = [k for k in self.data_frames if k.startswith(run_id)]
        for k in keys_to_delete:
            del self.data_frames[k]

        line_style_keys_to_delete = [k for k in self.line_styles if k.startswith(run_id)]
        for k in line_style_keys_to_delete:
            del self.line_styles[k]

        # Remove traces from the graph data
        self.graph_data["data"] = [d for d in self.graph_data["data"] if not d["trace_id"].startswith(run_id)]

        self.regenerate_comp_names()

        # Update the graph
        self.graph.update()

    def regenerate_comp_names(self):
        self._comp_names = set(col for x in self.data_frames.values() for col in x[0].columns)
