from dataclasses import dataclass
from typing import  Optional

@dataclass
class BindingConstant:
    species: str = ""
    logK: Optional[float] = None
    vary: bool = False
    isComp: bool = False
    min: Optional[float] = None
    max: Optional[float] = None

    @property
    def name(self) -> str:
        return self.species


