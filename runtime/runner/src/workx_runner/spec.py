from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunSpec:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> RunSpec:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("protocol_version") != "1":
            raise ValueError("unsupported protocol version")
        for key in (
            "attempt_id",
            "fencing_token",
            "model",
            "model_gateway",
            "tool_gateway",
            "limits",
            "cwd",
            "outputs_dir",
        ):
            if key not in data:
                raise ValueError(f"RunSpec is missing {key}")
        return cls(data)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)
