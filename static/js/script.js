/**
 * Smart Flashcard Engine – Client-Side Logic
 * Handles: file upload, drag-and-drop, flashcard practice,
 * SM-2 review submissions, dashboard interactions.
 */

document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    initUpload();
    initDashboard();
    initPractice();
});


/* ═══════════════════════════════════════════════════════
   ANIMATED PARTICLES (Hero Background)
   ═══════════════════════════════════════════════════════ */

function initParticles() {
    const container = document.getElementById('hero-particles');
    if (!container) return;

    for (let i = 0; i < 20; i++) {
        const particle = document.createElement('div');
        particle.classList.add('particle');
        const size = Math.random() * 4 + 2;
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.left = `${Math.random() * 100}%`;
        particle.style.animationDuration = `${Math.random() * 8 + 6}s`;
        particle.style.animationDelay = `${Math.random() * 5}s`;
        container.appendChild(particle);
    }
}


/* ═══════════════════════════════════════════════════════
   FILE UPLOAD (Drag & Drop + Click)
   ═══════════════════════════════════════════════════════ */

function initUpload() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    if (!uploadZone || !fileInput) return;

    const uploadContent = document.getElementById('upload-content');
    const uploadProgress = document.getElementById('upload-progress');
    const uploadSuccess = document.getElementById('upload-success');
    const uploadError = document.getElementById('upload-error');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const progressTitle = document.getElementById('progress-title');
    const progressSubtitle = document.getElementById('progress-subtitle');

    // Click to browse
    uploadZone.addEventListener('click', (e) => {
        if (e.target.closest('.btn') || e.target.closest('.success-actions')) return;
        if (!uploadContent.classList.contains('hidden')) {
            fileInput.click();
        }
    });

    // Drag events
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFile(files[0]);
    });

    // File input change
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
    });

    // Try again button
    const tryAgainBtn = document.getElementById('try-again-btn');
    if (tryAgainBtn) {
        tryAgainBtn.addEventListener('click', () => {
            showState('content');
            fileInput.value = '';
        });
    }

    function showState(state) {
        uploadContent.classList.toggle('hidden', state !== 'content');
        uploadProgress.classList.toggle('hidden', state !== 'progress');
        uploadSuccess.classList.toggle('hidden', state !== 'success');
        uploadError.classList.toggle('hidden', state !== 'error');
    }

    function handleFile(file) {
        // Validate
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showError('Please upload a PDF file.');
            return;
        }
        if (file.size > 1024 * 1024 * 1024) {
            showError('File is too large. Maximum size is 1 GB.');
            return;
        }

        uploadFile(file);
    }

    function uploadFile(file) {
        showState('progress');
        progressTitle.textContent = 'Uploading PDF...';
        progressSubtitle.textContent = 'Extracting text and generating flashcards. This may take a minute...';
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const formData = new FormData();
        formData.append('pdf', file);

        const xhr = new XMLHttpRequest();

        // Upload progress
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 50); // Upload is 50%
                progressBar.style.width = `${pct}%`;
                progressPercent.textContent = `${pct}%`;
                if (pct >= 50) {
                    progressTitle.textContent = 'Generating Flashcards...';
                    progressSubtitle.textContent = 'AI is analyzing your document and creating flashcards...';
                }
            }
        });

        // Simulate processing progress after upload completes
        let processingInterval;
        xhr.upload.addEventListener('load', () => {
            let pct = 50;
            processingInterval = setInterval(() => {
                pct += Math.random() * 3;
                if (pct > 92) pct = 92;
                progressBar.style.width = `${Math.round(pct)}%`;
                progressPercent.textContent = `${Math.round(pct)}%`;
            }, 500);
        });

        xhr.addEventListener('load', () => {
            if (processingInterval) clearInterval(processingInterval);

            try {
                const response = JSON.parse(xhr.responseText);

                if (xhr.status === 200 && response.success) {
                    // Success
                    progressBar.style.width = '100%';
                    progressPercent.textContent = '100%';

                    setTimeout(() => {
                        showState('success');
                        document.getElementById('success-title').textContent = 'Flashcards Generated!';
                        document.getElementById('success-subtitle').textContent =
                            `Created "${response.deck_name}" with ${response.card_count} flashcards.`;

                        // Update Practice Now button
                        const practiceBtn = document.getElementById('practice-now-btn');
                        if (practiceBtn) {
                            practiceBtn.addEventListener('click', () => {
                                window.location.href = `/practice/${response.deck_id}`;
                            });
                        }
                    }, 400);
                } else {
                    showError(response.error || 'An unexpected error occurred.');
                }
            } catch (e) {
                showError('Failed to process server response.');
            }
        });

        xhr.addEventListener('error', () => {
            if (processingInterval) clearInterval(processingInterval);
            showError('Network error. Please check your connection and try again.');
        });

        xhr.addEventListener('timeout', () => {
            if (processingInterval) clearInterval(processingInterval);
            showError('Request timed out. The PDF may be too large. Try a smaller file.');
        });

        xhr.timeout = 180000; // 3 minute timeout
        xhr.open('POST', '/upload');
        xhr.send(formData);
    }

    function showError(message) {
        showState('error');
        document.getElementById('error-message').textContent = message;
    }
}


