"""
AI-powered flashcard generation using OpenRouter API.
Uses openai/gpt-oss-120b:free model with OpenAI-compatible format.
"""

import os
import json
import re
import requests


def generate_flashcards(text, images=None):
    """
    Send extracted PDF text to OpenRouter API and get back flashcards.

    Args:
        text: Extracted text from PDF (will be truncated to 3000 chars)
        images: List of image dicts from PDF extraction (for context)

    Returns:
        list: [{"question": "...", "answer": "...", "page": int or None}]
    """
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smart-flashcard-engine.onrender.com",
        "X-Title": "Smart Flashcard Engine"
    }

    # Build image context if images exist
    image_context = ""
    if images and len(images) > 0:
        image_context = f"\n\nNote: The document contains {len(images)} image(s) on pages: {', '.join(str(img['page']) for img in images)}. Please generate questions that reference these visual elements where appropriate, mentioning 'the diagram/figure/image on page X'."

    # Truncate text to 3000 characters to stay within limits
    truncated_text = text[:3000]

    prompt = f"""Generate a comprehensive set of high-quality flashcards from the text below. Each flashcard must include a clear question and a concise answer. Cover definitions, concepts, examples, edge cases, and reasoning.{image_context}

Return ONLY a valid JSON array with no extra text, no markdown formatting, no code blocks. Just the raw JSON:
[{{"question": "...", "answer": "..."}}]

Text:
{truncated_text}"""

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

        # Associate images with cards based on page proximity
        if images and flashcards:
            flashcards = associate_images(flashcards, images)

        return flashcards

    except requests.exceptions.Timeout:
        raise Exception("API request timed out. Please try again.")
    except requests.exceptions.HTTPError as e:
        raise Exception(f"API error: {e.response.status_code} - {e.response.text[:200]}")
    except KeyError:
        raise Exception("Unexpected API response format.")
    except Exception as e:
        raise Exception(f"Failed to generate flashcards: {str(e)}")


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
            valid_cards.append({
                'question': str(card['question']).strip(),
                'answer': str(card['answer']).strip(),
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

    # Simple strategy: distribute images across cards
    # If a card mentions a specific page, attach the image from that page
    for card in flashcards:
        card_text = (card.get('question', '') + ' ' + card.get('answer', '')).lower()
        for img in images:
            page_num = img['page']
            if f'page {page_num}' in card_text or f'figure' in card_text or f'diagram' in card_text or f'image' in card_text:
                card['image_path'] = img['path']
                break

    # For remaining cards without images, attach first image if only one exists
    if len(images) == 1:
        for card in flashcards:
            if 'image_path' not in card:
                card['image_path'] = images[0]['path']

    return flashcards
