"""PDF text extraction and chunking shared by the bylaw ingesters."""

import fitz  # PyMuPDF


def extract_text_from_pdf(filepath):
    """Reads PDF and returns full text content."""
    try:
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        return text
    except Exception as e:
        print(f"[!] Error reading PDF {filepath}: {e}")
        return None


def chunk_text(text, chunk_size=1000, overlap=200):
    """Splits text into overlapping chunks."""
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a newline or period if possible to avoid cutting words
        # but only if we are not at the very end
        if end < len(text):
            # Look for last newline first
            last_break = chunk.rfind("\n")
            if last_break == -1:
                last_break = chunk.rfind(". ")

            if last_break > chunk_size * 0.7:  # Only back off if we don't lose too much
                end = start + last_break + 1
                chunk = text[start:end]

        if len(chunk.strip()) > 20:  # Filter out tiny noise
            chunks.append(chunk.strip())

        start = end - overlap

    return chunks
