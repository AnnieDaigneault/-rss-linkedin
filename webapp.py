#!/usr/bin/env python3
"""
RSS → LinkedIn Post Generator | extensio.ai
Lancer: python3 ~/Desktop/webapp.py
Ouvrir: http://localhost:5001
iPhone: http://[IP affichée]:5001
"""

import os, re, json, ssl, urllib.request, requests, io, base64
from pathlib import Path
from datetime import datetime
from html import unescape
from html.parser import HTMLParser

# Charger le fichier .env automatiquement si présent
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

import feedparser, anthropic, openai
from google import genai
from google.genai import types as genai_types
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

RSS_URL = "https://www.google.com/alerts/feeds/16960465778323342585/10731404475403027265"
HISTORY_FILE = Path.home() / "Desktop" / "linkedin_history.json"
FEED_SNAPSHOTS_FILE = Path.home() / "Desktop" / "feed_snapshots.json"

IMAGE_STYLE = (
    "STYLE 3D CGI ÉDITORIAL — reproduire exactement cette esthétique : "
    "FOND : dégradé horizontal lisse, rose chaud à gauche vers bleu pervenche froid à droite, "
    "saturation moyenne (ni pastel délavé, ni néon criard), luminosité médium. "
    "Sol légèrement réfléchissant, dans les mêmes tons que le fond. "
    "OBJETS ET PERSONNAGES : rendu 3D low-poly propre — silhouettes humaines simplifiées sans visage, "
    "objets technologiques géométriques, structures abstraites. "
    "Matière mate ou légèrement satinée, couleurs mauve, lavande, gris-bleu, blanc. "
    "ÉLÉMENTS RÉSEAU : lignes fines blanches lumineuses, nœuds brillants, motifs de circuits ou "
    "wireframe polygonal — qui évoquent la connectivité et la technologie. "
    "ÉCLAIRAGE : doux et diffus avec un point focal lumineux blanc ou cyan au centre. "
    "COMPOSITION : scène narrative centrée, espace aéré, profondeur de champ subtile. "
    "ABSOLUMENT AUCUN texte, lettre, chiffre, mot, sigle, code ou symbole écrit dans l'image. "
    "JAMAIS de fond noir, blanc pur, beige, orange, jaune ou vert."
)

EVALUATOR_SYSTEM = """Tu es Annie Daigneault, consultante en adoption responsable de l'IA pour les PME québécoises (extensio.ai). Tu évalues des articles de presse sur l'IA selon ta stratégie LinkedIn 2026.

CRITÈRE ÉLIMINATOIRE ABSOLU : Ne jamais retenir un article qui relaie simplement l'actualité sans valeur ajoutée identifiable (analyse, données actionnables, prise de position possible). C'est le critère #1.

UN ARTICLE EST ÉLIGIBLE s'il correspond à au moins un de ces 4 types de posts LinkedIn :

Type B — Expertise (pilier principal, 4-5/mois) :
- Rapport ou étude avec données actionnables et contexte PME québécois possible
- Sujets prioritaires : adoption IA, gestion du changement, gouvernance IA, ROI, formation, Shadow AI, IA agentique, éthique IA, productivité, Loi 25, conformité
- Permet une prise de position tranchée et nuancée (ni hype, ni alarmisme)

Type C — Communauté (3-4/mois) :
- Sujet pouvant générer un débat substantiel ou une vraie question ouverte
- Biais IA, résistances organisationnelles, compétences émergentes, futurs du travail, enjeux humains

Type D — Écosystème québécois (2-3/mois) :
- Implique des acteurs locaux : Brigade IA, CPQ, Mila, UdeM, Obvia, gouvernement QC
- Lien direct avec la réalité et le contexte des PME québécoises

Type A — Portée (1-2/mois, rare) :
- Percée technologique ou cas d'usage concret lié à l'expérience terrain d'Annie

CRITÈRES D'EXCLUSION :
- Article purement technique sans angle organisationnel ou humain
- Marketing ou publicité déguisée
- Trop générique, pas de substance réelle
- Hors thématique : adoption IA, PME, gouvernance, formation, éthique IA
"""

LINKEDIN_SYSTEM = """Tu rédiges des posts LinkedIn dans le style d'Annie Daigneault, consultante en adoption responsable de l'IA pour les PME québécoises (extensio.ai). Son fil conducteur : l'IA doit servir l'humain, pas le remplacer.

STRUCTURE TYPIQUE :
1. Accroche percutante — statistique frappante, question directe ou constat provocateur
2. Contextualisation — source, étude ou actualité qui ancre le propos
3. Développement en prose fluide (pas de bullet points sauf exception)
4. Prise de position personnelle — "Ce que j'en pense...", "Car sur le terrain, je constate que..."
5. Ouverture/conclusion — question rhétorique vers les PME québécoises
6. Source(s) → "🔎 [Source], [Titre], [date] : [URL]"

RÈGLES STYLISTIQUES OBLIGATOIRES :
- Emojis à la FIN des phrases, jamais au début (3-5 max par post)
- 💙 pour thématique québécoise (CPQ, Mila, écosystème local, fierté QC)
- 🧡 par défaut ou pour thématique Anthropic/Claude
- Utiliser "on" plutôt que "tu" ou "vous" dans les accroches
- Parenthèses expressives pour humaniser : (carrément impressionnant !), (😮‍💨), (Et c'est gratuit.), (je ne sais pas pourquoi)
- Micro-phrases de 3-5 mots pour l'impact : "On est rendus là.", "À suivre.", "Résultat :"
- Connecteurs préférés : "Car" (en début de phrase), "Sauf que", "En clair", "Parce que" (début de paragraphe)
- Formulations signature : "Ce que j'en pense...", "Pourquoi c'est important ?", "Et maintenant ?"
- Longueur : 150-400 mots. Ni trop court, ni interminable.
- JAMAIS d'astérisques (`*` ou `**`) — LinkedIn ne supporte pas le markdown, ils s'affichent en brut
- JAMAIS de `#hashtags` dans le corps du post — si hashtags, uniquement en toute fin, max 3

10 TICS IA À ÉVITER ABSOLUMENT — vérifier chaque post avant de le retourner :
1. Structure "Ce n'est pas X, c'est Y" — trop mécanique, reformuler autrement
2. Tirets longs (—) — préférer les deux-points ou reformuler
3. "Dans un monde où...", "À l'ère de...", "Force est de constanter", "Il est important de noter"
4. Structure académique rigide visible (intro/développement/conclusion marqués)
5. Redondances artificielles — ne pas répéter la même idée paraphrasée
6. Majuscules excessives : écrire "intelligence artificielle" pas "Intelligence Artificielle"
7. Deux-points systématiques dans les titres — varier les formulations
8. Gras excessif — utiliser avec parcimonie, pas sur chaque mot-clé
9. Emojis en rafale — max 1-2 par paragraphe
10. Enthousiasme forcé : pas de "Révolutionnaire !", "Incroyable !", "Game-changer !", "Fascinant !"
"""

