"""
MAS-Medicare-Appeals programmatic supervisor.

Replaces the deleted Agent Bricks supervisor endpoint with a code-based
ResponsesAgent that orchestrates the same 4 tools:

  1. Genie space 01f1083faf3b1f32b53f69073b52bb38  (Claim Denials & Appeals Review)
  2. UC MCP connection  conn_aichemy_pubmed       (PubMed via openpharma)
  3. UC MCP connection  raven_medicare_mcp        (Medicare Part D drug lookups)
  4. UC MCP connection  conn_clinicaltrials       (ClinicalTrials.gov)

Output shape matches the Databricks Agent Framework ResponsesAgent schema,
which the existing FastAPI app (server/routes/chat.py) already understands.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Callable, Iterator, List

import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from pydantic import BaseModel

from databricks.sdk import WorkspaceClient
from databricks_mcp import DatabricksMCPClient

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
LLM_ENDPOINT_NAME = os.environ.get("MAS_LLM_ENDPOINT", "databricks-claude-sonnet-4-6")
MAX_TURNS = 10

GENIE_SPACE_ID = "01f1083faf3b1f32b53f69073b52bb38"
GENIE_TOOL_NAME = "query_appeals_data"
GENIE_TOOL_DESCRIPTION = (
    "Query the Claim Denials & Appeals Review Genie space using natural language. "
    "Use this for any question about specific claims, members, denials, appeals "
    "statuses, eligibility, state corroboration, or aggregate counts/trends from "
    "Molina's claims data. Provide a single natural-language question."
)

MCP_CONNECTIONS = [
    ("pubmed",          "conn_aichemy_pubmed"),
    ("medicare_part_d", "raven_medicare_mcp"),
    ("clinicaltrials",  "conn_clinicaltrials"),
]

SYSTEM_PROMPT = (
    "You are the Medicare Appeals Triage supervisor for a Molina Healthcare claims "
    "operations team. Your job is to help case workers resolve incoming Salesforce "
    "cases about claim denials, appeals, eligibility, and member benefits.\n\n"
    "You orchestrate the following tools:\n"
    f"  - {GENIE_TOOL_NAME}: structured queries on Molina's internal claims/appeals data\n"
    "  - pubmed_*: peer-reviewed clinical evidence (PubMed)\n"
    "  - medicare_part_d_*: Medicare Part D drug pricing/coverage lookups\n"
    "  - clinicaltrials_*: ClinicalTrials.gov for trial/treatment evidence\n\n"
    "Routing guidance:\n"
    "  - Start with the appeals Genie tool for any question about a specific claim, "
    "member, denial reason, or appeals status.\n"
    "  - Use Medicare Part D tools for drug coverage, NDC, prescriber, or spending questions.\n"
    "  - Use PubMed / ClinicalTrials when the user asks for clinical evidence to support "
    "medical-necessity appeals.\n"
    "  - Call multiple tools when needed, then synthesize a single concise answer.\n\n"
    "Style: professional, empathetic, healthcare-appropriate. Reference claim IDs, "
    "dates, and appeals statuses verbatim. Avoid jargon unless explained."
)


# ── Tool wiring ──────────────────────────────────────────────────────────────
class ToolInfo(BaseModel):
    name: str
    spec: dict  # OpenAI tools schema entry
    exec_fn: Callable[..., str]

    model_config = {"arbitrary_types_allowed": True}


def _mcp_server_url(host: str, conn_name: str) -> str:
    return f"{host}/api/2.0/mcp/external/{conn_name}"


def _make_mcp_exec(server_url: str, tool_name: str, ws: WorkspaceClient):
    def _exec(**kwargs) -> str:
        client = DatabricksMCPClient(server_url=server_url, workspace_client=ws)
        resp = client.call_tool(tool_name, kwargs)
        return "".join(c.text for c in resp.content if hasattr(c, "text"))
    return _exec


def _fetch_mcp_tools(ws: WorkspaceClient, host: str) -> List[ToolInfo]:
    infos: list[ToolInfo] = []
    for label, conn in MCP_CONNECTIONS:
        url = _mcp_server_url(host, conn)
        try:
            client = DatabricksMCPClient(server_url=url, workspace_client=ws)
            tools = client.list_tools()
        except Exception as e:
            logger.warning(f"Failed to list tools for MCP connection {conn}: {e}")
            continue
        for t in tools:
            schema = (t.inputSchema or {}).copy()
            schema.setdefault("properties", {})
            # Prefix tool name with the connection label so they're disambiguated
            qualified = f"{label}__{t.name}"
            infos.append(
                ToolInfo(
                    name=qualified,
                    spec={
                        "type": "function",
                        "function": {
                            "name": qualified,
                            "description": t.description or f"{label} MCP tool {t.name}",
                            "parameters": schema,
                        },
                    },
                    exec_fn=_make_mcp_exec(url, t.name, ws),
                )
            )
    return infos


def _make_genie_exec(ws: WorkspaceClient, space_id: str):
    """Stateless Genie call: one user question per invocation; conversation is
    started fresh each call. The supervisor LLM keeps track of context."""
    from databricks.sdk.service.dashboards import GenieAPI  # type: ignore

    api = GenieAPI(ws.api_client)

    def _exec(question: str) -> str:
        try:
            convo = api.start_conversation_and_wait(space_id, question)
            msg = convo.message
            if msg is None:
                return "[Genie returned no message]"
            parts: list[str] = []
            if getattr(msg, "content", None):
                parts.append(msg.content or "")
            for attach in (getattr(msg, "attachments", None) or []):
                # Query attachment includes a description + SQL + sample rows
                q = getattr(attach, "query", None)
                if q is not None:
                    if getattr(q, "description", None):
                        parts.append(q.description)
                    if getattr(q, "query", None):
                        parts.append(f"\nSQL:\n```sql\n{q.query}\n```")
                    # Fetch the query result
                    try:
                        result = api.get_message_query_result_by_attachment(
                            space_id, convo.conversation_id, msg.id, attach.attachment_id
                        )
                        sr = getattr(result, "statement_response", None)
                        if sr and getattr(sr, "result", None):
                            data = sr.result.data_array or []
                            cols = [c.name for c in sr.manifest.schema.columns] if sr.manifest else []
                            preview = [dict(zip(cols, row)) for row in data[:25]]
                            parts.append(f"\nRows (first {len(preview)}): {json.dumps(preview, default=str)}")
                    except Exception as e:
                        parts.append(f"\n[Genie result fetch failed: {e}]")
                text_attach = getattr(attach, "text", None)
                if text_attach is not None and getattr(text_attach, "content", None):
                    parts.append(text_attach.content)
            return "\n".join(p for p in parts if p) or "[Genie returned empty answer]"
        except Exception as e:
            return f"[Genie error: {e}]"

    return _exec


def _genie_tool_info(ws: WorkspaceClient) -> ToolInfo:
    return ToolInfo(
        name=GENIE_TOOL_NAME,
        spec={
            "type": "function",
            "function": {
                "name": GENIE_TOOL_NAME,
                "description": GENIE_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "A natural-language question for the appeals Genie space.",
                        }
                    },
                    "required": ["question"],
                },
            },
        },
        exec_fn=_make_genie_exec(ws, GENIE_SPACE_ID),
    )


# ── Format conversion ────────────────────────────────────────────────────────
def _responses_msg_to_chat(msg: dict[str, Any]) -> list[dict]:
    """Convert a single ResponsesAgent-format item to OpenAI chat-completions msgs."""
    t = msg.get("type")
    if t == "function_call":
        return [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": msg["call_id"],
                "type": "function",
                "function": {"name": msg["name"], "arguments": msg["arguments"]},
            }],
        }]
    if t == "function_call_output":
        return [{
            "role": "tool",
            "content": msg["output"],
            "tool_call_id": msg["call_id"],
        }]
    if t == "message" and isinstance(msg.get("content"), list):
        return [{
            "role": msg.get("role", "assistant"),
            "content": "".join(
                c.get("text", "") if isinstance(c, dict) else str(c)
                for c in msg["content"]
            ),
        }]
    # Plain {role, content}
    return [{k: v for k, v in msg.items() if k in ("role", "content", "name", "tool_calls", "tool_call_id")}]


# ── Agent class ──────────────────────────────────────────────────────────────
class MedicareAppealsSupervisor(ResponsesAgent):
    """Multi-turn supervisor with Genie + 3 MCP connection tools."""

    def __init__(self):
        # Lazy: instantiate workspace + tools per request so deployment is hermetic
        self._tools_cache: list[ToolInfo] | None = None
        self._ws_cache: WorkspaceClient | None = None

    def _ws(self) -> WorkspaceClient:
        if self._ws_cache is None:
            self._ws_cache = WorkspaceClient()
        return self._ws_cache

    def _tools(self) -> list[ToolInfo]:
        if self._tools_cache is None:
            ws = self._ws()
            host = ws.config.host or os.environ.get("DATABRICKS_HOST", "")
            if host and not host.startswith("http"):
                host = f"https://{host}"
            host = host.rstrip("/")
            tools = _fetch_mcp_tools(ws, host)
            tools.append(_genie_tool_info(ws))
            self._tools_cache = tools
            logger.info(
                f"Loaded {len(tools)} tools: " + ", ".join(t.name for t in tools)
            )
        return self._tools_cache

    def _openai_client(self):
        # Uses the SDK's auth chain so it works inside a serving endpoint,
        # a notebook, or a CLI profile equally.
        return self._ws().serving_endpoints.get_open_ai_client()

    def _call_llm(self, history: list[dict], tools: list[ToolInfo]):
        msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history:
            msgs.extend(_responses_msg_to_chat(item))
        client = self._openai_client()
        return client.chat.completions.create(
            model=LLM_ENDPOINT_NAME,
            messages=msgs,
            tools=[t.spec for t in tools],
            tool_choice="auto",
            temperature=0.2,
        )

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        output_items: list[dict] = []
        for ev in self.predict_stream(request):
            if ev.type == "response.output_item.done":
                output_items.append(ev.item)
        return ResponsesAgentResponse(
            output=output_items,
            custom_outputs=getattr(request, "custom_inputs", None),
        )

    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Iterator[ResponsesAgentStreamEvent]:
        tools = self._tools()
        tools_by_name = {t.name: t for t in tools}

        history: list[dict] = []
        for inp in request.input:
            history.append(inp.model_dump() if hasattr(inp, "model_dump") else dict(inp))

        for turn in range(MAX_TURNS):
            resp = self._call_llm(history, tools)
            choice = resp.choices[0].message
            tool_calls = choice.tool_calls or []

            if not tool_calls:
                text = choice.content or ""
                msg_item = {
                    "id": f"msg_{uuid.uuid4().hex}",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done", item=msg_item
                )
                return

            # Emit each tool call as a function_call item, then execute and emit output
            for tc in tool_calls:
                fc_item = {
                    "id": f"fc_{uuid.uuid4().hex}",
                    "call_id": tc.id,
                    "type": "function_call",
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                history.append(fc_item)
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done", item=fc_item
                )

                tool = tools_by_name.get(tc.function.name)
                if tool is None:
                    out = f"[Unknown tool {tc.function.name}]"
                else:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        out = tool.exec_fn(**args)
                    except Exception as e:
                        out = f"[Tool {tc.function.name} error: {e}]"

                out_item = {
                    "id": f"fco_{uuid.uuid4().hex}",
                    "call_id": tc.id,
                    "type": "function_call_output",
                    "output": str(out)[:50000],
                }
                history.append(out_item)
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done", item=out_item
                )

        # Safety net: max turns reached
        msg_item = {
            "id": f"msg_{uuid.uuid4().hex}",
            "type": "message",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": "I wasn't able to complete the request within the tool-call budget. "
                        "Please try a more focused question.",
            }],
        }
        yield ResponsesAgentStreamEvent(type="response.output_item.done", item=msg_item)


mlflow.models.set_model(MedicareAppealsSupervisor())


if __name__ == "__main__":
    # Quick local smoke test (requires DATABRICKS_PROFILE=hls_amer in env)
    logging.basicConfig(level=logging.INFO)
    agent = MedicareAppealsSupervisor()
    req = ResponsesAgentRequest(
        input=[{
            "role": "user",
            "content": "How many open appeals cases do we have?",
        }]
    )
    resp = agent.predict(req)
    for item in resp.output:
        print(json.dumps(item, indent=2, default=str))
