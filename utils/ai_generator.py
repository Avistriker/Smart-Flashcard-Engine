"""
AI-powered flashcard generation using OpenRouter API.
Uses parallel chunking for fast, comprehensive coverage of long documents.
"""

import os
import json
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# Larger chunks = fewer API calls = faster
CHUNK_SIZE = 6000
# Maximum total characters to process from the PDF
MAX_TEXT_LENGTH = 12000
# Minimum cards expected per chunk
MIN_CARDS_PER_CHUNK = 5

# Updated model list with reliable free models (verified April 2026)
FALLBACK_MODELS = [
    "z-ai/glm-4.5-air:free",  # New reliable model
    "google/gemma-4-31b-it:free",
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "deepseek/deepseek-r1-0528:free",
]

# Max retries per model before moving on
MAX_RETRIES_PER_MODEL = 2

# Backoff seconds per retry attempt (exponential)
RETRY_BACKOFF = [2, 5, 10]

# Rate limit cooldown tracking
_rate_limit_tracker = {}
_last_request_time = 0
_MIN_REQUEST_INTERVAL = 1.5  # seconds between requests to avoid rate limits


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

    # ── PARALLEL execution: all chunks at once ──
    all_flashcards = []
    errors = []

    if total_chunks == 1:
        # Single chunk — no threading overhead needed
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


def _call_openrouter_with_openai(api_key, model, prompt):
    """
    Make API call using OpenAI-compatible client.
    This approach often handles rate limits better.
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
            timeout=90.0,
        )
        
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://smart-flashcard-engine.onrender.com",
                "X-Title": "Smart Flashcard Engine",
            },
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        content = completion.choices[0].message.content
        
        if not content or not content.strip():
            raise APIError(f"Empty content from {model}")
        
        return parse_flashcard_json(content)
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower():
            raise RateLimitError(f"Rate limited on {model}: {error_msg}")
        raise APIError(f"API error on {model}: {error_msg}")


def _call_openrouter_requests(api_key, model, prompt):
    """
    Make API call using direct requests (fallback method).
    """
    global _last_request_time
    
    # Rate limiting
    now = time.time()
    time_since_last = now - _last_request_time
    if time_since_last < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - time_since_last)
    
    _last_request_time = time.time()
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smart-flashcard-engine.onrender.com",
        "X-Title": "Smart Flashcard Engine"
    }
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    
    response = requests.post(url, headers=headers, json=data, timeout=90)
    
    if response.status_code == 429:
        raise RateLimitError(f"Rate limited on {model}")
    
    if response.status_code != 200:
        raise APIError(f"HTTP {response.status_code} from {model}: {response.text[:200]}")
    
    result = response.json()
    
    if 'error' in result:
        err = result['error']
        msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
        raise APIError(f"{model}: {msg}")
    
    if 'choices' not in result or len(result['choices']) == 0:
        raise APIError(f"No choices returned by {model}")
    
    content = result["choices"][0]["message"].get("content", "")
    
    if not content or not content.strip():
        raise APIError(f"Empty content from {model}")
    
    return parse_flashcard_json(content)


def _call_openrouter(api_key, model, prompt):
    """
    Make a single API call to OpenRouter.
    Tries OpenAI client first, then falls back to requests.
    """
    try:
        return _call_openrouter_with_openai(api_key, model, prompt)
    except (RateLimitError, APIError):
        raise
    except Exception as e:
        # If OpenAI client fails for any reason, try requests
        print(f"  OpenAI client failed, trying requests: {str(e)[:100]}")
        return _call_openrouter_requests(api_key, model, prompt)


class RateLimitError(Exception):
    """Raised when the API returns 429."""
    pass


class APIError(Exception):
    """Raised for non-rate-limit API errors."""
    pass


def _try_models(api_key, prompt, models, chunk_num):
    """
    Try a list of models with retries and exponential backoff.
    Returns flashcards on success, or raises with the last error.
    """
    last_error = None

    for model in models:
        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            try:
                tag = f"[Chunk {chunk_num}]"
                if attempt > 1:
                    tag += f" (retry {attempt})"
                print(f"{tag} Trying {model}...")

                cards = _call_openrouter(api_key, model, prompt)
                print(f"{tag} [OK] {len(cards)} cards from {model}")
                return cards

            except RateLimitError as e:
                print(f"{tag} Rate limit: {e}")
                last_error = str(e)
                # Exponential backoff before retrying same model
                if attempt < MAX_RETRIES_PER_MODEL:
                    wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                    print(f"{tag} Waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                else:
                    break  # move to next model

            except APIError as e:
                print(f"{tag} API error: {e}")
                last_error = str(e)
                break  # API error (not rate limit) — skip to next model

            except requests.exceptions.Timeout:
                print(f"{tag} Timeout on {model}")
                last_error = f"Timeout on {model}"
                break

            except Exception as e:
                error_str = str(e)
                print(f"{tag} Error: {error_str[:200]}")
                last_error = error_str
                break

        # Small delay between switching models
        time.sleep(1)

    return None  # signal that all models failed in this pass


def _generate_chunk_flashcards(api_key, text_chunk, images, chunk_num, total_chunks):
    """
    Generate flashcards for a single text chunk.
    Cycles through fallback models with retries until one succeeds.
    """
    prompt = _build_prompt(text_chunk, images, chunk_num, total_chunks)

    # Try all models
    cards = _try_models(api_key, prompt, FALLBACK_MODELS, chunk_num)
    if cards:
        return cards

    # If all models failed, wait and retry with the best model
    print(f"[Chunk {chunk_num}] All models failed. Waiting 10s for final retry...")
    time.sleep(10)
    
    cards = _try_models(api_key, prompt, FALLBACK_MODELS[:2], chunk_num)
    if cards:
        return cards

    raise Exception("All AI models failed after retries. Please try again in a few minutes.")


def _deduplicate_cards(cards):
    """Remove near-duplicate cards by comparing question similarity."""
    if len(cards) <= 1:
        return cards

    unique_cards = []
    seen_questions = set()

    for card in cards:
        # Normalize: lowercase, remove punctuation, collapse whitespace
        normalized = re.sub(r'[^\w\s]', '', card['question'].lower())
        normalized = ' '.join(normalized.split())

        # Use first 60 chars as a fingerprint
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
    """Associate extracted images with flashcards."""
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
