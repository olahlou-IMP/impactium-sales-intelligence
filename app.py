"""
Impactium Sales Intelligence — Web App v2
Mode Light / Complet + Historique partagé persistant (JSON).
"""

import os
import json
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import anthropic
import uvicorn

app = FastAPI(title="Impactium Sales Intelligence")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
PLAYBOOKS_DIR = Path("playbooks")
PLAYBOOKS_DIR.mkdir(exist_ok=True)
HISTORY_FILE = Path("playbooks/history.json")
MAX_RETRIES = 3
RETRY_DELAY = 65

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(entries):
    HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

def add_to_history(entry):
    entries = load_history()
    entries.insert(0, entry)
    if len(entries) > 100:
        entries = entries[:100]
    save_history(entries)

PROMPT_LIGHT = """Outil Sales Intelligence Impactium. Génère un playbook de vente HTML CONCIS.

WORKFLOW: 1) Recherche web (2-3 queries max) 2) Analyse rapide 3) HTML compact

SECTIONS: Hero(nom,poste,score ICP) | KPIs(4 max) | Brief préparation(2§) | Pitch(ice-breaker+pitch 30s) | Solutions(3 cartes Impactium) | Messages(Email+LinkedIn) | Next steps

MARQUE: fond #001D62(60-70%), or #C8A44E(KPIs), Montserrat/Lato/Space Mono, logo:https://cdn.prod.website-files.com/67c72cd11c32072334fc9599/67c791c8ab02826c49593e65_Logo%20Impactium%205.png, grain CSS, zéro coins arrondis, zéro fond blanc

CONFIDENTIEL: TalenToBe/MyPrint→"Analyse Soft Skills & Alignement", MichelAI→"Recrutement IA & Matching", Kumullus→"Vidéo Learning Interactif", EdBuildIA→"Création E-learning par IA", 33Trucs→"Microlearning par Stories"

TON: Business/P&L, chiffres avant mots. Interdit: bienveillance,épanouissement,holistique,QVT,win-win,synergies

5 CAPACITÉS: Recrutement IA(-80%temps) | Soft Skills(-66%erreurs) | Vidéo Learning(×4 engagement) | E-learning IA(-90%coûts) | Microlearning(85%complétion)

CSS: :root{--b:#001D62;--bd:#001248;--bl:#002A80;--bv:#0033CC;--g:#C8A44E;--gb:#E8C86E;--gd:rgba(200,164,78,.15);--gg:rgba(200,164,78,.08);--w:#fff;--w9:rgba(255,255,255,.92);--w7:rgba(255,255,255,.7);--w5:rgba(255,255,255,.5);--w3:rgba(255,255,255,.3);--w1:rgba(255,255,255,.1);--w05:rgba(255,255,255,.05);--red:#EF4444;--green:#22C55E;--orange:#F59E0B;--black:#000}

OUTPUT: UNIQUEMENT le HTML complet (<!DOCTYPE html> à </html>). Rien d'autre."""

