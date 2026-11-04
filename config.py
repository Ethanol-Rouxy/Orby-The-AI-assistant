"""Configuration d'Orby. C'est le fichier que tu modifieras le plus."""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ASSISTANT_NAME = "Orby"

# ---------------------------------------------------------------------------
# Fournisseurs d'IA, PAR ORDRE DE PRIORITE.
# Tous parlent le même format (compatible OpenAI) : pour en ajouter un,
# copie un bloc, change l'URL, le modèle et le nom de la variable de clé.
# Un fournisseur sans clé dans le fichier .env est simplement ignoré.
# ---------------------------------------------------------------------------
PROVIDERS = [
    {
        "name": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
        "color": "#4285F4",
    },
    {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        "color": "#F55036",
    },
    {
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
        "color": "#FA520F",
    },
]

COOLDOWN_SECONDS = 60   # pause d'un fournisseur après une limite de quota
MAX_TOOL_STEPS = 6      # nombre max d'actions enchaînées pour une question
MAX_HISTORY = 30        # messages gardés en mémoire (économise le quota)

# ---------------------------------------------------------------------------
# Sécurité : Orby ne peut lire/ouvrir QUE dans ces dossiers.
# ---------------------------------------------------------------------------
ALLOWED_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]

# Applications qu'Orby a le droit de lancer (nom -> commande).
if sys.platform.startswith("win"):
    APPS = {
        "bloc-notes": ["notepad"],
        "terminal": ["cmd"], # Invite de commandes
        "gestionnaire-tâches": ["taskmgr"], # Voir les processus
        "explorateur de fichier": ["explorer"], # Courrier
    }
elif sys.platform == "darwin":
    APPS = {
        "calculatrice": ["open", "-a", "Calculator"],
        "notes": ["open", "-a", "Notes"],
    }
else:
    APPS = {
        "calculatrice": ["gnome-calculator"],
        "fichiers": ["xdg-open", str(Path.home())],
    }

# Sites favoris affichés dans le mode "Ouvrir / lancer".
FAVORITE_SITES = {
    "ChatGPT": "https://chatgpt.com",
    "Gémini": "https://gemini.google.com",
    "Claude": "https://claude.ai",
    "GitHub": "https://github.com",
    "YouTube": "https://www.youtube.com",
    "Spotify": "https://open.spotify.com",
}

# ---------------------------------------------------------------------------
# Infos du jour, météo, mini-écran (HUD), rappels
# ---------------------------------------------------------------------------
# Flux RSS des actualités (ajoute / retire les tiens). Un flux en panne est ignoré.
NEWS_FEEDS = [
    {"name": "Le Monde",    "url": "https://www.lemonde.fr/rss/une.xml"},
    {"name": "France Info", "url": "https://www.francetvinfo.fr/titres.rss"},
    {"name": "Le Figaro",   "url": "https://www.lefigaro.fr/rss/figaro_actualites.xml"},
]
NEWS_COUNT = 15                 # nombre de titres affichés
WEATHER_CITY = "Porrentruy"     # ta ville (météo Open-Meteo, sans clé)

# Au tout premier affichage, Orby propose ces actions dans sa bulle.
STARTUP_OFFER = True
STARTUP_OFFER_TEXT = "Je te montre les nouvelles du jour ?"
STARTUP_OFFERS = [               # (texte du bouton, clé) ; clés : une clé de MODES ou "briefing"
    ("📰 Les infos du jour", "news"),
    ("🧠 Brief du matin (IA)", "briefing"),
    ("📊 Mini-écran météo / système", "hud"),
]
STARTUP_OFFER_MS = 30000        # la proposition disparaît toute seule après ce délai
BRIEFING_PROMPT = (
    "Fais-moi un brief rapide : la météo (get_weather), les 5 infos les plus importantes du jour "
    "(get_news), mes rappels (list_reminders) et l'état de mon PC (system_status). Sois concis."
)

