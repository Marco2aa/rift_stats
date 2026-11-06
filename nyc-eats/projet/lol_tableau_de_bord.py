"""Rift Stats : tableau de bord League of Legends (Streamlit). Il ne lit que l'API, jamais les bases.

Lancer, après l'API (depuis /projet, pour que le thème .streamlit/config.toml soit pris en compte) :
    docker exec -it -w /projet python streamlit run lol_tableau_de_bord.py --server.address 0.0.0.0 --server.port 8501
Puis ouvrir http://localhost:8501

Trois états, signalés par le badge en haut de la page :
    En direct        l'API répond et des parties ont été collectées (collecte_riot.py)
    API connectée    l'API répond mais aucune partie n'est encore en base (champions et similarité réels)
    Démonstration    l'API ne répond pas : données INVENTÉES, pour voir l'interface
"""
import html
import random
import unicodedata
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import requests
import streamlit as st

API = "http://localhost:8000"   # l'API tourne dans le même conteneur
ROLES = {"(tous)": None, "Haut": "TOP", "Jungle": "JUNGLE", "Milieu": "MIDDLE",
         "Bas": "BOTTOM", "Soutien": "UTILITY"}
NOM_ROLE = {v: k for k, v in ROLES.items() if v}
OR, OR_CLAIR, BLEU, GRIS, TEXTE = "#C8AA6E", "#F0E6D2", "#0AC8B9", "#8C93A3", "#E8E2D0"


# ---------------------------------------------------------------- accès à l'API

def appeler(chemin, methode="GET", delai=10, **parametres):
    reponse = requests.request(methode, API + chemin, params=parametres, timeout=delai)
    reponse.raise_for_status()
    return reponse.json()


def sans_accents(texte):
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower().replace("'", "").replace(" ", "")


FILES = {420: "Classée solo", 440: "Classée flex", 400: "Normale", 430: "Normale", 490: "Partie rapide",
         450: "ARAM", 1700: "Arena", 900: "URF", 1900: "URF"}
SERVEURS = {"EUW": "euw1", "EUNE": "eun1", "NA": "na1", "KR": "kr", "BR": "br1", "TR": "tr1", "JP": "jp1", "OCE": "oc1"}


@st.cache_data(ttl=86400, show_spinner=False)
def version_data_dragon():
    """Dernière version des images (Data Dragon, sans clé)."""
    try:
        return requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=3).json()[0]
    except Exception:
        return "16.22.1"


def icone(champion_id):
    return f"https://ddragon.leagueoflegends.com/cdn/{version_data_dragon()}/img/champion/{champion_id}.png"


def icone_objet(objet_id):
    return f"https://ddragon.leagueoflegends.com/cdn/{version_data_dragon()}/img/item/{objet_id}.png"


# ---------------------------------------------------------------- données de démonstration (inventées)

DEMO_CHAMPIONS = [
    ("Ahri", "Ahri", "MIDDLE", "Mage"), ("Jinx", "Jinx", "BOTTOM", "Tireur"),
    ("LeeSin", "Lee Sin", "JUNGLE", "Combattant"), ("Thresh", "Thresh", "UTILITY", "Soutien"),
    ("Darius", "Darius", "TOP", "Combattant"), ("Garen", "Garen", "TOP", "Combattant"),
    ("Yasuo", "Yasuo", "MIDDLE", "Combattant"), ("Ezreal", "Ezreal", "BOTTOM", "Tireur"),
    ("Lux", "Lux", "UTILITY", "Mage"), ("Vi", "Vi", "JUNGLE", "Combattant"),
    ("Kaisa", "Kai'Sa", "BOTTOM", "Tireur"), ("MissFortune", "Miss Fortune", "BOTTOM", "Tireur"),
    ("Ornn", "Ornn", "TOP", "Tank"), ("Aatrox", "Aatrox", "TOP", "Combattant"),
    ("Sylas", "Sylas", "MIDDLE", "Mage"), ("Viego", "Viego", "JUNGLE", "Assassin"),
    ("Nautilus", "Nautilus", "UTILITY", "Tank"), ("Leona", "Leona", "UTILITY", "Tank"),
    ("Caitlyn", "Caitlyn", "BOTTOM", "Tireur"), ("Graves", "Graves", "JUNGLE", "Tireur"),
    ("Orianna", "Orianna", "MIDDLE", "Mage"), ("Camille", "Camille", "TOP", "Combattant"),
    ("Lulu", "Lulu", "UTILITY", "Soutien"), ("Jhin", "Jhin", "BOTTOM", "Tireur"),
    ("Khazix", "Kha'Zix", "JUNGLE", "Assassin"), ("Akali", "Akali", "MIDDLE", "Assassin"),
    ("Sett", "Sett", "TOP", "Combattant"), ("Vayne", "Vayne", "BOTTOM", "Tireur"),
    ("Morgana", "Morgana", "UTILITY", "Mage"), ("Elise", "Elise", "JUNGLE", "Mage"),
]
DEMO_PSEUDOS = ["Brumelame", "NoctisFaille", "Pixel Drake", "Lumen Ward", "Hextouch",
                "Volt Baron", "Sablemarin", "Kraken Doux", "Orage Bleu", "Minuit Gank"]


