from dataclasses import dataclass, InitVar
from typing import Optional
import unicodedata


@dataclass
class ExptDataType:
    name: str = ""
    lnsigma: Optional[float] = None
    lnsigma_min: Optional[float] = None
    lnsigma_max: Optional[float] = None
    units: str = ""
    _measurement_method: str = ""
    init_meas: InitVar[str] = ""  # Default method for experimental data type

    def __post_init__(self, init_meas: str) -> None:
        # Normalise legacy measurement key before processing.
        if init_meas == "uv_abs":
            init_meas = "uvvis"
        if init_meas:
            self._measurement_method = init_meas
            lnsigma = (-10, -6, -4)  # Default values for lnsigma
            if init_meas == "nmrInteg":
                lnsigma = (-11, -8, -4)
                self.lnsigma = self.lnsigma if self.lnsigma is not None else -8

            elif init_meas == "Hppm" or init_meas == "Fppm" or init_meas == "nmrShift":
                lnsigma = (-8, -5, -3)

            elif init_meas == "measConc":
                lnsigma = (-10, -6, -4)

            elif init_meas == "uvvis":
                lnsigma = (-11, -7, -3)
                if not self.units:
                    self.units = "absorbance"

            elif init_meas == "fluorescence":
                lnsigma = (-8, -4, 0)
                if not self.units:
                    self.units = "intensity"

            self.lnsigma_min = self.lnsigma_min if self.lnsigma_min is not None else lnsigma[0]
            self.lnsigma = self.lnsigma if self.lnsigma is not None else lnsigma[1]
            self.lnsigma_max = self.lnsigma_max if self.lnsigma_max is not None else lnsigma[2]

        self.name = unicodedata.normalize("NFC", self.name)  # Normalize the name to NFC form

    @property
    def meas(self) -> str:
        """Get the measurement method for the experimental data type."""
        # Normalise legacy key: uv_abs is an alias for uvvis.
        if self._measurement_method == "uv_abs":
            return "uvvis"
        return self._measurement_method

    # @property
    # def method(self) -> str:
    #     """Get the method for the experimental data type."""
    #     return self._method

    # # @method.setter
    # # def method(self, value: str):
    # #     """Set the method for the experimental data type."""
    # #     if value in ["nmrConc", "nmrShift", "measConc", "other"]:
    # #         self._method = value

    # #         if value == "nmrConc":
    # #             self.lnsigma = -8
    # #             self.lnsigma_min = -11
    # #             self.lnsigma_max = -4
    # #         elif value == "nmrShift":
    # #             self.lnsigma = -6
    # #             self.lnsigma_min = -10
    # #             self.lnsigma_max = -4
    # #         elif value == "measConc":
    # #             self.lnsigma = -6
    # #             self.lnsigma_min = -10
    # #             self.lnsigma_max = -4

    #     # TODO make config file?
    #     else:
    #         raise ValueError(
    #             f"Invalid method: {value}. Must be one of ['nmrConc', 'nmrShift', 'measConc', 'other']."
    #         )
