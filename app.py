"""
Smart Flashcard Engine – Main Flask Application.
Converts PDFs into AI-generated flashcards with spaced repetition.
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from models import init_db, Session, Deck, Card, update_sm2
from utils.pdf_extractor import extract_from_pdf
from utils.ai_generator import generate_flashcards

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'smart-flashcard-engine-secret-2024')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1 GB max upload

# On Render, use /tmp for writable storage (ephemeral filesystem)
IS_RENDER = os.getenv('RENDER')
UPLOAD_FOLDER = '/tmp/uploads' if IS_RENDER else 'uploads'
IMAGES_FOLDER = '/tmp/static/images/cards' if IS_RENDER else 'static/images/cards'
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGES_FOLDER, exist_ok=True)

# Initialize database
init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────
# PAGE ROUTES
# ──────────────────────────────────────────

@app.route('/')
def index():
    """Landing page with PDF upload."""
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    """Dashboard showing all decks and stats."""
    session = Session()
    try:
        decks = session.query(Deck).order_by(Deck.created_at.desc()).all()
        deck_data = []
        total_cards = 0
        total_mastered = 0
        total_due = 0
        total_learning = 0
        total_new = 0

        for deck in decks:
            cards = deck.cards.all()
            mastered = sum(1 for c in cards if c.mastery_level == 'mastered')
            learning = sum(1 for c in cards if c.mastery_level == 'learning')
            new = sum(1 for c in cards if c.mastery_level == 'new')
            due = sum(1 for c in cards if c.is_due)

            total_cards += len(cards)
            total_mastered += mastered
            total_due += due
            total_learning += learning
            total_new += new

            deck_data.append({
                'id': deck.id,
                'name': deck.name,
                'created_at': deck.created_at.strftime('%b %d, %Y'),
                'total_cards': len(cards),
                'mastered': mastered,
                'due': due,
                'learning': learning,
                'new': new,
                'progress': round(((mastered * 100 + learning * 40) / len(cards)) if cards else 0),
            })

        stats = {
            'total_cards': total_cards,
            'mastered': total_mastered,
            'due': total_due,
            'learning': total_learning,
            'new': total_new,
            'total_decks': len(decks),
        }

        return render_template('dashboard.html', decks=deck_data, stats=stats)
    finally:
        session.close()


@app.route('/practice/<int:deck_id>')
def practice(deck_id):
    """Practice page for a specific deck."""
    session = Session()
    try:
        deck = session.query(Deck).get(deck_id)
        if not deck:
            flash('Deck not found.', 'error')
            return redirect(url_for('dashboard'))
        return render_template('practice.html', deck=deck.to_dict())
    finally:
        session.close()


# ──────────────────────────────────────────
# API ROUTES
# ──────────────────────────────────────────

@app.route('/upload', methods=['POST'])
def upload():
    """Handle PDF upload, extract text, generate flashcards via AI."""
    filepath = None
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['pdf']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        session = Session()
        try:
            # 1. Extract text and images from PDF
            extraction = extract_from_pdf(filepath)
            text = extraction['text']
            images = extraction['images']

            if not text or len(text.strip()) < 50:
                return jsonify({'error': 'Could not extract enough text from the PDF. Please try a different file.'}), 400

            # 2. Generate flashcards via AI
            flashcards = generate_flashcards(text, images)

            # 3. Create deck
            deck_name = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
            deck = Deck(name=deck_name, total_cards=len(flashcards))
            session.add(deck)
            session.flush()  # get deck.id

            # 4. Create cards
            for fc in flashcards:
                card = Card(
                    deck_id=deck.id,
                    question=fc['question'],
                    answer=fc['answer'],
                    image_path=fc.get('image_path', None),
                )
                session.add(card)

            session.commit()

            return jsonify({
                'success': True,
                'deck_id': deck.id,
                'deck_name': deck.name,
                'card_count': len(flashcards),
                'message': f'Generated {len(flashcards)} flashcards!'
            })

        except Exception as e:
            session.rollback()
            import traceback
            traceback.print_exc()
            # Return a user-friendly error message
            error_msg = str(e)
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "API rate limit exceeded. Please wait a moment and try again."
            return jsonify({'error': error_msg}), 500
        finally:
            session.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected server error: {str(e)}'}), 500
    finally:
        # Clean up uploaded file
        if filepath and os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/deck/<int:deck_id>/cards')
def get_deck_cards(deck_id):
    """Get cards for practice — prioritizes due cards for spaced repetition."""
    session = Session()
    try:
        deck = session.query(Deck).get(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404

        mode = request.args.get('mode', 'smart')  # 'smart' or 'all'
        now = datetime.utcnow()

        if mode == 'all':
            practice_cards = deck.cards.all()
        else:
            due_cards = deck.cards.filter(Card.next_review_date <= now).all()

            if due_cards:
                practice_cards = due_cards
            else:
                all_cards = deck.cards.all()
                if not all_cards:
                    return jsonify({'cards': [], 'total': 0})

                new_cards = [c for c in all_cards if c.repetitions == 0]
                if new_cards:
                    practice_cards = new_cards
                else:
                    next_review = min(c.next_review_date for c in all_cards)
                    return jsonify({
                        'cards': [],
                        'total': 0,
                        'all_reviewed': True,
                        'next_review': next_review.isoformat(),
                    })

        cards = [c.to_dict() for c in practice_cards]
        return jsonify({'cards': cards, 'total': len(cards)})
    finally:
        session.close()


@app.route('/api/card/<int:card_id>/review', methods=['POST'])
def review_card(card_id):
    """Submit a review rating for a card (Easy/Medium/Hard)."""
    session = Session()
    try:
        card = session.query(Card).get(card_id)
        if not card:
            return jsonify({'error': 'Card not found'}), 404

        data = request.get_json()
        quality = data.get('quality', 3)

        if quality not in [1, 3, 5]:
            return jsonify({'error': 'Quality must be 1 (Hard), 3 (Medium), or 5 (Easy)'}), 400

        card = update_sm2(card, quality)
        session.commit()

        return jsonify({
            'success': True,
            'card_id': card.id,
            'next_review': card.next_review_date.isoformat(),
            'interval': card.interval,
            'easiness_factor': round(card.easiness_factor, 2),
        })
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/deck/<int:deck_id>', methods=['DELETE'])
def delete_deck(deck_id):
    """Delete a deck and all its cards."""
    session = Session()
    try:
        deck = session.query(Deck).get(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404

        cards = deck.cards.all()
        for card in cards:
            if card.image_path:
                img_full_path = card.image_path.lstrip('/')
                if os.path.exists(img_full_path):
                    os.remove(img_full_path)

        session.delete(deck)
        session.commit()
        return jsonify({'success': True, 'message': 'Deck deleted successfully'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/deck/<int:deck_id>/stats')
def deck_stats(deck_id):
    """Get detailed statistics for a deck."""
    session = Session()
    try:
        deck = session.query(Deck).get(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404

        cards = deck.cards.all()
        mastered = sum(1 for c in cards if c.mastery_level == 'mastered')
        learning = sum(1 for c in cards if c.mastery_level == 'learning')
        new = sum(1 for c in cards if c.mastery_level == 'new')
        due = sum(1 for c in cards if c.is_due)

        return jsonify({
            'total': len(cards),
            'mastered': mastered,
            'learning': learning,
            'new': new,
            'due': due,
            'progress': round(((mastered * 100 + learning * 40) / len(cards)) if cards else 0),
        })
    finally:
        session.close()


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
