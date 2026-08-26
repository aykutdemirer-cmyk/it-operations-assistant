from typing import Literal

from pydantic import BaseModel


class ICMPScanRequest(BaseModel):
    cidr: str


class PortResult(BaseModel):
    port: int
    status: Literal["open", "closed", "timeout"]
    latency_ms: float | None = None


DeviceType = Literal[
    "firewall",
    "router",
    "switch",
    "server",
    "workstation",
    "printer",
    "access_point",
    "camera",
    "nas",
    "network_device",
    "unknown",
]


class PingResult(BaseModel):
    ip: str
    status: Literal["up", "down"]
    latency_ms: float | None = None
    mac_address: str | None = None
    vendor: str | None = None
    hostname: str | None = None
    open_ports: list[PortResult] = []
    device_type: DeviceType = "unknown"
    confidence: Literal["high", "medium", "low"] = "low"
    evidence: list[str] = []


class ScanResult(BaseModel):
    cidr: str
    total_hosts: int
    alive_hosts: int
    hosts: list[PingResult]
