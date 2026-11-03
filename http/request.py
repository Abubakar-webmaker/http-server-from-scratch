from dataclasses import dataclass, field


@dataclass
class Request:
    method: str
    path: str
    version: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""