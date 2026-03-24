"""
Impactium Sales Intelligence — Web App
Serveur Python qui expose une interface web pour générer des playbooks personnalisés.
L'équipe commerciale tape un nom d'entreprise + contact → Claude fait la recherche → playbook HTML généré.
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import anthropic
import uvicorn

app = FastAPI(title="Impactium Sales Intelligence")

# --- Config ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
PLAYBOOKS_DIR = Path("playbooks")
PLAYBOOKS_DIR.mkdir(exist_ok=True)

# --- System prompt pour la génération de playbook ---
SYSTEM_PROMPT = """Tu es l'outil Sales Intelligence d'Impactium. Quand on te donne un nom d'entreprise et/ou un nom de contact, tu génères un playbook de vente 100% personnalisé.

## Workflow

1. **Recherche web** — Lance au minimum 4-6 recherches web pour trouver des données RÉELLES :
   - "[Entreprise] Maroc actualités 2025 2026" — croissance, projets, résultats
   - "[Entreprise] recrutement emploi effectifs" — volume RH, postes ouverts
   - "[Entreprise] chiffre affaires résultats financiers" — santé financière
   - "[Prénom Nom] [Entreprise] LinkedIn" — parcours, poste, formation
   - Secteur + enjeux RH au Maroc

2. **Analyse** — Extraire des CHIFFRES précis, des FAITS datés, des TENDANCES. Calculer un score ICP (0-100).

3. **Génération** — Produire un fichier HTML complet et autonome avec ces sections :
   - Hero (nom, poste, score ICP animé SVG, tags de signaux)
   - Chiffre-choc (UN chiffre massif calculé à partir des données réelles)
   - KPIs (5-6 métriques clés en grille)
   - Brief de préparation (3-4 paragraphes consultants, faits réels)
   - Approche & pitch (posture, vocabulaire, ice-breakers personnalisés, pain points, pitch 30 sec)
   - Structure d'appel (timeline 6 étapes avec phrases personnalisées)
   - Solutions recommandées (4 cartes Impactium avec arguments spécifiques)
   - Objections anticipées (4-5 accordéons avec réponses personnalisées)
   - Messages pré-rédigés (LinkedIn, Email, Relance J+3, Script vocal)
   - Plan d'action (séquence J0→J+30)

## Règles impératives

### Marque Impactium
- Fond dominant : bleu executive #001D62 (60-70%+ de la surface)
- Accent or #C8A44E pour les KPIs uniquement
- Polices : Montserrat (titres), Lato (corps), Space Mono (labels)
- Logo CDN : https://cdn.prod.website-files.com/67c72cd11c32072334fc9599/67c791c8ab02826c49593e65_Logo%20Impactium%205.png
- Grain CSS subtil, zéro coins arrondis, zéro fond blanc

### Confidentialité partenaires — JAMAIS mentionner :
- TalenToBe, MyPrint® → dire "Analyse Soft Skills & Alignement"
- MichelAI → dire "Recrutement IA & Matching"
- Kumullus → dire "Vidéo Learning Interactif"
- EdBuildIA → dire "Création E-learning par IA"
- 33Trucs → dire "Microlearning par Stories"

### Ton de voix
- Business/P&L, pas jargon RH. "Capital humain", pas "bien-être des collaborateurs"
- "Recommander un diagnostic", pas "proposer une démo"
- Concret : chiffres avant mots
- Interdit : bienveillance, épanouissement, holistique, QVT, win-win, synergies, révolutionnaire, disruptif

### Les 5 capacités Impactium
| Capacité | Impact |
|---|---|
| Recrutement IA & Matching | -80% temps, -65% coût/embauche |
| Analyse Soft Skills & Alignement | -66% erreurs casting, +12% productivité |
| Vidéo Learning Interactif | ×4 engagement, -70% temps onboarding |
| Création E-learning par IA | -90% coûts production, -45% abandon |
| Microlearning par Stories | 85% complétion, ×7 rétention 30j |

### Chiffres-clés
- +21% productivité, +18% revenue, -35% turnover
- 6-9 mois salaire = coût mauvais recrutement (SHRM)
- 80% formations jamais appliquées (McKinsey)
- 89% échecs recrutement = soft skills (Leadership IQ)

## Format de sortie
Retourne UNIQUEMENT le code HTML complet (de <!DOCTYPE html> à </html>), rien d'autre. Pas de markdown, pas d'explication, juste le HTML.

Utilise exactement ce CSS (variables, composants, nav sticky, score ring animé, timeline, accordéons, boutons copier, responsive, print) :

