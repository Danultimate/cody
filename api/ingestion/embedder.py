import time
import voyageai

BATCH_SIZE = 128
SLEEP_BETWEEN_BATCHES = 1.0  # seconds


def embed_chunks(chunks: list[dict], api_key: str) -> list[list[float]]:
    """
    Embed chunk contents using Voyage AI voyage-code-3.
    Returns a list of 1024-dim float vectors, order-matched to input chunks.
    """
    client = voyageai.Client(api_key=api_key)
    texts = [c["content"] for c in chunks]
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result = client.embed(batch, model="voyage-code-3", input_type="document")
        all_embeddings.extend(result.embeddings)

        if i + BATCH_SIZE < len(texts):
            time.sleep(SLEEP_BETWEEN_BATCHES)

    return all_embeddings