/* ═══════════════════════════════════════════════════════
   DASHBOARD
   ═══════════════════════════════════════════════════════ */

function initDashboard() {
    // Animate stat numbers
    animateCounters();

    // Render analytics charts
    renderCharts();

    // Delete deck buttons
    const deleteButtons = document.querySelectorAll('.deck-delete-btn');
    const deleteModal = document.getElementById('delete-modal');
    const cancelDelete = document.getElementById('cancel-delete');
    const confirmDelete = document.getElementById('confirm-delete');
    let deckToDelete = null;

    if (!deleteModal) return;

    deleteButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deckToDelete = btn.dataset.deckId;
            deleteModal.classList.remove('hidden');
        });
    });

    if (cancelDelete) {
        cancelDelete.addEventListener('click', () => {
            deleteModal.classList.add('hidden');
            deckToDelete = null;
        });
    }

    if (confirmDelete) {
        confirmDelete.addEventListener('click', async () => {
            if (!deckToDelete) return;

            confirmDelete.disabled = true;
            confirmDelete.textContent = 'Deleting...';

            try {
                const res = await fetch(`/api/deck/${deckToDelete}`, { method: 'DELETE' });
                const data = await res.json();

                if (data.success) {
                    // Animate card removal
                    const deckCard = document.getElementById(`deck-${deckToDelete}`);
                    if (deckCard) {
                        deckCard.style.transition = 'all 0.3s ease';
                        deckCard.style.transform = 'scale(0.9)';
                        deckCard.style.opacity = '0';
                        setTimeout(() => {
                            deckCard.remove();
                            // Reload to update stats
                            window.location.reload();
                        }, 300);
                    }
                } else {
                    alert(data.error || 'Failed to delete deck.');
                }
            } catch (e) {
                alert('Network error. Please try again.');
            } finally {
                deleteModal.classList.add('hidden');
                confirmDelete.disabled = false;
                confirmDelete.textContent = 'Delete';
                deckToDelete = null;
            }
        });
    }

    // Close modal on overlay click
    if (deleteModal) {
        deleteModal.addEventListener('click', (e) => {
            if (e.target === deleteModal) {
                deleteModal.classList.add('hidden');
                deckToDelete = null;
            }
        });
    }
}


/* ═══════════════════════════════════════════════════════
   DASHBOARD CHARTS (Pure Canvas 2D)
   ═══════════════════════════════════════════════════════ */

function renderCharts() {
    const dataEl = document.getElementById('chart-data');
    if (!dataEl) return;

    let chartData;
    try {
        chartData = JSON.parse(dataEl.textContent);
    } catch (e) {
        console.error('Failed to parse chart data:', e);
        return;
    }

    // Delay rendering slightly to ensure layout is complete and clientWidth/Height are available
    requestAnimationFrame(() => {
        renderDonutChart(chartData.stats);
        renderBarChart(chartData.decks);
    });
}


/* ── Donut Chart ──────────────────────────────────────── */