def clean_post(text):
    """Retire le formatage markdown que LinkedIn n'interprète pas (astérisques, #)."""
    # Gras/italique markdown : **texte** ou *texte* → texte
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    return text.strip()

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__(); self.reset(); self.fed = []
    def handle_data(self, d): self.fed.append(d)
    def get_data(self): return " ".join(self.fed)

def strip_html(text):
    s = HTMLStripper(); s.feed(text)
    return unescape(s.get_data()).strip()

session_data = {}

# ── History helpers ──────────────────────────────────────────────────────────

def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except Exception:
        return []

def save_to_history(post, article, image=""):
    history = load_history()
    # Si le dernier entry a le même texte, juste mettre à jour l'image
    if history and history[0].get("post") == post:
        if image:
            history[0]["image"] = image
        HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "titre": article.get("titre", ""),
        "url": article.get("url", ""),
        "post": post,
        "image": image
    }
    history.insert(0, entry)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def load_feed_snapshots():
    if FEED_SNAPSHOTS_FILE.exists():
        try:
            return json.loads(FEED_SNAPSHOTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_feed_snapshot(articles):
    snapshots = load_feed_snapshots()
    date_key = datetime.now().strftime("%Y-%m-%d")
    snapshots[date_key] = {
        "date": date_key,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "articles": articles,
        "total": len(articles),
        "eligible": sum(1 for a in articles if a.get("eligible"))
    }
    FEED_SNAPSHOTS_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8")

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/health")
def health():
    anthropic_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
    buffer_ok = bool(os.environ.get("BUFFER_ACCESS_TOKEN"))
    return jsonify({
        "anthropic": anthropic_ok,
        "openai": openai_ok,
        "buffer": buffer_ok,
        "ok": anthropic_ok and openai_ok
    })

@app.route("/api/fetch-articles", methods=["POST"])
def fetch_articles():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY manquante. Crée un fichier .env sur le Bureau."}), 400

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(RSS_URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            content = r.read()
        feed = feedparser.parse(content)
    except Exception as e:
        return jsonify({"error": f"Erreur RSS: {str(e)}"}), 500

    articles = [{"title": strip_html(e.get("title","")), "url": e.get("link",""),
                 "summary_raw": strip_html(e.get("summary",""))[:600]}
                for e in feed.entries]

    if not articles:
        return jsonify({"error": "Aucun article dans le flux RSS. Vérifie l'URL de ton alerte Google."}), 404

    client = anthropic.Anthropic()
    articles_text = "".join(
        f"\nARTICLE {i}:\nTitre: {a['title']}\nURL: {a['url']}\nExtrait: {a['summary_raw']}\n"
        for i, a in enumerate(articles, 1)
    )

    prompt = f"""Évalue ces {len(articles)} articles selon la stratégie LinkedIn 2026. Retourne-les TOUS, éligibles ou non.

{articles_text}

Pour CHAQUE article, retourne un objet JSON avec :
- "num": numéro (int)
- "titre": titre (string)
- "url": URL (string)
- "resume": résumé 2-4 phrases en français (string)
- "eligible": true si mérite un post LinkedIn, false sinon
- "type_post": "A", "B", "C" ou "D" si éligible, "" sinon
- "raison_exclusion": si non éligible, raison courte en 1 phrase, "" sinon
- "angle1": si éligible, premier angle LinkedIn percutant 1 phrase, "" sinon
- "angle2": si éligible, deuxième angle distinct 1 phrase, "" sinon

Retourne UNIQUEMENT un tableau JSON valide avec les {len(articles)} articles."""

    response = client.messages.create(
        model="claude-opus-4-6", max_tokens=8192,
        system=EVALUATOR_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return jsonify({"articles": []})
    try:
        fresh = json.loads(match.group())

        # ── Accumulation fil d'actualités ────────────────────────────────────
        existing = session_data.get("all_articles_feed", [])
        existing_urls = {a.get("url", "") for a in existing}
        fresh_urls = {a.get("url", "") for a in fresh}

        # Marquer is_new sur les articles qu'on n'avait pas encore
        new_count = 0
        for a in fresh:
            a["is_new"] = a.get("url", "") not in existing_urls
            if a["is_new"]:
                new_count += 1

        # Articles précédents absents du flux actuel (archivés) → is_new = False
        archived = [a for a in existing if a.get("url", "") not in fresh_urls]
        for a in archived:
            a["is_new"] = False

        # Fusion : articles frais en premier, archivés en dessous
        merged = fresh + archived

        # Renumérotation séquentielle
        for i, a in enumerate(merged, 1):
            a["num"] = i

        session_data["all_articles_feed"] = merged
        eligible = [a for a in merged if a.get("eligible")]
        session_data["eligible"] = eligible

        # Sauvegarder le snapshot du jour
        save_feed_snapshot(merged)

        return jsonify({"articles": merged, "new_count": new_count})
    except Exception:
        return jsonify({"articles": [], "new_count": 0})

@app.route("/api/draft-post", methods=["POST"])
def draft_post():
    data = request.json
    eligible = session_data.get("eligible", [])
    article = next((a for a in eligible if a["num"] == data.get("article_num")), None)
    if not article:
        return jsonify({"error": "Article non trouvé"}), 404

    angle = article[f"angle{data.get('angle_num', 1)}"]
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6", max_tokens=2048,
        system=LINKEDIN_SYSTEM,
        messages=[{"role": "user", "content": f"""Rédige un post LinkedIn complet.
Article: {article['titre']}
URL: {article['url']}
Résumé: {article['resume']}
Angle: {angle}"""}]
    )
    post = clean_post(response.content[0].text)
    session_data["current_post"] = post
    session_data["current_article"] = article
    return jsonify({"post": post})

@app.route("/api/refine-post", methods=["POST"])
def refine_post():
    data = request.json
    post = data.get("post", session_data.get("current_post", ""))
    article = session_data.get("current_article", {})
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6", max_tokens=2048,
        system=LINKEDIN_SYSTEM,
        messages=[{"role": "user", "content": f"""Modifie ce post LinkedIn.

POST ACTUEL:
---
{post}
---

MODIFICATION: {data.get('feedback', '')}
Article source: "{article.get('titre', '')}"

Retourne le post révisé complet."""}]
    )
    new_post = clean_post(response.content[0].text)
    session_data["current_post"] = new_post
    return jsonify({"post": new_post})

@app.route("/api/generate-angles", methods=["POST"])
def generate_angles():
    """Génère 2 angles LinkedIn pour un article non retenu par l'évaluateur."""
    data = request.json or {}
    article = data.get("article", {})
    if not article:
        return jsonify({"error": "Article manquant"}), 400

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6", max_tokens=400,
        system=EVALUATOR_SYSTEM,
        messages=[{"role": "user", "content": f"""Génère 2 angles LinkedIn pour cet article, même si tu ne l'aurais pas sélectionné spontanément.

Titre: {article.get('titre', '')}
URL: {article.get('url', '')}
Résumé: {article.get('resume', '')}

Retourne UNIQUEMENT ce JSON:
{{"angle1": "premier angle percutant, 1 phrase", "angle2": "deuxième angle distinct, 1 phrase"}}"""}]
    )
    text = response.content[0].text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return jsonify({"error": "Impossible de générer les angles"}), 500
    try:
        angles = json.loads(match.group())
        # Ajouter l'article aux éligibles pour que draftPost puisse l'utiliser
        article["angle1"] = angles.get("angle1", "")
        article["angle2"] = angles.get("angle2", "")
        eligible = session_data.get("eligible", [])
        eligible = [a for a in eligible if a.get("num") != article.get("num")]
        eligible.append(article)
        session_data["eligible"] = eligible
        return jsonify(angles)
    except Exception:
        return jsonify({"error": "Erreur parsing angles"}), 500

