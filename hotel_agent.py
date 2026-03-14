import streamlit as st
import uuid
import os
import json
import base64
import re
from google.cloud import geminidataanalytics_v1alpha as geminidataanalytics
from google.oauth2 import service_account

# --- PAGE CONFIG (must be first Streamlit command) ---
st.set_page_config(page_title="Hotel Data Intelligence", page_icon="🏨", layout="wide")

# --- 1. CONFIGURATION ---
PROJECT_ID = "gen-lang-client-0143536012"
LOCATION = "global"
AGENT_ID = "agent_b9a402f4-9a19-40c7-849e-e1df4f3ad0b2"

# --- 2. SPELLING CORRECTIONS & ALIASES ---
CITY_ALIASES = {
    # Bangalore variations
    "bangalore": "Bengaluru", "blr": "Bengaluru", "banglore": "Bengaluru", "bangaluru": "Bengaluru",
    "bengaluru": "Bengaluru", "bengalore": "Bengaluru", "banglaore": "Bengaluru",
    # Mumbai variations
    "bombay": "Mumbai", "mumbai": "Mumbai", "mum": "Mumbai", "bom": "Mumbai",
    # Delhi variations
    "delhi": "Delhi", "new delhi": "New Delhi", "newdelhi": "New Delhi", "del": "Delhi",
    # Chennai variations
    "chennai": "Chennai", "madras": "Chennai", "che": "Chennai",
    # Hyderabad variations
    "hyderabad": "Hyderabad", "hyd": "Hyderabad", "hydrabad": "Hyderabad", "secundrabad": "Hyderabad",
    # Kolkata variations
    "kolkata": "Kolkata", "calcutta": "Kolkata", "cal": "Kolkata",
    # Goa variations
    "goa": "Goa", "panaji": "Goa", "panjim": "Goa",
    # Jaipur variations
    "jaipur": "Jaipur", "jaipure": "Jaipur",
    # Pune variations
    "pune": "Pune", "poona": "Pune",
    # Ahmedabad variations
    "ahmedabad": "Ahmedabad", "ahemdabad": "Ahmedabad", "amdavad": "Ahmedabad",
    # Udaipur variations
    "udaipur": "Udaipur", "udiapur": "Udaipur",
    # Agra variations
    "agra": "Agra",
    # Kochi variations
    "kochi": "Kochi", "cochin": "Kochi",
}

HOTEL_ALIASES = {
    # Taj variations
    "taj": "Taj", "tajj": "Taj", "taz": "Taj",
    # ITC variations
    "itc": "ITC", "i.t.c": "ITC", "i t c": "ITC",
    # Leela variations
    "leela": "Leela", "lela": "Leela", "leelaa": "Leela", "the leela": "Leela",
    # Oberoi variations
    "oberoi": "Oberoi", "oberoy": "Oberoi", "the oberoi": "Oberoi",
    # Marriott variations
    "marriott": "Marriott", "marriot": "Marriott", "mariot": "Marriott", "jw marriott": "JW Marriott",
    # Hyatt variations
    "hyatt": "Hyatt", "hyat": "Hyatt", "hayatt": "Hyatt", "grand hyatt": "Grand Hyatt",
    # Vivanta variations
    "vivanta": "Vivanta", "viventa": "Vivanta", "vivantha": "Vivanta",
    # Radisson variations
    "radisson": "Radisson", "radison": "Radisson", "raddison": "Radisson",
    # Sheraton variations
    "sheraton": "Sheraton", "sharaton": "Sheraton", "shereton": "Sheraton",
    # Hilton variations
    "hilton": "Hilton", "hillton": "Hilton",
    # Westin variations
    "westin": "Westin", "westinn": "Westin",
}

ASPECT_ALIASES = {
    # Room variations
    "room": "Room", "rooms": "Room", "bedroom": "Room", "suite": "Room", "accomodation": "Room", "accommodation": "Room",
    # Dining variations
    "dining": "Dining", "food": "Dining", "restaurant": "Dining", "breakfast": "Dining", "dinner": "Dining", 
    "lunch": "Dining", "cuisine": "Dining", "meals": "Dining", "eating": "Dining", "buffet": "Dining",
    # Staff variations
    "staff": "Staff", "service": "Staff", "employees": "Staff", "hospitality": "Staff", "concierge": "Staff",
    "reception": "Staff", "housekeeping": "Staff", "servers": "Staff", "waiters": "Staff",
    # Cleanliness variations
    "cleanliness": "Cleanliness", "clean": "Cleanliness", "hygiene": "Cleanliness", "dirty": "Cleanliness",
    "tidiness": "Cleanliness", "houskeeping": "Cleanliness", "sanitization": "Cleanliness",
    # Location variations
    "location": "Location", "place": "Location", "area": "Location", "locality": "Location", "neighbourhood": "Location",
    # Amenities variations
    "amenities": "Amenities", "facilities": "Amenities", "pool": "Amenities", "gym": "Amenities", 
    "spa": "Amenities", "wifi": "Amenities", "parking": "Amenities", "amenety": "Amenities",
    # Value for Money variations
    "value": "Value for Money", "price": "Value for Money", "cost": "Value for Money", "expensive": "Value for Money",
    "cheap": "Value for Money", "worth": "Value for Money", "pricing": "Value for Money", "rates": "Value for Money",
}