function renderDonutChart(stats) {
    const canvas = document.getElementById('donut-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // High-DPI scaling — use wrapper size, fallback to 280
    const wrapper = canvas.parentElement;
    const displayW = (wrapper ? wrapper.clientWidth : 0) || canvas.clientWidth || 280;
    const displayH = (wrapper ? wrapper.clientHeight : 0) || canvas.clientHeight || 280;
    canvas.width = displayW * dpr;
    canvas.height = displayH * dpr;
    canvas.style.width = displayW + 'px';
    canvas.style.height = displayH + 'px';
    ctx.scale(dpr, dpr);

    const cx = displayW / 2;
    const cy = displayH / 2;
    const outerR = Math.min(cx, cy) - 10;
    const innerR = outerR * 0.62; // donut hole

    const segments = [
        { label: 'Mastered',  value: stats.mastered,  color: '#34d399' },
        { label: 'Learning',  value: stats.learning,  color: '#6366f1' },
        { label: 'Due',       value: stats.due,       color: '#fbbf24' },
        { label: 'New',       value: stats.new,       color: '#64748b' },
    ];

    const total = segments.reduce((s, seg) => s + seg.value, 0);

    // If everything is 0, draw an empty ring
    if (total === 0) {
        drawEmptyDonut(ctx, cx, cy, outerR, innerR, displayW, displayH);
        return;
    }

    // Animate the donut sweep
    const duration = 900; // ms
    const startTime = performance.now();

    function draw(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic

        ctx.clearRect(0, 0, displayW, displayH);

        // Background track
        ctx.beginPath();
        ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
        ctx.arc(cx, cy, innerR, 0, Math.PI * 2, true);
        ctx.fillStyle = 'rgba(100,116,139,0.12)';
        ctx.fill();

        // Draw segments with sweep animation
        const totalSweep = Math.PI * 2 * eased;
        let currentAngle = -Math.PI / 2; // start from top
        let drawnSoFar = 0;

        segments.forEach(seg => {
            if (seg.value === 0) return;
            const segAngle = (seg.value / total) * Math.PI * 2;
            const availableSweep = Math.max(0, totalSweep - drawnSoFar);
            const drawAngle = Math.min(segAngle, availableSweep);

            if (drawAngle <= 0) {
                drawnSoFar += segAngle;
                return;
            }

            ctx.beginPath();
            ctx.arc(cx, cy, outerR, currentAngle, currentAngle + drawAngle);
            ctx.arc(cx, cy, innerR, currentAngle + drawAngle, currentAngle, true);
            ctx.closePath();
            ctx.fillStyle = seg.color;
            ctx.fill();

            currentAngle += drawAngle;
            drawnSoFar += segAngle;
        });

        // Center text
        const overallPct = total > 0 ? Math.round((stats.mastered / total) * 100) : 0;
        ctx.fillStyle = '#f1f5f9';
        ctx.font = `700 ${Math.round(innerR * 0.55)}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${Math.round(overallPct * eased)}%`, cx, cy - 6);

        ctx.fillStyle = '#94a3b8';
        ctx.font = `500 ${Math.round(innerR * 0.22)}px Inter, sans-serif`;
        ctx.fillText('Mastered', cx, cy + innerR * 0.32);

        if (progress < 1) {
            requestAnimationFrame(draw);
        }
    }
    requestAnimationFrame(draw);
}

function drawEmptyDonut(ctx, cx, cy, outerR, innerR, w, h) {
    // Subtle empty ring
    ctx.clearRect(0, 0, w, h);

    ctx.beginPath();
    ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2, true);
    ctx.fillStyle = 'rgba(100,116,139,0.15)';
    ctx.fill();

    // Dashed outline for style
    ctx.beginPath();
    ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(100,116,139,0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.beginPath();
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(100,116,139,0.2)';
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Center text
    ctx.fillStyle = '#64748b';
    ctx.font = '700 28px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('0%', cx, cy - 6);

    ctx.fillStyle = '#475569';
    ctx.font = '500 12px Inter, sans-serif';
    ctx.fillText('No data yet', cx, cy + 20);
}


/* ── Bar Chart (Deck Mastery Progress) ────────────────── */

