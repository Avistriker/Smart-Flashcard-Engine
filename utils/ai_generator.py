"""
AI-powered flashcard generation using OpenRouter API.
Uses chunking for comprehensive coverage of long documents
and a rich prompt for teacher-quality card generation.
"""

import os
import json
import re
import requests


# Maximum characters per API call (model context window safe)
CHUNK_SIZE = 4000
# Maximum total characters to process from the PDF
MAX_TEXT_LENGTH = 12000
# Minimum cards expected per chunk
MIN_CARDS_PER_CHUNK = 5


def generate_flashcards(text, images=None):
    """
    Send extracted PDF text to OpenRouter API and get back flashcards.
    Uses chunking to handle long documents comprehensively.

    Args:
        text: Extracted text from PDF
        images: List of image dicts from PDF extraction (for context)

    Returns:
        list: [{"question": "...", "answer": "...", "page": int or None}]
    """
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")

    # Limit total text but process much more than before
    working_text = text[:MAX_TEXT_LENGTH]

    # Split into chunks for comprehensive coverage
    chunks = _split_into_chunks(working_text, CHUNK_SIZE)

    all_flashcards = []
    for i, chunk in enumerate(chunks):
        chunk_cards = _generate_chunk_flashcards(
            api_key, chunk, images,
            chunk_num=i + 1,
            total_chunks=len(chunks)
        )
        all_flashcards.extend(chunk_cards)

    # Deduplicate similar cards
    all_flashcards = _deduplicate_cards(all_flashcards)

    # Associate images with cards based on page proximity
    if images and all_flashcards:
        all_flashcards = associate_images(all_flashcards, images)

    if not all_flashcards:
        raise Exception("No flashcards could be generated from this document.")

    return all_flashcards


def _split_into_chunks(text, chunk_size):
    """
    Split text into chunks, preferring to break at paragraph
    or sentence boundaries for better context.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        # Try to break at a paragraph boundary
        candidate = remaining[:chunk_size]
        break_pos = candidate.rfind('\n\n')

        if break_pos < chunk_size * 0.3:
            # No good paragraph break — try sentence boundary
            break_pos = candidate.rfind('. ')
            if break_pos < chunk_size * 0.3:
                break_pos = chunk_size  # hard cut

        break_pos += 1  # include the break character
        chunks.append(remaining[:break_pos].strip())
        remaining = remaining[break_pos:].strip()

    return [c for c in chunks if len(c.strip()) > 50]


def _generate_chunk_flashcards(api_key, text_chunk, images, chunk_num, total_chunks):
    """Generate flashcards for a single text chunk."""

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smart-flashcard-engine.onrender.com",
        "X-Title": "Smart Flashcard Engine"
    }

    # Build image context
    image_context = ""
    if images and len(images) > 0:
        image_context = f"\n\nNote: The document contains {len(images)} image(s) on pages: {', '.join(str(img['page']) for img in images)}. Where relevant, reference visual elements (e.g. 'Refer to the diagram on page X')."

    chunk_info = ""
    if total_chunks > 1:
        chunk_info = f" (This is section {chunk_num} of {total_chunks} from the document.)"

    prompt = f"""You are an expert teacher creating flashcards for a student. Generate a comprehensive set of high-quality flashcards from the text below.{chunk_info}

Create DIVERSE card types:
1. **Definitions** — "What is X?" → concise definition
2. **Key Concepts** — "Explain the concept of X" → clear explanation
3. **Relationships** — "How does X relate to Y?" → connection between ideas
4. **Edge Cases** — "What happens when X?" → boundary conditions, exceptions
5. **Worked Examples** — "Solve/Calculate X" → step-by-step answer
6. **Reasoning** — "Why does X occur?" → cause-effect understanding

Rules:
- Cover the material COMPREHENSIVELY — don't skip important points
- Questions should be specific and unambiguous
- Answers should be concise but complete (2-4 sentences max)
- Avoid trivial or overly obvious questions
- Generate at least {MIN_CARDS_PER_CHUNK} cards{image_context}

