# 📚 Smart Flashcard Engine

> **AI-powered study tool that converts PDFs into intelligent flashcards with spaced repetition.**
> 🌐 Live Demo: https://flashcard-dvkl.onrender.com/

---

## 🖼️ Preview

<img width="697" height="401" alt="image" src="https://github.com/user-attachments/assets/46448b86-ebdf-4ba2-b7b1-272164c02a7a" />


---

## 🧠 What Is It?

Smart Flashcard Engine is a full-stack web application that lets you **upload any PDF** and automatically generates high-quality Q&A flashcards using an AI language model. Once generated, cards are studied using a **spaced repetition** algorithm (SM-2) that schedules reviews at the optimal time — so you study smarter, not harder.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📄 **PDF Upload** | Upload any PDF up to 1 GB — text and images are both extracted |
| 🤖 **AI Flashcard Generation** | AI reads your document and writes Q&A flashcard pairs covering key concepts |
| 🔄 **Spaced Repetition (SM-2)** | Cards are scheduled based on how well you know them — Hard, Medium, or Easy |
| 📊 **Progress Dashboard** | Visual stats: total cards, mastered, due for review, learning — per deck and overall |
| 📈 **Analytics Charts** | Donut chart (card status distribution) and bar chart (deck-level mastery progress) |
| 🗂️ **Multiple Decks** | Manage multiple flashcard decks from different PDFs |
| 🗑️ **Delete Decks** | Remove a deck and all its cards with one click |
| 🎯 **Smart Practice Mode** | Prioritizes due cards; falls back to new cards on first study |

---

## 🛠️ Tech Stack

### Backend

| Technology | Role |
|---|---|
| **Python 3.11** | Primary language |
| **Flask** | Web framework — handles routing, templating, and API endpoints |
| **SQLAlchemy** | ORM for database access |
| **SQLite** | Lightweight database (stored as `flashcards.db`) |
| **PyMuPDF (fitz)** | Extracts text and images from uploaded PDF files |
| **Gunicorn** | WSGI server for production deployment |
| **python-dotenv** | Loads environment variables from `.env` |

### AI Integration

| Technology | Role |
|---|---|
| **OpenRouter API** | Calls an LLM to generate Q&A flashcard pairs from extracted PDF text |
| `utils/ai_generator.py` | Sends extracted content to the AI and parses the response into cards |

### Frontend

| Technology | Role |
|---|---|
| **Jinja2 Templates** | Server-side HTML rendering (`base.html`, `dashboard.html`, etc.) |
| **Vanilla JavaScript** | Handles upload flow, card flipping, rating, and chart rendering |
| **Custom CSS** | Dark-themed UI with animations, progress rings, and responsive design |
| **Canvas API** | Custom-drawn donut and bar charts (no external chart library) |
| **Google Fonts (Inter)** | Typography |

### Deployment

| Technology | Role |
|---|---|
| **Render** | Cloud platform for hosting (Free tier) |
| **render.yaml** | Infrastructure-as-code config for Render |
| **Procfile** | Alternative process runner config |
| `/tmp` filesystem | Render uses an ephemeral filesystem; uploads and DB are stored in `/tmp` |

---

## 🧬 Spaced Repetition — SM-2 Algorithm

The app implements a modified **SM-2** algorithm. After flipping a card, you rate your recall:

| Rating | Quality | Effect |
|---|---|---|
| 😓 Hard | 1 | Repetitions drop by 1 (min 0); card re-appears tomorrow |
| 🤔 Medium | 3 | Repetitions increase; standard interval growth |
| 😎 Easy | 5 | Repetitions increase; interval grows faster (×1.3 bonus) |

**Mastery levels** are determined by repetitions and interval:

- **New** — never reviewed (`repetitions == 0`)
- **Learning** — reviewed at least once (`repetitions >= 1`)
- **Mastered** — reviewed ≥ 3 times with interval ≥ 6 days

The **Easiness Factor (EF)** starts at 2.5 and is adjusted after every review. It controls how fast intervals grow and never drops below 1.3.

---

## 📁 Project Structure

```
smart-flashcard-engine/
│
├── app.py                   # Main Flask app — routes & API endpoints
├── models.py                # SQLAlchemy models (Deck, Card) + SM-2 logic
├── requirements.txt         # Python dependencies
├── runtime.txt              # Python version for Render
├── Procfile                 # Process runner config
├── render.yaml              # Render deployment config
│
├── utils/
│   ├── pdf_extractor.py     # PDF text + image extraction (PyMuPDF)
│   └── ai_generator.py      # AI flashcard generation via OpenRouter
│
├── templates/
│   ├── base.html            # Base layout with navbar and footer
│   ├── index.html           # Landing page with upload zone
│   ├── dashboard.html       # Deck overview, stats, and analytics
│   └── practice.html        # Flashcard practice UI
│
└── static/
    ├── css/style.css        # All styles (dark theme, animations, responsive)
    └── js/script.js         # Upload flow, flip animation, rating, charts
```

---

## 🚀 Getting Started (Local)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/smart-flashcard-engine.git
cd smart-flashcard-engine
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
FLASK_SECRET_KEY=any_random_secret_string
```

> Get a free OpenRouter API key at [openrouter.ai](https://openrouter.ai)

### 5. Run the app

```bash
python app.py
```

Open your browser at `http://localhost:5000`

---

## ☁️ Deploying to Render

1. Push the project to a GitHub repository.
2. Go to [render.com](https://render.com) and create a new **Web Service**.
3. Connect your GitHub repo — Render will detect `render.yaml` automatically.
4. Add the following environment variables in the Render dashboard:
   - `OPENROUTER_API_KEY` — your OpenRouter key
   - `FLASK_SECRET_KEY` — auto-generated by Render (already in `render.yaml`)
5. Click **Deploy**. Render handles the rest.

> ⚠️ **Note:** Render's free tier uses an ephemeral filesystem. The database (`/tmp/flashcards.db`) and uploads are reset on every restart/deploy. For persistence, upgrade to a paid plan and use an external database (e.g., PostgreSQL).

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload PDF, extract text, generate flashcards |
| `GET` | `/api/deck/<id>/cards` | Get cards for a deck (`?mode=smart` or `?mode=all`) |
| `POST` | `/api/card/<id>/review` | Submit a review rating (quality: 1, 3, or 5) |
| `DELETE` | `/api/deck/<id>` | Delete a deck and all its cards |
| `GET` | `/api/deck/<id>/stats` | Get mastery statistics for a deck |

---

## 📦 Dependencies

```
flask           # Web framework
requests        # HTTP client (for OpenRouter API calls)
python-dotenv   # .env file support
PyMuPDF         # PDF text and image extraction
sqlalchemy      # ORM and database toolkit
gunicorn        # Production WSGI server
```

---

## 📝 License

MIT License — feel free to use, modify, and distribute.

---

> Built with ❤️ for smarter studying.