:root{--b:#001D62;--bd:#001248;--bl:#002A80;--bv:#0033CC;--g:#C8A44E;--gb:#E8C86E;--gd:rgba(200,164,78,.15);--gg:rgba(200,164,78,.08);--w:#fff;--w9:rgba(255,255,255,.92);--w7:rgba(255,255,255,.7);--w5:rgba(255,255,255,.5);--w3:rgba(255,255,255,.3);--w1:rgba(255,255,255,.1);--w05:rgba(255,255,255,.05);--red:#EF4444;--green:#22C55E;--orange:#F59E0B;--black:#000}

Inclure le JavaScript pour : copyText, IntersectionObserver sur les nav links, animation du score ring.
"""

# --- Personas pour enrichir le prompt ---
PERSONAS = {
    "dg": "DG/CEO — Angle: ROI, P&L, croissance. Chiffres sur SES données.",
    "drh": "DRH — Angle: Simplification, un seul interlocuteur, KPIs pour la direction.",
    "formation": "Responsable Formation — Angle: Engagement, complétion, rétention mesurable.",
    "manager": "Manager opérationnel — Angle: Rapidité, fiabilité, opérationnel.",
    "autre": "Profil à identifier via la recherche web."
}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Page d'accueil — formulaire de génération."""
    return Path("frontend.html").read_text(encoding="utf-8")


@app.get("/playbooks/{filename}", response_class=HTMLResponse)
async def get_playbook(filename: str):
    """Servir un playbook généré."""
    filepath = PLAYBOOKS_DIR / filename
    if filepath.exists():
        return HTMLResponse(filepath.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Playbook introuvable</h1>", status_code=404)


@app.get("/api/playbooks")
async def list_playbooks():
    """Lister les playbooks déjà générés."""
    playbooks = []
    for f in sorted(PLAYBOOKS_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        name = f.stem.replace("Playbook_", "").replace("_", " ")
        playbooks.append({
            "filename": f.name,
            "name": name,
            "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
            "size": f"{f.stat().st_size // 1024}KB"
        })
    return playbooks


@app.post("/api/generate")
async def generate_playbook(request: Request):
    """Générer un playbook via Claude API avec web search."""
    body = await request.json()
    entreprise = body.get("entreprise", "").strip()
    contact = body.get("contact", "").strip()
    persona = body.get("persona", "autre")
    notes = body.get("notes", "").strip()

    if not entreprise:
        return JSONResponse({"error": "Nom d'entreprise requis"}, status_code=400)

    api_key = body.get("api_key", "") or ANTHROPIC_API_KEY
    if not api_key:
        return JSONResponse({"error": "Clé API Anthropic requise"}, status_code=400)

    # Build user prompt
    user_prompt = f"Génère un playbook de vente complet pour :\n\n"
    user_prompt += f"**Entreprise :** {entreprise}\n"
    if contact:
        user_prompt += f"**Contact :** {contact}\n"
    if persona != "autre":
        user_prompt += f"**Persona :** {PERSONAS.get(persona, '')}\n"
    if notes:
        user_prompt += f"**Notes supplémentaires :** {notes}\n"
    user_prompt += f"\nDate du jour : {datetime.now().strftime('%d %B %Y')}\n"
    user_prompt += "\nFais tes recherches web, analyse les résultats, et génère le playbook HTML complet."

    client = anthropic.Anthropic(api_key=api_key)

    async def stream_response():
        """Stream la génération pour un feedback en temps réel."""
        try:
            # Step 1: signal start
            yield json.dumps({"type": "status", "message": "Recherche en cours..."}) + "\n"

            # Call Claude with web search via tool use
            response = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Collect full HTML from response
            html_content = ""
            search_queries = []

            for block in response.content:
                if block.type == "text":
                    html_content += block.text
                elif block.type == "tool_use" and block.name == "web_search":
                    search_queries.append(block.input.get("query", ""))

            # Handle multi-turn if needed (tool results)
            messages = [{"role": "user", "content": user_prompt}]
            current_response = response

            while current_response.stop_reason == "tool_use":
                # Build assistant message with all content blocks
                assistant_content = []
                tool_results = []

                for block in current_response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                        if block.name == "web_search":
                            search_queries.append(block.input.get("query", ""))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": tool_results})

                yield json.dumps({
                    "type": "status",
                    "message": f"Recherche : {search_queries[-1] if search_queries else '...'}"
                }) + "\n"

                current_response = client.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                    messages=messages,
                )

                for block in current_response.content:
                    if block.type == "text":
                        html_content += block.text

            # Clean up — extract just the HTML
            html_match = re.search(r'(<!DOCTYPE html>.*?</html>)', html_content, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(1)

            # Save playbook
            safe_entreprise = re.sub(r'[^a-zA-Z0-9]', '_', entreprise)
            safe_contact = re.sub(r'[^a-zA-Z0-9]', '_', contact) if contact else "General"
            filename = f"Playbook_{safe_entreprise}_{safe_contact}.html"
            filepath = PLAYBOOKS_DIR / filename
            filepath.write_text(html_content, encoding="utf-8")

            yield json.dumps({
                "type": "complete",
                "filename": filename,
                "searches": search_queries,
                "html": html_content
            }) + "\n"

        except anthropic.APIError as e:
            yield json.dumps({"type": "error", "message": f"Erreur API: {str(e)}"}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Erreur: {str(e)}"}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
