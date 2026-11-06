# Image Python du kit NYC Eats : Jupyter, clients des trois bases, API et tableau de bord.
FROM python:3.13.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /travail
EXPOSE 8888 8000 8501

# Jupyter sans mot de passe : le kit ne tourne que sur la machine de l'étudiant (localhost).
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", \
     "--ServerApp.token=", "--ServerApp.password=", "--ServerApp.root_dir=/"]