function renderBarChart(decks) {
    const canvas = document.getElementById('bar-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // Use wrapper size, fallback to 500x280
    const wrapper = canvas.parentElement;
    const displayW = (wrapper ? wrapper.clientWidth : 0) || canvas.clientWidth || 500;
    const displayH = (wrapper ? wrapper.clientHeight : 0) || canvas.clientHeight || 280;
    canvas.width = displayW * dpr;
    canvas.height = displayH * dpr;
    canvas.style.width = displayW + 'px';
    canvas.style.height = displayH + 'px';
    ctx.scale(dpr, dpr);

    if (!decks || decks.length === 0) {
        // Empty state
        ctx.fillStyle = '#475569';
        ctx.font = '500 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Upload PDFs to see deck progress', displayW / 2, displayH / 2);
        return;
    }

    const padding = { top: 20, right: 30, bottom: 40, left: 120 };
    const chartW = displayW - padding.left - padding.right;
    const chartH = displayH - padding.top - padding.bottom;
    const barHeight = Math.min(32, (chartH / decks.length) - 12);
    const gap = (chartH - barHeight * decks.length) / (decks.length + 1);

    const colors = {
        mastered: '#34d399',
        learning: '#6366f1',
        new:      '#334155',
        bg:       'rgba(100,116,139,0.12)',
    };

    // Animation
    const duration = 800;
    const startTime = performance.now();

    function draw(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        ctx.clearRect(0, 0, displayW, displayH);

        decks.forEach((deck, i) => {
            const y = padding.top + gap + i * (barHeight + gap);

            // Truncate long names
            let name = deck.name;
            if (name.length > 16) name = name.substring(0, 14) + '…';

            // Deck label
            ctx.fillStyle = '#cbd5e1';
            ctx.font = '500 12px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            ctx.fillText(name, padding.left - 10, y + barHeight / 2);

            // Background bar
            const rx = padding.left;
            const rw = chartW;
            roundRect(ctx, rx, y, rw, barHeight, 6, colors.bg);

            if (deck.total === 0) return;

            // Stacked bar segments: mastered | learning | new
            const masteredW = (deck.mastered / deck.total) * chartW * eased;
            const learningW = (deck.learning / deck.total) * chartW * eased;

            // Mastered segment
            if (masteredW > 0) {
                roundRect(ctx, rx, y, masteredW, barHeight, 6, colors.mastered);
            }

            // Learning segment (next to mastered)
            if (learningW > 0) {
                const lx = rx + masteredW;
                ctx.fillStyle = colors.learning;
                ctx.fillRect(lx, y, learningW, barHeight);
            }

            // Percentage label
            const pct = Math.round(deck.progress * eased);
            ctx.fillStyle = '#f1f5f9';
            ctx.font = '600 11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            const labelX = rx + Math.max(masteredW + learningW + 8, 8);
            if (labelX + 30 < displayW) {
                ctx.fillText(`${pct}%`, labelX, y + barHeight / 2);
            }
        });

        // Legend at the bottom
        if (progress >= 1) {
            const legendY = displayH - 12;
            const legends = [
                { label: 'Mastered', color: colors.mastered },
                { label: 'Learning', color: colors.learning },
                { label: 'Remaining', color: '#475569' },
            ];
            let lx = padding.left;
            legends.forEach(l => {
                ctx.fillStyle = l.color;
                ctx.fillRect(lx, legendY - 5, 10, 10);
                ctx.fillStyle = '#94a3b8';
                ctx.font = '400 11px Inter, sans-serif';
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                ctx.fillText(l.label, lx + 14, legendY);
                lx += ctx.measureText(l.label).width + 30;
            });
        }

        if (progress < 1) {
            requestAnimationFrame(draw);
        }
    }
    requestAnimationFrame(draw);
}

/** Utility: draw a filled rounded rectangle */
function roundRect(ctx, x, y, w, h, r, fill) {
    if (w < 0) return;
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
}

function animateCounters() {
    const counters = document.querySelectorAll('.stat-number[data-count]');
    counters.forEach(counter => {
        const target = parseInt(counter.dataset.count, 10);
        if (isNaN(target) || target === 0) {
            counter.textContent = '0';
            return;
        }

        let current = 0;
        const step = Math.max(1, Math.ceil(target / 40));
        const interval = setInterval(() => {
            current += step;
            if (current >= target) {
                current = target;
                clearInterval(interval);
            }
            counter.textContent = current;
        }, 30);
    });
}


/* ═══════════════════════════════════════════════════════
   PRACTICE MODE
   ═══════════════════════════════════════════════════════ */

