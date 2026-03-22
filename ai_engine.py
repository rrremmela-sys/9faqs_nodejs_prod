"""
=============================================================
ZENERAL AI ENGINE
=============================================================
Plug-and-play RAG (Retrieval Augmented Generation) engine.
Each client can have their own Pinecone index + system prompt.

USAGE in main.py:
    from ai_engine import get_ai_response
    answer = get_ai_response(question, client_id="9faqs")
=============================================================
"""

import os
from openai import OpenAI

# ── Clients AI Config ──
# Add each client's Pinecone index and AI settings here
AI_CONFIG = {
    "9faqs": {
        "pinecone_index": os.getenv("PINECONE_INDEX_9FAQS", "9faqs-kb"),
        "use_rag":        True,
        "model":          "gpt-4o-mini",
        "max_tokens":     200,
        "temperature":    0.7,
        "system_prompt": """You are a helpful WhatsApp assistant for 9faqs (https://9faqs.com).
9faqs is an online tech learning platform offering Python training and AI workshops.

Use the provided context to answer questions accurately.
Keep answers SHORT (2-4 lines) — this is WhatsApp.
Be warm, friendly and encouraging.
Always suggest enrolling at https://9faqs.com/enroll
If unsure → "Visit 9faqs.com or type Hi to talk to our team"
Reply in the same language as the user."""
    },

    # ── Add new client AI config here ──
    "resort_demo": {
        "pinecone_index": os.getenv("PINECONE_INDEX_RESORT", "resort-kb"),
        "use_rag":        False,   # No RAG for resort — uses system prompt only
        "model":          "gpt-4o-mini",
        "max_tokens":     150,
        "temperature":    0.7,
        "system_prompt": """You are a helpful WhatsApp assistant for Sunset Resort.
Help guests with room bookings, amenities, and resort information.
Keep answers SHORT and friendly. Always encourage booking."""
    },
}

# ── Pinecone + OpenAI clients (lazy loaded) ──
_openai_client = None
_pinecone_indexes = {}

def get_openai():
    global _openai_client
    if not _openai_client:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            _openai_client = OpenAI(api_key=api_key)
    return _openai_client

def get_pinecone_index(index_name):
    global _pinecone_indexes
    if index_name not in _pinecone_indexes:
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            _pinecone_indexes[index_name] = pc.Index(index_name)
            print(f"✅ Pinecone connected: {index_name}")
        except Exception as e:
            print(f"⚠️ Pinecone error: {e}")
            return None
    return _pinecone_indexes.get(index_name)

# ── RAG: Search Pinecone for relevant context ──
def search_knowledge_base(question, index_name, top_k=5):
    """Search Pinecone for relevant context"""
    try:
        client = get_openai()
        index  = get_pinecone_index(index_name)
        if not client or not index:
            return ""

        # Create embedding for question
        embedding = client.embeddings.create(
            model="text-embedding-3-small",
            input=question
        ).data[0].embedding

        # Search Pinecone
        results = index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True
        )

        # Build context from results
        context = ""
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            text = meta.get("text") or meta.get("content") or meta.get("context", "")
            if text:
                context += text + "\n---\n"

        return context.strip()

    except Exception as e:
        print(f"⚠️ Pinecone search error: {e}")
        return ""

# ── Main AI Response Function ──
def get_ai_response(question, client_id="9faqs"):
    """
    Get AI response for a question.
    Uses RAG if Pinecone index is configured for this client.
    Falls back to pure OpenAI if RAG fails.
    Returns None if completely fails.
    """
    config = AI_CONFIG.get(client_id, AI_CONFIG.get("9faqs"))
    client = get_openai()

    if not client:
        print("⚠️ OpenAI not configured")
        return None

    try:
        context = ""

        # Use RAG if enabled
        if config.get("use_rag") and config.get("pinecone_index"):
            context = search_knowledge_base(
                question,
                config["pinecone_index"]
            )
            if context:
                print(f"📚 RAG context found ({len(context)} chars)")

        # Build messages
        system_msg = config["system_prompt"]
        user_msg   = question

        if context:
            user_msg = f"Context from knowledge base:\n{context}\n\nUser question: {question}"

        response = client.chat.completions.create(
            model=config.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg}
            ],
            max_tokens=config.get("max_tokens", 150),
            temperature=config.get("temperature", 0.7)
        )

        answer = response.choices[0].message.content.strip()

        # Reject if too long or empty
        if not answer or len(answer) > 500:
            return None

        print(f"🤖 AI [{client_id}]: {answer[:80]}...")
        return answer

    except Exception as e:
        print(f"⚠️ AI error: {e}")
        return None


if __name__ == "__main__":
    print("=== AI Engine Test ===")
    ans = get_ai_response("What Python courses do you offer?", "9faqs")
    print("Answer:", ans)
