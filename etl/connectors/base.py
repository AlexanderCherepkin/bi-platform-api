from abc import ABC, abstractmethod
from typing import List, Dict, Any


class Connector(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw data rows from source system."""
        pass

    @abstractmethod
    def authenticate(self) -> bool:
        """Ensure valid auth/session tokens."""
        pass
