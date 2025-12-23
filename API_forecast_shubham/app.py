# app.py

import streamlit as st
import main
from main import app as langgraph_app

st.set_page_config(page_title="Energy Bot", page_icon="⚡")
st.title("⚡ Energy Forecast Agent")


# ============================================================
# INIT MESSAGE HISTORY
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# RENDER STORED CHAT HISTORY
# ============================================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ============================================================
# USER INPUT
# ============================================================
user_msg = st.chat_input("Ask something...")

if user_msg:

    # Save user message
    st.session_state.messages.append({"role": "user", "content": user_msg})

    with st.chat_message("user"):
        st.markdown(user_msg)

    # Build agent state
    state = {
        "user_message": user_msg,
        "actions": [],
        "response_text": "",
        "tool_result": [],
        "final_response": ""
    }

    stream_state = {"bot_response": ""}


    # ============================================================
    # STREAMING ASSISTANT BLOCK
    # ============================================================
    with st.chat_message("assistant"):

        placeholder = st.empty()

        # Callback for streaming LLM text
        def ui_stream(chunk):
            stream_state["bot_response"] += str(chunk)
            placeholder.markdown(stream_state["bot_response"])

        # Connect callback into main.py
        main.STREAM_CALLBACK = ui_stream

        # Run LangGraph
        for _ in langgraph_app.stream(state):
            pass


    # ============================================================
    # SAVE FINAL TEXT MESSAGE
    # ============================================================
    if stream_state["bot_response"].strip():
        st.session_state.messages.append({
            "role": "assistant",
            "content": stream_state["bot_response"]
        })
