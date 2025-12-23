# ============================================================
# main.py — FINAL VERSION (ONLY predict + retrain)
# ============================================================

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, List, Dict, Any
from llm import call_llm, call_llm_stream
from datetime import datetime

from tools import (
    predict,
    retrain
)

from langchain_core.messages import AIMessage, ToolMessage
import json, uuid, re
import dateutil.parser


# ============================================================
# STATE
# ============================================================
class AgentState(TypedDict):
    user_message: str
    actions: List[Dict[str, Any]]
    response_text: str
    tool_result: List[Dict[str, Any]]
    final_response: str


STREAM_CALLBACK = None


# ============================================================
# JSON REPAIR
# ============================================================
def try_json_repair(raw: str):
    txt = raw.strip().replace("'", '"')
    txt = re.sub(r",\s*([\]}])", r"\1", txt)

    if txt.count("{") > txt.count("}"):
        txt += "}"
    if txt.count("[") > txt.count("]"):
        txt += "]"

    return txt


def extract_json_like(s: str) -> str:
    """
    Attempt to extract the JSON snippet from model output that may be wrapped
    in markdown fences or additional text. Returns the most JSON-like substring
    (object or array) or the original string if nothing found.
    """
    if not isinstance(s, str):
        return s

    # Remove common fenced code blocks like ```json
    s_clean = re.sub(r"```[a-zA-Z]*", "", s)
    s_clean = s_clean.replace("```", "")

    # Try to find a JSON object first
    obj_start = s_clean.find("{")
    obj_end = s_clean.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        return s_clean[obj_start:obj_end + 1]

    # Fallback: try to find a JSON array
    arr_start = s_clean.find("[")
    arr_end = s_clean.rfind("]")
    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        return s_clean[arr_start:arr_end + 1]

    return s


# ============================================================
# UNIVERSAL DATETIME PARSER
# ============================================================
def parse_any_date(s: str) -> str:
    if not isinstance(s, str):
        return s

    s = s.strip().replace("T", " ")

    try:
        dt = dateutil.parser.parse(s, dayfirst=True)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return s


# ============================================================
# INPUT ARG NORMALIZER
# ============================================================
def normalize_llm_args(tool_name: str, args: dict):
    rename_map = {
        "input": "datetime_str",
        "date": "datetime_str",
        "datetime": "datetime_str",
        "when": "datetime_str"
    }

    fixed = {}

    for k, v in args.items():
        new_key = rename_map.get(k, k)
        fixed[new_key] = v

    # Normalize only for predict
    if tool_name == "predict" and "datetime_str" in fixed:
        fixed["datetime_str"] = parse_any_date(fixed["datetime_str"])

    return fixed

current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# ============================================================
# LLM CHAT NODE (STRICT JSON)
# ============================================================
def chat_node(state: AgentState):

    current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    prompt = f"""
    You are an AI assistant with access to two tools:

    TOOLS:
    - predict(datetime_str)
    - retrain()

    TODAY'S DATETIME (reference):
    {current_dt}

    You MUST output ONLY valid JSON:

    {{
    "actions": [
        {{"tool": "tool_name", "args": {{ }} }}
    ],
    "response": "Natural language reply"
    }}

    RULES:

    1. If the user is just chatting → DO NOT call any tool.
    Use: "actions": []

    2. You ARE allowed to call MULTIPLE tools, BUT ONLY if the user clearly requests multiple actions.
    Example:
        "retrain then forecast tomorrow"
        → actions = [retrain, predict]

    3. STRICT RULE:
    NEVER call `retrain` unless the user explicitly uses words like:
    "retrain", "update model", "train again", "refit the model".
    DO NOT call retrain automatically.
    DO NOT include retrain just to 'help'.
    If user does not explicitly request retraining → do NOT call retrain.

    4. Use `predict` ONLY when the user asks for a forecast, load value, power demand, or provides a date.

    5. If user requests only a prediction:
        → actions = [predict]
    (NO retrain)

    6. ALL user dates must be converted to ISO "YYYY-MM-DD HH:MM:SS".
    All relative dates (“tomorrow”, “next Monday”) MUST be interpreted relative to:
    {current_dt}

    USER MESSAGE:
    "{state['user_message']}"
    """





    raw = call_llm(prompt).strip()
    print(f"\n[DEBUG → RAW LLM OUTPUT] {raw}")

    try:
        parsed = json.loads(raw)
    except Exception:
        # Try to extract a JSON-like substring (handles code fences and extra text)
        extracted = extract_json_like(raw)
        if extracted != raw:
            print(f"[DEBUG] Extracted JSON-like content → {extracted}")
        repaired = try_json_repair(extracted)
        print(f"[DEBUG] Attempting JSON repair → {repaired}")
        try:
            parsed = json.loads(repaired)
        except Exception:
            parsed = {"actions": [], "response": "I could not understand your request."}

    actions = parsed.get("actions", [])
    if not isinstance(actions, list):
        actions = [actions]

    actions = [a for a in actions if isinstance(a, dict) and a.get("tool")]

    state["actions"] = actions
    state["response_text"] = parsed.get("response", "")

    print(f"[DEBUG → Actions] {actions}")
    print(f"[DEBUG → Response] {state['response_text']}\n")

    return state