# ---------------------------------------------------------------------------
# Bureaux virtuels Windows
#   "stay" : Orby reste sur le bureau où tu l'as lancé (il se cache sur les autres). Pour le faire venir
#            sur le bureau où tu es : raccourci clavier ou clic sur l'icône de la zone de notification.
#   "all"  : Orby est visible sur tous les bureaux.
# ---------------------------------------------------------------------------
DESKTOP_MODE = "stay"

# Mini-écran en version réduite : afficher le nom (CPU, RAM...) devant chaque chiffre ?
HUD_COMPACT_LABELS = True

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
HOTKEY = "<ctrl>+<alt>+space"       # afficher / masquer Orby

# Taille des fenêtres (en pixels). Tu peux aussi redimensionner la console à la souris en tirant
# sur un de ses bords ou coins ; la taille choisie est mémorisée.
CONSOLE_SIZE = (470, 560)           # taille au premier lancement
CONSOLE_MIN_SIZE = (320, 380)       # la console ne descend pas en dessous
BUBBLE_WIDTH = 300                  # largeur de la bulle d'Orby (la hauteur s'adapte au texte)

# Texte dit par Orby quand tu cliques dessus.
BUBBLE_GREETING = "Salut ! Qu'est-ce qu'on fait ?"

# Ce qu'Orby dit au démarrage. {moment} = Bonjour / Bonsoir, {name} = son nom.
STARTUP_LINES = [
    "{moment} ! Moi c'est {name}. Clique sur moi quand tu as besoin de quelque chose.",
    "Systèmes en ligne. {name} à ton service.",
    "{moment} ! Prêt à bosser ? Je suis là.",
    "Réveil terminé. {name} est opérationnel !",
]
# Quand tu le réaffiches après l'avoir masqué.
BACK_LINES = ["Me revoilà !", "De retour !", "Tu m'as appelé ?"]
# Quand tu le caresses (au plus une fois toutes les 25 s).
PET_LINES = ["Hehe, ça chatouille !", "Mmh, continue…", "Merci, ça fait du bien !",
             "Bip bip !"]

# Les boutons de la bulle. Chaque bouton ouvre une page DIFFÉRENTE de la console.
#   page  : "chat" (discussion), "files" (explorateur), "launcher" (lanceur), "summary" (résumés)
#   label : texte du bouton   |   title : titre affiché dans la console
#   greeting / placeholder : textes de la page chat   |   extra : consigne ajoutée au prompt de l'IA
MODES = [
    {
        "key": "chat", "page": "chat",
        "label": "💬 Discuter", "title": "CHAT",
        "greeting": "On discute ! Pose-moi ce que tu veux.",
        "placeholder": "Écris ton message…",
        "extra": "",
    },
    {
        "key": "files", "page": "files",
        "label": "📁 Explorer mes fichiers", "title": "FICHIERS",
        "greeting": "", "placeholder": "",
        "extra": "L'utilisateur travaille sur ses fichiers : privilégie search_files, list_dir et read_file.",
    },
    {
        "key": "open", "page": "launcher",
        "label": "🚀 Ouvrir / lancer", "title": "LANCEUR",
        "greeting": "", "placeholder": "",
        "extra": "",
    },
    {
        "key": "summary", "page": "summary",
        "label": "📝 Résumer un document", "title": "RÉSUMÉ",
        "greeting": "", "placeholder": "",
        "extra": "Mode résumé : lis le fichier demandé avec read_file puis résume-le clairement.",
    },
    {
        "key": "news", "page": "news",
        "label": "📰 Infos du jour", "title": "INFOS",
        "greeting": "", "placeholder": "",
        "extra": "Pour les actualités, utilise get_news.",
    },
    {   # ouvre le petit écran flottant (pas une page de la console)
        "key": "hud", "page": "hud",
        "label": "📊 Mini-écran", "title": "HUD",
        "greeting": "", "placeholder": "", "extra": "",
    },
]

