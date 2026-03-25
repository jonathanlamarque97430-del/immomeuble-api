"""
conftest.py — Configuration pytest racine

Ajoute le dossier racine du projet au sys.path pour que
`from app.main import app` fonctionne depuis n'importe quel
sous-dossier (tests/, etc.).
"""
import sys
import os

# Ajoute le dossier racine (où se trouve app/) au path Python
sys.path.insert(0, os.path.dirname(__file__))