PROMPT_COMPLETE = """Outil Sales Intelligence Impactium. Génère un playbook de vente HTML COMPLET et détaillé.

WORKFLOW: 1) Recherche web (3-4 queries: entreprise+Maroc+actualités, entreprise+RH+recrutement, contact+LinkedIn, secteur+enjeux) 2) Analyse: chiffres, faits datés, score ICP 0-100 3) HTML complet autonome

SECTIONS HTML: Hero(nom,poste,score ICP SVG animé,signaux) | Chiffre-choc | KPIs(5-6 grille) | Brief préparation(3-4§ faits réels) | Approche&pitch(ice-breakers,pain points,pitch 30s) | Structure appel(timeline 6 étapes) | Solutions(4 cartes Impactium) | Objections(4-5 accordéons) | Messages(LinkedIn,Email,Relance J+3,Script vocal) | Plan action(J0→J+30)

MARQUE: fond #001D62(60-70%), or #C8A44E(KPIs), Montserrat/Lato/Space Mono, logo:https://cdn.prod.website-files.com/67c72cd11c32072334fc9599/67c791c8ab02826c49593e65_Logo%20Impactium%205.png, grain CSS, zéro coins arrondis, zéro fond blanc

CONFIDENTIALITÉ: TalenToBe/MyPrint→"Analyse Soft Skills & Alignement", MichelAI→"Recrutement IA & Matching", Kumullus→"Vidéo Learning Interactif", EdBuildIA→"Création E-learning par IA", 33Trucs→"Microlearning par Stories"

TON: Business/P&L, "capital humain" pas "bien-être". Chiffres avant mots. Interdit: bienveillance,épanouissement,holistique,QVT,win-win,synergies,révolutionnaire,disruptif

5 CAPACITÉS: Recrutement IA(-80%temps,-65%coût) | Soft Skills(-66%erreurs,+12%prod) | Vidéo Learning(×4 engagement,-70%onboarding) | E-learning IA(-90%coûts,-45%abandon) | Microlearning Stories(85%complétion,×7 rétention)

STATS: +21%prod,+18%revenue,-35%turnover | 6-9 mois salaire=mauvais recrutement(SHRM) | 80%formations jamais appliquées(McKinsey) | 89%échecs=soft skills(Leadership IQ)

CSS: :root{--b:#001D62;--bd:#001248;--bl:#002A80;--bv:#0033CC;--g:#C8A44E;--gb:#E8C86E;--gd:rgba(200,164,78,.15);--gg:rgba(200,164,78,.08);--w:#fff;--w9:rgba(255,255,255,.92);--w7:rgba(255,255,255,.7);--w5:rgba(255,255,255,.5);--w3:rgba(255,255,255,.3);--w1:rgba(255,255,255,.1);--w05:rgba(255,255,255,.05);--red:#EF4444;--green:#22C55E;--orange:#F59E0B;--black:#000}
JS: copyText, IntersectionObserver nav, score ring animation

OUTPUT: UNIQUEMENT le HTML complet (<!DOCTYPE html> à </html>). Rien d'autre."""

PERSONAS = {
    "dg": "DG/CEO — ROI, P&L, croissance",
    "drh": "DRH — Simplification, KPIs direction",
    "formation": "Resp. Formation — Engagement, complétion, rétention",
    "manager": "Manager — Rapidité, fiabilité, opérationnel",
    "autre": "Profil à identifier via recherche web"
}


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("frontend.html").read_text(encoding="utf-8")


