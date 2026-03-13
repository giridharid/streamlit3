import streamlit as st
import uuid
import os
import json
import base64
from google.cloud import geminidataanalytics_v1alpha as geminidataanalytics
from google.oauth2 import service_account

# --- 1. CONFIGURATION ---
PROJECT_ID = "gen-lang-client-0143536012"
LOCATION = "global"
AGENT_ID = "agent_b9a402f4-9a19-40c7-849e-e1df4f3ad0b2"

# --- 2. CREDENTIALS HANDLING FOR RAILWAY ---
def get_credentials():
    gcp_creds = os.environ.get("GCP_CREDENTIALS_JSON", "")
    
    if gcp_creds:
        gcp_creds = gcp_creds.strip()
        if gcp_creds.startswith('"') and gcp_creds.endswith('"'):
            gcp_creds = gcp_creds[1:-1]
        if gcp_creds.startswith("'") and gcp_creds.endswith("'"):
            gcp_creds = gcp_creds[1:-1]
        
        try:
            if gcp_creds.strip().startswith("{"):
                creds_dict = json.loads(gcp_creds)
            else:
                padding = 4 - len(gcp_creds) % 4
                if padding != 4:
                    gcp_creds += "=" * padding
                decoded = base64.b64decode(gcp_creds).decode('utf-8')
                creds_dict = json.loads(decoded)
            
            return service_account.Credentials.from_service_account_info(creds_dict)
        except Exception as e:
            st.error(f"Credential error: {e}")
            return None
    return None

# --- 3. INITIALIZE CLIENT ---
@st.cache_resource
def get_chat_client():
    credentials = get_credentials()
    if credentials:
        return geminidataanalytics.DataChatServiceClient(credentials=credentials)
    return geminidataanalytics.DataChatServiceClient()

chat_client = get_chat_client()
parent_path = f"projects/{PROJECT_ID}/locations/{LOCATION}"
agent_path = f"{parent_path}/dataAgents/{AGENT_ID}"

# --- 4. SESSION STATE INITIALIZATION ---
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = f"hotel-chat-{uuid.uuid4().hex[:6]}"

if "messages" not in st.session_state:
    st.session_state.messages = []

conv_path = chat_client.conversation_path(PROJECT_ID, LOCATION, st.session_state.conversation_id)

def setup_conversation():
    try:
        chat_client.get_conversation(name=conv_path)
    except Exception:
        conversation = geminidataanalytics.Conversation(agents=[agent_path])
        request = geminidataanalytics.CreateConversationRequest(
            parent=parent_path,
            conversation_id=st.session_state.conversation_id,
            conversation=conversation,
        )
        chat_client.create_conversation(request=request)

# --- 5. STREAMLIT UI ---
st.set_page_config(page_title="Hotel Data Analyst", page_icon="🏨")
st.title("🏨 Hotel Data Analyst")

with st.spinner("Setting up secure agent conversation..."):
    setup_conversation()

# Draw the chat history on the screen from previous interactions
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 6. CHAT INPUT & STREAMING ---
if user_input := st.chat_input("Ask about your hotels (e.g., What is so great about Leela Bangalore?):"):
    
    # Save and display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Assistant response area
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # Send the request with the Data Agent Context explicitly set
            response_stream = chat_client.chat(
                request={
                    "parent": parent_path,
                    "conversation_reference": {
                        "conversation": conv_path,
                        "data_agent_context": {
                            "data_agent": agent_path
                        }
                    },
                    "messages": [
                        {
                            "user_message": {
                                "text": user_input
                            }
                        }
                    ]
                }
            )
            
            # Parse the streaming response
            for chunk in response_stream:
                
                # 1. Catch the Agent's "Thoughts" (System Messages)
                if hasattr(chunk, 'system_message') and hasattr(chunk.system_message, 'text'):
                    for part in chunk.system_message.text.parts:
                        st.caption(f"💭 *{part}*")
                
                # 2. Catch the Actual Answer
                if hasattr(chunk, 'agent_message') and hasattr(chunk.agent_message, 'text'):
                    for part in chunk.agent_message.text.parts:
                        full_response += str(part)
                        message_placeholder.markdown(full_response + "▌")
                        
                # Fallback for the standard Gemini structure
                elif hasattr(chunk, 'message'):
                    msg = chunk.message
                    if hasattr(msg, 'content') and hasattr(msg.content, 'parts'):
                        for part in msg.content.parts:
                            part_text = part.text if hasattr(part, 'text') else str(part)
                            full_response += part_text
                            message_placeholder.markdown(full_response + "▌")

            # Finalize the UI
            if full_response:
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                message_placeholder.markdown("*(Finished analyzing, but looking for final answer structure...)*")

        except Exception as e:
            st.error(f"Chat failed: {e}")

# Clear conversation button
if st.session_state.messages:
    if st.button("🗑️ Clear Conversation"):
        st.session_state.messages = []
        st.session_state.conversation_id = f"hotel-chat-{uuid.uuid4().hex[:6]}"
        st.rerun()