# ---------------------------------------------------------------------------
# TAILLE (zoom) : molette de la souris sur Orby, ou clic droit -> Taille.
# ---------------------------------------------------------------------------
DEFAULT_ZOOM = 1.0
ZOOM_LEVELS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]

# ---------------------------------------------------------------------------
# PERSONNAGE ANIMÉ (spritesheets)
# Dépose tes PNG dans le dossier assets/character/ (voir LISEZMOI.txt).
# ---------------------------------------------------------------------------
AVATAR = "sprite"                   # "sprite" (tes spritesheets), "square" ou "dot"
SPRITES_DIR = Path(__file__).parent / "assets" / "character"
SPRITE_FRAME_SIZE = (100, 100)  # taille d'UNE image dans la feuille (largeur, hauteur)
SPRITE_SCALE = 1.0              # taille de base (le zoom se multiplie avec)
SPRITE_SPEED = 1.0              # VITESSE GLOBALE de toutes les animations (0.5 = 2x plus lent, 2 = 2x plus vite)
SPRITE_SMOOTH = False           # False = pixel art net, True = lissé (pour du dessin HD)

# Une entrée par animation.
#   file   : nom du PNG dans SPRITES_DIR
#   fps    : VITESSE de CETTE animation, en images par seconde (plus petit = plus lent)
#   loop   : True = tourne en boucle, False = jouée une seule fois
#   frames : (optionnel) nombre d'images à lire, si la détection automatique se trompe
# Seule "idle" est obligatoire. Les autres sont optionnelles.
SPRITE_ANIMATIONS = {
    "idle":         {"file": "idle.png",         "fps": 8,  "loop": True},
    "start":        {"file": "start.png",        "fps": 12, "loop": False},
    "stop":         {"file": "stop.png",         "fps": 12, "loop": False},
    "thinking":     {"file": "thinking.png",     "fps": 10, "loop": True},
    "working":      {"file": "working.png",      "fps": 10, "loop": True},
    "error":        {"file": "error.png",        "fps": 8,  "loop": True},
    "pet":          {"file": "pet.png",          "fps": 10, "loop": True},   # quand on le caresse

    # --- Déplacement : une animation par sens (toutes optionnelles) ---------------------
    "drag":            {"file": "drag.png",            "fps": 10, "loop": True},  # BASE : vertical / sens inconnu
    "drag_straight":   {"file": "drag_straight.png",   "fps": 10, "loop": True},  # (ancien nom de "drag", gardé)
    "drag_left":       {"file": "drag_left.png",       "fps": 10, "loop": True},  # vers la gauche
    "drag_right":      {"file": "drag_right.png",      "fps": 10, "loop": True},  # vers la droite
    "drag_left_up":    {"file": "drag_left_up.png",    "fps": 10, "loop": True},  # diagonale haut-gauche
    "drag_left_down":  {"file": "drag_left_down.png",  "fps": 10, "loop": True},  # diagonale bas-gauche
    "drag_right_up":   {"file": "drag_right_up.png",   "fps": 10, "loop": True},  # diagonale haut-droite
    "drag_right_down": {"file": "drag_right_down.png", "fps": 10, "loop": True},  # diagonale bas-droite
}

# Réglages du déplacement (animations drag_* ci-dessus) :
#  - Un sens sans fichier utilise l'animation la plus proche : drag_left_up -> drag_left -> drag.
#  - Si un côté manque (ex. drag_right_up absent mais drag_left_up présent), il est créé en miroir.
DRAG_MIRROR = True
DRAG_MIN_SPEED = 80     # px/s : en dessous, Orby garde l'animation en cours (ignore les petits tremblements)
DRAG_AXIS_RATIO = 0.4   # MARGE d'angle : 0.4 = un mouvement à moins de ~22° de la verticale (ou de
                        # l'horizontale) compte comme "tout droit". Plus petit = plus sensible aux diagonales.
