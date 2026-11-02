from dataclasses import dataclass


@dataclass
class Request:
    method: str
    path: str
    version: str
    headers: dict[str, str]
    body: bytes