@st.cache_data
def demo():
    alea = random.Random(2026)
    stats = []
    for champion_id, nom, role, classe in DEMO_CHAMPIONS:
        parties = alea.randint(35, 420)
        victoires = round(parties * alea.uniform(0.45, 0.555))
        stats.append({"champion_id": champion_id, "nom": nom, "role": role, "classe": classe,
                      "parties": parties, "victoires": victoires,
                      "taux_victoire": round(100 * victoires / parties, 1), "kda": round(alea.uniform(1.8, 4.2), 2)})
    total = sum(c["parties"] for c in stats) // 10   # 10 joueurs par partie
    for c in stats:
        c["taux_selection"] = round(100 * c["parties"] / total, 1)
    lp = sorted((alea.randint(900, 1900) for _ in DEMO_PSEUDOS), reverse=True)
    classement = []
    for rang, (pseudo, points) in enumerate(zip(DEMO_PSEUDOS, lp), start=1):
        victoires = alea.randint(140, 320)
        classement.append({"rang": rang, "puuid": None, "pseudo": f"{pseudo}#EUW", "lp": points,
                           "victoires": victoires, "defaites": victoires - alea.randint(20, 90)})
    catalogue = [{"champion_id": c["champion_id"], "nom": c["nom"], "titre": "", "classe": c["classe"]} for c in stats]
    sante = {"parties": total, "redis": True, "champions": len(stats), "joueurs": len(classement), "patch": "démo"}
    return stats, classement, sante, catalogue


def charger(role, min_parties):
    """Renvoie (stats, classement, sante, catalogue, etat, erreur)."""
    try:
        sante = appeler("/lol/sante")
    except Exception:
        stats, classement, sante, catalogue = demo()
        stats = [c for c in stats if c["parties"] >= min_parties and (role is None or c["role"] == role)]
        return stats, classement, sante, catalogue, "demo", None
    try:
        catalogue = appeler("/lol/champions")
        stats = appeler("/lol/champions/stats", role=role, min_parties=min_parties)
        classement = appeler("/lol/classement", nombre=10)
        return stats, classement, sante, catalogue, ("direct" if sante["parties"] else "vide"), None
    except Exception as erreur:
        return [], [], sante, [], "erreur", str(erreur)


def similaires(champion, catalogue, etat):
    if etat != "demo":
        try:
            return appeler(f"/lol/champions/{champion['champion_id']}/similaires")
        except Exception:
            return []
    return [{"champion_id": c["champion_id"], "nom": c["nom"], "distance": None} for c in catalogue
            if c["classe"] == champion["classe"] and c["champion_id"] != champion["champion_id"]][:5]


# ---------------------------------------------------------------- style et animations

