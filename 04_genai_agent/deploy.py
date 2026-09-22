"""
Log, register, and deploy the MAS-Medicare-Appeals supervisor.

Usage (from /Users/raven.mukherjee/claude-code/medicare-appeals-chat/supervisor):
    DATABRICKS_CONFIG_PROFILE=hls_amer python deploy.py

Produces a serving endpoint via databricks-agents and prints its name so the
caller can wire it into the app.
"""

from __future__ import annotations

import os
import sys

import mlflow
from mlflow.models.resources import (
    DatabricksGenieSpace,
    DatabricksServingEndpoint,
    DatabricksUCConnection,
)
from databricks.sdk import WorkspaceClient
from databricks import agents

from agent import (
    GENIE_SPACE_ID,
    LLM_ENDPOINT_NAME,
    MCP_CONNECTIONS,
)

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE", "hls_amer")
os.environ["DATABRICKS_CONFIG_PROFILE"] = PROFILE

UC_MODEL_NAME = os.environ.get(
    "MAS_UC_MODEL_NAME",
    "hls_amer_catalog.appeals_review_agents.mas_medicare_appeals_supervisor",
)


def main() -> None:
    ws = WorkspaceClient(profile=PROFILE)
    user = ws.current_user.me().user_name
    host = (ws.config.host or "").rstrip("/")

    mlflow.set_tracking_uri(f"databricks://{PROFILE}")
    mlflow.set_registry_uri(f"databricks-uc://{PROFILE}")
    mlflow.set_experiment(f"/Users/{user}/mas_medicare_appeals_supervisor")

    resources = [
        DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT_NAME),
        DatabricksGenieSpace(genie_space_id=GENIE_SPACE_ID),
    ]
    for _, conn in MCP_CONNECTIONS:
        resources.append(DatabricksUCConnection(connection_name=conn))

    here = os.path.dirname(os.path.abspath(__file__))
    agent_script = os.path.join(here, "agent.py")
    req_file = os.path.join(here, "requirements.txt")

    print(f"Logging model from {agent_script}")
    with mlflow.start_run(run_name="mas_medicare_appeals_supervisor"):
        info = mlflow.pyfunc.log_model(
            artifact_path="agent",
            python_model=agent_script,
            pip_requirements=req_file,
            resources=resources,
        )

    print(f"Registering as {UC_MODEL_NAME}")
    registered = mlflow.register_model(info.model_uri, UC_MODEL_NAME)
    print(f"Registered version: {registered.version}")

    print("Deploying via databricks-agents...")
    deployment = agents.deploy(
        model_name=UC_MODEL_NAME,
        model_version=int(registered.version),
        scale_to_zero=True,
    )
    endpoint_name = getattr(deployment, "endpoint_name", None) or getattr(deployment, "name", None)
    print(f"Deployed endpoint: {endpoint_name}")
    print(f"Review app URL: {getattr(deployment, 'review_app_url', None)}")
    if endpoint_name:
        # Echo to a small file for the next deploy step to pick up
        with open(os.path.join(here, ".endpoint"), "w") as f:
            f.write(endpoint_name + "\n")


if __name__ == "__main__":
    sys.exit(main() or 0)
