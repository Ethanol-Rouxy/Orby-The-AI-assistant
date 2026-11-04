@echo off
REM 1. Création de l'environnement virtuel s'il n'existe pas encore
if not exist ".venv" (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
)

REM 2. Activation de l'environnement et installation/mise a jour si besoin (optionnel)
call .venv\Scripts\activate

REM 3. Lancement des autres commandes si tu en as d'autres
REM (mets tes autres commandes ici si besoin)

echo Lancement du script principal en arriere-plan...
REM Utilisation de pythonw pour détacher le processus et cacher la console du script Python
start /b .venv\Scripts\pythonw.exe main.py

REM On quitte proprement le .bat sans garder de pause bloquante
exit