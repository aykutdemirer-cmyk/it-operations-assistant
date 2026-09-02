from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routes import (  # noqa: E402
    agent_commands,
    agent_ssh,
    agents,
    asset_snmp_profiles,
    assets,
    discovery,
    health,
    monitoring,
    scans,
    snmp,
    snmp_profiles,
)

app = FastAPI(title="IT Operations Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    # PUT/DELETE Faz 29'da SNMP Profile CRUD için eklendi (bkz.
    # app/routes/snmp_profiles.py) — önceden yalnızca GET/POST vardı.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(discovery.router)
app.include_router(assets.router)
app.include_router(scans.router)
app.include_router(snmp.router)
app.include_router(monitoring.router)
app.include_router(agents.router)
app.include_router(agent_commands.router)
app.include_router(agent_ssh.router)
app.include_router(snmp_profiles.router)
app.include_router(asset_snmp_profiles.router)