st.set_page_config(page_title="Rift Stats", page_icon="⚔️", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;800&family=Inter:wght@400;500;600&display=swap');
:root { --or:#C8AA6E; --or-clair:#F0E6D2; --bleu:#0AC8B9; --fond:#0A1428; --carte:#111E33; --texte:#E8E2D0; --gris:#8C93A3;
        --rouge:#FF8A80; --ambre:#F5C26B; --ease:cubic-bezier(.2,.8,.2,1); }
@property --n { syntax:'<integer>'; initial-value:0; inherits:false; }

/* fond : deux halos qui dérivent lentement */
.stApp { background: radial-gradient(900px 500px at 10% 0%, #1E2D5088, transparent 60%),
                     radial-gradient(700px 500px at 90% 30%, #0AC8B914, transparent 60%), var(--fond);
         background-size: 140% 140%; animation: derive 28s ease-in-out infinite alternate; }
@keyframes derive { to { background-position: 100% 60%, 0% 40%, 0 0; } }
html, body, .stMarkdown, p, label, input { font-family:'Inter', system-ui, sans-serif; }
h1, h2, h3, h4 { font-family:'Cinzel', Georgia, serif !important; color:var(--or-clair) !important; letter-spacing:.04em; }
section[data-testid="stSidebar"] { background:linear-gradient(180deg,#0F1B30,#070E1A); border-right:1px solid #C8AA6E33; }

/* apparitions */
@keyframes monter { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:none; } }
@keyframes glisser { from { opacity:0; transform:translateX(-14px); } to { opacity:1; transform:none; } }
@keyframes apparaitre { from { opacity:0; } to { opacity:1; } }
.stTabs [role="tabpanel"] { animation: apparaitre .45s var(--ease) both; }
.stTabs [data-baseweb="tab"] { font-family:'Cinzel', serif; letter-spacing:.05em; transition: color .2s; }
.stTabs [data-baseweb="tab"]:hover { color:var(--or-clair); }

/* bandeau : titre au reflet doré qui défile, balayage lumineux */
.bandeau { position:relative; overflow:hidden; border:1px solid #C8AA6E55; border-radius:6px; padding:24px 28px; margin-bottom:18px;
           background:linear-gradient(120deg,#0A1428EE,#12233FEE); animation: monter .6s var(--ease) both; }
.bandeau::after { content:""; position:absolute; inset:0; pointer-events:none;
                  background:linear-gradient(105deg, transparent 40%, #F0E6D214 50%, transparent 60%);
                  transform:translateX(-100%); animation: balayer 6s ease-in-out 1s infinite; }
@keyframes balayer { 0%,60% { transform:translateX(-100%); } 100% { transform:translateX(100%); } }
.bandeau h1 { margin:0; font-size:2.6rem; background:linear-gradient(90deg,var(--or),var(--or-clair),var(--or)); background-size:200% auto;
              -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; animation: reflet 5s linear infinite; }
@keyframes reflet { to { background-position:200% center; } }
.bandeau p { margin:4px 0 0; color:var(--gris); }

/* badge d'état avec point qui pulse */
.badge { display:inline-flex; align-items:center; gap:8px; padding:4px 12px; border-radius:99px; font-size:.8rem; font-weight:600; margin-top:12px; }
.badge i { width:8px; height:8px; border-radius:50%; background:currentColor; animation: pulse 1.8s ease-out infinite; }
@keyframes pulse { 0% { box-shadow:0 0 0 0 currentColor; } 100% { box-shadow:0 0 0 8px transparent; } }
.badge.direct { color:var(--bleu); background:#0AC8B91A; border:1px solid #0AC8B966; }
.badge.vide { color:var(--ambre); background:#F5C26B1A; border:1px solid #F5C26B66; }
.badge.demo, .badge.erreur { color:var(--rouge); background:#E840401A; border:1px solid #E8404066; }

/* tuiles des chiffres clés, avec compteur animé (CSS seul) */
.tuile { background:var(--carte); border:1px solid #C8AA6E33; border-top:2px solid var(--or); border-radius:6px; padding:14px 18px; margin-bottom:8px;
         animation: monter .6s var(--ease) both; animation-delay:calc(var(--i) * 90ms + 150ms); transition: transform .25s var(--ease), box-shadow .25s; }
.tuile:hover { transform:translateY(-4px); box-shadow:0 10px 30px #00000066, 0 0 0 1px #C8AA6E66; }
.tuile .etiquette { color:var(--gris); font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }
.tuile .valeur { font-family:'Cinzel', serif; font-size:1.9rem; color:var(--or-clair); font-variant-numeric:tabular-nums; }
.tuile .detail { color:var(--gris); font-size:.8rem; }
.compteur { --n:var(--cible); counter-reset:n var(--n); animation: compter 1.6s var(--ease) both; animation-delay:calc(var(--i) * 90ms + 200ms); }
.compteur::after { content:counter(n); }
@keyframes compter { from { --n:0; } }

/* top 10 : barres qui se remplissent l'une après l'autre */
.top { display:flex; flex-direction:column; gap:6px; }
.ligne { display:grid; grid-template-columns:26px 40px minmax(110px,1fr) minmax(120px,2.2fr) 64px; align-items:center; gap:12px;
         padding:6px 10px; border-radius:6px; animation: monter .5s var(--ease) both; animation-delay:calc(var(--i) * 70ms);
         transition: background .2s, transform .2s var(--ease); }
.ligne:hover { background:#C8AA6E12; transform:translateX(4px); }
.ligne .pos { font-family:'Cinzel', serif; color:var(--or); text-align:right; }
.ligne img { width:40px; height:40px; border-radius:50%; border:2px solid #C8AA6E88; transition: transform .3s var(--ease), border-color .3s; }
.ligne:hover img { transform:scale(1.12) rotate(-4deg); border-color:var(--or); }
.ligne .nom { font-weight:600; color:var(--or-clair); line-height:1.15; }
.ligne .nom small { display:block; font-weight:400; color:var(--gris); font-size:.75rem; }
.piste { position:relative; height:10px; border-radius:99px; background:#ffffff0d; overflow:hidden; }
.barre { position:absolute; inset:0 auto 0 0; width:var(--w); border-radius:99px;
         background:linear-gradient(90deg,#785A28,var(--or),var(--or-clair)); box-shadow:0 0 12px #C8AA6E66;
         animation: remplir 1.1s var(--ease) both; animation-delay:calc(var(--i) * 70ms + 200ms); }
@keyframes remplir { from { width:0; } }
.repere { position:absolute; left:50%; top:-2px; bottom:-2px; border-left:2px dashed var(--bleu); opacity:.7; }
.ligne .val { font-variant-numeric:tabular-nums; color:var(--or-clair); text-align:right; font-weight:600; }
.legende { color:var(--gris); font-size:.78rem; margin:6px 0 18px; }
@media (max-width: 640px) { .ligne { grid-template-columns:22px 34px 1fr 56px; } .piste { display:none; } }

/* podium */
.podium { display:flex; gap:14px; flex-wrap:wrap; align-items:flex-end; margin-bottom:16px; }
.marche { flex:1 1 180px; background:var(--carte); border:1px solid #C8AA6E33; border-radius:6px; padding:18px 16px; text-align:center;
          animation: monter .6s var(--ease) both; animation-delay:calc(var(--i) * 120ms); transition: transform .25s var(--ease); }
.marche:hover { transform:translateY(-6px); }
.marche.p1 { order:2; padding-top:28px; border-color:var(--or); animation: monter .6s var(--ease) both, lueur 2.6s ease-in-out .8s infinite; }
.marche.p2 { order:1; } .marche.p3 { order:3; }
@keyframes lueur { 50% { box-shadow:0 0 34px #C8AA6E55; } }
.marche .rang { font-family:'Cinzel', serif; font-size:1.7rem; color:var(--or); }
.marche .pseudo { font-weight:600; color:var(--or-clair); margin:4px 0; overflow-wrap:anywhere; }
.marche .lp { color:var(--bleu); font-variant-numeric:tabular-nums; }

/* fiche champion / profil joueur : anneau doré qui tourne autour de l'icône */
.fiche { display:flex; gap:22px; align-items:center; flex-wrap:wrap; margin-bottom:14px; animation: monter .5s var(--ease) both; }
.anneau { position:relative; width:112px; height:112px; border-radius:50%; display:grid; place-items:center; flex:none; }
.anneau::before { content:""; position:absolute; inset:0; border-radius:50%;
                  background:conic-gradient(var(--or), transparent 30%, var(--bleu) 50%, transparent 70%, var(--or));
                  animation: tourner 4s linear infinite; }
@keyframes tourner { to { transform:rotate(360deg); } }
.anneau img { position:relative; width:100px; height:100px; border-radius:50%; border:3px solid var(--fond); }
.fiche h3 { margin:0 !important; overflow-wrap:anywhere; }
.fiche .titre { color:var(--gris); margin:2px 0 0; }
.rang-badge { display:inline-block; margin-top:6px; padding:3px 10px; border-radius:99px; font-size:.8rem; font-weight:600;
              color:var(--or); border:1px solid #C8AA6E66; background:#C8AA6E14; }

/* cartes (champions proches, favoris, objets) */
.cartes { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:8px; }
.carte { width:118px; text-align:center; background:var(--carte); border:1px solid #C8AA6E33; border-radius:6px; padding:12px 8px;
         animation: monter .5s var(--ease) both; animation-delay:calc(var(--i) * 80ms + 150ms); transition: transform .25s var(--ease), border-color .25s; }
.carte:hover { transform:translateY(-5px) scale(1.03); border-color:var(--or); }
.carte img { width:56px; height:56px; border-radius:50%; }
.carte.objet img { border-radius:6px; border:1px solid #C8AA6E66; }
.carte div { color:var(--or-clair); font-weight:600; font-size:.82rem; margin-top:6px; line-height:1.2; }
.carte small { color:var(--gris); font-size:.72rem; display:block; margin-top:2px; }
.carte small b { color:var(--bleu); font-weight:600; }

/* matchups */
.duel { display:grid; grid-template-columns:34px 1fr auto; gap:10px; align-items:center; padding:6px 10px; border-radius:6px;
        border-left:3px solid var(--c); background:#ffffff06; margin-bottom:6px;
        animation: glisser .45s var(--ease) both; animation-delay:calc(var(--i) * 70ms); transition: background .2s; }
.duel:hover { background:#ffffff10; }
.duel img { width:34px; height:34px; border-radius:50%; }
.duel span { color:var(--or-clair); font-weight:600; }
.duel small { color:var(--gris); font-weight:400; margin-left:6px; }
.duel b { color:var(--c); font-variant-numeric:tabular-nums; }

/* historique des parties */
.partie { display:grid; grid-template-columns:42px minmax(90px,1fr) 90px 110px 90px; gap:12px; align-items:center;
          padding:8px 12px; border-radius:6px; margin-bottom:6px; border-left:3px solid var(--c);
          background:linear-gradient(90deg, var(--fondc), transparent 70%);
          animation: glisser .45s var(--ease) both; animation-delay:calc(var(--i) * 45ms); transition: transform .2s var(--ease); }
.partie:hover { transform:translateX(4px); }
.partie.v { --c:var(--bleu); --fondc:#0AC8B91A; } .partie.d { --c:var(--rouge); --fondc:#E840401A; }
.partie img { width:42px; height:42px; border-radius:50%; }
.partie .nom { color:var(--or-clair); font-weight:600; line-height:1.15; }
.partie .nom small { display:block; color:var(--gris); font-weight:400; font-size:.75rem; }
.partie .res { color:var(--c); font-weight:600; }
.partie .kda { font-variant-numeric:tabular-nums; color:var(--texte); }
.partie .kda small, .partie .quand { color:var(--gris); font-size:.75rem; }
@media (max-width: 640px) { .partie { grid-template-columns:36px 1fr 70px; } .partie .kda, .partie .quand { display:none; } }

/* infra : les nœuds du replica set */
.noeuds { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:16px; }
.noeud { flex:1 1 180px; background:var(--carte); border:1px solid #C8AA6E33; border-radius:6px; padding:16px; color:var(--c);
         animation: monter .5s var(--ease) both; animation-delay:calc(var(--i) * 100ms); }
.noeud.PRIMARY { --c:var(--or); border-color:var(--or); } .noeud.SECONDARY { --c:var(--bleu); } .noeud.panne { --c:var(--rouge); border-color:#E8404088; }
.noeud .etat { display:flex; align-items:center; gap:8px; font-weight:600; font-size:.85rem; letter-spacing:.06em; }
.noeud .etat i { width:9px; height:9px; border-radius:50%; background:currentColor; animation: pulse 1.8s ease-out infinite; }
.noeud .nom { font-family:'Cinzel', serif; color:var(--or-clair); font-size:1.2rem; margin-top:6px; }

/* barre de recherche globale : loupe, halo doré au focus */
.st-key-recherche_globale [data-baseweb="input"] { border:1px solid #C8AA6E55 !important; border-radius:10px !important; background:#0F1B30 !important;
    transition: border-color .25s, box-shadow .25s; animation: monter .6s var(--ease) .1s both; }
.st-key-recherche_globale [data-baseweb="input"]:focus-within { border-color:var(--or) !important; box-shadow:0 0 0 3px #C8AA6E2E, 0 0 28px #C8AA6E33; }
.st-key-recherche_globale input { font-size:1.05rem !important; padding:14px 16px 14px 46px !important; background:transparent !important;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='%23C8AA6E' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m20 20-3.5-3.5'/%3E%3C/svg%3E") !important;
    background-repeat:no-repeat !important; background-position:16px center !important; }
.st-key-panneau_resultat { animation: monter .45s var(--ease) both; }
.st-key-panneau_resultat > div { border-color:#C8AA6E55 !important; background:#0D182C99; }
.aide-recherche { color:var(--gris); font-size:.78rem; margin:-6px 0 12px 4px; }
.aide-recherche b { color:var(--or); font-weight:600; }

.pied { color:var(--gris); font-size:.72rem; margin-top:40px; border-top:1px solid #C8AA6E22; padding-top:10px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation:none !important; transition:none !important; } }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- petits composants

def nombre(n):
    return f"{n:,}".replace(",", " ")


def e(texte):
    return html.escape(str(texte))


def tuile(colonne, i, etiquette, valeur, detail="", compteur=False):
    if compteur:   # le chiffre défile de 0 jusqu'à sa valeur
        valeur = f'<span class="compteur" style="--cible:{int(valeur)};--i:{i}" aria-label="{int(valeur)}"></span>'
    colonne.markdown(f'<div class="tuile" style="--i:{i}"><div class="etiquette">{etiquette}</div>'
                     f'<div class="valeur">{valeur}</div><div class="detail">{detail}</div></div>', unsafe_allow_html=True)


def html_bloc(contenu):
    st.markdown(contenu, unsafe_allow_html=True)


def barres_top(top):
    lignes = []
    for i, c in enumerate(top):
        largeur = max(2, min(100, (c["taux_victoire"] - 40) * 5))      # échelle de 40 % à 60 %
        lignes.append(
            f'<div class="ligne" style="--i:{i};--w:{largeur:.1f}%"><span class="pos">{i + 1}</span>'
            f'<img src="{icone(c["champion_id"])}" alt="">'
            f'<span class="nom">{e(c["nom"])}<small>{NOM_ROLE.get(c["role"], "")} · {nombre(c["parties"])} parties</small></span>'
            f'<span class="piste"><span class="barre"></span><span class="repere"></span></span>'
            f'<span class="val">{c["taux_victoire"]:.1f} %</span></div>')
    return '<div class="top">' + "".join(lignes) + "</div>"


def entete(image, titre, sous_titre="", badge=""):
    html_bloc(f'<div class="fiche"><div class="anneau"><img src="{image}" alt=""></div>'
              f'<div><h3>{e(titre)}</h3><p class="titre">{sous_titre}</p>'
              f'{f"<span class=rang-badge>{badge}</span>" if badge else ""}</div></div>')


def cartes(elements, objet=False):
    """elements : [(image, nom, ligne de détail en HTML)]"""
    html_bloc('<div class="cartes">' + "".join(
        f'<div class="carte{" objet" if objet else ""}" style="--i:{i}"><img src="{img}" alt="">'
        f'<div>{e(nom)}</div><small>{detail}</small></div>' for i, (img, nom, detail) in enumerate(elements)) + "</div>")


def duels(liste, couleur):
    if not liste:
        st.caption("Pas assez de duels.")
        return
    html_bloc("".join(
        f'<div class="duel" style="--i:{i};--c:{couleur}"><img src="{icone(m["champion_id"])}" alt="">'
        f'<span>{e(m["nom"])}<small>{m["parties"]} duel{"s" if m["parties"] > 1 else ""}</small></span>'
        f'<b>{m["taux_victoire"]:.0f} %</b></div>' for i, m in enumerate(liste)))


def il_y_a(iso):
    date = datetime.fromisoformat(iso)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    secondes = (datetime.now(timezone.utc) - date).total_seconds()
    if secondes < 3600:
        return f"il y a {max(1, int(secondes // 60))} min"
    if secondes < 86400:
        return f"il y a {int(secondes // 3600)} h"
    return f"il y a {int(secondes // 86400)} j"


def theme_graphique(graphique):
    return graphique.configure(background="transparent").configure_view(stroke=None) \
        .configure_axis(labelColor=TEXTE, titleColor=GRIS, gridColor="#C8AA6E1A", domainColor="#C8AA6E44")


def lire_profil(puuid):
    try:
        return appeler(f"/lol/joueurs/{puuid}")
    except Exception:
        return None


def afficher_champion(champion, prefixe):
    """La fiche complète d'un champion (utilisée par l'onglet et par la recherche)."""
    details = None
    if etat == "direct":
        try:
            details = appeler(f"/lol/champions/{champion['champion_id']}/details")
        except Exception:
            details = None
    ses_stats = next((s for s in stats if s["champion_id"] == champion["champion_id"]), None)
    titre = e(champion.get("titre") or "")
    entete(icone(champion["champion_id"]), champion["nom"],
           f'{titre + " · " if titre else ""}{e(champion["classe"] or "")}')
    if ses_stats:
        a, b, c = st.columns(3)
        a.metric("Victoire", f"{ses_stats['taux_victoire']} %", f"{ses_stats['taux_victoire'] - 50:+.1f} pts vs 50 %")
        b.metric("Parties", nombre(ses_stats["parties"]))
        c.metric("KDA moyen", ses_stats["kda"])
    elif details and details["parties"]:
        st.caption(f"{details['parties']} partie(s) en base : sous le minimum choisi dans les filtres.")
    else:
        st.caption("Pas encore de partie pour ce champion.")

    if details and details["parties"]:
        st.markdown("#### Objets clés")
        if details["objets"]:
            cartes([(icone_objet(o["objet_id"]), o["nom"],
                     f'{o["frequence"]:.0f} % des parties<br><b>{o["taux_victoire"]:.0f} % victoire</b>')
                    for o in details["objets"]], objet=True)
        st.markdown("#### Selon la durée de la partie")
        duree = pd.DataFrame(details["duree"])
        if not duree.empty:
            base = alt.Chart(duree).encode(x=alt.X("tranche:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)))
            barres = base.mark_bar(color=OR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=38).encode(
                y=alt.Y("taux_victoire:Q", title="victoire (%)", scale=alt.Scale(domain=[0, 100])),
                tooltip=[alt.Tooltip("tranche", title="durée"), alt.Tooltip("taux_victoire", title="victoire (%)"),
                         alt.Tooltip("parties")])
            valeurs = base.mark_text(dy=-8, color=OR_CLAIR).encode(
                y="taux_victoire:Q", text=alt.Text("parties:Q", format="d"))
            ligne_50 = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(color=BLEU, strokeDash=[4, 4]).encode(y="y:Q")
            st.altair_chart(theme_graphique((barres + valeurs + ligne_50).properties(height=240)),
                            width="stretch", key=f"duree_{prefixe}")
            st.caption("Le chiffre au-dessus de chaque barre est le nombre de parties de la tranche.")
        st.markdown("#### Face à son adversaire direct (même rôle)")
        gauche, droite = st.columns(2)
        with gauche:
            st.caption("Gagne le plus contre")
            duels(details["meilleurs_matchups"], "var(--bleu)")
        with droite:
            st.caption("Perd le plus contre")
            duels(details["pires_matchups"], "var(--rouge)")

    st.markdown("#### Champions qui lui ressemblent")
    proches = similaires(champion, catalogue, etat)
    if proches:
        cartes([(icone(p["champion_id"]), p["nom"],
                 "distance " + format(p["distance"], ".2f") if p["distance"] is not None else "même classe")
                for p in proches])
    else:
        st.caption("Aucun champion proche trouvé.")


def texte_rang(profil):
    if profil["classement"]:
        r = profil["classement"]
        return f'#{r["rang"]} Challenger · {nombre(r["lp"])} LP · {r["victoires"]} V / {r["defaites"]} D'
    if profil.get("rang_riot"):
        r = profil["rang_riot"]
        division = "" if r["palier"] in ("MASTER", "GRANDMASTER", "CHALLENGER") else f' {r["division"]}'
        return f'{r["palier"].title()}{division} · {r["lp"]} LP · {r["victoires"]} V / {r["defaites"]} D'
    return ""


def afficher_profil(profil, prefixe):
    """Le profil complet d'un joueur (utilisé par l'onglet et par la recherche)."""
    if profil is None:
        st.warning("Joueur introuvable.")
        return
    image = (icone(profil["favoris"][0]["champion_id"]) if profil["favoris"] else
             f"https://ddragon.leagueoflegends.com/cdn/{version_data_dragon()}/img/profileicon/29.png")
    entete(image, profil["pseudo"],
           f'Rôle principal : {NOM_ROLE.get(profil["role_principal"], "?")}' if profil["role_principal"] else "",
           texte_rang(profil))
    if not profil["parties"]:
        st.caption("Aucune partie de ce joueur n'est en base.")
        return
    rang = profil["classement"]
    a, b, c, d = st.columns(4)
    tuile(a, 0, "Parties en base", profil["parties"], "MongoDB", compteur=True)
    tuile(b, 1, "Victoire", f'{profil["taux_victoire"]:.0f} %', f'{profil["victoires"]} victoires')
    tuile(c, 2, "KDA", f'{profil["kda"]:.2f}', "(kills + assists) / morts")
    if rang:
        tuile(d, 3, "Classement", f'#{rang["rang"]}', "Redis · ZREVRANK")
    elif profil.get("rang_riot"):
        tuile(d, 3, "Rang officiel", e(profil["rang_riot"]["palier"].title()), "Riot League-V4 · cache Redis 10 min")
    else:
        tuile(d, 3, "Rang", "–", "non classé en solo/duo")
    st.markdown("#### Champions favoris")
    cartes([(icone(f["champion_id"]), f["nom"],
             f'{f["parties"]} partie{"s" if f["parties"] > 1 else ""}<br><b>{f["taux_victoire"]:.0f} % victoire</b>')
            for f in profil["favoris"]])
    st.markdown("#### Dernières parties")
    html_bloc("".join(
        f'<div class="partie {"v" if p["victoire"] else "d"}" style="--i:{i}">'
        f'<img src="{icone(p["champion_id"])}" alt="">'
        f'<span class="nom">{e(p["champion"])}<small>{NOM_ROLE.get(p["role"], "")}'
        f'{" · " if p["role"] in NOM_ROLE else ""}{FILES.get(p.get("file"), "Autre mode")}</small></span>'
        f'<span class="res">{"Victoire" if p["victoire"] else "Défaite"}</span>'
        f'<span class="kda">{p["kills"]} / {p["morts"]} / {p["assists"]}<br><small>{nombre(p["or"])} or</small></span>'
        f'<span class="quand">{p["duree_s"] // 60} min<br>{il_y_a(p["date"])}</span></div>'
        for i, p in enumerate(profil["historique"])))


def recherche_globale():
    """La barre de recherche : champions (catalogue), joueurs en base (MongoDB), ou Riot ID sur les serveurs Riot."""
    with st.container(key="recherche_globale"):
        texte = st.text_input("Rechercher", key="texte_recherche", label_visibility="collapsed",
                              placeholder="Rechercher un champion (Ahri) ou un joueur (Pseudo#TAG)…")
    html_bloc('<div class="aide-recherche">Astuce : tapez votre <b>Riot ID complet</b>, par exemple '
              '<b>Pseudo#EUW</b>, pour charger vos propres statistiques depuis les serveurs Riot.</div>')
    texte = texte.strip()
    if len(texte) < 2:
        return

    cle = sans_accents(texte.split("#")[0])
    resultats = [("champion", c["champion_id"], f"Champion · {c['nom']}") for c in catalogue
                 if cle and cle in sans_accents(c["nom"])][:6]
    if en_ligne:
        try:
            resultats += [("joueur", j["puuid"], f"Joueur · {j['pseudo']} ({j['parties']} partie{'s' if j['parties'] > 1 else ''})")
                          for j in appeler("/lol/joueurs", q=texte, limite=6)]
        except Exception:
            pass
        if "#" in texte and not texte.endswith("#"):
            resultats.append(("riot", texte, f"Chercher « {texte} » sur les serveurs Riot"))
    if not resultats:
        st.caption("Aucun résultat. Pour un joueur qui n'est pas encore en base, tapez son Riot ID complet (Pseudo#TAG).")
        return

    choix = st.pills("Résultats", list(range(len(resultats))), format_func=lambda i: resultats[i][2], default=0,
                     key=f"pills_{texte}", label_visibility="collapsed")
    if choix is None:
        return
    genre, identifiant, _ = resultats[choix]
    with st.container(border=True, key="panneau_resultat"):
        if genre == "champion":
            afficher_champion(next(c for c in catalogue if c["champion_id"] == identifiant), "recherche")
        elif genre == "joueur":
            afficher_profil(lire_profil(identifiant), "recherche")
        else:
            importes = st.session_state.setdefault("importes", {})
            g, d = st.columns([1, 3])
            serveur = g.selectbox("Serveur", list(SERVEURS), key="serveur_riot")
            d.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
            cle_import = f"{SERVEURS[serveur]}:{identifiant.lower()}"
            if d.button(f"Charger {identifiant} depuis Riot", type="primary", key="bouton_riot"):
                with st.spinner("Recherche du compte, du rang et des 15 dernières parties chez Riot…"):
                    try:
                        importes[cle_import] = appeler("/lol/riot/joueur", methode="POST", delai=120,
                                                       riot_id=identifiant, plateforme=SERVEURS[serveur])
                    except requests.HTTPError as erreur:
                        try:
                            message = erreur.response.json().get("detail", str(erreur))
                        except ValueError:
                            message = str(erreur)
                        st.error(message)
                    except Exception as erreur:
                        st.error(f"L'API ne répond pas : {erreur}")
            if cle_import in importes:
                resultat = importes[cle_import]
                st.caption(f"{resultat['nouvelles']} nouvelle(s) partie(s) importée(s) sur {resultat['parties_trouvees']} "
                           f"trouvée(s), {resultat['appels_riot']} appels à l'API Riot. Ces parties sont rangées à part : "
                           "elles ne modifient pas les statistiques des champions.")
                afficher_profil(lire_profil(resultat["puuid"]), "riot")
            else:
                st.caption("Le chargement prend quelques secondes et utilise environ 18 appels de votre clé Riot.")



# ---------------------------------------------------------------- la page

st.sidebar.markdown("### Filtres")
nom_role = st.sidebar.radio("Rôle", list(ROLES))
min_parties = st.sidebar.slider("Parties minimum par champion", 0, 200, 20, step=5)
st.sidebar.caption("Le taux de victoire n'a de sens qu'avec assez de parties.")

stats, classement, sante, catalogue, etat, erreur = charger(ROLES[nom_role], min_parties)
en_ligne = etat in ("direct", "vide")

badges = {
    "direct": f"En direct · patch {e(sante.get('patch'))}",
    "vide": "API connectée · aucune partie collectée pour l'instant",
    "demo": "Démonstration · données inventées, l'API /lol ne répond pas",
    "erreur": "Erreur de l'API",
}
html_bloc(f'<div class="bandeau"><h1>Rift Stats</h1>'
          f'<p>Taux de victoire des champions et classement des joueurs · parties classées solo/duo</p>'
          f'<span class="badge {etat}"><i></i>{badges[etat]}</span></div>')

if etat == "erreur":
    st.error(f"L'API répond mais une route a échoué : {erreur}")
elif etat == "vide":
    st.info("Les champions et la similarité sont réels (Data Dragon + PostgreSQL). Pour les statistiques et le "
            "classement, lancez la collecte avec votre clé Riot :\n\n"
            "`docker exec --env-file riot.env python python -u /travail/lol/collecte_riot.py`")

recherche_globale()

# 1. les chiffres clés
meilleur = max(stats, key=lambda c: c["taux_victoire"], default=None)
c1, c2, c3, c4 = st.columns(4)
tuile(c1, 0, "Parties analysées", sante["parties"], "MongoDB", compteur=True)
tuile(c2, 1, "Champions joués", len(stats), f"sur {nombre(sante['champions'])} · PostgreSQL", compteur=True)
tuile(c3, 2, "Joueurs classés", sante.get("joueurs", len(classement)),
      "Redis " + ("en ligne" if sante["redis"] else "hors ligne"), compteur=True)
tuile(c4, 3, "Meilleur taux de victoire", f"{meilleur['taux_victoire']:.1f} %" if meilleur else "–",
      e(meilleur["nom"]) if meilleur else "aucun champion")

st.write("")
onglets = st.tabs(["Champions", "Fiche champion", "Joueurs", "Classement", "Infra"])

# 2. les champions : taux de victoire (agrégation MongoDB)
with onglets[0]:
    if not stats:
        st.info("Aucun champion à afficher" + (" : baissez le nombre minimum de parties." if etat in ("demo", "direct") else "."))
    else:
        table = pd.DataFrame(stats).sort_values("taux_victoire", ascending=False)
        st.subheader(f"Top 10 par taux de victoire · {nom_role}")
        html_bloc(barres_top(table.head(10).to_dict("records")))
        html_bloc('<div class="legende">Barre de 40 % à 60 % · la ligne pointillée marque 50 %</div>')

        st.subheader("Tous les champions")
        table["icone"] = table["champion_id"].map(icone)
        table["role"] = table["role"].map(lambda r: NOM_ROLE.get(r, r))
        st.dataframe(
            table[["icone", "nom", "role", "classe", "parties", "taux_victoire", "taux_selection", "kda"]],
            hide_index=True, width="stretch", height=420,
            column_config={
                "icone": st.column_config.ImageColumn("", width="small"),
                "nom": "Champion", "role": "Rôle", "classe": "Classe", "parties": "Parties",
                "taux_victoire": st.column_config.ProgressColumn("Victoire", min_value=0, max_value=100, format="%.1f %%"),
                "taux_selection": st.column_config.NumberColumn("Présence", format="%.1f %%",
                                                                help="part des parties où le champion est joué"),
                "kda": st.column_config.NumberColumn("KDA", format="%.2f"),
            })

# 3. la fiche d'un champion : similarité (pgvector), objets, durée, matchups (MongoDB)
with onglets[1]:
    if not catalogue:
        st.info("Aucun champion en base : lancez /travail/lol/charger_champions.py")
    else:
        par_nom = {c["nom"]: c for c in catalogue}
        noms = sorted(par_nom)
        choix = st.selectbox("Champion", noms, index=noms.index("Ahri") if "Ahri" in noms else 0)
        afficher_champion(par_nom[choix], "onglet")

# 4. le profil d'un joueur (Redis pour le rang, MongoDB pour les parties)
with onglets[2]:
    if not en_ligne:
        st.info("Les profils de joueurs sont disponibles quand l'API tourne.")
    else:
        st.caption("Pour un autre joueur, ou pour vous, utilisez la barre de recherche en haut de la page.")
        options = [j for j in classement if j["pseudo"] != "Joueur inconnu"]
        selection = st.session_state.get("table_classement")
        lignes = selection["selection"]["rows"] if selection else []
        if lignes and lignes[0] < len(classement):
            choisi = classement[lignes[0]]
            options = [choisi] + [j for j in options if j["puuid"] != choisi["puuid"]]
        if options:
            joueur = st.selectbox("Joueur du classement", options, format_func=lambda j: f"{j['pseudo']} · #{j['rang']}")
            afficher_profil(lire_profil(joueur["puuid"]), "onglet")


# 5. le classement des joueurs (ensemble trié Redis)
with onglets[3]:
    st.subheader("Les meilleurs joueurs du serveur")
    if not classement:
        st.info("Le classement est vide : il se remplit pendant la collecte.")
    else:
        marches = "".join(
            f'<div class="marche p{j["rang"]}" style="--i:{j["rang"] - 1}"><div class="rang">#{j["rang"]}</div>'
            f'<div class="pseudo">{e(j["pseudo"])}</div><div class="lp">{nombre(j["lp"])} LP</div></div>'
            for j in classement[:3])
        html_bloc(f'<div class="podium">{marches}</div>')
        joueurs = pd.DataFrame(classement)
        joueurs["taux"] = (100 * joueurs["victoires"] / (joueurs["victoires"] + joueurs["defaites"]).clip(lower=1)).round(1)
        st.dataframe(joueurs[["rang", "pseudo", "lp", "victoires", "defaites", "taux"]], hide_index=True,
                     width="stretch", key="table_classement",
                     on_select="rerun" if en_ligne else "ignore", selection_mode="single-row",
                     column_config={
                         "rang": "Rang", "pseudo": "Joueur", "lp": st.column_config.NumberColumn("LP", format="%d"),
                         "victoires": "V", "defaites": "D",
                         "taux": st.column_config.ProgressColumn("Victoire", min_value=0, max_value=100, format="%.1f %%")})
        if en_ligne:
            st.caption("Cochez un joueur puis ouvrez l'onglet Joueurs pour voir son profil.")

# 6. l'infrastructure : les trois bases et le replica set (pour la question CAP)
with onglets[4]:
    if not en_ligne:
        st.info("L'état des bases est disponible quand l'API tourne.")
    else:
        if st.button("Rafraîchir"):
            pass   # un clic relance simplement la page
        infra = appeler("/lol/infra")
        mongo, rds, pg = infra["mongodb"], infra["redis"], infra["postgresql"]
        st.markdown(f"#### MongoDB · replica set {e(mongo.get('replica_set', '?'))}")
        if mongo.get("en_ligne") is False:
            st.error(f"MongoDB ne répond pas : {mongo.get('erreur')}")
        else:
            html_bloc('<div class="noeuds">' + "".join(
                f'<div class="noeud {n["etat"] if n["en_ligne"] else "panne"}" style="--i:{i}">'
                f'<div class="etat"><i></i>{e(n["etat"] if n["en_ligne"] else "HORS LIGNE")}</div>'
                f'<div class="nom">{e(n["nom"].split(":")[0])}</div></div>' for i, n in enumerate(mongo["noeuds"])) + "</div>")
            a, b, c, d = st.columns(4)
            tuile(a, 0, "Parties", mongo["documents"], "documents", compteur=True)
            tuile(b, 1, "Taille moyenne", f'{mongo["taille_moyenne_octets"] / 1024:.1f} Ko', "par partie")
            tuile(c, 2, "Stockage", f'{mongo["stockage_octets"] / 1024 / 1024:.1f} Mo', "compressé (WiredTiger)")
            tuile(d, 3, "Index", mongo["index"], f'{mongo["taille_index_octets"] / 1024:.0f} Ko', compteur=True)
            st.caption("Les écritures vont au primaire puis sont copiées sur les secondaires. Si le primaire tombe, "
                       "les deux autres élisent un nouveau primaire : essayez `docker stop mongo1` puis Rafraîchir.")
        g, d = st.columns(2)
        with g:
            st.markdown("#### Redis")
            if rds.get("en_ligne") is False:
                st.error(f"Redis ne répond pas : {rds.get('erreur')}")
            else:
                x, y = st.columns(2)
                tuile(x, 0, "Clés", rds["cles"], f'dont {rds["cles_cache"]} en cache (60 s)', compteur=True)
                tuile(y, 1, "Mémoire", e(rds["memoire"]), "utilisée")
        with d:
            st.markdown("#### PostgreSQL")
            if pg.get("en_ligne") is False:
                st.error(f"PostgreSQL ne répond pas : {pg.get('erreur')}")
            else:
                x, y = st.columns(2)
                tuile(x, 0, "Champions", pg["champions"], f'{nombre(pg["objets"])} objets', compteur=True)
                tuile(y, 1, "Taille", e(pg["taille"]), "tables + index + vecteurs")

html_bloc('<div class="pied">Données : API Riot Games (League-V4, Account-V1, Match-V5) et Data Dragon. '
          "Rift Stats isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games "
          "or anyone officially involved in producing or managing Riot Games properties. "
          "Riot Games, League of Legends are trademarks or registered trademarks of Riot Games, Inc.</div>")
