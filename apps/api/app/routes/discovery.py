from fastapi import APIRouter, HTTPException

from app.discovery.cidr import InvalidCIDRError
from app.discovery.schemas import ICMPScanRequest, ScanResult
from app.discovery.scanner import scan_network

router = APIRouter(prefix="/api/discovery")


@router.post("/icmp", response_model=ScanResult)
async def post_icmp_scan(request: ICMPScanRequest) -> ScanResult:
    try:
        return await scan_network(request.cidr)
    except InvalidCIDRError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
