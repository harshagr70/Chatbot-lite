from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from neo4j import GraphDatabase
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.generation import GraphRAG
from langchain_community.llms import Ollama
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from typing import Dict, Optional, Any, List
from contextlib import asynccontextmanager


load_dotenv()

# ------------------------------------------------------------------------------
class LLMResponse:
    def __init__(self, content: str):
        self.content = content

# ------------------------------------------------------------------------------
class LocalLlamaLLM:
    def __init__(self, model="llama3", temperature=0):
        self.llm = Ollama(model=model)
        self.temperature = temperature

    def __call__(self, prompt: str, *args, **kwargs) -> LLMResponse:
        return self.invoke(prompt, *args, **kwargs)

    def invoke(self, prompt: str, *args, **kwargs) -> LLMResponse:
        response_text = self.llm.invoke(prompt, *args, **kwargs)
        return LLMResponse(response_text)

    def predict(self, prompt: str, *args, **kwargs) -> LLMResponse:
        return self.__call__(prompt, *args, **kwargs)

# ------------------------------------------------------------------------------

class ConnectionDetails(BaseModel):
    uri: str
    username: str
    password: str
    database: str = "neo4j"

class QueryRequest(BaseModel):
    query: str
    connection_details: Optional[ConnectionDetails] = None
    include_graph_data: bool = False

class GraphNode(BaseModel):
    id: str
    label: str
    properties: Dict[str, Any]

class GraphRelationship(BaseModel):
    id: str
    type: str
    startNode: str
    endNode: str
    properties: Dict[str, Any]

class GraphData(BaseModel):
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]

class QueryResponse(BaseModel):
    cypher_query: str
    results: list
    explanation: Optional[str] = None
    graph_data: Optional[GraphData] = None

# ------------------------------------------------------------------------------
neo4j_schema = """
Node properties:
Movie {title: STRING, released: INTEGER, genre: STRING}
Actor {name: STRING}
Director {name: STRING}

Relationships:
(:Actor)-[:ACTED_IN]->(:Movie)
(:Director)-[:DIRECTED]->(:Movie)
"""

examples = [
    "USER INPUT: 'Which actors starred in the Matrix?' QUERY: MATCH (p:Person)-[:ACTED_IN]->(m:Movie) WHERE m.title = 'The Matrix' RETURN p.name",
    "USER INPUT: 'Which actors starred in The Matrix?' QUERY: MATCH (p:Actor)-[:ACTED_IN]->(m:Movie) WHERE m.title = 'The Matrix' RETURN p.name",  
    "USER INPUT: 'Who directed Inception?' QUERY: MATCH (d:Director)-[:DIRECTED]->(m:Movie) WHERE m.title = 'Inception' RETURN d.name",  
    "USER INPUT: 'List all movies directed by Christopher Nolan.' QUERY: MATCH (d:Director {name: 'Christopher Nolan'})-[:DIRECTED]->(m:Movie) RETURN m.title",  
    "USER INPUT: 'Which movies did Leonardo DiCaprio act in?' QUERY: MATCH (a:Actor {name: 'Leonardo DiCaprio'})-[:ACTED_IN]->(m:Movie) RETURN m.title",  
    "USER INPUT: 'List all action movies.' QUERY: MATCH (m:Movie) WHERE m.genre = 'Action' RETURN m.title",  
    "USER INPUT: 'Find all sci-fi movies.' QUERY: MATCH (m:Movie) WHERE m.genre = 'Sci-Fi' RETURN m.title",  
    "USER INPUT: 'Who acted in The Dark Knight?' QUERY: MATCH (a:Actor)-[:ACTED_IN]->(m:Movie) WHERE m.title = 'The Dark Knight' RETURN a.name",  
    "USER INPUT: 'Which movies were released in 2010?' QUERY: MATCH (m:Movie) WHERE m.released = 2010 RETURN m.title",  
    "USER INPUT: 'Who directed The Matrix?' QUERY: MATCH (d:Director)-[:DIRECTED]->(m:Movie) WHERE m.title = 'The Matrix' RETURN d.name",  
    "USER INPUT: 'Find all movies Keanu Reeves acted in.' QUERY: MATCH (a:Actor {name: 'Keanu Reeves'})-[:ACTED_IN]->(m:Movie) RETURN m.title",  
    "USER INPUT: 'List all directors.' QUERY: MATCH (d:Director) RETURN d.name",  
    "USER INPUT: 'List all actors.' QUERY: MATCH (a:Actor) RETURN a.name",  
    "USER INPUT: 'Find all movies released after 2000.' QUERY: MATCH (m:Movie) WHERE m.released > 2000 RETURN m.title",  
    "USER INPUT: 'List all movies released before 2010.' QUERY: MATCH (m:Movie) WHERE m.released < 2010 RETURN m.title",  
    "USER INPUT: 'Who directed Interstellar?' QUERY: MATCH (d:Director)-[:DIRECTED]->(m:Movie) WHERE m.title = 'Interstellar' RETURN d.name",  
    "USER INPUT: 'Which actors have acted in both The Matrix and The Matrix Reloaded?' QUERY: MATCH (a:Actor)-[:ACTED_IN]->(m1:Movie {title: 'The Matrix'}), (a)-[:ACTED_IN]->(m2:Movie {title: 'The Matrix Reloaded'}) RETURN a.name",  
    "USER INPUT: 'Find movies that Christian Bale has acted in.' QUERY: MATCH (a:Actor {name: 'Christian Bale'})-[:ACTED_IN]->(m:Movie) RETURN m.title",  
    "USER INPUT: 'Who produced The Dark Knight?' QUERY: MATCH (p:Person)-[:PRODUCED]->(m:Movie) WHERE m.title = 'The Dark Knight' RETURN p.name",  
    "USER INPUT: 'Find movies that were both directed and produced by Christopher Nolan.' QUERY: MATCH (d:Director {name: 'Christopher Nolan'})-[:DIRECTED]->(m:Movie)<-[:PRODUCED]-(d) RETURN m.title",  
    "USER INPUT: 'List all movies along with their release year.' QUERY: MATCH (m:Movie) RETURN m.title, m.released"
]

