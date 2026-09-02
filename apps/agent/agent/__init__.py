"""IT Operations Assistant — Windows/Linux Agent (Faz 30).

Backend'in `apps/api/app/agents/` alt sistemine (Faz 28-29) bir istemci.
Backend'e GÖMÜLÜ değil — bağımsız, ayrı olarak dağıtılabilen bir Python
uygulaması (`apps/agent/`). Bkz. `README.md`."""

__version__ = "1.0.0"

# `AgentInventoryRequest.schema_version`/`AgentTelemetryRequest.
# schema_version` ile birebir — ileride agent payload şekli değişirse
# backend hangi sürümle konuştuğunu bilir (bkz. docs/decisions.md).
SCHEMA_VERSION = 1