def preprocess_query(query):
    """
    Preprocess the query to correct spelling mistakes for cities, hotels, aspects
    """
    processed = query
    
    # Correct city names
    for alias, correct in CITY_ALIASES.items():
        pattern = re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)
        processed = pattern.sub(correct, processed)
    
    # Correct hotel names
    for alias, correct in HOTEL_ALIASES.items():
        pattern = re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)
        processed = pattern.sub(correct, processed)
    
    # Correct aspect names
    for alias, correct in ASPECT_ALIASES.items():
        pattern = re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)
        processed = pattern.sub(correct, processed)
    
    return processed

def build_enhanced_prompt(user_query):
    """
    Build an enhanced prompt that includes:
    1. Preprocessed query with corrections
    2. Instructions for language handling
    """
    processed_query = preprocess_query(user_query)
    
    enhanced_prompt = f"""
User Query: {processed_query}

Instructions:
1. If the user's query is in a language other than English, first understand the query, then analyze the data, and respond in the SAME language as the query.
2. Use the corrected entity names provided in the query (cities, hotels, aspects).
3. Be helpful and provide data-driven insights.
4. If you detect any remaining spelling errors or ambiguous names, try to infer the correct entity and mention the correction politely.

Original user input: {user_query}
"""
    return enhanced_prompt

# --- 3. CREDENTIALS HANDLING FOR RAILWAY ---
def get_credentials():
    gcp_creds = os.environ.get("GCP_CREDENTIALS_JSON", "")
    
    if not gcp_creds:
        return None
    
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

# --- 4. INITIALIZE CLIENT ---
@st.cache_resource
def get_chat_client():
    credentials = get_credentials()
    if credentials:
        from google.api_core import client_options
        client_opts = client_options.ClientOptions()
        return geminidataanalytics.DataChatServiceClient(
            credentials=credentials,
            client_options=client_opts
        )
    else:
        try:
            return geminidataanalytics.DataChatServiceClient()
        except Exception as e:
            st.error(f"Failed to create client. Set GCP_CREDENTIALS_JSON environment variable.")
            st.error(f"Error: {e}")
            st.stop()

chat_client = get_chat_client()
parent_path = f"projects/{PROJECT_ID}/locations/{LOCATION}"
agent_path = f"{parent_path}/dataAgents/{AGENT_ID}"

# --- 5. SESSION STATE INITIALIZATION ---
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = f"hotel-intel-{uuid.uuid4().hex[:6]}"

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

# --- 6. STREAMLIT UI ---
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #1e3a5f 0%, #0d9488 100%);
        border-radius: 12px;
        margin-bottom: 24px;
    }
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
    }
    .main-header p {
        color: rgba(255,255,255,0.85);
        margin: 8px 0 0 0;
        font-size: 0.95rem;
    }
</style>
<div class="main-header">
    <h1>🏨 Hotel Data Intelligence</h1>
    <p>Ask questions in any language • Auto-corrects city & hotel names</p>
</div>
""", unsafe_allow_html=True)

with st.spinner("Connecting to intelligence agent..."):
    setup_conversation()

# Language support info
with st.expander("🌐 Supported Languages & Smart Corrections", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Languages:** English, हिंदी, தமிழ், తెలుగు, ಕನ್ನಡ, മലയാളം, मराठी, বাংলা, ગુજરાતી, ਪੰਜਾਬੀ, and more...
        
        **City Corrections:**
        - Bangalore, Blr, Banglore → Bengaluru
        - Bombay → Mumbai
        - Madras → Chennai
        - Calcutta → Kolkata
        """)
    with col2:
        st.markdown("""
        **Hotel Corrections:**
        - Marriot, Mariot → Marriott
        - Oberoy → Oberoi
        - Viventa → Vivanta
        
        **Aspect Corrections:**
        - Food, Restaurant → Dining
        - Clean, Hygiene → Cleanliness
        - Price, Cost → Value for Money
        """)

# Draw chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 7. CHAT INPUT & STREAMING ---
if user_input := st.chat_input("Ask about hotels in any language... (e.g., 'बैंगलोर में सबसे अच्छा होटल कौन सा है?')"):
    
    # Show original input
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Preprocess and enhance the query
    enhanced_query = build_enhanced_prompt(user_input)

    # Assistant response area
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
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
                                "text": enhanced_query
                            }
                        }
                    ]
                }
            )
            
            # Parse the streaming response
            for chunk in response_stream:
                
                # Catch the Agent's "Thoughts"
                if hasattr(chunk, 'system_message') and hasattr(chunk.system_message, 'text'):
                    for part in chunk.system_message.text.parts:
                        st.caption(f"💭 *{part}*")
                
                # Catch the Actual Answer
                if hasattr(chunk, 'agent_message') and hasattr(chunk.agent_message, 'text'):
                    for part in chunk.agent_message.text.parts:
                        full_response += str(part)
                        message_placeholder.markdown(full_response + "▌")
                        
                # Fallback for standard Gemini structure
                elif hasattr(chunk, 'message'):
                    msg = chunk.message
                    if hasattr(msg, 'content') and hasattr(msg.content, 'parts'):
                        for part in msg.content.parts:
                            part_text = part.text if hasattr(part, 'text') else str(part)
                            full_response += part_text
                            message_placeholder.markdown(full_response + "▌")

            # Finalize
            if full_response:
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                message_placeholder.markdown("*(Processing complete)*")

        except Exception as e:
            st.error(f"Chat failed: {e}")

# Clear conversation button
if st.session_state.messages:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_id = f"hotel-intel-{uuid.uuid4().hex[:6]}"
            st.rerun()

# Footer
st.divider()
st.caption("🏨 Hotel Data Intelligence • Powered by Gemini Data Analytics • Supports multiple languages")
