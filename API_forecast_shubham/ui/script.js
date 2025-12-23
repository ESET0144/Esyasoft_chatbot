// script.js - minimal frontend to call /chat endpoint and render messages

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");

function appendUser(text){
  const div = document.createElement("div");
  div.className = "msg user";
  div.innerHTML = `<div class="content">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function appendBot(text, toolResult){
  const div = document.createElement("div");
  div.className = "msg bot";
  let html = `<div class="content">${escapeHtml(text)}</div>`;
  if(toolResult){
    html += `<div class="tool"><strong>Tool Result:</strong><br/>${escapeHtml(toolResult)}</div>`;
  }
  div.innerHTML = html;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function appendLoading(){
  const div = document.createElement("div");
  div.className = "msg bot";
  div.id = "loading";
  div.innerHTML = `<div class="content">Thinking<span id="dots">.</span></div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
  let dots = 1;
  window._loadingInterval = setInterval(()=>{
    const el = document.getElementById("dots");
    if(el) el.textContent = ".".repeat(dots % 4);
    dots++;
  }, 400);
}

function removeLoading(){
  clearInterval(window._loadingInterval);
  const loading = document.getElementById("loading");
  if(loading) loading.remove();
}

function scrollToBottom(){
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(str){
  if(!str) return "";
  return str
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");
}

async function sendMessage(){
  const text = inputEl.value.trim();
  if(!text) return false;

  appendUser(text);
  inputEl.value = "";
  appendLoading();

  try{
    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({message: text})
    });

    removeLoading();

    if(!res.ok){
      const err = await res.text();
      appendBot("Error: " + res.status + " " + err);
      return false;
    }

    const data = await res.json();
    // prefer final_response/response keys
    const botText = data.response || data.final_response || data.reply || "";
    const tool = data.tool_result || data.toolResult || data.tool || "";
    appendBot(botText, tool);

  }catch(e){
    removeLoading();
    appendBot("Network error: " + e.message);
  }

  return false;
}

// send on enter
inputEl.addEventListener("keydown", (e)=>{
  if(e.key === "Enter" && !e.shiftKey){
    e.preventDefault();
    sendMessage();
  }
});
