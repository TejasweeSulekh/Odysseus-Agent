import os
import chromadb
from chromadb.utils import embedding_functions

# Keep the vector DB local and persistent inside our database folder
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'chroma_db'))
os.makedirs(DB_DIR, exist_ok=True)

# Initialize ChromaDB client
client = chromadb.PersistentClient(path=DB_DIR)

# Use an ultra-lightweight, fast local embedding model (runs on CPU)
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

# Get or create our memory collection
collection = client.get_or_create_collection(
    name="odysseus_workspace", 
    embedding_function=sentence_transformer_ef
)

def memorize_text(doc_id: str, text: str, metadata: dict = None):
    """Chunks text and stores it in the vector database."""
    if not metadata:
        metadata = {"source": doc_id}
        
    # Naive chunking: Split by paragraphs to keep it simple and lightweight
    chunks = [chunk.strip() for chunk in text.split('\n\n') if len(chunk.strip()) > 50]
    
    if not chunks:
        return "Nothing to memorize."

    # Create unique IDs for each chunk
    ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [metadata for _ in chunks]
    
    try:
        # Upsert (Update or Insert) the chunks into the vector database
        collection.upsert(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        return f"SUCCESS: Memorized {len(chunks)} chunks from {doc_id}."
    except Exception as e:
        return f"ERROR memorizing text: {e}"

def query_memory(query_string: str, n_results: int = 2) -> str:
    """Searches the vector database for the most relevant context."""
    try:
        results = collection.query(
            query_texts=[query_string],
            n_results=n_results
        )
        
        if not results['documents'][0]:
            return f"MEMORY SEARCH: No relevant memories found for '{query_string}'."
            
        memory_context = "--- RECALLED MEMORY ---\n"
        for i, doc in enumerate(results['documents'][0]):
            source = results['metadatas'][0][i].get('source', 'Unknown')
            memory_context += f"Source [{source}]: {doc}\n\n"
            
        return memory_context
    except Exception as e:
        return f"ERROR querying memory: {e}"

if __name__ == "__main__":
    # Quick Test
    memorize_text("test_doc.md", "Odysseus is an edge-optimized AI OS. It uses SQLite for slow-path kanban execution.")
    memorize_text("test_doc2.md", "The Fast-Path uses an in-memory ReAct loop to minimize latency.")
    print(query_memory("How does the slow path work?"))