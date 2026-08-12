from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal

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
    """Check if provider version is properly pinned."""
    # Allowed: exact version (6.2.1 or = 6.2.1) or pessimistic (~> 6.0)
    if version in ["6.2.1", "= 6.2.1", "~> 6.0"]:
        return True
    # Reject: >=, *, latest, or anything else
    return False

@app.post("/terraform/plan")
def terraform_plan(request: PlanRequest):
    # Rule 1: Type validation (Pydantic handles this automatically)
    # If we get here, types are correct
    
    # Rule 2: Environment must match
    if request.environment != REQUIRED_ENV:
        return {"decision": "reject", "reason": "ENVIRONMENT_MISMATCH"}
    
    # Rule 3: State backend and locking
    if request.state.backend not in ALLOWED_BACKENDS:
        return {"decision": "reject", "reason": "STATE_UNSAFE"}
    if not request.state.locked:
        return {"decision": "reject", "reason": "STATE_UNSAFE"}
    
    # Rule 4: Provider version pinning
    if not validate_provider_version(request.providerVersion):
        return {"decision": "reject", "reason": "UNPINNED_PROVIDER"}
    
    # Rule 5: Labels must match exactly
    if request.resource.labels != REQUIRED_LABELS:
        return {"decision": "reject", "reason": "MISSING_LABELS"}
    
    # Rule 6: Secret must be null or secret://...
    if request.resource.secret is not None:
        if not request.resource.secret.startswith("secret://"):
            return {"decision": "reject", "reason": "PLAINTEXT_SECRET"}
    
    # Rule 7: Stateful deletes require approval
    if request.resource.action == "delete":
        if request.resource.type in STATEFUL_TYPES:
            if not request.destroyApproved:
                return {"decision": "reject", "reason": "DELETE_NOT_APPROVED"}
    
    # Rule 8: Production storage_bucket can't use forceDestroy
    if request.resource.type == "storage_bucket":
        if request.resource.forceDestroy:
            return {"decision": "reject", "reason": "FORCE_DESTROY"}
    
    # All checks passed
    return {"decision": "approve", "reason": "APPROVE"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
