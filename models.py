"""
Database models for Smart Flashcard Engine.
Uses SQLAlchemy ORM with SQLite backend.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta

Base = declarative_base()


class Deck(Base):
    """A collection of flashcards generated from a single PDF."""
    __tablename__ = 'decks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_cards = Column(Integer, default=0)

    cards = relationship('Card', backref='deck', cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'total_cards': self.total_cards,
        }


class Card(Base):
    """A single flashcard with SM-2 spaced repetition metadata."""
    __tablename__ = 'cards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_id = Column(Integer, ForeignKey('decks.id'), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    image_path = Column(String(500), nullable=True)

    # SM-2 spaced repetition fields
    easiness_factor = Column(Float, default=2.5)
    interval = Column(Integer, default=0)        # days until next review
    repetitions = Column(Integer, default=0)      # consecutive correct answers
    next_review_date = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'deck_id': self.deck_id,
            'question': self.question,
            'answer': self.answer,
            'image_path': self.image_path,
            'easiness_factor': self.easiness_factor,
            'interval': self.interval,
            'repetitions': self.repetitions,
            'next_review_date': self.next_review_date.isoformat(),
        }

    @property
    def is_due(self):
        return datetime.utcnow() >= self.next_review_date

    @property
    def mastery_level(self):
        """Return mastery status based on repetitions and interval."""
        if self.repetitions >= 5 and self.interval >= 21:
            return 'mastered'
        elif self.repetitions >= 2:
            return 'learning'
        else:
            return 'new'


def update_sm2(card, quality):
    """
    Update a card's spaced repetition data using the SM-2 algorithm.

    quality: 1 = Hard, 3 = Medium, 5 = Easy
    """
    if quality >= 3:  # correct response
        if card.repetitions == 0:
            card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = round(card.interval * card.easiness_factor)
        card.repetitions += 1
    else:  # incorrect / hard
        card.repetitions = 0
        card.interval = 1

    # Update easiness factor (minimum 1.3)
    card.easiness_factor = max(
        1.3,
        card.easiness_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    )

    card.next_review_date = datetime.utcnow() + timedelta(days=card.interval)
    return card


# Database setup — use /tmp on Render (ephemeral filesystem)
import os as _os
_db_dir = '/tmp' if _os.getenv('RENDER') else '.'
_db_path = _os.path.join(_db_dir, 'flashcards.db')
engine = create_engine(f'sqlite:///{_db_path}', echo=False)
Session = sessionmaker(bind=engine)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)