@app.get("/playbooks/{filename}", response_class=HTMLResponse)
async def get_playbook(filename: str):
    filepath = PLAYBOOKS_DIR / filename
    if filepath.exists():
        return HTMLResponse(filepath.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Playbook introuvable</h1>", status_code=404)


@app.get("/api/playbooks")
async def list_playbooks():
    return load_history()


@app.post("/api/generate")
async def generate_playbook(request: Request):
    body = await request.json()
    entreprise = body.get("entreprise", "").strip()
    contact = body.get("contact", "").strip()
    persona = body.get("persona", "autre")
    notes = body.get("notes", "").strip()
    mode = body.get("mode", "light")
    user_name = body.get("user_name", "Anonyme").strip() or "Anonyme"

    if not entreprise:
        return JSONResponse({"error": "Nom d'entreprise requis"}, status_code=400)

    api_key = body.get("api_key", "") or ANTHROPIC_API_KEY
    if not api_key:
        return JSONResponse({"error": "Clé API Anthropic requise"}, status_code=400)

    if mode == "light":
        system_prompt = PROMPT_LIGHT
        max_tokens = 8000
        max_uses = 2
    else:
        system_prompt = PROMPT_COMPLETE
        max_tokens = 12000
        max_uses = 3

    parts = [f"Playbook pour: {entreprise}"]
    if contact:
        parts.append(f"Contact: {contact}")
    if persona != "autre":
        parts.append(f"Persona: {PERSONAS.get(persona, '')}")
    if notes:
        parts.append(f"Notes: {notes}")
    parts.append(f"Date: {datetime.now().strftime('%d %B %Y')}")
    parts.append("Fais tes recherches web puis génère le playbook HTML complet.")
    user_prompt = "\n".join(parts)

    client = anthropic.Anthropic(api_key=api_key)

    async def stream_response():
        try:
            yield json.dumps({"type": "status", "message": f"Mode {'rapide' if mode == 'light' else 'complet'} — Lancement..."}) + "\n"

            api_params = dict(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
            )

            response = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.messages.create(
                        **api_params,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt < MAX_RETRIES - 1:
                        wait = RETRY_DELAY * (attempt + 1)
                        yield json.dumps({"type": "status", "message": f"Rate limit — retry dans {wait}s..."}) + "\n"
                        time.sleep(wait)
                    else:
                        yield json.dumps({"type": "error", "message": "Rate limit dépassé. Attends 2 min."}) + "\n"
                        return

            if not response:
                yield json.dumps({"type": "error", "message": "Pas de réponse."}) + "\n"
                return

            html_content = ""
            search_queries = []

            for block in response.content:
                if block.type == "text":
                    html_content += block.text
                elif block.type == "tool_use":
                    q = block.input.get("query", "")
                    if q:
                        search_queries.append(q)

            messages = [{"role": "user", "content": user_prompt}]
            current_response = response
            turn_count = 0
            max_turns = 6 if mode == "complete" else 3

            while current_response.stop_reason == "tool_use" and turn_count < max_turns:
                turn_count += 1
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
                        q = block.input.get("query", "")
                        if q:
                            search_queries.append(q)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search completed."
                        })
                    elif block.type == "server_tool_use":
                        assistant_content.append({
                            "type": "server_tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                        q = block.input.get("query", "")
                        if q:
                            search_queries.append(q)
                    elif block.type == "web_search_tool_result":
                        assistant_content.append(block)

                messages.append({"role": "assistant", "content": assistant_content})
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

                yield json.dumps({
                    "type": "status",
                    "message": f"Recherche {turn_count}: {search_queries[-1] if search_queries else '...'}"
                }) + "\n"

                for attempt in range(MAX_RETRIES):
                    try:
                        current_response = client.messages.create(
                            **api_params,
                            messages=messages,
                        )
                        break
                    except anthropic.RateLimitError:
                        if attempt < MAX_RETRIES - 1:
                            wait = RETRY_DELAY * (attempt + 1)
                            yield json.dumps({"type": "status", "message": f"Rate limit — retry dans {wait}s..."}) + "\n"
                            time.sleep(wait)
                        else:
                            yield json.dumps({"type": "error", "message": "Rate limit dépassé. Attends 2 min."}) + "\n"
                            return

                for block in current_response.content:
                    if block.type == "text":
                        html_content += block.text

            yield json.dumps({"type": "status", "message": "Génération du playbook HTML..."}) + "\n"

            html_match = re.search(r'(<!DOCTYPE html>.*?</html>)', html_content, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(1)

            if not html_content.strip() or len(html_content) < 100:
                yield json.dumps({"type": "error", "message": "Playbook vide. Réessaie."}) + "\n"
                return

            safe_entreprise = re.sub(r'[^a-zA-Z0-9]', '_', entreprise)
            safe_contact = re.sub(r'[^a-zA-Z0-9]', '_', contact) if contact else "General"
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"Playbook_{safe_entreprise}_{safe_contact}_{ts}.html"
            filepath = PLAYBOOKS_DIR / filename
            filepath.write_text(html_content, encoding="utf-8")

            entry = {
                "filename": filename,
                "entreprise": entreprise,
                "contact": contact or "—",
                "persona": persona,
                "mode": mode,
                "user": user_name,
                "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "searches": search_queries,
                "size": f"{len(html_content) // 1024}KB"
            }
            add_to_history(entry)

            yield json.dumps({
                "type": "complete",
                "filename": filename,
                "searches": search_queries,
                "html": html_content
            }) + "\n"

        except anthropic.AuthenticationError:
            yield json.dumps({"type": "error", "message": "Clé API invalide. Vérifie sur console.anthropic.com"}) + "\n"
        except anthropic.APIError as e:
            yield json.dumps({"type": "error", "message": f"Erreur API: {str(e)}"}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Erreur: {str(e)}"}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