# ============================================================
# TOOL EXECUTION
# ============================================================
tool_executor = ToolNode([
    predict,
    retrain
])


def clean_args(args):
    out = {}
    for k, v in args.items():
        if v in ["", None]:
            continue

        if k == "limit":
            try:
                out[k] = int(v)
                continue
            except:
                continue

        out[k] = v

    return out


def tool_node(state: AgentState):
    results = []

    for action in state["actions"]:
        tool_name = action["tool"]

        raw_args = action.get("args", {})
        processed_args = normalize_llm_args(tool_name, raw_args)
        tool_args = clean_args(processed_args)

        tool_call = {
            "name": tool_name,
            "args": tool_args,
            "id": str(uuid.uuid4())
        }

        print(f"[DEBUG → Tool Call] {tool_call}")

        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        invoke_result = tool_executor.invoke({"messages": [ai_msg]})

        output = None
        for msg in invoke_result.get("messages", []):
            if isinstance(msg, ToolMessage):
                output = msg.content

        print(f"[DEBUG → Tool Result] {output}\n")

        results.append({"tool": tool_name, "output": output})

    state["tool_result"] = results
    return state


# ============================================================
# RESPONSE NODE
# ============================================================
def response_node(state: AgentState):
    if not state["actions"]:
        txt = state["response_text"]
        print("Bot:", txt)
        if STREAM_CALLBACK:
            STREAM_CALLBACK(txt)
        state["final_response"] = txt
        return state

    combined = ""
    for item in state["tool_result"]:
        combined += f"\n=== TOOL: {item['tool']} ===\n{item['output']}\n"

    prompt = f"""
Summarize this in short:

{combined}

Try to be as witty as possible.
"""

    final = ""
    print("Bot: ", end="")

    for chunk in call_llm_stream(prompt):
        print(chunk, end="")
        if STREAM_CALLBACK:
            STREAM_CALLBACK(chunk)
        final += chunk

    print()
    state["final_response"] = final
    return state


# ============================================================
# ROUTER + GRAPH
# ============================================================
def router(state: AgentState):
    return "tool" if state["actions"] else "respond"


graph = StateGraph(AgentState)
graph.add_node("chat", chat_node)
graph.add_node("tool", tool_node)
graph.add_node("respond", response_node)

graph.set_entry_point("chat")
graph.add_conditional_edges("chat", router, {"tool": "tool", "respond": "respond"})
graph.add_edge("tool", "respond")
graph.add_edge("respond", END)

app = graph.compile()


# ============================================================
# TERMINAL MODE
# ============================================================
if __name__ == "__main__":
    print("\n🤖 Agent Ready!\n")
    while True:
        user = input("You: ")
        state = {
            "user_message": user,
            "actions": [],
            "response_text": "",
            "tool_result": [],
            "final_response": ""
        }
        for _ in app.stream(state):
            pass