@app.route("/api/generate-concepts", methods=["POST"])
def generate_concepts():
    post = request.json.get("post", session_data.get("current_post", ""))
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6", max_tokens=800,
        system="Tu es un directeur artistique spécialisé en visuels LinkedIn professionnels.",
        messages=[{"role": "user", "content": f"""Pour ce post LinkedIn, propose 3 concepts d'image distincts à générer avec Imagen 4.

{post}

RÈGLES ABSOLUES pour chaque concept :
- Décrire uniquement des éléments VISUELS (formes, lumières, objets, compositions)
- AUCUN nom propre, marque, acronyme, sigle, pays, ville, organisation ou mot identifiable
- AUCUNE instruction de texte ou étiquette — l'image ne doit contenir AUCUN mot
- Métaphore visuelle forte qui évoque le thème sans le nommer
- Style : rendu 3D éthéré, bokeh, mauve/lavande/rose/bleu-turquoise, wireframe lumineux

Format EXACT (3 lignes, une par concept) :
CONCEPT 1: [description purement visuelle, sans nom propre]
CONCEPT 2: [description purement visuelle, sans nom propre]
CONCEPT 3: [description purement visuelle, sans nom propre]"""}]
    )
    text = response.content[0].text.strip()
    concepts = re.findall(r"CONCEPT \d+:\s*(.+?)(?=CONCEPT \d+:|$)", text, re.DOTALL)
    concepts = [c.strip() for c in concepts if c.strip()]
    session_data["concepts"] = concepts
    return jsonify({"concepts": concepts})

@app.route("/api/generate-image", methods=["POST"])
def generate_image():
    try:
        idx = request.json.get("concept_idx", 0)
        concepts = session_data.get("concepts", [])
        article = session_data.get("current_article", {})
        if idx >= len(concepts):
            return jsonify({"error": "Concept non trouvé"}), 404

        client = openai.OpenAI()
        response = client.images.generate(
            model="gpt-image-2",
            prompt=f"{concepts[idx]} {IMAGE_STYLE}",
            size="1536x1024", quality="high", n=1
        )

        b64 = response.data[0].b64_json if response.data else None
        if not b64:
            return jsonify({"error": "Aucune donnée image retournée"}), 500

        img_data = base64.b64decode(b64)

        # Redimensionner au format LinkedIn : 1200×627 px (ratio 1.91:1), JPEG 82%
        from PIL import Image
        import io as _io
        src = Image.open(_io.BytesIO(img_data))
        target_ratio = 1200 / 627          # ≈ 1.914
        src_w, src_h = src.size
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            # Trop large : rogner les côtés
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            src = src.crop((left, 0, left + new_w, src_h))
        else:
            # Trop haut : rogner haut/bas
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            src = src.crop((0, top, src_w, top + new_h))
        src = src.resize((1200, 627), Image.LANCZOS)
        if src.mode == "RGBA":
            src = src.convert("RGB")
        buf = _io.BytesIO()
        src.save(buf, format="JPEG", quality=82, optimize=True)
        final_data = buf.getvalue()

        slug = re.sub(r"\s+", "-", re.sub(r"[^a-zA-Z0-9\s]", "", article.get("titre","linkedin")).strip().lower())[:50]
        filename = f"linkedin_{slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.jpg"

        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        (downloads / filename).write_bytes(final_data)
        session_data["last_image_filename"] = filename

        post = session_data.get("current_post", "")
        if post:
            save_to_history(post, article, filename)

        return jsonify({"filename": filename})

    except openai.BadRequestError as e:
        return jsonify({"error": f"Contenu refusé : {str(e)[:300]}"}), 400
    except openai.AuthenticationError:
        return jsonify({"error": "Clé OpenAI invalide ou expirée"}), 401
    except openai.RateLimitError:
        return jsonify({"error": "Quota OpenAI dépassé. Réessaie dans quelques secondes."}), 429
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Erreur génération image : {str(e)[:400]}"}), 500

@app.route("/api/view-image")
def view_image():
    filename = session_data.get("last_image_filename")
    if filename:
        img_path = Path.home() / "Downloads" / filename
        if img_path.exists():
            mimetype = "image/jpeg" if filename.endswith(".jpg") else "image/png"
            response = send_file(str(img_path), mimetype=mimetype)
            response.headers["Cache-Control"] = "no-store"
            return response
    return "Image non trouvée", 404

@app.route("/api/download-image")
def download_image():
    filename = session_data.get("last_image_filename", "linkedin_image.png")
    img_path = Path.home() / "Downloads" / filename
    if img_path.exists():
        return send_file(str(img_path), mimetype="image/png",
                         as_attachment=True, download_name=filename)
    return "Image non trouvée", 404

@app.route("/api/save-history", methods=["POST"])
def save_history_route():
    data = request.json or {}
    post = data.get("post") or session_data.get("current_post", "")
    article = session_data.get("current_article", {})
    image = data.get("image", "")
    if not post:
        return jsonify({"error": "Post vide"}), 400
    save_to_history(post, article, image)
    return jsonify({"ok": True})

@app.route("/api/get-history")
def get_history_route():
    return jsonify({"history": load_history()})

@app.route("/api/feed-snapshots")
def get_feed_snapshots():
    snapshots = load_feed_snapshots()
    # Retourner les dates triées du plus récent au plus ancien, sans les articles (léger)
    summary = []
    for date_key in sorted(snapshots.keys(), reverse=True):
        s = snapshots[date_key]
        summary.append({
            "date": date_key,
            "fetched_at": s.get("fetched_at", ""),
            "total": s.get("total", 0),
            "eligible": s.get("eligible", 0)
        })
    return jsonify({"snapshots": summary})

@app.route("/api/feed-snapshot/<date_key>")
def get_feed_snapshot(date_key):
    snapshots = load_feed_snapshots()
    if date_key not in snapshots:
        return jsonify({"error": "Snapshot non trouvé"}), 404
    snap = snapshots[date_key]
    articles = snap.get("articles", [])
    # Recharger en session
    session_data["all_articles_feed"] = articles
    session_data["eligible"] = [a for a in articles if a.get("eligible")]
    return jsonify({"articles": articles, "date": date_key})

