"""
AI-powered flashcard generation using OpenRouter API (openai/gpt-oss-120b:free).
Uses parallel chunking for fast, comprehensive coverage of long documents.
"""

import os
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# Larger chunks = fewer API calls = faster
CHUNK_SIZE = 6000
# Maximum total characters to process from the PDF
MAX_TEXT_LENGTH = 12000
# Minimum cards expected per chunk
MIN_CARDS_PER_CHUNK = 5

# OpenRouter model
OPENROUTER_MODEL = "openai/gpt-oss-120b:free"

# Max retries before giving up
MAX_RETRIES = 3

# Backoff seconds per retry attempt (exponential)
RETRY_BACKOFF = [2, 5, 10]

# Rate limit cooldown tracking
_last_request_time = 0
_MIN_REQUEST_INTERVAL = 1.5  # seconds between requests to avoid rate limits


class RateLimitError(Exception):
    """Raised when the API returns 429."""
    pass


class APIError(Exception):
    """Raised for non-rate-limit API errors."""
    pass


def generate_flashcards(text, images=None):
    """
    Send extracted PDF text to OpenRouter API and get back flashcards.
    Uses PARALLEL chunking for speed.

    Args:
        text: Extracted text from PDF
        images: List of image dicts from PDF extraction (for context)

    Returns:
        list: [{"question": "...", "answer": "...", "page": int or None}]
    """
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")

    # Limit total text
    working_text = text[:MAX_TEXT_LENGTH]

    # Split into chunks
    chunks = _split_into_chunks(working_text, CHUNK_SIZE)
    total_chunks = len(chunks)

    print(f"[Generator] Processing {total_chunks} chunk(s) in parallel...")

    all_flashcards = []
    errors = []

    if total_chunks == 1:
        cards = _generate_chunk_flashcards(
            api_key, chunks[0], images, 1, 1
        )
        all_flashcards.extend(cards)
    else:
        with ThreadPoolExecutor(max_workers=min(total_chunks, 2)) as executor:
            futures = {
                executor.submit(
                    _generate_chunk_flashcards,
                    api_key, chunk, images, i + 1, total_chunks
                ): i
                for i, chunk in enumerate(chunks)
            }

            for future in as_completed(futures):
                chunk_idx = futures[future]
                try:
                    cards = future.result()
                    all_flashcards.extend(cards)
                except Exception as e:
                    print(f"[Generator] Chunk {chunk_idx + 1} failed: {e}")
                    errors.append(str(e))

    # Deduplicate similar cards
    all_flashcards = _deduplicate_cards(all_flashcards)

    # Associate images with cards based on page proximity
    if images and all_flashcards:
        all_flashcards = associate_images(all_flashcards, images)

    if not all_flashcards:
        error_detail = "; ".join(errors) if errors else "Unknown error"
        raise Exception(f"No flashcards could be generated. {error_detail}")

    print(f"[Generator] Done! {len(all_flashcards)} unique flashcards generated.")
    return all_flashcards


def _split_into_chunks(text, chunk_size):
    """Split text into chunks, preferring to break at paragraph or sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        candidate = remaining[:chunk_size]
        break_pos = candidate.rfind('\n\n')

        if break_pos < chunk_size * 0.3:
            break_pos = candidate.rfind('. ')
            if break_pos < chunk_size * 0.3:
                break_pos = chunk_size

        break_pos += 1
        chunks.append(remaining[:break_pos].strip())
        remaining = remaining[break_pos:].strip()

    return [c for c in chunks if len(c.strip()) > 50]


def _build_prompt(text_chunk, images, chunk_num, total_chunks):
    """Build the flashcard generation prompt."""
    image_hint = ""
    if images and len(images) > 0:
        image_hint = f" The document has {len(images)} image(s)."

    chunk_info = ""
    if total_chunks > 1:
        chunk_info = f" (Section {chunk_num}/{total_chunks})"

    return f"""Generate flashcards from this text.{chunk_info}{image_hint}

