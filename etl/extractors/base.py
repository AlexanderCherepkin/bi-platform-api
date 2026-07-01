from abc import ABC, abstractmethod
from typing import Any


class Extractor(ABC):
    source: str

    @abstractmethod
    def extract(self) -> list[dict[str, Any]]:
        pass
