♟️ Chess — Jeu d’échecs en Python avec interface graphique
Un jeu d’échecs local simple et intuitif, codé en Python avec tkinter.




🧩 Fonctionnalités
Plateau d’échecs interactif (8x8)

Mouvement des pièces avec les règles de base

Interface graphique via tkinter

Partie locale entre deux joueurs

Légère et sans dépendance externe

⚙️ Installation
1. Prérequis
Assure-toi d’avoir installé :

Python 3.10+

pip (inclus avec Python)

2. Cloner le projet
bash
Copier
Modifier
git clone https://github.com/Maxence287/Chess.git
cd Chess
3. (Optionnel) Environnement virtuel
bash
Copier
Modifier
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS / Linux
4. Dépendances
Aucune dépendance externe ! Tout est inclus via Python standard (tkinter, os, etc.)

▶️ Lancer le jeu
bash
Copier
Modifier
python chess_game.py
Une fenêtre s’ouvrira avec le plateau d’échecs.
Tu peux directement jouer à deux sur le même PC.

📦 Créer un fichier .exe (pour Windows)
1. Installer PyInstaller
bash
Copier
Modifier
pip install pyinstaller
2. Générer le .exe
bash
Copier
Modifier
pyinstaller --onefile --windowed chess_game.py
Le fichier .exe final sera dans le dossier dist/

Le flag --windowed évite l’ouverture d’une console

3. Lancer le jeu
Va dans dist/ et double-clique sur chess_game.exe