DRAG_HOLD_MS = 90       # un nouveau sens doit durer au moins ça (ms) avant de changer d'animation

# ---------------------------------------------------------------------------
# DÉPLACEMENT EN 2 SPRITES : la TÊTE suit la souris, le CORPS est calculé (pendule) et pivote.
# Si les fichiers sont absents, on retombe sur les animations drag_* ci-dessus.
# ---------------------------------------------------------------------------
SPLIT_ENABLED = True
# Pour chaque image : "frame_size": (l, h) = taille d'UNE image ; "frames": N = nombre d'images en bande ;
# "scale": 1.0 = agrandit / réduit cette partie seulement.
SPLIT_HEAD = {"file": "drag-head.png", "fps": 10, "loop": True, "scale": 1.0}              # feuille 100x100
SPLIT_BODY = {"file": "corps.png",     "fps": 10, "loop": True, "scale": 1.0, "frame_size": (18, 25)}
SPLIT_BODY_SMOOTH = False        # False = corps net (pixel art, bords en escalier quand il tourne) ; True = rotation lissée
SPLIT_DEBUG = False             # True = affiche le centre de la tête (rose), du corps (cyan) et le contour de la tête utilisé (orange)
SPLIT_HEAD_POS = (0, 0)         # position de la tête par rapport à l'ancien sprite (pixels de la feuille)
SPLIT_HEAD_BOX = (22, 6, 79, 52)   # zone occupée par la tête dans sa feuille : x1, y1, x2, y2 (le corps tourne autour)
SPLIT_HEAD_SHAPE = 2.5          # 2 = contour de la tête en ellipse ; plus grand = plus carré (le corps s'écarte moins en diagonale)
SPLIT_GAP = 2.5                 # espace (px de la feuille) entre la tête et le corps AU REPOS, comme en idle
                                # (au début et à la fin du déplacement, le corps est à cette distance)

# Le corps se place à l'OPPOSÉ de la direction de déplacement et tourne autour de la tête
# (vers le haut quand tu descends Orby, à gauche quand tu vas à droite...). À l'arrêt il retombe en dessous.
SPLIT_FOLLOW = 0.06             # réactivité : plus grand = le corps rejoint sa place plus vite
SPLIT_BRAKE = 0.18              # amortissement : plus petit = il se balance davantage
SPLIT_MIN_SPEED = 90            # px/s : en dessous, le corps retombe simplement sous la tête
SPLIT_STRETCH = 0.02            # éloignement du corps par px/s de vitesse (px de la feuille)
SPLIT_MAX_EXTRA = 14            # éloignement maximum (px de la feuille)
SPLIT_RELEASE_DELAY = 0.7       # secondes d'attente après avoir relâché Orby, avant de remettre l'animation idle

# Effets de secours, dessinés par le code quand tu n'as pas (ou en plus de) tes animations :
PET_HEARTS = True    # petits coeurs qui montent quand on le caresse
DRAG_TILT = False     # Orby se penche quand on le déplace, comme s'il était suspendu

SYSTEM_PROMPT = (
    f"Tu t'appelles {ASSISTANT_NAME}. Tu es un petit robot compagnon qui vit sur le bureau "
    "de l'utilisateur, en overlay. Tu es sympa, un peu geek, tu fais des phrases courtes et "
    "tu réponds en français. Pour lister, chercher, lire ou ouvrir des fichiers, ou lancer "
    "une application, utilise les outils fournis. Ne prétends jamais avoir ouvert ou lu un "
    "fichier sans avoir appelé l'outil correspondant. Tu peux aussi donner les actualités "
    "(get_news), la météo (get_weather), l'état du PC (system_status) et gérer des rappels "
    "(add_reminder, list_reminders). Si un outil renvoie une erreur, explique-la simplement. "
    "Utilise le format Markdown ; mets le code dans des blocs ``` avec le nom du langage."
)