# ------------------------------------------------------------------------------

class Neo4jConnection:
    def __init__(self):
        self.driver = None
        self.retriever = None
        self.rag = None
        
    def connect(self, uri, username, password, database="neo4j"):
        
        if self.driver:
            self.close()
            
        try:
            
            self.driver = GraphDatabase.driver(uri, auth=(username, password), database=database)
            
            
            with self.driver.session(database=database) as session:
                session.run("RETURN 1")
                
            
            local_llm_for_retriever = LocalLlamaLLM(model="llama3.2")
            self.retriever = Text2CypherRetriever(
                driver=self.driver, 
                llm=local_llm_for_retriever, 
                neo4j_schema=neo4j_schema, 
                examples=examples
            )
            
            local_llm_for_generation = LocalLlamaLLM(model="llama3.2")
            self.rag = GraphRAG(retriever=self.retriever, llm=local_llm_for_generation)
            
            return True
        except Exception as e:
            if self.driver:
                self.driver.close()
                self.driver = None
            raise e
    
    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            self.retriever = None
            self.rag = None
    
    def execute_query(self, cypher_query, database="neo4j"):
        if not self.driver:
            raise ValueError("Not connected to Neo4j")
            
        with self.driver.session(database=database) as session:
            result = session.run(cypher_query)
            records = [record.data() for record in result]
            return records
            

# Global connection manager
connection_manager = Neo4jConnection()

# Application startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load from environment if available
    try:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")
        
        if uri and user and password:
            connection_manager.connect(uri, user, password)
    except Exception:
        # Don't fail startup if connection fails
        pass
        
    yield
    
    # Shutdown: Close all connections
    connection_manager.close()

# ------------------------------------------------------------------------------
# FastAPI App
app = FastAPI(lifespan=lifespan)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# API Endpoints
@app.post("/connect")
async def connect_to_neo4j(details: ConnectionDetails):
    try:
        success = connection_manager.connect(
            details.uri, 
            details.username, 
            details.password, 
            details.database
        )
        return {"status": "connected" if success else "failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def process_query(request: QueryRequest):
    try:
        # If connection details are provided, connect first
        if request.connection_details:
            connection_manager.connect(
                request.connection_details.uri,
                request.connection_details.username,
                request.connection_details.password,
                request.connection_details.database
            )
            
        # Check if we're connected
        if not connection_manager.driver or not connection_manager.retriever or not connection_manager.rag:
            raise HTTPException(status_code=400, detail="Not connected to Neo4j. Please connect first.")
            
        # Process the query
        query_text = request.query
        
        # Get the Cypher query
        search_results = connection_manager.retriever.search(query_text=query_text)
        generated_cypher = search_results.metadata.get("cypher", "No Cypher query generated")
        
        # Execute the query
        results = []
        graph_data = None
        
        if generated_cypher and generated_cypher != "No Cypher query generated":
            try:
                results = connection_manager.execute_query(generated_cypher)
                
                # Get graph visualization data if requested
                if request.include_graph_data:
                    graph_data = connection_manager.get_graph_data(generated_cypher)
            except Exception as e:
                # If execution fails, continue with empty results
                print(f"Query execution error: {str(e)}")
        
        # Generate explanation
        response = connection_manager.rag.search(query_text=query_text)
        explanation = response.answer
        
        return {
            "cypher_query": generated_cypher,
            "results": results,
            "explanation": explanation,
            "graph_data": graph_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------------------------
# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "connected": connection_manager.driver is not None}

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)