@app.route("/api/buffer-send", methods=["POST"])
def buffer_send():
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        return jsonify({"error": "BUFFER_ACCESS_TOKEN non configuré"}), 400

    data = request.json or {}
    post_text = data.get("post") or session_data.get("current_post", "")

    try:
        profiles_resp = requests.get(
            "https://api.bufferapp.com/1/profiles.json",
            params={"access_token": token},
            timeout=15
        )
        profiles_resp.raise_for_status()
        profiles = profiles_resp.json()
        linkedin_ids = [p["id"] for p in profiles if p.get("service") == "linkedin"]
        if not linkedin_ids:
            return jsonify({"error": "Aucun profil LinkedIn trouvé dans Buffer"}), 400
    except Exception as e:
        return jsonify({"error": f"Erreur Buffer (profils): {str(e)}"}), 500

    try:
        form_data = [("access_token", token), ("text", post_text)]
        for pid in linkedin_ids:
            form_data.append(("profile_ids[]", pid))
        resp = requests.post(
            "https://api.bufferapp.com/1/updates/create.json",
            data=form_data,
            timeout=15
        )
        result = resp.json()
        if not resp.ok:
            return jsonify({"error": result.get("message", "Erreur Buffer")}), 400

        # Sauvegarder dans l'historique
        article = session_data.get("current_article", {})
        image = session_data.get("last_image_filename", "")
        save_to_history(post_text, article, image)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"Erreur Buffer: {str(e)}"}), 500

