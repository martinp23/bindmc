from dataclasses import dataclass

@dataclass
class Component:
    name: str = ""
    start_conc: float|None = 0
    end_conc: float|None = 0
    constant: bool = False
    _start_units: str = "mM"
    _end_units: str = "mM"
    spacing: str = "lin"  # 'lin' or 'log', default is linear spacing

    UNIT_CONVERSIONS = {
        "M": 1,
        "mM": 1e3,
        "μM": 1e6,
        "µM": 1e6,
        "uM": 1e6,  # support ASCII 'u'
        "nM": 1e9,
        "pM": 1e12,
    }

    @property
    def start_conc_nice(self) -> float | None:
        """Get start concentration in the specified units (user-friendly)."""
        factor = self.UNIT_CONVERSIONS.get(self.start_units, 1)
        return self.start_conc * factor if self.start_conc is not None else None

    @start_conc_nice.setter
    def start_conc_nice(self, value: float):
        """Set start concentration from user-friendly units to base units (M)."""
        factor = self.UNIT_CONVERSIONS.get(self.start_units, 1)
        self.start_conc = value / factor if value is not None else None

    @property
    def end_conc_nice(self) -> float|None:
        """Get end concentration in the specified units (user-friendly)."""
        factor = self.UNIT_CONVERSIONS.get(self.end_units, 1)
        return self.end_conc * factor if self.end_conc is not None else None

    @end_conc_nice.setter
    def end_conc_nice(self, value: float):
        """Set end concentration from user-friendly units to base units (M)."""
        factor = self.UNIT_CONVERSIONS.get(self.end_units, 1)
        self.end_conc = value / factor if value is not None else None

    @property
    def start_units(self) -> str:
        """Get the start concentration units."""
        return self._start_units

    @start_units.setter
    def start_units(self, value: str):
        """Set the start concentration units and recalculate start_conc."""
        oldunits = self._start_units
        convfactor = self.UNIT_CONVERSIONS.get(value, 1) / self.UNIT_CONVERSIONS.get(
            oldunits, 1
        )
        self._start_units = value

        self.start_conc = (
            self.start_conc / convfactor if self.start_conc is not None else None
        )

    @property
    def end_units(self) -> str:
        """Get the end concentration units."""
        return self._end_units

    @end_units.setter
    def end_units(self, value: str):
        """Set the end concentration units and recalculate end."""
        oldunits = self._end_units
        convfactor = self.UNIT_CONVERSIONS.get(value, 1) / self.UNIT_CONVERSIONS.get(
            oldunits, 1
        )
        self._end_units = value

        self.end_conc = (
            self.end_conc / convfactor if self.end_conc is not None else None
        )

    # """Class to represent a component in the simulation."""
    # def __init__(self, name, start_conc=None, end_conc=None, constant=False, start_unit='mM', end_unit='mM'):

    #     self.name = name
    #     self.start_conc = start_conc
    #     self.end_conc = end_conc
    #     self.constant = constant
    #     self.start_unit = start_unit
    #     self.end_unit = end_unit

    # def to_dict(self):
    #     """Convert Component to a dictionary."""
    #     return {
    #         'name': self.name,
    #         'start_conc': self.start_conc,
    #         'end_conc': self.end_conc,
    #         'constant': self.constant,
    #         'start_unit': self.start_unit,
    #         'end_unit': self.end_unit
    #     }