function initPractice() {
    const container = document.querySelector('.practice-container');
    if (!container) return;

    const deckId = container.dataset.deckId;
    const flashcard = document.getElementById('flashcard');
    const flashcardWrapper = document.getElementById('flashcard-wrapper');
    const practiceLoading = document.getElementById('practice-loading');
    const ratingButtons = document.getElementById('rating-buttons');
    const sessionComplete = document.getElementById('session-complete');
    const practiceEmpty = document.getElementById('practice-empty');
    const progressBar = document.getElementById('practice-progress-bar');
    const currentCardNum = document.getElementById('current-card-num');
    const totalCardNum = document.getElementById('total-card-num');

    let cards = [];
    let currentIndex = 0;
    let isFlipped = false;
    let sessionStats = { easy: 0, medium: 0, hard: 0, total: 0 };

    // Load cards
    loadCards();

    async function loadCards() {
        try {
            const res = await fetch(`/api/deck/${deckId}/cards`);
            const data = await res.json();

            if (data.cards && data.cards.length > 0) {
                cards = data.cards;
                totalCardNum.textContent = cards.length;
                practiceLoading.classList.add('hidden');
                flashcardWrapper.classList.remove('hidden');
                showCard(0);
            } else {
                practiceLoading.classList.add('hidden');
                practiceEmpty.classList.remove('hidden');
            }
        } catch (e) {
            practiceLoading.innerHTML = '<p style="color: var(--color-danger);">Failed to load cards. Please try again.</p>';
        }
    }

    function showCard(index) {
        if (index >= cards.length) {
            showSessionComplete();
            return;
        }

        currentIndex = index;
        isFlipped = false;
        flashcard.classList.remove('is-flipped');
        ratingButtons.classList.add('hidden');

        const card = cards[index];
        document.getElementById('card-question').textContent = card.question;
        document.getElementById('card-answer').textContent = card.answer;

        // Handle images
        const imgFrontContainer = document.getElementById('card-image-front');
        const imgBackContainer = document.getElementById('card-image-back');
        const imgFront = document.getElementById('card-img-front');
        const imgBack = document.getElementById('card-img-back');

        if (card.image_path) {
            imgFront.src = card.image_path;
            imgBack.src = card.image_path;
            imgFrontContainer.classList.remove('hidden');
            imgBackContainer.classList.remove('hidden');
        } else {
            imgFrontContainer.classList.add('hidden');
            imgBackContainer.classList.add('hidden');
        }

        // Update progress
        currentCardNum.textContent = index + 1;
        const pct = ((index) / cards.length) * 100;
        progressBar.style.width = `${pct}%`;
    }

    // Flip card on click
    if (flashcard) {
        flashcard.addEventListener('click', () => {
            toggleFlip();
        });
    }

    // Keyboard controls
    document.addEventListener('keydown', (e) => {
        if (!flashcardWrapper || flashcardWrapper.classList.contains('hidden')) return;

        switch (e.code) {
            case 'Space':
                e.preventDefault();
                toggleFlip();
                break;
            case 'Digit1':
            case 'Numpad1':
                if (isFlipped) submitRating(1);
                break;
            case 'Digit2':
            case 'Numpad2':
                if (isFlipped) submitRating(3);
                break;
            case 'Digit3':
            case 'Numpad3':
                if (isFlipped) submitRating(5);
                break;
        }
    });

    function toggleFlip() {
        isFlipped = !isFlipped;
        flashcard.classList.toggle('is-flipped', isFlipped);

        if (isFlipped) {
            ratingButtons.classList.remove('hidden');
        } else {
            ratingButtons.classList.add('hidden');
        }
    }

    // Rating button clicks
    const ratingBtns = document.querySelectorAll('.btn-rating');
    ratingBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const quality = parseInt(btn.dataset.quality, 10);
            submitRating(quality);
        });
    });

    async function submitRating(quality) {
        const card = cards[currentIndex];

        // Track stats
        sessionStats.total++;
        if (quality === 5) sessionStats.easy++;
        else if (quality === 3) sessionStats.medium++;
        else sessionStats.hard++;

        // Submit to server
        try {
            await fetch(`/api/card/${card.id}/review`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ quality })
            });
        } catch (e) {
            console.error('Failed to submit review:', e);
        }

        // Next card
        showCard(currentIndex + 1);
    }

    function showSessionComplete() {
        flashcardWrapper.classList.add('hidden');
        sessionComplete.classList.remove('hidden');
        progressBar.style.width = '100%';

        document.getElementById('stat-total-reviewed').textContent = sessionStats.total;
        document.getElementById('stat-easy-count').textContent = sessionStats.easy;
        document.getElementById('stat-medium-count').textContent = sessionStats.medium;
        document.getElementById('stat-hard-count').textContent = sessionStats.hard;
    }

    // Restart practice
    const restartBtn = document.getElementById('restart-practice');
    if (restartBtn) {
        restartBtn.addEventListener('click', () => {
            sessionStats = { easy: 0, medium: 0, hard: 0, total: 0 };
            sessionComplete.classList.add('hidden');
            practiceLoading.classList.remove('hidden');
            flashcardWrapper.classList.add('hidden');
            progressBar.style.width = '0%';
            loadCards();
        });
    }
}