# ── HTML ───────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RSS → LinkedIn | extensio.ai</title>
<style>
  :root {
    --mint: #3ecfb2; --teal: #1a9e87; --dark: #1a2332; --gray: #6b7a8d;
    --light: #f4f7f9; --white: #fff; --border: #e2e8f0;
    --shadow: 0 4px 20px rgba(0,0,0,0.08); --radius: 14px;
    --red: #e53e3e; --red-bg: #fff5f5;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--light); color: var(--dark); min-height: 100vh; }
  header { background: var(--white); border-bottom: 1px solid var(--border);
           padding: 16px 20px; display: flex; align-items: center; gap: 12px;
           position: sticky; top: 0; z-index: 100; }
  .logo { width: 32px; height: 32px; background: linear-gradient(135deg,var(--mint),var(--teal));
          border-radius: 8px; display: flex; align-items: center; justify-content: center;
          color: white; font-weight: 700; font-size: 14px; flex-shrink: 0; }
  header h1 { font-size: 17px; font-weight: 600; }
  .header-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
  .key-status { font-size: 12px; padding: 4px 10px;
                border-radius: 20px; font-weight: 600; }
  .key-status.ok { background: rgba(62,207,178,0.15); color: var(--teal); }
  .key-status.missing { background: var(--red-bg); color: var(--red); cursor: pointer; }
  .btn-history { background: none; border: 1.5px solid var(--border); border-radius: 8px;
                 padding: 5px 12px; font-size: 13px; cursor: pointer; color: var(--gray);
                 font-weight: 500; transition: all 0.2s; }
  .btn-history:hover { border-color: var(--mint); color: var(--teal); }
  main { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
  .screen { display: none; }
  .screen.active { display: block; }
  .card { background: var(--white); border-radius: var(--radius);
          padding: 32px; box-shadow: var(--shadow); }
  .card.center { text-align: center; }
  .icon { font-size: 44px; margin-bottom: 16px; }
  h2 { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
  .sub { color: var(--gray); line-height: 1.6; margin-bottom: 24px; font-size: 15px; }
  .btn { display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px;
         border-radius: 10px; border: none; cursor: pointer; font-size: 15px;
         font-weight: 600; transition: all 0.2s; }
  .btn-primary { background: linear-gradient(135deg,var(--mint),var(--teal)); color: white;
                 box-shadow: 0 4px 12px rgba(62,207,178,0.3); }
  .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(62,207,178,0.4); }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
  .btn-secondary { background: var(--light); color: var(--dark); border: 1px solid var(--border); }
  .btn-secondary:hover { background: var(--border); }
  .btn-ghost { background: transparent; color: var(--teal); border: 1.5px solid var(--mint); }
  .btn-ghost:hover { background: rgba(62,207,178,0.08); }
  .btn-buffer { background: transparent; color: #3d5a9a; border: 1.5px solid #3d5a9a; }
  .btn-buffer:hover { background: rgba(61,90,154,0.07); }
  .btn-full { width: 100%; justify-content: center; }
  .btn-sm { padding: 8px 16px; font-size: 13px; }
  .spinner { width: 40px; height: 40px; border: 3px solid var(--border);
             border-top-color: var(--mint); border-radius: 50%;
             animation: spin 0.8s linear infinite; margin: 0 auto 20px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .section-h { margin-bottom: 20px; }
  .section-h h2 { font-size: 20px; font-weight: 700; }
  .section-h p { color: var(--gray); font-size: 14px; margin-top: 4px; }
  .badge { display: inline-block; background: rgba(62,207,178,0.15); color: var(--teal);
           border-radius: 20px; padding: 2px 10px; font-size: 12px; font-weight: 600; margin-left: 6px; }
  .article-card { background: var(--white); border-radius: var(--radius); padding: 20px;
                  margin-bottom: 14px; box-shadow: var(--shadow);
                  border: 1.5px solid transparent; transition: border-color 0.2s; }
  .article-card:hover { border-color: var(--mint); }
  .art-num { font-size: 11px; font-weight: 700; color: var(--teal);
             text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .art-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; line-height: 1.4; }
  .art-title a { color: var(--dark); text-decoration: none; }
  .art-title a:hover { color: var(--teal); }
  .art-resume { font-size: 13px; color: var(--gray); line-height: 1.6; margin-bottom: 14px; }
  .angles-label { font-size: 12px; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.5px; margin-bottom: 8px; }
  .angle-btn { display: block; width: 100%; text-align: left; padding: 11px 14px;
               border-radius: 10px; border: 1.5px solid var(--border); background: var(--light);
               cursor: pointer; font-size: 13px; color: var(--dark); line-height: 1.4;
               margin-bottom: 8px; transition: all 0.2s; }
  .angle-btn:hover { border-color: var(--mint); background: rgba(62,207,178,0.06); }
  .angle-num { display: inline-block; background: var(--mint); color: white;
               border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700; margin-right: 8px; }
  .post-label { font-size: 12px; font-weight: 600; color: var(--gray);
                text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
  textarea.post-text { width: 100%; min-height: 200px; max-height: 60vh;
                       border: 1.5px solid var(--border);
                       border-radius: 10px; padding: 14px; font-size: 14px; line-height: 1.7;
                       color: var(--dark); background: var(--light); resize: vertical;
                       font-family: inherit; transition: border-color 0.2s; overflow-y: auto; }
  textarea.post-text:focus { outline: none; border-color: var(--mint); }
  .char-count { font-size: 12px; color: var(--gray); text-align: right; margin-top: 6px; }
  .refine-input { width: 100%; padding: 12px 14px; border: 1.5px solid var(--border);
                  border-radius: 10px; font-size: 14px; font-family: inherit;
                  background: var(--light); margin-bottom: 12px; transition: border-color 0.2s;
                  resize: none; min-height: 46px; max-height: 140px; overflow-y: auto;
                  line-height: 1.5; }
  .refine-input:focus { outline: none; border-color: var(--mint); }
  .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
  .concept-card { background: var(--white); border-radius: var(--radius); padding: 18px;
                  margin-bottom: 12px; box-shadow: var(--shadow);
                  border: 2px solid transparent; cursor: pointer; transition: all 0.2s; }
  .concept-card:hover { border-color: var(--mint); transform: translateY(-1px); }
  .concept-card.selected { border-color: var(--teal); background: rgba(62,207,178,0.05); }
  .concept-num { font-size: 11px; font-weight: 700; color: var(--teal);
                 text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .concept-text { font-size: 14px; color: var(--dark); line-height: 1.6; }
  .image-result { background: var(--white); border-radius: var(--radius);
                  padding: 20px; box-shadow: var(--shadow); text-align: center; }
  .image-result img { width: 100%; border-radius: 10px; margin-bottom: 14px; box-shadow: var(--shadow); display: block; }
  .img-filename { font-size: 12px; color: var(--gray); font-family: monospace; margin-bottom: 16px; }
  .error-box { background: var(--red-bg); border: 1.5px solid #feb2b2; border-radius: var(--radius);
               padding: 16px 18px; color: var(--red); font-size: 14px;
               margin-bottom: 16px; line-height: 1.5; }
  .warn-box { background: #fffbeb; border: 1.5px solid #f6e05e; border-radius: var(--radius);
              padding: 16px 18px; color: #744210; font-size: 14px; margin-bottom: 16px; }
  .warn-box code { background: rgba(0,0,0,0.08); padding: 2px 6px; border-radius: 4px;
                   font-size: 13px; display: block; margin-top: 8px; }
  .divider { height: 1px; background: var(--border); margin: 18px 0; }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
           background: var(--dark); color: white; padding: 12px 20px; border-radius: 10px;
           font-size: 14px; font-weight: 500; box-shadow: 0 8px 24px rgba(0,0,0,0.2);
           opacity: 0; transition: opacity 0.3s; z-index: 200; white-space: nowrap; }
  .toast.show { opacity: 1; }
  /* History */
  .history-card { background: var(--white); border-radius: var(--radius); padding: 20px;
                  margin-bottom: 14px; box-shadow: var(--shadow);
                  border: 1.5px solid transparent; transition: border-color 0.2s; }
  .history-card:hover { border-color: var(--mint); }
  .hist-meta { font-size: 11px; color: var(--gray); margin-bottom: 6px;
               display: flex; gap: 10px; flex-wrap: wrap; }
  .hist-title { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
  .hist-title a { color: var(--dark); text-decoration: none; }
  .hist-title a:hover { color: var(--teal); }
  .hist-preview { font-size: 13px; color: var(--gray); line-height: 1.5;
                  white-space: pre-wrap; word-break: break-word; }
  .hist-toggle { font-size: 12px; color: var(--teal); cursor: pointer;
                 background: none; border: none; padding: 4px 0; margin-top: 6px; }
  .hist-image-tag { display: inline-block; background: rgba(62,207,178,0.12);
                    color: var(--teal); border-radius: 6px; padding: 2px 8px;
                    font-size: 11px; font-weight: 600; }
  .empty-state { text-align: center; padding: 48px 20px; color: var(--gray); }
  .empty-state .icon { font-size: 40px; margin-bottom: 12px; }
  @media(max-width:480px) {
    main { padding: 14px 10px; }
    .card { padding: 24px 18px; }
    .btn-row { flex-direction: column; }
    .btn-row .btn { width: 100%; justify-content: center; }
    header h1 { font-size: 15px; }
  }
</style>
</head>
<body>
<header>
  <div class="logo">e.</div>
  <h1>RSS → LinkedIn</h1>
  <div class="header-right">
    <button class="btn-history" onclick="showHistory()">🗂️ Historique</button>
    <div id="key-status" class="key-status" onclick="showKeyHelp()">Vérification...</div>
  </div>
</header>
<main>

  <!-- Welcome -->
  <div id="screen-welcome" class="screen active">
    <div class="card center">
      <div class="icon">📡</div>
      <h2>Bonjour Annie 👋</h2>
      <p class="sub">Je vais analyser tes alertes Google sur l'IA et te proposer les articles qui méritent un post LinkedIn.</p>
      <div id="welcome-error"></div>
      <button id="btn-analyze" class="btn btn-primary" onclick="fetchArticles()">
        ✨ Analyser les alertes
      </button>
    </div>
    <div id="feed-snapshots-section" style="display:none; margin-top:24px;">
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
        <span style="font-size:16px; font-weight:600; color:#1a1a2e;">📅 Fils précédents</span>
        <span style="font-size:13px; color:#888;">Clique sur une date pour recharger le fil</span>
      </div>
      <div id="feed-snapshots-list" style="display:flex; flex-direction:column; gap:8px;"></div>
    </div>
  </div>

  <!-- Loading -->
  <div id="screen-loading" class="screen">
    <div class="card center">
      <div class="spinner"></div>
      <h2 id="loading-title">Récupération des alertes...</h2>
      <p class="sub" id="loading-sub">Claude analyse chaque article pour toi</p>
    </div>
  </div>

  <!-- Articles -->
  <div id="screen-articles" class="screen">
    <div class="section-h">
      <h2>Articles retenus <span class="badge" id="article-count">0</span></h2>
      <p>Clique sur un angle pour démarrer la rédaction</p>
    </div>
    <div id="articles-list"></div>
    <button class="btn btn-secondary btn-full" onclick="fetchArticles()" style="margin-top:4px">
      🔄 Actualiser
    </button>
  </div>

  <!-- Editor -->
  <div id="screen-editor" class="screen">
    <div class="section-h">
      <h2>Ton post LinkedIn ✍️</h2>
      <p id="editor-ctx"></p>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="post-label">Post rédigé par Claude</div>
      <textarea class="post-text" id="post-textarea" oninput="updateCount()"></textarea>
      <div class="char-count" id="char-count">0 caractères</div>
      <div class="btn-row" style="margin-top:12px">
        <button class="btn btn-ghost btn-sm" onclick="copyPost()">📋 Copier le post</button>
        <button class="btn btn-buffer btn-sm buffer-btn" onclick="sendToBuffer()" style="display:none">📤 Envoyer à Buffer</button>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="post-label">Demande une modification</div>
      <textarea class="refine-input" id="refine-input" rows="2"
        placeholder="Ex: Raccourcis l'accroche, ajoute une donnée québécoise... (Entrée pour envoyer, Maj+Entrée pour nouvelle ligne)"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){refinePost();event.preventDefault();}"
        oninput="autoResize(this)"></textarea>
      <div class="btn-row">
        <button class="btn btn-ghost btn-sm" onclick="refinePost()">⚡ Modifier</button>
        <button class="btn btn-primary" onclick="goToConcepts()">C'est parfait → 🎨 Images</button>
      </div>
    </div>
    <button class="btn btn-secondary btn-sm" onclick="show('screen-articles')">← Changer d'article</button>
  </div>

  <!-- Concepts -->
  <div id="screen-concepts" class="screen">
    <div class="section-h">
      <h2>Concepts d'image 🖼️</h2>
      <p>Choisis un concept, je génère avec GPT Image 2</p>
    </div>
    <div id="concepts-list"></div>
    <div id="concept-action" style="display:none;margin-top:14px">
      <button class="btn btn-primary btn-full" onclick="generateImage()">🎨 Générer cette image</button>
    </div>
    <button class="btn btn-secondary btn-sm" style="margin-top:12px" onclick="show('screen-editor')">
      ← Retour au post
    </button>
  </div>

  <!-- Image result -->
  <div id="screen-image" class="screen">
    <div class="section-h"><h2>Image prête 🎉</h2></div>
    <div class="image-result">
      <img id="result-img" src="" alt="Image générée">
      <div class="img-filename" id="result-filename"></div>
      <div class="btn-row" style="justify-content:center;flex-wrap:wrap">
        <a class="btn btn-primary" id="download-btn" href="/api/download-image" download>⬇️ Télécharger</a>
        <button class="btn btn-ghost" onclick="copyPost()">📋 Copier le post</button>
        <button class="btn btn-buffer buffer-btn" onclick="sendToBuffer()" style="display:none">📤 Envoyer à Buffer</button>
        <button class="btn btn-secondary" onclick="show('screen-articles')">📰 Nouvel article</button>
      </div>
    </div>
    <p style="margin-top:12px;text-align:center;font-size:13px;color:var(--gray)">
      Aussi sauvegardée dans ton dossier <strong>Downloads</strong>
    </p>
  </div>

  <!-- Historique -->
  <div id="screen-history" class="screen">
    <div class="section-h">
      <h2>Historique des posts 🗂️</h2>
      <p>Tes posts LinkedIn générés, du plus récent au plus ancien</p>
    </div>
    <div id="history-list"></div>
    <button class="btn btn-secondary btn-sm" onclick="show('screen-welcome')" style="margin-top:4px">
      ← Retour
    </button>
  </div>

</main>
<div class="toast" id="toast"></div>

<script>
let selectedConcept = null;
let hasBuffer = false;
let currentPostText = '';
let historyData = {};
let nonEligibleData = {};

function show(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  window.scrollTo(0,0);
}

function toast(msg, ms=3500) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'), ms);
}

function autoResize(el) {
  el.style.height = 'auto';
  const maxH = Math.floor(window.innerHeight * 0.6);
  el.style.height = Math.min(el.scrollHeight, maxH) + 'px';
}

function updateCount() {
  const ta = document.getElementById('post-textarea');
  currentPostText = ta.value;
  const len = ta.value.length;
  const cc = document.getElementById('char-count');
  if (len > 3000) {
    cc.textContent = len + ' / 3 000 caractères — dépasse la limite LinkedIn ⚠️';
    cc.style.color = 'var(--red)';
  } else if (len > 2800) {
    cc.textContent = len + ' / 3 000 caractères';
    cc.style.color = '#c05b00';
  } else {
    cc.textContent = len + ' caractères';
    cc.style.color = '';
  }
  autoResize(ta);
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Clés API ──────────────────────────────────────────────────────────────────

async function checkKeys() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    hasBuffer = d.buffer;
    document.querySelectorAll('.buffer-btn').forEach(b => {
      b.style.display = hasBuffer ? '' : 'none';
    });
    const el = document.getElementById('key-status');
    if (d.ok) {
      el.textContent = '✓ Clés API ok';
      el.className = 'key-status ok';
    } else {
      el.textContent = '⚠ Clés API manquantes';
      el.className = 'key-status missing';
      showKeyHelp();
    }
    loadFeedSnapshots();
  } catch(e) {
    console.error('Health check failed:', e);
  }
}

function showKeyHelp() {
  const status = document.getElementById('key-status');
  if (status.className.includes('missing')) {
    document.getElementById('welcome-error').innerHTML = `
      <div class="warn-box">
        ⚠️ <strong>Clés API manquantes.</strong> Crée un fichier <code>.env</code> sur le Bureau avec:
        <code>ANTHROPIC_API_KEY=sk-ant-ta-clé<br>OPENAI_API_KEY=sk-proj-ta-clé</code>
        Puis relance: <code>python3 ~/Desktop/webapp.py</code>
      </div>`;
  }
}

// ── Fils d'actualités sauvegardés ─────────────────────────────────────────────

async function loadFeedSnapshots() {
  try {
    const r = await fetch('/api/feed-snapshots');
    const d = await r.json();
    const snapshots = d.snapshots || [];
    const section = document.getElementById('feed-snapshots-section');
    const list = document.getElementById('feed-snapshots-list');
    if (snapshots.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    list.innerHTML = snapshots.map(s => {
      const date = new Date(s.date + 'T12:00:00');
      const label = date.toLocaleDateString('fr-CA', { weekday:'long', day:'numeric', month:'long', year:'numeric' });
      return `<div onclick="loadFeedSnapshot('${s.date}')" style="
        display:flex; align-items:center; justify-content:space-between;
        padding:12px 16px; background:#fff; border:1px solid #e8e8f0;
        border-radius:10px; cursor:pointer; transition:all .15s;
        box-shadow:0 1px 3px rgba(0,0,0,.05);"
        onmouseover="this.style.background='#f5f5ff';this.style.borderColor='#b0a8e8'"
        onmouseout="this.style.background='#fff';this.style.borderColor='#e8e8f0'">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:20px;">📅</span>
          <div>
            <div style="font-weight:600; font-size:14px; color:#1a1a2e; text-transform:capitalize;">${label}</div>
            <div style="font-size:12px; color:#888; margin-top:2px;">${s.total} articles · ${s.eligible} éligibles</div>
          </div>
        </div>
        <span style="font-size:18px; color:#b0a8e8;">›</span>
      </div>`;
    }).join('');
  } catch(e) { console.error('loadFeedSnapshots error:', e); }
}

async function loadFeedSnapshot(dateKey) {
  show('screen-loading');
  document.getElementById('loading-title').textContent = 'Chargement du fil...';
  document.getElementById('loading-sub').textContent = dateKey;
  try {
    const r = await fetch(`/api/feed-snapshot/${dateKey}`);
    const d = await r.json();
    if (d.error) { show('screen-welcome'); toast('Erreur: ' + d.error); return; }
    renderArticles(d.articles);
    show('screen-articles');
  } catch(e) {
    show('screen-welcome');
    toast('Erreur lors du chargement');
  }
}

// ── Presse-papier ─────────────────────────────────────────────────────────────

async function copyPost() {
  const text = currentPostText || document.getElementById('post-textarea')?.value || '';
  if (!text) { toast('Aucun post à copier'); return; }
  try {
    await navigator.clipboard.writeText(text);
    toast('📋 Copié dans le presse-papier !');
  } catch(e) {
    // Fallback : sélection manuelle
    const ta = document.getElementById('post-textarea');
    if (ta) { ta.select(); document.execCommand('copy'); toast('📋 Copié !'); }
    else toast('Impossible de copier automatiquement');
  }
}

// ── Buffer ────────────────────────────────────────────────────────────────────

async function sendToBuffer() {
  const post = currentPostText || document.getElementById('post-textarea')?.value || '';
  if (!post) { toast('Aucun post à envoyer'); return; }
  toast('Envoi à Buffer...', 10000);
  try {
    const r = await fetch('/api/buffer-send', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({post})
    });
    const d = await r.json();
    if (!r.ok || d.error) { toast('❌ ' + d.error, 5000); return; }
    toast('✅ Post envoyé à Buffer !', 4000);
  } catch(e) { toast('❌ Erreur Buffer: ' + e.message, 5000); }
}

// ── Articles ──────────────────────────────────────────────────────────────────

async function fetchArticles() {
  const btn = document.getElementById('btn-analyze');
  if (btn) btn.disabled = true;

  document.getElementById('loading-title').textContent = 'Récupération des alertes Google...';
  document.getElementById('loading-sub').textContent = 'Claude analyse chaque article pour toi';
  show('screen-loading');

  try {
    const r = await fetch('/api/fetch-articles', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: '{}'
    });
    const d = await r.json();

    if (!r.ok || d.error) {
      document.getElementById('articles-list').innerHTML =
        '<div class="error-box">❌ ' + (d.error || 'Erreur inconnue') + '</div>';
      document.getElementById('article-count').textContent = '0';
      show('screen-articles');
      return;
    }

    const articles = d.articles || [];
    const newCount = d.new_count || 0;
    renderArticles(articles, newCount);
    loadFeedSnapshots();
    show('screen-articles');
    if (newCount > 0) {
      toast(`✨ ${newCount} nouvel article${newCount > 1 ? 's' : ''} ajouté${newCount > 1 ? 's' : ''}`, 4000);
    } else if (articles.length > 0) {
      toast('Aucun nouvel article — fil à jour', 3000);
    }
  } catch(e) {
    document.getElementById('welcome-error').innerHTML =
      '<div class="error-box">❌ Erreur: ' + e.message + '</div>';
    show('screen-welcome');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderArticles(articles, newCount) {
  const eligible = articles.filter(a => a.eligible);
  const nonEligible = articles.filter(a => !a.eligible);
  const newEligible = eligible.filter(a => a.is_new).length;
  document.getElementById('article-count').textContent =
    eligible.length + (newEligible > 0 ? ` (+${newEligible} nouveaux)` : '');

  if (!articles.length) {
    document.getElementById('articles-list').innerHTML =
      '<div class="error-box">Aucun article reçu. Réessaie plus tard.</div>';
    return;
  }

  let html = '';

  if (!eligible.length) {
    html += '<div class="warn-box">Aucun article éligible aujourd&#39;hui selon les critères LinkedIn.</div>';
  } else {
    html += eligible.map(a => `
      <div class="article-card">
        <div class="art-num">Article ${a.num}${a.type_post ? ' · Type ' + escapeHtml(a.type_post) : ''}${a.is_new ? ' <span style="background:#e8fff5;color:#1a9e87;border-radius:6px;padding:1px 7px;font-size:10px;font-weight:700;margin-left:4px">NOUVEAU</span>' : ''}</div>
        <div class="art-title"><a href="${escapeHtml(a.url)}" target="_blank">${escapeHtml(a.titre)}</a></div>
        <div class="art-resume">${escapeHtml(a.resume)}</div>
        <div class="angles-label">Angles LinkedIn</div>
        <button class="angle-btn" onclick="draftPost(${a.num},1)">
          <span class="angle-num">1</span>${escapeHtml(a.angle1)}
        </button>
        <button class="angle-btn" onclick="draftPost(${a.num},2)">
          <span class="angle-num">2</span>${escapeHtml(a.angle2)}
        </button>
      </div>`).join('');
  }

  if (nonEligible.length) {
    html += `<div class="divider" style="margin:24px 0 18px"></div>
    <div class="section-h">
      <h2 style="font-size:16px;color:var(--gray)">Tous les articles consultés
        <span class="badge" style="background:rgba(107,122,141,0.12);color:var(--gray)">${nonEligible.length} non retenus</span>
      </h2>
      <p>Lus par l'agent, non retenus pour un post LinkedIn</p>
    </div>`;
    nonEligibleData = {};
    html += nonEligible.map(a => {
      nonEligibleData[a.num] = a;
      return `
      <div class="article-card" id="ne-card-${a.num}" style="opacity:0.7;border-left:3px solid var(--border)">
        <div class="art-num" style="color:var(--gray)">Article ${a.num} · Non retenu${a.is_new ? ' <span style="background:#e8fff5;color:#1a9e87;border-radius:6px;padding:1px 7px;font-size:10px;font-weight:700;margin-left:4px">NOUVEAU</span>' : ''}</div>
        <div class="art-title"><a href="${escapeHtml(a.url)}" target="_blank">${escapeHtml(a.titre)}</a></div>
        ${a.raison_exclusion ? `<div class="art-resume" style="font-style:italic;font-size:12px;margin-bottom:6px">↳ ${escapeHtml(a.raison_exclusion)}</div>` : ''}
        <div class="art-resume">${escapeHtml(a.resume)}</div>
        <div id="ne-angles-${a.num}">
          <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="generateAngles(${a.num}, this)">
            ✨ Générer des angles LinkedIn
          </button>
        </div>
      </div>`;
    }).join('');
  }

  document.getElementById('articles-list').innerHTML = html;
}

async function draftPost(num, angle) {
  document.getElementById('loading-title').textContent = 'Rédaction du post...';
  document.getElementById('loading-sub').textContent = 'Claude adapte le style à ton écriture';
  show('screen-loading');
  try {
    const r = await fetch('/api/draft-post', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({article_num:num, angle_num:angle})
    });
    const d = await r.json();
    if (!r.ok || d.error) { toast('Erreur: '+(d.error||'inconnue')); show('screen-articles'); return; }
    document.getElementById('post-textarea').value = d.post;
    currentPostText = d.post;
    document.getElementById('editor-ctx').textContent = 'Article '+num+' · Angle '+angle;
    updateCount();
    show('screen-editor');
  } catch(e) { toast('Erreur: '+e.message); show('screen-articles'); }
}

async function refinePost() {
  const fb = document.getElementById('refine-input').value.trim();
  if (!fb) { toast('Décris la modification souhaitée'); return; }
  const post = document.getElementById('post-textarea').value;
  document.getElementById('loading-title').textContent = 'Révision en cours...';
  document.getElementById('loading-sub').textContent = 'Claude applique tes modifications';
  show('screen-loading');
  try {
    const r = await fetch('/api/refine-post', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({feedback:fb, post})
    });
    const d = await r.json();
    document.getElementById('post-textarea').value = d.post;
    currentPostText = d.post;
    const ri = document.getElementById('refine-input');
    ri.value = ''; ri.style.height = '';
    updateCount();
    show('screen-editor');
    toast('✅ Post mis à jour');
  } catch(e) { toast('Erreur: '+e.message); show('screen-editor'); }
}

async function goToConcepts() {
  const post = document.getElementById('post-textarea').value;
  currentPostText = post;
  document.getElementById('loading-title').textContent = 'Génération des concepts...';
  document.getElementById('loading-sub').textContent = 'Claude imagine 3 visuels pour ton post';
  show('screen-loading');
  try {
    const r = await fetch('/api/generate-concepts', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({post})
    });
    const d = await r.json();
    renderConcepts(d.concepts||[]);
    show('screen-concepts');
  } catch(e) { toast('Erreur: '+e.message); show('screen-editor'); }
}

function renderConcepts(concepts) {
  selectedConcept = null;
  document.getElementById('concept-action').style.display = 'none';
  document.getElementById('concepts-list').innerHTML = concepts.map((c,i)=>`
    <div class="concept-card" id="c${i}" onclick="selectConcept(${i})">
      <div class="concept-num">Concept ${i+1}</div>
      <div class="concept-text">${escapeHtml(c)}</div>
    </div>`).join('');
}

function selectConcept(i) {
  document.querySelectorAll('.concept-card').forEach(c=>c.classList.remove('selected'));
  document.getElementById('c'+i).classList.add('selected');
  selectedConcept = i;
  document.getElementById('concept-action').style.display = 'block';
}

async function generateImage() {
  if (selectedConcept === null) return;
  document.getElementById('loading-title').textContent = "Génération de l'image...";
  document.getElementById('loading-sub').textContent = 'GPT Image 2 crée ton visuel (30–60 sec)';
  show('screen-loading');
  try {
    const r = await fetch('/api/generate-image', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({concept_idx:selectedConcept})
    });
    const d = await r.json();
    if (!r.ok || d.error) { toast('Erreur: '+(d.error||'inconnue')); show('screen-concepts'); return; }
    document.getElementById('result-img').src = '/api/view-image?t=' + Date.now();
    document.getElementById('result-filename').textContent = d.filename;
    document.getElementById('download-btn').setAttribute('download', d.filename);
    show('screen-image');
  } catch(e) { toast('Erreur: '+e.message); show('screen-concepts'); }
}

// ── Historique ────────────────────────────────────────────────────────────────

async function showHistory() {
  show('screen-history');
  document.getElementById('history-list').innerHTML = '<div style="text-align:center;padding:24px;color:var(--gray)">Chargement...</div>';
  try {
    const r = await fetch('/api/get-history');
    const d = await r.json();
    renderHistory(d.history || []);
  } catch(e) {
    document.getElementById('history-list').innerHTML = '<div class="error-box">Erreur de chargement</div>';
  }
}

function renderHistory(history) {
  if (!history.length) {
    document.getElementById('history-list').innerHTML = `
      <div class="empty-state">
        <div class="icon">📭</div>
        <p>Aucun post dans l'historique.<br>Les posts sont sauvegardés automatiquement lors de la génération d'image ou de l'envoi à Buffer.</p>
      </div>`;
    return;
  }

  historyData = {};
  document.getElementById('history-list').innerHTML = history.map((entry, idx) => {
    const date = entry.date ? entry.date.replace('T', ' à ').slice(0, 16) : '';
    const full = entry.post || '';
    historyData[idx] = full;
    const preview = full.slice(0, 200);
    const hasMore = full.length > 200;
    const imageTag = entry.image ? `<span class="hist-image-tag">🖼️ ${escapeHtml(entry.image)}</span>` : '';
    return `
      <div class="history-card">
        <div class="hist-meta">
          <span>📅 ${escapeHtml(date)}</span>
          ${imageTag}
        </div>
        <div class="hist-title">
          ${entry.url
            ? `<a href="${escapeHtml(entry.url)}" target="_blank">${escapeHtml(entry.titre || 'Sans titre')}</a>`
            : escapeHtml(entry.titre || 'Sans titre')}
        </div>
        <div class="hist-preview" id="hist-prev-${idx}">${escapeHtml(preview)}${hasMore ? '...' : ''}</div>
        ${hasMore ? `<button class="hist-toggle" onclick="toggleHistEntry(${idx})">▼ Voir tout le post</button>` : ''}
      </div>`;
  }).join('');
}

function toggleHistEntry(idx) {
  const el = document.getElementById('hist-prev-'+idx);
  const btn = el.nextElementSibling;
  const full = historyData[idx] || '';
  if (btn && btn.textContent.startsWith('▼')) {
    el.textContent = full;
    btn.textContent = '▲ Réduire';
  } else {
    el.textContent = full.slice(0, 200) + '...';
    if (btn) btn.textContent = '▼ Voir tout le post';
  }
}

// ── Angles pour articles non-retenus ─────────────────────────────────────────

async function generateAngles(num, btn) {
  const article = nonEligibleData[num];
  if (!article) return;
  btn.disabled = true;
  btn.textContent = 'Génération des angles...';
  try {
    const r = await fetch('/api/generate-angles', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({article})
    });
    const d = await r.json();
    if (!r.ok || d.error) {
      toast('Erreur: ' + (d.error || 'inconnue'), 4000);
      btn.disabled = false; btn.textContent = '✨ Générer des angles LinkedIn';
      return;
    }
    // Remplacer le bouton par les angles
    const card = document.getElementById('ne-card-' + num);
    if (card) card.style.opacity = '1';
    const container = document.getElementById('ne-angles-' + num);
    container.innerHTML = `
      <div class="angles-label" style="margin-top:10px">Angles LinkedIn</div>
      <button class="angle-btn" onclick="draftPost(${num},1)">
        <span class="angle-num">1</span>${escapeHtml(d.angle1)}
      </button>
      <button class="angle-btn" onclick="draftPost(${num},2)">
        <span class="angle-num">2</span>${escapeHtml(d.angle2)}
      </button>`;
  } catch(e) {
    toast('Erreur: ' + e.message, 4000);
    btn.disabled = false; btn.textContent = '✨ Générer des angles LinkedIn';
  }
}

// Lancer la vérification des clés au chargement
window.addEventListener('load', checkKeys);
</script>
</body>
</html>"""

if __name__ == "__main__":
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"

    print("\n" + "="*52)
    print("  🚀 RSS → LinkedIn Generator | extensio.ai")
    print("="*52)
    print(f"\n  💻 Desktop  →  http://localhost:5001")
    print(f"  📱 iPhone   →  http://{local_ip}:5001")
    print(f"\n  (iPhone: même WiFi requis)")
    print("\n  Ctrl+C pour arrêter\n" + "="*52 + "\n")

    missing = [k for k in ["ANTHROPIC_API_KEY","OPENAI_API_KEY"] if not os.environ.get(k)]
    if missing:
        print("⚠️  Clés manquantes:", ", ".join(missing))
        print("   Crée ~/Desktop/.env avec:")
        for k in missing:
            print(f"   {k}=ta-clé-ici")
        print()
    if not os.environ.get("BUFFER_ACCESS_TOKEN"):
        print("ℹ️  BUFFER_ACCESS_TOKEN non défini — bouton Buffer masqué")
        print()

    app.run(host="0.0.0.0", port=5001, debug=False)
