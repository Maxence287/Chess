import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import chess
import chess.pgn
import time
import logging
import datetime
import random
import os
import json
import chess.polyglot
import socket
import threading
import pickle
from pyngrok import ngrok

# --- CONFIG ---
SQUARE_SIZE = 80
BOARD_SIZE = 8 * SQUARE_SIZE
THEMES = {
    "Chess.com": {"light": "#EEEED2", "dark": "#769656", "highlight": "#BACA44", "bg": "#212121", "button": "#4CAF50", "text": "#FFFFFF", "border": "#424242"},
    "Classic": {"light": "#F0D9B5", "dark": "#B58863", "highlight": "#FFFF99", "bg": "#F5F5F5", "button": "#D3D3D3", "text": "#333333", "border": "#B0B0B0"},
    "Dark": {"light": "#769656", "dark": "#2F2F2F", "highlight": "#FFD700", "bg": "#1A1A1A", "button": "#424242", "text": "#FFFFFF", "border": "#555555"}
}
PIECES_UNICODE = {
    "P": "♙", "p": "♟", "R": "♖", "r": "♜", "N": "♘", "n": "♞",
    "B": "♗", "b": "♝", "Q": "♕", "q": "♛", "K": "♔", "k": "♚"
}
ANIMATION_SPEED = 10
ANIMATION_STEPS = 5
SOCKET_TIMEOUT = 10  # Timeout for socket operations in seconds