Create diverse Q&A cards: definitions, key concepts, relationships, examples, reasoning.
Rules: specific questions, concise answers (2-3 sentences), at least {MIN_CARDS_PER_CHUNK} cards.

Return ONLY a JSON array, no markdown, no code blocks, no extra text:
[{{"question": "...", "answer": "..."}}]

Text:
{text_chunk}"""


def _call_openrouter(api_key, prompt):
    """
    Make a single API call to OpenRouter using the openai/gpt-oss-120b:free model.
    Returns parsed flashcard list on success, raises on failure.
    """
    global _last_request_time

    # Rate limiting
    now = time.time()
    time_since_last = now - _last_request_time
    if time_since_last < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - time_since_last)

    _last_request_time = time.time()

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            extra_body={"reasoning": {"enabled": True}}
        )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise APIError("Empty response from OpenRouter")

        return parse_flashcard_json(content)

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
            raise RateLimitError(f"Rate limited by OpenRouter: {error_msg}")
        raise APIError(f"OpenRouter API error: {error_msg}")


def _generate_chunk_flashcards(api_key, text_chunk, images, chunk_num, total_chunks):
    """
    Generate flashcards for a single text chunk with retries.
    """
    prompt = _build_prompt(text_chunk, images, chunk_num, total_chunks)
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tag = f"[Chunk {chunk_num}]"
            if attempt > 1:
                tag += f" (retry {attempt})"
            print(f"{tag} Calling OpenRouter ({OPENROUTER_MODEL})...")

            cards = _call_openrouter(api_key, prompt)
            print(f"{tag} [OK] {len(cards)} cards generated")
            return cards

        except RateLimitError as e:
            print(f"[Chunk {chunk_num}] Rate limit: {e}")
            last_error = str(e)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                print(f"[Chunk {chunk_num}] Waiting {wait}s before retry...")
                time.sleep(wait)

        except APIError as e:
            print(f"[Chunk {chunk_num}] API error: {e}")
            last_error = str(e)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                time.sleep(wait)

        except Exception as e:
            print(f"[Chunk {chunk_num}] Unexpected error: {str(e)[:200]}")
            last_error = str(e)
            break

    raise Exception(f"OpenRouter failed after {MAX_RETRIES} attempts. Last error: {last_error}")


def _deduplicate_cards(cards):
    """Remove near-duplicate cards by comparing question similarity."""
    if len(cards) <= 1:
        return cards

    unique_cards = []
    seen_questions = set()

    for card in cards:
        normalized = re.sub(r'[^\w\s]', '', card['question'].lower())
        normalized = ' '.join(normalized.split())
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
    # Remove any <think>...</think> reasoning blocks
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    # Remove markdown code block markers if present
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)

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

    raise Exception("Could not parse flashcards from OpenRouter response. The model did not return valid JSON.")


def validate_cards(cards):
    """Validate that each card has question and answer fields."""
    valid_cards = []
    for card in cards:
        if isinstance(card, dict) and 'question' in card and 'answer' in card:
            q = str(card['question']).strip()
            a = str(card['answer']).strip()
            if len(q) > 5 and len(a) > 5:
                valid_cards.append({
                    'question': q,
                    'answer': a,
                    'page': card.get('page', None)
                })
    if not valid_cards:
        raise Exception("No valid flashcards found in OpenRouter response.")
    return valid_cards


def associate_images(flashcards, images):
    """Associate extracted images with flashcards."""
    if not images:
        return flashcards

    for card in flashcards:
        card_text = (card.get('question', '') + ' ' + card.get('answer', '')).lower()
        for img in images:
            page_num = img['page']
            if f'page {page_num}' in card_text or 'figure' in card_text or 'diagram' in card_text or 'image' in card_text:
                card['image_path'] = img['path']
                break

    if len(images) == 1:
        for card in flashcards:
            if 'image_path' not in card:
                card['image_path'] = images[0]['path']

    return flashcards
