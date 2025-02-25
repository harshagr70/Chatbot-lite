import streamlit as st
import requests
import pandas as pd
import os
from dotenv import load_dotenv



load_dotenv()


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


st.set_page_config(
    page_title="Neo4j GraphRAG Explorer",
    layout="wide",
    initial_sidebar_state="expanded"
)


st.markdown("""
<style>
    .connection-status {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .connected {
        background-color: #d4edda;
        color: #155724;
    }
    .disconnected {
        background-color: #f8d7da;
        color: #721c24;
    }
    .small-text {
        font-size: 12px;
    }
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .result-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)


if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'connection_details' not in st.session_state:
    st.session_state.connection_details = {
        "uri": os.getenv("NEO4J_URI", ""),
        "username": os.getenv("NEO4J_USER", ""),
        "password": os.getenv("NEO4J_PASSWORD", ""),
        "database": os.getenv("NEO4J_DATABASE", "neo4j")
    }
if 'last_response' not in st.session_state:
    st.session_state.last_response = None

# Helper Functions
def check_api_health():
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        return response.status_code == 200 and response.json().get("status") == "healthy"
    except Exception as e:
        st.sidebar.error(f"API health check error: {str(e)}")
        return False

def connect_to_database(uri, username, password, database):
    try:
        response = requests.post(
            f"{API_BASE_URL}/connect",
            json={
                "uri": uri,
                "username": username,
                "password": password,
                "database": database
            },
            timeout=10
        )
        if response.status_code == 200 and response.json().get("status") == "connected":
            st.session_state.connected = True
            return True
        else:
            st.session_state.connected = False
            error_msg = response.json().get("detail", "Unknown error")
            st.error(f"Connection failed: {error_msg}")
            return False
    except Exception as e:
        st.error(f"Connection error: {str(e)}")
        st.session_state.connected = False
        return False

def process_query(query_text, include_graph_data=True):
    try:
        data = {
            "query": query_text,
            "include_graph_data": include_graph_data
        }
        
        
        if not st.session_state.connected:
            data["connection_details"] = st.session_state.connection_details
        
        
        st.session_state.request_payload = data
        
        response = requests.post(
            f"{API_BASE_URL}/query",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            
            st.session_state.last_response = response.json()
            
            
            st.session_state.connected = True
            return True
        else:
            error_detail = "Unknown error"
            try:
                error_detail = response.json().get('detail', 'Unknown error')
            except:
                error_detail = f"Status code: {response.status_code}"
                
            st.error(f"Query error: {error_detail}")
            return False
    except Exception as e:
        st.error(f"Query processing error: {str(e)}")
        return False


st.title("Chatbot-Lite")


with st.sidebar:
    st.header("Connection Settings")
    
    
    uri = st.text_input("Neo4j URI", value=st.session_state.connection_details["uri"])
    username = st.text_input("Username", value=st.session_state.connection_details["username"])
    password = st.text_input("Password", value=st.session_state.connection_details["password"], type="password")
    database = st.text_input("Database", value=st.session_state.connection_details["database"])
    
    connect_button = st.button("Connect to Neo4j")
    
    if connect_button:
        with st.spinner("Connecting to Neo4j..."):
            
            st.session_state.connection_details = {
                "uri": uri,
                "username": username,
                "password": password,
                "database": database
            }
            
            
            if connect_to_database(uri, username, password, database):
                st.success("Connected successfully!")
            else:
                st.error("Failed to connect to Neo4j.")
    
    
    api_status = check_api_health()
    if api_status:
        st.sidebar.success("API is healthy")
    else:
        st.sidebar.error("API is not available")

    
    if st.session_state.connected:
        st.markdown('<div class="connection-status connected">✅ Connected to Neo4j</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="connection-status disconnected">❌ Not connected to Neo4j</div>', unsafe_allow_html=True)
    
    
    st.header("Example Queries")
    example_queries = [
        "Which actors starred in The Matrix?",
        "Who directed Inception?",
        "List all movies directed by Christopher Nolan.",
        "Which movies did Leonardo DiCaprio act in?",
        "Find all sci-fi movies.",
        "Find movies released after 2000.",
        "Who acted in The Dark Knight?"
    ]
    
    for query in example_queries:
        if st.button(query, key=f"example_{query}"):
            st.session_state.query = query
            process_query(query, include_graph_data=True)
            
            st.rerun()


st.header("Natural Language Query")


query = st.text_area("Enter your question about the movie database", 
                     value=st.session_state.get("query", ""), 
                     height=100)

col1, col2 = st.columns([1, 1])

with col2:
    search_button = st.button("Search", type="primary")

if search_button and query:
    st.session_state.query = query
    with st.spinner("Processing your query..."):
        success = process_query(query)


if st.session_state.last_response is not None:
    st.markdown("---")
    
    
    response_data = st.session_state.last_response
    cypher_query = response_data.get("cypher_query", "No Cypher query generated")
    results = response_data.get("results", [])
    explanation = response_data.get("explanation", "")
    graph_data = response_data.get("graph_data")
    
    
    st.subheader("Generated Cypher Query")
    st.code(cypher_query, language="cypher")
    
    
    st.subheader("Query Results")
    
    if not results:
        st.info("No results found for your query.")
    else:
        
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)
    
    
    if explanation:
        st.subheader("Explanation")
        st.write(explanation)

    
    with st.expander("Debug Information", expanded=False):
        st.subheader("Raw Response")
        st.json(response_data)
        
        if hasattr(st.session_state, 'request_payload'):
            st.subheader("Request Payload")
            st.json(st.session_state.request_payload)


st.markdown("---")
st.markdown(
    "<div class='small-text'>Neo4j GraphRAG Explorer powered by Streamlit and FastAPI</div>", 
    unsafe_allow_html=True
)