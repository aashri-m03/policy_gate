from flask import Flask, request, jsonify
import os

app = Flask(__name__)

EXPECTED_ENVIRONMENT = "prod-tjzrsh"

REQUIRED_LABELS = {
    "owner": "student-yk6md",
    "environment": "production",
    "cost_center": "cc-ej9a"
}

ALLOWED_BACKENDS = {
    "gcs",
    "s3",
    "azurerm",
    "remote"
}

ALLOWED_ACTIONS = {
    "create",
    "update",
    "delete"
}

DESTRUCTIVE_TYPES = {
    "storage_bucket",
    "sql_database",
    "persistent_disk"
}


def reject(reason):
    return jsonify({
        "decision": "reject",
        "reason": reason
    }), 200


def approve():
    return jsonify({
        "decision": "approve",
        "reason": "APPROVE"
    }), 200


# -------------------------------------------------
# SECRET FORMAT
# -------------------------------------------------

def valid_secret_reference(secret):
    # null is allowed
    if secret is None:
        return True

    # Must be a string if not null
    if type(secret) is not str:
        return False

    # Must start with secret://
    if not secret.startswith("secret://"):
        return False

    # Must contain something after secret://
    if len(secret) <= len("secret://"):
        return False

    return True


# -------------------------------------------------
# SCHEMA VALIDATION
# -------------------------------------------------

def valid_schema(data):

    # Top-level must be an object
    if type(data) is not dict:
        return False

    # Exact top-level fields
    required_top = {
        "environment",
        "state",
        "providerVersion",
        "destroyApproved",
        "resource"
    }

    if set(data.keys()) != required_top:
        return False

    # Top-level types
    if type(data["environment"]) is not str:
        return False

    if type(data["state"]) is not dict:
        return False

    if type(data["providerVersion"]) is not str:
        return False

    if type(data["destroyApproved"]) is not bool:
        return False

    if type(data["resource"]) is not dict:
        return False

    # -------------------------------------------------
    # STATE
    # -------------------------------------------------

    state = data["state"]

    if set(state.keys()) != {
        "backend",
        "locked"
    }:
        return False

    if type(state["backend"]) is not str:
        return False

    if type(state["locked"]) is not bool:
        return False

    # -------------------------------------------------
    # RESOURCE
    # -------------------------------------------------

    resource = data["resource"]

    required_resource = {
        "address",
        "type",
        "action",
        "labels",
        "secret",
        "forceDestroy"
    }

    if set(resource.keys()) != required_resource:
        return False

    if type(resource["address"]) is not str:
        return False

    if type(resource["type"]) is not str:
        return False

    if type(resource["action"]) is not str:
        return False

    if resource["action"] not in ALLOWED_ACTIONS:
        return False

    if type(resource["labels"]) is not dict:
        return False

    # SECRET:
    # Schema only checks null OR string.
    # Actual secret:// validation happens in RULE 6.
    if resource["secret"] is not None:
        if type(resource["secret"]) is not str:
            return False

    if type(resource["forceDestroy"]) is not bool:
        return False

    # Label keys and values must be strings
    for key, value in resource["labels"].items():

        if type(key) is not str:
            return False

        if type(value) is not str:
            return False

    return True


# -------------------------------------------------
# MAIN ENDPOINT
# -------------------------------------------------

@app.route("/terraform/plan", methods=["POST"])
def terraform_plan():

    # =================================================
    # RULE 1: SCHEMA VALIDATION
    # =================================================

    if not request.is_json:
        return reject("INVALID_PLAN")

    data = request.get_json(silent=True)

    if not valid_schema(data):
        return reject("INVALID_PLAN")

    resource = data["resource"]

    # =================================================
    # RULE 2: ENVIRONMENT
    # =================================================

    if data["environment"] != EXPECTED_ENVIRONMENT:
        return reject("ENVIRONMENT_MISMATCH")

    # =================================================
    # RULE 3: STATE
    # =================================================

    state = data["state"]

    if state["backend"] not in ALLOWED_BACKENDS:
        return reject("STATE_UNSAFE")

    if state["locked"] is not True:
        return reject("STATE_UNSAFE")

    # =================================================
    # RULE 4: PROVIDER
    # =================================================

    provider = data["providerVersion"]

    allowed_providers = {
        "6.2.1",
        "= 6.2.1",
        "~> 6.0"
    }

    if provider not in allowed_providers:
        return reject("UNPINNED_PROVIDER")

    # =================================================
    # RULE 5: LABELS
    # =================================================

    labels = resource["labels"]

    for key, expected_value in REQUIRED_LABELS.items():

        if key not in labels:
            return reject("MISSING_LABELS")

        if labels[key] != expected_value:
            return reject("MISSING_LABELS")

    # =================================================
    # RULE 6: SECRET
    # =================================================

    secret = resource["secret"]

    if not valid_secret_reference(secret):
        return reject("PLAINTEXT_SECRET")

    # =================================================
    # RULE 7: DELETE APPROVAL
    # =================================================

    if (
        resource["action"] == "delete"
        and resource["type"] in DESTRUCTIVE_TYPES
        and data["destroyApproved"] is not True
    ):
        return reject("DELETE_NOT_APPROVED")

    # =================================================
    # RULE 8: FORCE DESTROY
    # =================================================

    if (
        data["environment"] == EXPECTED_ENVIRONMENT
        and resource["type"] == "storage_bucket"
        and resource["forceDestroy"] is True
    ):
        return reject("FORCE_DESTROY")

    # =================================================
    # ALL RULES PASSED
    # =================================================

    return approve()


# -------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok"
    })


# -------------------------------------------------
# START SERVER
# -------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
