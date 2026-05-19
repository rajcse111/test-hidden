from dataclasses import dataclass
from typing import Any

from app.core.config import Settings


@dataclass
class RuntimeState:
    settings: Settings

    def update(self, values: dict[str, Any]) -> Settings:
        normalized = dict(values)
        if "provider" in normalized:
            normalized["default_provider"] = normalized.pop("provider")
        if "model" in normalized:
            normalized["default_model"] = normalized.pop("model")
        self.settings = self.settings.model_copy(update=normalized)
        return self.settings
