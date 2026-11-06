"""Tableau de bord de NYC Eats (Streamlit). Il ne lit que l'API, jamais les bases directement.

Lancer (après l'API) :
    docker exec -it python streamlit run /projet/tableau_de_bord.py --server.address 0.0.0.0 --server.port 8501
Puis ouvrir http://localhost:8501
"""
import altair as alt
import pandas as pd
import requests
import streamlit as st

API = "http://localhost:8000"   # l'API tourne dans le même conteneur


def appeler(chemin, **parametres):
    reponse = requests.get(API + chemin, params=parametres, timeout=10)
    reponse.raise_for_status()
    return reponse.json()


st.set_page_config(page_title="NYC Eats", layout="wide")
st.title("NYC Eats : tableau de bord")

quartier = st.sidebar.selectbox("Quartier", ["(tous)"] + appeler("/quartiers"))
filtre = None if quartier == "(tous)" else quartier

# 1. Les chiffres clés
sante = appeler("/sante")
colonne1, colonne2, colonne3 = st.columns(3)
colonne1.metric("Restaurants (MongoDB)", f"{sante['mongodb']:,}".replace(",", " "))
colonne2.metric("Avis clients (PostgreSQL)", f"{sante['postgresql']:,}".replace(",", " "))
colonne3.metric("Restaurants consultés (Redis)", len(appeler("/classement", nombre=1000)))

# 2. Une métrique calculée dans MongoDB (pipeline d'agrégation, mise en cache dans Redis)
st.subheader("Cuisines au meilleur score d'inspection (score bas = bon)")
cuisines = pd.DataFrame(appeler("/stats/cuisines", quartier=filtre))
if not cuisines.empty:
    graphique = alt.Chart(cuisines).mark_bar().encode(
        x=alt.X("cuisine", sort="y", title="cuisine"),      # de la meilleure à la moins bonne
        y=alt.Y("score_moyen", title="score moyen"),
        tooltip=["cuisine", "score_moyen", "inspections"],
    )
    st.altair_chart(graphique, use_container_width=True)

# 3. Les restaurants les plus consultés (ensemble trié Redis)
st.subheader("Les plus consultés")
classement = pd.DataFrame(appeler("/classement", nombre=10))
st.dataframe(classement if not classement.empty else pd.DataFrame({"info": ["Aucune consultation pour l'instant"]}))

# 4. Une fiche, ses avis et les restaurants qui lui ressemblent (PostgreSQL + pgvector)
st.subheader("Fiche d'un restaurant")
restaurant_id = st.text_input("Identifiant (restaurant_id), par exemple 40356483")
if restaurant_id:
    try:
        fiche = appeler(f"/restaurants/{restaurant_id}")
        st.write(f"**{fiche['restaurant']['name']}** ({fiche['restaurant']['cuisine']}, {fiche['restaurant']['borough']})"
                 f" : lu depuis {fiche['origine']}, {fiche['vues']} consultation(s)")
        for un_avis in fiche["avis"]:
            st.write(f"{'★' * un_avis['note']} {un_avis['auteur']} : {un_avis['texte']}")
        similaires = pd.DataFrame(appeler(f"/restaurants/{restaurant_id}/similaires"))
        if not similaires.empty:
            st.write("Restaurants qui lui ressemblent :")
            st.dataframe(similaires)
    except requests.HTTPError:
        st.warning("Restaurant inconnu.")