Return ONLY a valid JSON array with no extra text, no markdown formatting, no code blocks. Just the raw JSON:
[{{"question": "...", "answer": "..."}}]

Text:
{text_chunk}"""

    data = {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        result = response.json()

        content = result["choices"][0]["message"]["content"]
        flashcards = parse_flashcard_json(content)
        return flashcards

    except requests.exceptions.Timeout:
        raise Exception("API request timed out. Please try again.")
    except requests.exceptions.HTTPError as e:
        raise Exception(f"API error: {e.response.status_code} - {e.response.text[:200]}")
    except KeyError:
        raise Exception("Unexpected API response format.")
    except Exception as e:
        # If one chunk fails, log and continue with others
        if "Could not parse" in str(e):
            print(f"Warning: Chunk {chunk_num} failed to parse, skipping.")
            return []
        raise Exception(f"Failed to generate flashcards: {str(e)}")


def _deduplicate_cards(cards):
    """
    Remove near-duplicate cards by comparing question similarity.
    Uses a simple approach: normalize questions and check for high overlap.
    """
    if len(cards) <= 1:
        return cards

    unique_cards = []
    seen_questions = set()

    for card in cards:
        # Normalize: lowercase, remove punctuation, collapse whitespace
        normalized = re.sub(r'[^\w\s]', '', card['question'].lower())
        normalized = ' '.join(normalized.split())

        # Check if a very similar question was already seen
        # Use first 60 chars as a fingerprint (catches most duplicates)
        fingerprint = normalized[:60]

        if fingerprint not in seen_questions:
            seen_questions.add(fingerprint)
            unique_cards.append(card)

    return unique_cards


def parse_flashcard_json(content):
    """
    Parse the AI response to extract flashcard JSON.
    Handles various formats: raw JSON, markdown code blocks, etc.
    """
    # Remove any <think>...</think> reasoning blocks from the response
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    # Try direct JSON parse first
    try:
        cards = json.loads(content)
        if isinstance(cards, list):
            return validate_cards(cards)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if code_block_match:
        try:
            cards = json.loads(code_block_match.group(1))
            if isinstance(cards, list):
                return validate_cards(cards)
        except json.JSONDecodeError:
            pass

    # Try finding JSON array in the text
    bracket_match = re.search(r'\[[\s\S]*\]', content)
    if bracket_match:
        try:
            cards = json.loads(bracket_match.group(0))
            if isinstance(cards, list):
                return validate_cards(cards)
        except json.JSONDecodeError:
            pass

    raise Exception("Could not parse flashcards from AI response. The model did not return valid JSON.")


def validate_cards(cards):
    """Validate that each card has question and answer fields."""
    valid_cards = []
    for card in cards:
        if isinstance(card, dict) and 'question' in card and 'answer' in card:
            q = str(card['question']).strip()
            a = str(card['answer']).strip()
            # Skip empty or trivially short Q&A
            if len(q) > 5 and len(a) > 5:
                valid_cards.append({
                    'question': q,
                    'answer': a,
                    'page': card.get('page', None)
                })
    if not valid_cards:
        raise Exception("No valid flashcards found in AI response.")
    return valid_cards


def associate_images(flashcards, images):
    """
    Associate extracted images with flashcards.
    Distributes images evenly across cards, or attaches by page reference.
    """
    if not images:
        return flashcards

    # If a card mentions a specific page, attach the image from that page
    for card in flashcards:
        card_text = (card.get('question', '') + ' ' + card.get('answer', '')).lower()
        for img in images:
            page_num = img['page']
            if f'page {page_num}' in card_text or 'figure' in card_text or 'diagram' in card_text or 'image' in card_text:
                card['image_path'] = img['path']
                break

    # For remaining cards without images, attach first image if only one exists
    if len(images) == 1:
        for card in flashcards:
            if 'image_path' not in card:
                card['image_path'] = images[0]['path']

    return flashcards
