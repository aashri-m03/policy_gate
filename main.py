from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from typing import Optional, Dict

app = FastAPI()

# Required values
REQUIRED_ENV = "prod-tjzrsh"
REQUIRED_LABELS = {
    "owner": "student-yk6md",
    "environment": "production",
    "cost_center": "cc-ej9a"
}
ALLOWED_BACKENDS = {"gcs", "s3", "azurerm", "remote"}
STATEFUL_TYPES = {"storage_bucket", "sql_database", "persistent_disk"}

# Pydantic models for schema validation
class Resource(BaseModel):
    address: str
    type: str
    action: str
    labels: Dict[str, str]
    secret: Optional[str] = None
    forceDestroy: bool = False

class State(BaseModel):
    backend: str
    locked: bool

class PlanRequest(BaseModel):
    environment: str
    state: State
    providerVersion: str
    destroyApproved: bool
    resource: Resource

def validate_provider_version(version: str) -> bool:
    if version in ["6.2.1", "= 6.2.1", "~> 6.0"]:
        return True
    return False

def validate_plan(data: dict) -> dict:
    # Rule 2–8 logic (same as before), but now we assume schema is OK
    # Environment
    if data.get("environment") != REQUIRED_ENV:
        return {"decision": "reject", "reason": "ENVIRONMENT_MISMATCH"}

    state = data.get("state")
    if not isinstance(state, dict):
        return {"decision": "reject", "reason": "INVALID_PLAN"}
    if state.get("backend") not in ALLOWED_BACKENDS:
        return {"decision": "reject", "reason": "STATE_UNSAFE"}
    if state.get("locked") is not True:
        return {"decision": "reject", "reason": "STATE_UNSAFE"}

    provider_version = data.get("providerVersion")
    if not isinstance(provider_version, str):
        return {"decision": "reject", "reason": "INVALID_PLAN"}
    if not validate_provider_version(provider_version):
        return {"decision": "reject", "reason": "UNPINNED_PROVIDER"}

    destroy_approved = data.get("destroyApproved")
    if not isinstance(destroy_approved, bool):
        return {"decision": "reject", "reason": "INVALID_PLAN"}

    resource = data.get("resource")
    if not isinstance(resource, dict):
        return {"decision": "reject", "reason": "INVALID_PLAN"}

    # Labels
    labels = resource.get("labels")
    if not isinstance(labels, dict):
        return {"decision": "reject", "reason": "INVALID_PLAN"}
    if labels != REQUIRED_LABELS:
        return {"decision": "reject", "reason": "MISSING_LABELS"}

    # Secret
    secret = resource.get("secret")
    if secret is not None and not isinstance(secret, str):
        return {"decision": "reject", "reason": "INVALID_PLAN"}
    if secret is not None and not secret.startswith("secret://"):
        return {"decision": "reject", "reason": "PLAINTEXT_SECRET"}

    # Action and type
    action = resource.get("action")
    res_type = resource.get("type")
    if not isinstance(action, str) or not isinstance(res_type, str):
        return {"decision": "reject", "reason": "INVALID_PLAN"}

    # Rule 7: stateful deletes
    if action == "delete":
        if res_type in STATEFUL_TYPES:
            if destroy_approved is not True:
                return {"decision": "reject", "reason": "DELETE_NOT_APPROVED"}

    # Rule 8: forceDestroy
    force_destroy = resource.get("forceDestroy")
    if not isinstance(force_destroy, bool):
        return {"decision": "reject", "reason": "INVALID_PLAN"}
    if res_type == "storage_bucket" and force_destroy is True:
        return {"decision": "reject", "reason": "FORCE_DESTROY"}

    return {"decision": "approve", "reason": "APPROVE"}

@app.post("/terraform/plan")
async def terraform_plan(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(
            status_code=200,
            content={"decision": "reject", "reason": "INVALID_PLAN"}
        )

    # Basic top-level type checks (schema validation)
    if not isinstance(data, dict):
        return JSONResponse(
            status_code=200,
            content={"decision": "reject", "reason": "INVALID_PLAN"}
        )

    # Check required top-level keys exist with roughly correct types
    required_keys = ["environment", "state", "providerVersion", "destroyApproved", "resource"]
    for k in required_keys:
        if k not in data:
            return JSONResponse(
                status_code=200,
                content={"decision": "reject", "reason": "INVALID_PLAN"}
            )

    # Now run detailed validation
    result = validate_plan(data)
    return JSONResponse(status_code=200, content=result)