# --- LOGGING ---
logging.basicConfig(filename='logs.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

# --- EVALUATION / BOT ---
PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}
PIECE_SQUARE_TABLES = {
    chess.PAWN: [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10,
                 5, 5, 10, 25, 25, 10, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5,
                 5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
    chess.KNIGHT: [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10, 5, -30,
                   -30, 10, 15, 20, 20, 15, 10, -30, -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
    chess.BISHOP: [-20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 5, 5, 5, 5, 5, -10, -10, 5, 10, 15, 15, 10, 5, -10,
                   -10, 10, 10, 15, 15, 10, 10, -10, -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
    chess.ROOK: [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
                 -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0],
    chess.QUEEN: [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 5, 5, 5, 0, -10,
                  -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
    chess.KING: [-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -20, -30, -30, -40, -40, -30, -30, -20,
                 -10, -20, -20, -20, -20, -20, -20, -10, 20, 20, 10, 0, 0, 10, 20, 20, 20, 20, 10, 0, 0, 10, 20, 20]
}

def evaluate(board, learning_data=None):
    try:
        if board.is_checkmate():
            return -99999 if board.turn == chess.WHITE else 99999
        if board.is_stalemate() or board.is_insufficient_material():
            return 0

        score = 0
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                value = PIECE_VALUES[piece.piece_type]
                psqt = PIECE_SQUARE_TABLES[piece.piece_type]
                idx = square if piece.color == chess.WHITE else 63 - square
                weight = learning_data["weights"].get("pawn" if piece.piece_type == chess.PAWN else "king" if piece.piece_type == chess.KING else "mobility", 1.0) if learning_data else 1.0
                score += (value + psqt[idx]) * weight if piece.color == chess.WHITE else -(value + psqt[idx]) * weight

        mobility = len(list(board.legal_moves)) * 5 * (learning_data["weights"].get("mobility", 1.0) if learning_data else 1.0)
        score += mobility if board.turn == chess.WHITE else -mobility

        return score
    except Exception as e:
        logging.error(f"Evaluation failed: {e}")
        return 0

def alpha_beta(board, depth, alpha, beta, maximizing, learning_data=None):
    try:
        if depth == 0 or board.is_game_over():
            return evaluate(board, learning_data), None

        best_move = None
        moves = list(board.legal_moves)
        for move in moves:
            board.push(move)
            eval_score, _ = alpha_beta(board, depth - 1, alpha, beta, not maximizing, learning_data)
            board.pop()
            if maximizing:
                if eval_score > alpha:
                    alpha = eval_score
                    best_move = move
                if alpha >= beta:
                    break
            else:
                if eval_score < beta:
                    beta = eval_score
                    best_move = move
                if beta <= alpha:
                    break
        return alpha if maximizing else beta, best_move
    except Exception as e:
        logging.error(f"Alpha-beta search failed: {e}")
        return 0, None

def get_bot_move(board, difficulty, learning_data=None):
    try:
        experience = learning_data["games"] if learning_data and learning_data["games"] > 0 else 0
        depth = min(6, max(2, 2 + experience // 10))
        if experience < 20 and os.path.exists("polyglot.bin"):
            with chess.polyglot.open_reader("polyglot.bin") as reader:
                entries = list(reader.find_all(board))
                if entries:
                    return max(entries, key=lambda e: e.weight).move
        _, move = alpha_beta(board, depth, -float('inf'), float('inf'), board.turn == chess.WHITE, learning_data)
        return move
    except Exception as e:
        logging.error(f"Bot move generation failed: {e}")
        return random.choice(list(board.legal_moves)) if board.legal_moves else None

# --- PUZZLES (Static Example) ---
PUZZLES = [
    {"fen": "rnbqkb1r/pppp1ppp/5n2/5p2/5P2/5N2/PPPP1PPP/RNBQKB1R w KQkq - 1 2", "move": "e4", "solution": "e5"},
    {"fen": "rnbqkbnr/pppp1ppp/5n2/5p2/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2", "move": "e5", "solution": "Nf3"}
]

# --- GUI ---
class ChessApp:
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("Chess by Maxence - Inspired by Chess.com")
            self.board = chess.Board()
            self.selected_square = None
            self.possible_moves = []
            self.move_history = []
            self.captured_pieces = {chess.WHITE: [], chess.BLACK: []}
            self.current_theme = "Chess.com"
            self.timer = {"white": 600, "black": 600}
            self.timer_running = False
            self.timer_id = None  # To track timer after calls
            self.difficulty = 3
            self.game = chess.pgn.Game()
            self.board_flipped = False
            self.evaluations = []
            self.puzzle_mode = False
            self.current_puzzle = None
            self.best_moves = []
            self.player_moves = []
            self.animations_enabled = True
            self.learning_data = {"weights": {"pawn": 1.0, "king": 1.0, "mobility": 1.0}, "games": 0, "performance": 0.5, "elo": 1500}
            self.multiplayer_mode = False
            self.is_host = False
            self.player_color = chess.WHITE
            self.server_socket = None
            self.client_socket = None
            self.opponent_socket = None
            self.server_thread = None
            self.listen_thread = None
            self.game_port = None
            self.ngrok_url = None
            self.thread_lock = threading.Lock()  # For thread safety

            self.main_frame = tk.Frame(root, bg=THEMES[self.current_theme]["bg"], padx=10, pady=10)
            self.main_frame.pack(fill="both", expand=True)

            self.canvas = tk.Canvas(self.main_frame, width=BOARD_SIZE+40, height=BOARD_SIZE+40, bg=THEMES[self.current_theme]["border"], highlightthickness=2, highlightbackground=THEMES[self.current_theme]["text"])
            self.canvas.pack(side="left", padx=10, pady=10)
            self.canvas.bind("<Button-1>", self.on_click)

            self.sidebar = tk.Frame(self.main_frame, bg=THEMES[self.current_theme]["bg"], width=300, padx=5, pady=5)
            self.sidebar.pack(side="right", fill="y", padx=10, pady=10)

            self.status_label = tk.Label(self.main_frame, text="White's turn", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 12, "bold"))
            self.status_label.pack(side="bottom", fill="x", padx=10, pady=5)

            tk.Label(self.sidebar, text="Move History", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10, "bold")).pack(pady=(5, 0))
            ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", pady=2)
            self.move_listbox = tk.Listbox(self.sidebar, height=10, width=30, font=("Arial", 9), bg="#333333", fg=THEMES[self.current_theme]["text"], highlightthickness=0)
            self.move_listbox.pack(pady=(0, 5))

            tk.Label(self.sidebar, text="Captured Pieces", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10, "bold")).pack(pady=(5, 0))
            ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", pady=2)
            self.captured_white = tk.Label(self.sidebar, text="White Captures: ", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10))
            self.captured_white.pack(pady=2)
            self.captured_black = tk.Label(self.sidebar, text="Black Captures: ", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10))
            self.captured_black.pack(pady=2)

            tk.Label(self.sidebar, text="Timer", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10, "bold")).pack(pady=(5, 0))
            ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", pady=2)
            self.timer_label = tk.Label(self.sidebar, text="White: 10:00 | Black: 10:00", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10))
            self.timer_label.pack(pady=5)

            self.eval_label = tk.Label(self.sidebar, text="Evaluation: 0.0", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"], font=("Arial", 10))
            self.eval_label.pack(pady=5)

            controls = [
                ("New Game", self.new_game, "Start a new game"),
                ("Host Multiplayer", self.host_multiplayer, "Host a multiplayer game"),
                ("Join Multiplayer", self.join_multiplayer, "Join a multiplayer game"),
                ("Undo Move", self.undo_move, "Undo the last move"),
                ("Get Hint", self.get_hint, "Get a suggested move"),
                ("Resign", self.resign, "Resign the game"),
                ("Offer Draw", self.offer_draw, "Offer a draw"),
                ("Save Game", self.save_game, "Save game as PGN"),
                ("Load Game", self.load_game, "Load a PGN game"),
                ("Flip Board", self.flip_board, "Flip board perspective"),
                ("Start Puzzle", self.start_puzzle, "Start a puzzle"),
                ("Analyze Game", self.analyze_game, "Analyze the current game"),
                ("Deep Analysis", self.deep_analysis, "Perform a detailed analysis"),
                ("Save Analysis", self.save_analysis, "Save detailed analysis to file"),
                ("Toggle Animation", self.toggle_animation, "Enable/Disable animations")
            ]
            for text, cmd, _ in controls:
                btn = tk.Button(self.sidebar, text=text, command=cmd, width=20, bg=THEMES[self.current_theme]["button"], fg="#FFFFFF", font=("Arial", 9), relief="flat", bd=1)
                btn.pack(pady=2)

            self.theme_var = tk.StringVar(value="Chess.com")
            ttk.Combobox(self.sidebar, textvariable=self.theme_var, values=list(THEMES.keys()), state="readonly", width=18, font=("Arial", 9)).pack(pady=5)
            self.theme_var.trace("w", self.change_theme)
            self.difficulty_var = tk.StringVar(value="3")
            ttk.Combobox(self.sidebar, textvariable=self.difficulty_var, values=["1", "2", "3", "4", "5"], state="readonly", width=18, font=("Arial", 9)).pack(pady=5)
            self.difficulty_var.trace("w", self.change_difficulty)

            self.load_learning_data()
            logging.info("--- New Game Started ---")
            self.draw_board()
            self.update_pieces()
            self.update_timer()
        except Exception as e:
            logging.error(f"Initialization failed: {e}")
            messagebox.showerror("Error", f"Initialization failed: {e}")

    def host_multiplayer(self):
        try:
            if self.multiplayer_mode:
                messagebox.showwarning("Warning", "Already in a multiplayer game!")
                return

            self.cleanup_multiplayer()  # Ensure previous connections are closed
            self.multiplayer_mode = True
            self.is_host = True
            self.player_color = chess.WHITE
            self.board_flipped = False
            self.new_game()

            # Generate a random port and start server
            self.game_port = 5000 + random.randint(0, 1000)
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(SOCKET_TIMEOUT)
            self.server_socket.bind(('0.0.0.0', self.game_port))
            self.server_socket.listen(1)

            # Optional ngrok for public access
            use_ngrok = messagebox.askyesno("ngrok", "Use ngrok for public link? (Requires internet)")
            if use_ngrok:
                try:
                    public_url = ngrok.connect(self.game_port, "tcp")
                    self.ngrok_url = public_url.public_url
                    link = self.ngrok_url.replace("tcp://", "http://")
                except Exception as e:
                    logging.error(f"ngrok failed: {e}")
                    messagebox.showerror("Error", "Failed to create ngrok link. Using local IP instead.")
                    host_ip = socket.gethostbyname(socket.gethostname())
                    link = f"http://{host_ip}:{self.game_port}"
            else:
                host_ip = socket.gethostbyname(socket.gethostname())
                link = f"http://{host_ip}:{self.game_port}"

            messagebox.showinfo("Hosting", f"Share this link with your opponent:\n{link}")
            self.server_thread = threading.Thread(target=self.accept_connection)
            self.server_thread.daemon = True
            self.server_thread.start()
            logging.info(f"Hosting game on {link}")

        except Exception as e:
            logging.error(f"Host multiplayer failed: {e}")
            messagebox.showerror("Error", f"Host multiplayer failed: {e}")
            self.cleanup_multiplayer()

    def accept_connection(self):
        try:
            self.opponent_socket, addr = self.server_socket.accept()
            self.opponent_socket.settimeout(SOCKET_TIMEOUT)
            logging.info(f"Opponent connected from {addr}")
            self.root.after(0, lambda: self.status_label.config(text="Opponent connected! Your turn as White."))
            self.listen_thread = threading.Thread(target=self.listen_for_moves)
            self.listen_thread.daemon = True
            self.listen_thread.start()
        except socket.timeout:
            logging.error("Accept connection timed out")
            self.root.after(0, lambda: messagebox.showerror("Error", "Connection timed out while waiting for opponent"))
            self.root.after(0, self.cleanup_multiplayer)
        except Exception as e:
            logging.error(f"Accept connection failed: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Accept connection failed: {e}"))
            self.root.after(0, self.cleanup_multiplayer)

    def join_multiplayer(self):
        try:
            if self.multiplayer_mode:
                messagebox.showwarning("Warning", "Already in a multiplayer game!")
                return

            dialog = tk.Toplevel(self.root)
            dialog.title("Join Multiplayer Game")
            dialog.geometry("300x150")
            dialog.config(bg=THEMES[self.current_theme]["bg"])

            tk.Label(dialog, text="Enter Game Link:", bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"]).pack(pady=5)
            link_entry = tk.Entry(dialog, width=40)
            link_entry.pack(pady=5)
            link_entry.insert(0, "http://localhost:5000")  # Default for testing

            def join_game():
                link = link_entry.get().strip()
                if not link:
                    messagebox.showerror("Error", "Link cannot be empty!")
                    return
                try:
                    import re
                    match = re.search(r'http://([\w\.-]+):(\d+)', link)
                    if not match:
                        messagebox.showerror("Error", "Invalid link format! Expected http://<host>:<port>")
                        return
                    host, port = match.groups()
                    port = int(port)
                    self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.client_socket.settimeout(SOCKET_TIMEOUT)
                    self.client_socket.connect((host, port))
                    self.multiplayer_mode = True
                    self.is_host = False
                    self.player_color = chess.BLACK
                    self.board_flipped = True
                    self.new_game()
                    dialog.destroy()
                    self.status_label.config(text="Connected! Waiting for White's move.")
                    self.listen_thread = threading.Thread(target=self.listen_for_moves)
                    self.listen_thread.daemon = True
                    self.listen_thread.start()
                except socket.timeout:
                    logging.error("Connection timed out")
                    messagebox.showerror("Error", "Connection timed out while joining game")
                    self.cleanup_multiplayer()
                except Exception as e:
                    logging.error(f"Join game failed: {e}")
                    messagebox.showerror("Error", f"Join game failed: {e}")
                    self.cleanup_multiplayer()

            tk.Button(dialog, text="Join Game", command=join_game, bg=THEMES[self.current_theme]["button"], fg="#FFFFFF").pack(pady=10)
        except Exception as e:
            logging.error(f"Join multiplayer failed: {e}")
            messagebox.showerror("Error", f"Join multiplayer failed: {e}")

    def listen_for_moves(self):
        try:
            while self.multiplayer_mode:
                with self.thread_lock:
                    socket_to_use = self.opponent_socket if self.is_host else self.client_socket
                    if socket_to_use is None:
                        break
                data = socket_to_use.recv(1024)
                if not data:
                    self.root.after(0, lambda: messagebox.showinfo("Disconnected", "Opponent disconnected!"))
                    self.root.after(0, self.cleanup_multiplayer)
                    break
                try:
                    move = pickle.loads(data)
                    if not isinstance(move, chess.Move) or not self.board.is_legal(move):
                        logging.error("Invalid move received")
                        continue
                    self.root.after(0, lambda: self.receive_move(move))
                except pickle.PickleError as e:
                    logging.error(f"Invalid data received: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Error", "Invalid move data received"))
        except socket.timeout:
            logging.error("Listen for moves timed out")
            self.root.after(0, lambda: messagebox.showerror("Error", "Connection timed out"))
            self.root.after(0, self.cleanup_multiplayer)
        except Exception as e:
            logging.error(f"Listen for moves failed: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Listen for moves failed: {e}"))
            self.root.after(0, self.cleanup_multiplayer)

    def receive_move(self, move):
        try:
            captured_piece = self.board.piece_at(move.to_square)
            if captured_piece:
                self.captured_pieces[self.board.turn].append(captured_piece.piece_type)
            self.animate_move(move.from_square, move.to_square)
            san = self.board.san(move)
            self.board.push(move)
            self.move_history.append(move)
            self.update_pieces()
            logging.info(f"Received move: {san}")
            self.status_label.config(text="Your turn!" if self.board.turn == self.player_color else "Waiting for opponent's move...")
            if self.board.is_game_over():
                self.status_label.config(text=f"Game Over: {self.board.result()}")
        except Exception as e:
            logging.error(f"Receive move failed: {e}")
            messagebox.showerror("Error", f"Receive move failed: {e}")

    def send_move(self, move):
        try:
            socket_to_use = self.opponent_socket if self.is_host else self.client_socket
            if socket_to_use:
                socket_to_use.send(pickle.dumps(move))
                logging.info(f"Sent move: {move.uci()}")
                self.status_label.config(text="Waiting for opponent's move...")
        except socket.timeout:
            logging.error("Send move timed out")
            messagebox.showerror("Error", "Connection timed out while sending move")
            self.cleanup_multiplayer()
        except Exception as e:
            logging.error(f"Send move failed: {e}")
            messagebox.showerror("Error", f"Send move failed: {e}")
            self.cleanup_multiplayer()

    def cleanup_multiplayer(self):
        try:
            with self.thread_lock:
                self.multiplayer_mode = False
                self.is_host = False
                self.player_color = chess.WHITE
                if self.server_socket:
                    self.server_socket.close()
                    self.server_socket = None
                if self.client_socket:
                    self.client_socket.close()
                    self.client_socket = None
                if self.opponent_socket:
                    self.opponent_socket.close()
                    self.opponent_socket = None
                if self.ngrok_url:
                    try:
                        ngrok.disconnect(self.ngrok_url)
                    except:
                        pass
                    self.ngrok_url = None
                self.server_thread = None
                self.listen_thread = None
            self.new_game()
        except Exception as e:
            logging.error(f"Cleanup multiplayer failed: {e}")

    def draw_board(self):
        try:
            self.canvas.delete("all")
            self.canvas.create_rectangle(0, 0, BOARD_SIZE+40, BOARD_SIZE+40, fill=THEMES[self.current_theme]["border"], outline=THEMES[self.current_theme]["text"], width=2)
            for row in range(8):
                for col in range(8):
                    board_row = 7 - row if not self.board_flipped else row
                    board_col = col if not self.board_flipped else 7 - col
                    color = THEMES[self.current_theme]["light" if (board_row + board_col) % 2 == 0 else "dark"]
                    self.canvas.create_rectangle(
                        col*SQUARE_SIZE + 20, row*SQUARE_SIZE + 20,
                        (col+1)*SQUARE_SIZE + 20, (row+1)*SQUARE_SIZE + 20,
                        fill=color, outline="", tags="square"
                    )
            for i in range(8):
                row_label = str(8 - i) if not self.board_flipped else str(i + 1)
                col_label = chr(97 + i) if not self.board_flipped else chr(104 - i)
                self.canvas.create_text(10, i*SQUARE_SIZE + SQUARE_SIZE//2 + 20, text=row_label, font=("Arial", 12, "bold"), fill=THEMES[self.current_theme]["text"])
                self.canvas.create_text(i*SQUARE_SIZE + SQUARE_SIZE//2 + 20, BOARD_SIZE + 30, text=col_label, font=("Arial", 12, "bold"), fill=THEMES[self.current_theme]["text"])
        except Exception as e:
            logging.error(f"Draw board failed: {e}")
            messagebox.showerror("Error", f"Draw board failed: {e}")

    def animate_move(self, from_square, to_square):
        try:
            if not self.animations_enabled:
                self.update_pieces()
                return

            from_row = 7 - (from_square // 8) if not self.board_flipped else (from_square // 8)
            from_col = from_square % 8 if not self.board_flipped else 7 - (from_square % 8)
            to_row = 7 - (to_square // 8) if not self.board_flipped else (to_square // 8)
            to_col = to_square % 8 if not self.board_flipped else 7 - (to_square % 8)

            steps = ANIMATION_STEPS
            dx = (to_col - from_col) * SQUARE_SIZE / steps
            dy = (to_row - from_row) * SQUARE_SIZE / steps

            piece = self.board.piece_at(from_square)
            if not piece:
                logging.error(f"No piece found at from_square {from_square}")
                return
            symbol = PIECES_UNICODE.get(piece.symbol(), "♟")
            x, y = from_col * SQUARE_SIZE + SQUARE_SIZE//2 + 20, from_row * SQUARE_SIZE + SQUARE_SIZE//2 + 20
            piece_id = self.canvas.create_text(x, y, text=symbol, font=("Arial", 40), tags="moving_piece")
            for i in range(steps + 1):
                self.canvas.coords(piece_id, x + i * dx, y + i * dy)
                self.root.update()
                time.sleep(ANIMATION_SPEED / 1000)
            self.canvas.delete("moving_piece")
            self.update_pieces()
        except Exception as e:
            logging.error(f"Animate move failed: {e}")
            messagebox.showerror("Error", f"Animate move failed: {e}")

    def update_pieces(self):
        try:
            self.canvas.delete("piece")
            self.canvas.delete("highlight")
            self.canvas.delete("moving_piece")

            for square in chess.SQUARES:
                piece = self.board.piece_at(square)
                if piece:
                    row = 7 - (square // 8) if not self.board_flipped else (square // 8)
                    col = square % 8 if not self.board_flipped else 7 - (square % 8)
                    symbol = PIECES_UNICODE.get(piece.symbol(), "♟")
                    x, y = col*SQUARE_SIZE + SQUARE_SIZE//2 + 20, row*SQUARE_SIZE + SQUARE_SIZE//2 + 20
                    self.canvas.create_text(x, y, text=symbol, font=("Arial", 40), tags="piece")

            if self.selected_square is not None and self.possible_moves:
                for move in self.possible_moves:
                    to_sq = move.to_square
                    row = 7 - (to_sq // 8) if not self.board_flipped else (to_sq // 8)
                    col = to_sq % 8 if not self.board_flipped else 7 - (to_sq % 8)
                    x = col*SQUARE_SIZE + SQUARE_SIZE//2 + 20
                    y = row*SQUARE_SIZE + SQUARE_SIZE//2 + 20
                    self.canvas.create_oval(
                        x-16, y-16, x+16, y+16, fill=THEMES[self.current_theme]["highlight"], outline="", tags="highlight"
                    )

            self.update_captured_pieces()
            self.update_move_history()
            self.update_status()
            self.update_evaluation()
        except Exception as e:
            logging.error(f"Update pieces failed: {e}")
            messagebox.showerror("Error", f"Update pieces failed: {e}")

    def update_captured_pieces(self):
        try:
            white_captured = "".join(PIECES_UNICODE.get(chess.piece_symbol(p).upper(), "♟") for p in sorted(self.captured_pieces[chess.WHITE], reverse=True))
            black_captured = "".join(PIECES_UNICODE.get(chess.piece_symbol(p), "♟") for p in sorted(self.captured_pieces[chess.BLACK], reverse=True))
            self.captured_white.config(text=f"White Captures: {white_captured}")
            self.captured_black.config(text=f"Black Captures: {black_captured}")
        except Exception as e:
            logging.error(f"Update captured pieces failed: {e}")
            messagebox.showerror("Error", f"Update captured pieces failed: {e}")

    def update_move_history(self):
        try:
            self.move_listbox.delete(0, tk.END)
            temp_board = chess.Board()
            move_number = 1
            for i, move in enumerate(self.move_history):
                san = temp_board.san(move)
                eval_text = f" ({self.evaluations[i]/100:+.1f})" if i < len(self.evaluations) else ""
                if move_number % 2 == 1:
                    self.move_listbox.insert(tk.END, f"{move_number//2 + 1}. {san}{eval_text}")
                else:
                    self.move_listbox.insert(tk.END, f"   {san}{eval_text}")
                temp_board.push(move)
                move_number += 1
        except Exception as e:
            logging.error(f"Update move history failed: {e}")
            messagebox.showerror("Error", f"Update move history failed: {e}")

    def update_evaluation(self):
        try:
            score = evaluate(self.board, self.learning_data)
            if score is not None:
                score = score / 100.0
                self.eval_label.config(text=f"Evaluation: {score:+.1f}")
            else:
                self.eval_label.config(text="Evaluation: N/A")
        except Exception as e:
            logging.error(f"Evaluation update failed: {e}")
            self.eval_label.config(text="Evaluation: N/A")

    def update_status(self):
        try:
            if self.board.is_game_over():
                self.status_label.config(text=f"Game Over: {self.board.result()}", fg="#4CAF50")
                self.analyze_game_end()
            else:
                turn = "White" if self.board.turn == chess.WHITE else "Black"
                state = " (Check)" if self.board.is_check() else ""
                if self.multiplayer_mode:
                    if self.board.turn == self.player_color:
                        self.status_label.config(text=f"Your turn ({turn}){state}", fg="#D32F2F" if self.board.is_check() else THEMES[self.current_theme]["text"])
                    else:
                        self.status_label.config(text=f"Waiting for opponent's move ({turn}){state}", fg="#D32F2F" if self.board.is_check() else THEMES[self.current_theme]["text"])
                else:
                    self.status_label.config(text=f"{turn}'s turn{state}", fg="#D32F2F" if self.board.is_check() else THEMES[self.current_theme]["text"])
        except Exception as e:
            logging.error(f"Update status failed: {e}")
            messagebox.showerror("Error", f"Update status failed: {e}")

    def update_timer(self):
        try:
            if self.timer_running and not self.board.is_game_over():
                if self.board.turn == chess.WHITE:
                    self.timer["white"] -= 0.1
                else:
                    self.timer["black"] -= 0.1
                white_time = max(0, self.timer["white"])
                black_time = max(0, self.timer["black"])
                self.timer_label.config(
                    text=f"White: {int(white_time//60)}:{int(white_time%60):02d} | Black: {int(black_time//60)}:{int(black_time%60):02d}"
                )
                if white_time <= 0 or black_time <= 0:
                    winner = "Black" if white_time <= 0 else "White"
                    messagebox.showinfo("Time Out", f"{winner} wins on time!")
                    self.new_game()
                    logging.info(f"Game ended: {winner} wins on time")
                else:
                    self.timer_id = self.root.after(100, self.update_timer)
        except Exception as e:
            logging.error(f"Update timer failed: {e}")
            messagebox.showerror("Error", f"Update timer failed: {e}")

    def stop_timer(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.timer_running = False

    def on_click(self, event):
        try:
            if self.board.is_game_over() or self.puzzle_mode:
                messagebox.showinfo("Info", "Game Over or Puzzle Mode active" if self.board.is_game_over() else "Solve the puzzle first")
                logging.info(f"Click ignored: Game Over or Puzzle Mode")
                return

            if self.multiplayer_mode and self.board.turn != self.player_color:
                messagebox.showinfo("Info", "It's not your turn!")
                return

            col = (event.x - 20) // SQUARE_SIZE
            row = (event.y - 20) // SQUARE_SIZE
            if not (0 <= col < 8 and 0 <= row < 8):
                logging.info(f"Click outside board at ({event.x}, {event.y})")
                self.selected_square = None
                self.possible_moves = []
                self.update_pieces()
                return

            board_row = 7 - row if not self.board_flipped else row
            board_col = col if not self.board_flipped else 7 - col
            square = board_row * 8 + board_col

            logging.info(f"Click at ({event.x}, {event.y}) -> Square {square}")
            print(f"Click at ({event.x}, {event.y}) -> Square {square}")

            if self.selected_square is None:
                piece = self.board.piece_at(square)
                if piece and piece.color == self.board.turn:
                    self.selected_square = square
                    self.possible_moves = [move for move in self.board.legal_moves if move.from_square == square and self.board.is_legal(move)]
                    logging.info(f"Selected square {square} with piece {piece.symbol()}")
                    print(f"Selected square {square} with piece {piece.symbol()}")
                else:
                    logging.info(f"No piece or wrong color at square {square}")
                    print(f"No piece or wrong color at square {square}")
            else:
                move = None
                for m in self.possible_moves:
                    if m.to_square == square and self.board.is_legal(m):
                        move = m
                        break
                if move:
                    if self.board.piece_at(move.from_square).piece_type == chess.PAWN and chess.square_rank(move.to_square) in [0, 7]:
                        self.promotion_dialog(move)
                    else:
                        self.handle_move(move)
                else:
                    logging.info(f"No valid move at square {square}, deselecting")
                    self.selected_square = None
                    self.possible_moves = []

            self.update_pieces()
        except Exception as e:
            logging.error(f"On click failed: {e}")
            messagebox.showerror("Error", f"On click failed: {e}")

    def promotion_dialog(self, move):
        try:
            dialog = tk.Toplevel(self.root)
            dialog.title("Choose Promotion")
            dialog.geometry("300x80")
            dialog.config(bg=THEMES[self.current_theme]["bg"])
            pieces = [(chess.QUEEN, "Queen"), (chess.ROOK, "Rook"), (chess.BISHOP, "Bishop"), (chess.KNIGHT, "Knight")]
            for piece_type, name in pieces:
                tk.Button(dialog, text=name, command=lambda pt=piece_type: self.set_promotion(move, pt, dialog), width=8, font=("Arial", 10), bg=THEMES[self.current_theme]["button"], fg="#FFFFFF").pack(side="left", padx=5, pady=5)
        except Exception as e:
            logging.error(f"Promotion dialog failed: {e}")
            messagebox.showerror("Error", f"Promotion dialog failed: {e}")

    def set_promotion(self, move, piece_type, dialog):
        try:
            dialog.destroy()
            self.handle_move(chess.Move(move.from_square, move.to_square, promotion=piece_type))
        except Exception as e:
            logging.error(f"Set promotion failed: {e}")
            messagebox.showerror("Error", f"Set promotion failed: {e}")

    def handle_move(self, move):
        try:
            if not self.multiplayer_mode:
                best_score, best_move = alpha_beta(self.board, self.difficulty + 1, -float('inf'), float('inf'), self.board.turn == chess.WHITE, self.learning_data)
                self.best_moves.append((best_move, best_score))
                self.player_moves.append(move)

            before_eval = evaluate(self.board, self.learning_data)
            captured_piece = self.board.piece_at(move.to_square)
            if captured_piece:
                self.captured_pieces[self.board.turn].append(captured_piece.piece_type)
            self.animate_move(move.from_square, move.to_square)
            san = self.board.san(move)
            self.board.push(move)
            after_eval = evaluate(self.board, self.learning_data)
            self.evaluations.append(before_eval - after_eval if self.board.turn == chess.BLACK else after_eval - before_eval)
            self.move_history.append(move)
            player = "Human" if self.board.turn == chess.BLACK else "AI"
            logging.info(f"Move: {san} by {player} | Eval: {after_eval/100:+.1f} | Board: {self.board.fen()}")
            print(f"Move: {san} by {player}")

            self.selected_square = None
            self.possible_moves = []

            if self.multiplayer_mode:
                self.send_move(move)
            else:
                self.timer_running = True
                if self.board.is_game_over():
                    messagebox.showinfo("Game Over", f"Result: {self.board.result()}")
                    logging.info(f"Game Over: {self.board.result()}")
                elif self.puzzle_mode and san != self.current_puzzle["solution"]:
                    messagebox.showinfo("Puzzle", "Wrong move! Try again.")
                    self.board.pop()
                    self.move_history.pop()
                    self.evaluations.pop()
                    self.best_moves.pop()
                    self.player_moves.pop()
                    self.captured_pieces[self.board.turn].pop() if captured_piece else None
                    self.update_pieces()
                else:
                    self.root.after(500, self.play_bot)
        except Exception as e:
            logging.error(f"Move processing failed: {e}")
            messagebox.showerror("Error", f"Move processing failed: {e}")

    def play_bot(self):
        try:
            if self.board.is_game_over() or self.puzzle_mode:
                return
            if self.board.turn == chess.BLACK:
                move = get_bot_move(self.board, self.difficulty, self.learning_data)
                if move:
                    self.handle_move(move)
                else:
                    logging.error("Bot failed to find a move")
                    messagebox.showerror("Error", "Bot failed to find a move")
        except Exception as e:
            logging.error(f"Bot move failed: {e}")
            messagebox.showerror("Error", f"Bot move failed: {e}")

    def new_game(self):
        try:
            self.stop_timer()
            self.board.reset()
            self.move_history = []
            self.captured_pieces = {chess.WHITE: [], chess.BLACK: []}
            self.evaluations = []
            self.best_moves = []
            self.player_moves = []
            self.timer = {"white": 600, "black": 600}
            self.timer_running = False
            self.game = chess.pgn.Game()
            self.puzzle_mode = False
            self.current_puzzle = None
            self.selected_square = None
            self.possible_moves = []
            if not self.multiplayer_mode:
                self.is_host = False
                self.player_color = chess.WHITE
                self.board_flipped = False
            self.canvas.delete("all")
            self.draw_board()
            self.update_pieces()
            self.update_timer()
            logging.info("--- New Game Started ---")
        except Exception as e:
            logging.error(f"New game failed: {e}")
            messagebox.showerror("Error", f"New game failed: {e}")

    def undo_move(self):
        try:
            if self.move_history and not self.puzzle_mode and not self.multiplayer_mode:
                self.board.pop()
                self.move_history.pop()
                self.evaluations.pop() if self.evaluations else None
                self.best_moves.pop() if self.best_moves else None
                self.player_moves.pop() if self.player_moves else None
                if self.captured_pieces[self.board.turn]:
                    self.captured_pieces[self.board.turn].pop()
                self.selected_square = None
                self.possible_moves = []
                self.update_pieces()
                logging.info("Move undone")
        except Exception as e:
            logging.error(f"Undo failed: {e}")
            messagebox.showerror("Error", f"Undo failed: {e}")

    def get_hint(self):
        try:
            if not self.board.is_game_over() and not self.puzzle_mode and not self.multiplayer_mode:
                move = get_bot_move(self.board, self.difficulty, self.learning_data)
                if move:
                    san = self.board.san(move)
                    messagebox.showinfo("Hint", f"Suggested move: {san}")
                    logging.info(f"Hint requested: {san}")
                else:
                    logging.error("Hint generation failed: No move found")
                    messagebox.showerror("Error", "No hint available")
        except Exception as e:
            logging.error(f"Hint generation failed: {e}")
            messagebox.showerror("Error", f"Hint generation failed: {e}")

    def resign(self):
        try:
            if not self.board.is_game_over() and not self.puzzle_mode:
                winner = "Black" if self.board.turn == chess.WHITE else "White"
                messagebox.showinfo("Resign", f"{winner} wins by resignation!")
                self.cleanup_multiplayer()
                self.new_game()
                logging.info(f"Game resigned: {winner} wins")
        except Exception as e:
            logging.error(f"Resign failed: {e}")
            messagebox.showerror("Error", f"Resign failed: {e}")

    def offer_draw(self):
        try:
            if not self.board.is_game_over() and not self.puzzle_mode:
                if messagebox.askyesno("Draw", "Offer a draw?"):
                    messagebox.showinfo("Draw", "Game ends in a draw!")
                    self.cleanup_multiplayer()
                    self.new_game()
                    logging.info("Game ended in a draw")
        except Exception as e:
            logging.error(f"Draw offer failed: {e}")
            messagebox.showerror("Error", f"Draw offer failed: {e}")

    def save_game(self):
        try:
            game = chess.pgn.Game()
            game.headers["Event"] = "Chess Game"
            game.headers["White"] = "Player"
            game.headers["Black"] = "AI" if not self.multiplayer_mode else "Opponent"
            game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
            node = game
            for move in self.move_history:
                node = node.add_variation(move)
            file = filedialog.asksaveasfilename(defaultextension=".pgn", filetypes=[("PGN files", "*.pgn")])
            if file:
                with open(file, "w") as f:
                    print(game, file=f)
                logging.info(f"Game saved to {file}")
        except Exception as e:
            logging.error(f"Failed to save game: {e}")
            messagebox.showerror("Error", f"Failed to save game: {e}")

    def load_game(self):
        try:
            file = filedialog.askopenfilename(filetypes=[("PGN files", "*.pgn")])
            if file:
                with open(file) as f:
                    game = chess.pgn.read_game(f)
                if game:
                    self.board.reset()
                    self.move_history = []
                    self.captured_pieces = {chess.WHITE: [], chess.BLACK: []}
                    self.evaluations = []
                    self.best_moves = []
                    self.player_moves = []
                    node = game
                    temp_board = chess.Board()
                    while node.variations:
                        move = node.variations[0].move
                        captured = temp_board.piece_at(move.to_square)
                        if captured:
                            self.captured_pieces[temp_board.turn].append(captured.piece_type)
                        san = temp_board.san(move)
                        temp_board.push(move)
                        after_eval = evaluate(temp_board, self.learning_data)
                        self.evaluations.append(evaluate(temp_board, self.learning_data) - after_eval if temp_board.turn == chess.BLACK else after_eval - evaluate(temp_board, self.learning_data))
                        self.board.push(move)
                        self.move_history.append(move)
                        node = node.variations[0]
                    self.selected_square = None
                    self.possible_moves = []
                    self.update_pieces()
                    logging.info(f"Game loaded from {file}")
        except Exception as e:
            logging.error(f"Failed to load game: {e}")
            messagebox.showerror("Error", f"Failed to load game: {e}")

    def flip_board(self):
        try:
            self.board_flipped = not self.board_flipped
            self.canvas.delete("all")
            self.draw_board()
            self.update_pieces()
            logging.info("Board flipped")
        except Exception as e:
            logging.error(f"Flip board failed: {e}")
            messagebox.showerror("Error", f"Flip board failed: {e}")

    def start_puzzle(self):
        try:
            if not self.board.is_game_over() and not self.puzzle_mode and not self.multiplayer_mode:
                self.current_puzzle = random.choice(PUZZLES)
                self.board.set_fen(self.current_puzzle["fen"])
                self.puzzle_mode = True
                self.move_history = []
                self.captured_pieces = {chess.WHITE: [], chess.BLACK: []}
                self.evaluations = []
                self.best_moves = []
                self.player_moves = []
                self.selected_square = None
                self.possible_moves = []
                self.canvas.delete("all")
                self.draw_board()
                messagebox.showinfo("Puzzle", f"Solve: Play {self.current_puzzle['move']} to start.")
                self.update_pieces()
                logging.info(f"Puzzle started: {self.current_puzzle['fen']}")
        except Exception as e:
            logging.error(f"Start puzzle failed: {e}")
            messagebox.showerror("Error", f"Start puzzle failed: {e}")

    def analyze_game(self):
        try:
            if self.board.is_game_over() or self.puzzle_mode:
                messagebox.showinfo("Analysis", f"Final Evaluation: {evaluate(self.board, self.learning_data)/100:+.1f}")
                logging.info(f"Game analyzed: {evaluate(self.board, self.learning_data)/100:+.1f}")
            else:
                messagebox.showwarning("Analysis", "Finish the game first!")
        except Exception as e:
            logging.error(f"Analyze game failed: {e}")
            messagebox.showerror("Error", f"Analyze game failed: {e}")

    def analyze_game_end(self):
        try:
            if not self.move_history or self.puzzle_mode:
                return

            total_moves = len(self.player_moves)
            accurate_moves = 0
            blunders = []
            temp_board = chess.Board()
            for i, (player_move, (best_move, best_score)) in enumerate(zip(self.player_moves, self.best_moves)):
                if player_move == best_move:
                    accurate_moves += 1
                else:
                    temp_board.push(player_move)
                    player_score = evaluate(temp_board, self.learning_data)
                    temp_board.pop()
                    temp_board.push(best_move)
                    best_score = evaluate(temp_board, self.learning_data)
                    temp_board.pop()
                    eval_diff = abs(player_score - best_score) / 100.0
                    if eval_diff > 3:
                        blunders.append((i + 1, temp_board.san(player_move), temp_board.san(best_move), eval_diff))
                temp_board.push(player_move)

            accuracy = (accurate_moves / total_moves * 100) if total_moves > 0 else 0
            result = {"1-0": 1, "0-1": 0, "1/2-1/2": 0.5}.get(self.board.result(), 0)
            expected_score = 1 / (1 + 10 ** ((self.learning_data["elo"] - 1500) / 400))
            performance = result - expected_score
            self.learning_data["elo"] = min(max(self.learning_data["elo"] + 20 * performance, 800), 2800)
            self.adjust_learning_weights(result)

            analysis = []
            analysis.append(f"Game Analysis - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            analysis.append(f"Result: {self.board.result()}")
            analysis.append(f"Estimated Elo: {int(self.learning_data['elo'])}")
            analysis.append(f"Accuracy: {accuracy:.1f}%")
            analysis.append(f"Accurate Moves: {accurate_moves}/{total_moves}")
            if blunders:
                analysis.append("\nMajor Blunders:")
                for move_num, played, best, diff in blunders:
                    analysis.append(f"Move {move_num}: Played {played}, Best was {best} (Eval diff: {diff:.1f})")
            else:
                analysis.append("\nNo major blunders! Well played.")

            analysis.append("\nSuggestions for Improvement:")
            if accuracy < 60:
                analysis.append("- Focus on finding the best moves by evaluating positions carefully.")
            if blunders:
                analysis.append("- Avoid blunders by double-checking moves that significantly change the evaluation.")
            if self.timer["white"] < 60 or self.timer["black"] < 60:
                analysis.append("- Manage your time better to avoid time pressure mistakes.")
            analysis.append("- Practice tactical puzzles to improve your calculation skills.")

            with open("lvl.txt", "a") as f:
                f.write("\n".join(analysis) + "\n\n")

            summary = f"Game Over!\nEstimated Elo: {int(self.learning_data['elo'])}\nAccuracy: {accuracy:.1f}%\nCheck lvl.txt for details."
            messagebox.showinfo("Game Analysis", summary)
            logging.info(f"Game analysis written to lvl.txt | Elo: {int(self.learning_data['elo'])} | Accuracy: {accuracy:.1f}%")
            self.save_learning_data()
        except Exception as e:
            logging.error(f"End game analysis failed: {e}")
            messagebox.showerror("Error", f"End game analysis failed: {e}")

    def deep_analysis(self):
        try:
            if not self.move_history or self.puzzle_mode:
                messagebox.showwarning("Analysis", "No moves to analyze or puzzle mode active!")
                return

            total_moves = len(self.player_moves)
            accurate_moves = 0
            blunders = []
            missed_opportunities = []
            temp_board = chess.Board()
            for i, (player_move, (best_move, best_score)) in enumerate(zip(self.player_moves, self.best_moves)):
                if player_move == best_move:
                    accurate_moves += 1
                else:
                    temp_board.push(player_move)
                    player_score = evaluate(temp_board, self.learning_data)
                    temp_board.pop()
                    temp_board.push(best_move)
                    best_score = evaluate(temp_board, self.learning_data)
                    temp_board.pop()
                    eval_diff = abs(player_score - best_score) / 100.0
                    if eval_diff > 3:
                        blunders.append((i + 1, temp_board.san(player_move), temp_board.san(best_move), eval_diff))
                    if eval_diff > 1:
                        missed_opportunities.append((i + 1, temp_board.san(player_move), temp_board.san(best_move), eval_diff))
                temp_board.push(player_move)

            accuracy = (accurate_moves / total_moves * 100) if total_moves > 0 else 0
            result = {"1-0": 1, "0-1": 0, "1/2-1/2": 0.5}.get(self.board.result(), 0)
            elo = 800 + (accuracy * 10) + (result * 200) + (self.difficulty * 50)
            elo = min(max(int(elo), 800), 2800)

            analysis = []
            analysis.append(f"Detailed Game Analysis - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            analysis.append(f"Result: {self.board.result()}")
            analysis.append(f"Estimated Elo: {elo}")
            analysis.append(f"Accuracy: {accuracy:.1f}%")
            analysis.append(f"Accurate Moves: {accurate_moves}/{total_moves}")
            if blunders:
                analysis.append("\nMajor Blunders:")
                for move_num, played, best, diff in blunders:
                    analysis.append(f"Move {move_num}: Played {played}, Best was {best} (Eval diff: {diff:.1f})")
            if missed_opportunities:
                analysis.append("\nMissed Opportunities:")
                for move_num, played, best, diff in missed_opportunities:
                    analysis.append(f"Move {move_num}: Played {played}, Best was {best} (Eval diff: {diff:.1f})")
            analysis.append("\nMove-by-Move Evaluation:")
            temp_board = chess.Board()
            for i, move in enumerate(self.move_history):
                san = temp_board.san(move)
                temp_board.push(move)
                eval_score = evaluate(temp_board, self.learning_data) / 100.0
                analysis.append(f"Move {i+1}: {san} (Eval: {eval_score:+.1f})")

            self.last_deep_analysis = analysis
            messagebox.showinfo("Deep Analysis", "\n".join(analysis[:10]) + "\n\nFull details available to save in analysis.txt")
            logging.info("Deep analysis performed")
        except Exception as e:
            logging.error(f"Deep analysis failed: {e}")
            messagebox.showerror("Error", f"Deep analysis failed: {e}")

    def save_analysis(self):
        try:
            if not hasattr(self, 'last_deep_analysis'):
                messagebox.showwarning("Save Analysis", "Perform a deep analysis first!")
                return
            with open("analysis.txt", "a") as f:
                f.write("\n".join(self.last_deep_analysis) + "\n\n")
            messagebox.showinfo("Save Analysis", "Analysis saved to analysis.txt")
            logging.info("Deep analysis saved to analysis.txt")
        except Exception as e:
            logging.error(f"Save analysis failed: {e}")
            messagebox.showerror("Error", f"Save analysis failed: {e}")

    def toggle_animation(self):
        try:
            self.animations_enabled = not self.animations_enabled
            state = "enabled" if self.animations_enabled else "disabled"
            messagebox.showinfo("Animations", f"Animations {state}")
            logging.info(f"Animations {state}")
        except Exception as e:
            logging.error(f"Toggle animation failed: {e}")
            messagebox.showerror("Error", f"Toggle animation failed: {e}")

    def change_theme(self, *args):
        try:
            self.current_theme = self.theme_var.get()
            self.main_frame.config(bg=THEMES[self.current_theme]["bg"])
            self.canvas.config(bg=THEMES[self.current_theme]["border"])
            self.sidebar.config(bg=THEMES[self.current_theme]["bg"])
            self.status_label.config(bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"])
            self.timer_label.config(bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"])
            self.eval_label.config(bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"])
            self.move_listbox.config(bg="#333333", fg=THEMES[self.current_theme]["text"])
            for widget in self.sidebar.winfo_children():
                if isinstance(widget, tk.Button):
                    widget.config(bg=THEMES[self.current_theme]["button"], fg="#FFFFFF")
                elif isinstance(widget, tk.Label):
                    widget.config(bg=THEMES[self.current_theme]["bg"], fg=THEMES[self.current_theme]["text"])
                elif isinstance(widget, ttk.Combobox):
                    widget.config(background=THEMES[self.current_theme]["bg"])
            self.canvas.delete("all")
            self.draw_board()
            self.update_pieces()
            logging.info(f"Theme changed to {self.current_theme}")
        except Exception as e:
            logging.error(f"Theme change failed: {e}")
            messagebox.showerror("Error", f"Theme change failed: {e}")

    def change_difficulty(self, *args):
        try:
            self.difficulty = int(self.difficulty_var.get())
            logging.info(f"Difficulty changed to {self.difficulty}")
        except ValueError:
            self.difficulty = 3
            messagebox.showwarning("Warning", "Invalid difficulty, defaulting to 3")
            logging.warning("Invalid difficulty, defaulting to 3")
        except Exception as e:
            logging.error(f"Difficulty change failed: {e}")
            self.difficulty = 3
            messagebox.showerror("Error", f"Difficulty change failed: {e}")

    def load_learning_data(self):
        try:
            if os.path.exists("learning_data.json"):
                with open("learning_data.json", "r") as f:
                    content = f.read().strip()
                    if content:
                        self.learning_data = json.loads(content)
                    else:
                        logging.warning("learning_data.json is empty, using default.")
                        self.save_learning_data()
            else:
                logging.info("learning_data.json not found, creating default.")
                self.save_learning_data()
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding learning_data.json: {e}")
            self.save_learning_data()
        except Exception as e:
            logging.error(f"Load learning data failed: {e}")
            self.save_learning_data()

    def save_learning_data(self):
        try:
            with open("learning_data.json", "w") as f:
                json.dump(self.learning_data, f, indent=4)
        except Exception as e:
            logging.error(f"Save learning data failed: {e}")

    def adjust_learning_weights(self, result):
        try:
            expected = 1 / (1 + 10 ** ((self.learning_data["elo"] - 1500) / 400))
            error = result - expected
            for key in self.learning_data["weights"]:
                self.learning_data["weights"][key] += 0.01 * error
                self.learning_data["weights"][key] = max(0.1, min(2.0, self.learning_data["weights"][key]))
            self.learning_data["performance"] = (self.learning_data["performance"] * (self.learning_data["games"] - 1) + result) / self.learning_data["games"]
            self.learning_data["games"] += 1
        except Exception as e:
            logging.error(f"Adjust learning weights failed: {e}")

# --- MAIN ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ChessApp(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"Application failed: {e}")
        messagebox.showerror("Error", f"Application failed: {e}")
