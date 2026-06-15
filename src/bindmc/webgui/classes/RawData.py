import uuid
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class RawData:
    filename: str = ""
    data: pd.DataFrame = field(default_factory=pd.DataFrame, compare=False)
    id: uuid.UUID = field(default_factory= lambda: uuid.uuid4())

    def __post_init__(self):
        """Ensure data are appropriate types."""
        if not isinstance(self.id, uuid.UUID):
            if isinstance(self.id, str):
                self.id = uuid.UUID(self.id)


    def to_dict(self) -> dict[str, str|dict]:
        """Convert RawData to a dictionary."""
        return {
            "filename": self.filename,
            "data": (
                self.data.to_dict(orient="list")
                if isinstance(self.data, pd.DataFrame)
                else {}
            ),
            "id": str(self.id) if self.id else "",
        }


