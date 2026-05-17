"""
Materials Store
---------------
Uses ChromaDB (local, free) as a vector database to store and
semantically search learning materials, articles, and resources.
The embeddings are generated locally — no API calls needed.
"""

import os
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/materials/chroma_db")


def get_collection():
    """Get (or create) the learning materials collection."""
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Use Chroma's built-in sentence transformer embeddings (runs locally, free)
    ef = embedding_functions.DefaultEmbeddingFunction()

    return client.get_or_create_collection(
        name="learning_materials",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )


def add_material(
    doc_id: str,
    content: str,
    topic: str,
    source: str = "generated",
    difficulty: str = "intermediate",
    material_type: str = "article",  # article | example | reference | video_summary
):
    """
    Add a learning resource to the vector store.

    Args:
        doc_id:        Unique ID for this document
        content:       The text content to embed and store
        topic:         Which curriculum topic this relates to
        source:        Where this came from (url, "generated", etc.)
        difficulty:    beginner | intermediate | advanced
        material_type: Type of resource
    """
    collection = get_collection()
    collection.upsert(
        documents=[content],
        metadatas=[{
            "topic": topic,
            "source": source,
            "difficulty": difficulty,
            "type": material_type,
        }],
        ids=[doc_id],
    )


def search_materials(
    query: str,
    topic_filter: str | None = None,
    difficulty_filter: str | None = None,
    n_results: int = 3,
) -> list[dict]:
    """
    Semantically search for relevant learning materials.

    Args:
        query:            Natural language search query
        topic_filter:     Optional: restrict to a specific topic
        difficulty_filter: Optional: restrict to a difficulty level
        n_results:        How many results to return

    Returns:
        List of dicts with 'content', 'topic', 'source', 'distance'
    """
    collection = get_collection()

    where_clause = {}
    if topic_filter:
        where_clause["topic"] = topic_filter
    if difficulty_filter:
        where_clause["difficulty"] = difficulty_filter

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where_clause if where_clause else None,
    )

    materials = []
    for i, doc in enumerate(results["documents"][0]):
        materials.append({
            "content": doc,
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    return materials


def seed_example_materials():
    """
    Seed the vector store with a few example materials.
    Call this once to populate the DB for testing.
    """
    examples = [
        {
            "id": "python_lists_001",
            "content": (
                "Python lists are ordered, mutable collections. "
                "You can create a list with square brackets: my_list = [1, 2, 3]. "
                "List comprehensions offer a concise way to build lists: "
                "[x*2 for x in range(10)]. "
                "Common methods: append(), extend(), pop(), sort(), len()."
            ),
            "topic": "Python fundamentals",
            "difficulty": "beginner",
            "material_type": "reference",
        },
        {
            "id": "sql_joins_001",
            "content": (
                "SQL JOINs combine rows from two or more tables. "
                "INNER JOIN returns only matching rows. "
                "LEFT JOIN returns all rows from the left table plus matches from right. "
                "Example: SELECT u.name, o.total FROM users u "
                "LEFT JOIN orders o ON u.id = o.user_id;"
            ),
            "topic": "SQL and databases",
            "difficulty": "intermediate",
            "material_type": "reference",
        },
        {
            "id": "rest_api_001",
            "content": (
                "REST APIs use HTTP methods to perform CRUD operations. "
                "GET retrieves data, POST creates, PUT/PATCH updates, DELETE removes. "
                "Status codes: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, "
                "404 Not Found, 500 Server Error. "
                "Always version your API: /api/v1/resource."
            ),
            "topic": "APIs and web services",
            "difficulty": "intermediate",
            "material_type": "reference",
        },
    ]

    for ex in examples:
        add_material(
            doc_id=ex["id"],
            content=ex["content"],
            topic=ex["topic"],
            difficulty=ex["difficulty"],
            material_type=ex["material_type"],
        )

    print(f"Seeded {len(examples)} example materials.")
