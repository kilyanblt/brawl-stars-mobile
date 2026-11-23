import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.brawlstars.com/v1"
API_TOKEN = os.getenv("BRAWL_STARS_API_TOKEN", "").strip()


class BrawlAPIError(Exception):
    pass


class BrawlStarsClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "BrawlStarsStatsDesktop/1.0"
        })

    @staticmethod
    def normalize_tag(tag: str) -> str:
        tag = tag.strip().upper().replace(" ", "")
        if not tag:
            raise ValueError("Entre un tag de joueur.")
        if not tag.startswith("#"):
            tag = "#" + tag
        return tag

    def _get(self, endpoint: str) -> dict[str, Any]:
        url = f"{API_BASE}{endpoint}"
        try:
            response = self.session.get(url, timeout=15)
        except requests.RequestException as exc:
            raise BrawlAPIError(f"Erreur réseau : {exc}") from exc

        if response.status_code == 401:
            raise BrawlAPIError("Token API invalide ou absent (401).")
        if response.status_code == 403:
            raise BrawlAPIError(
                "Accès refusé (403). Vérifie ton token et l'adresse IP autorisée "
                "dans le portail développeur Supercell."
            )
        if response.status_code == 404:
            raise BrawlAPIError("Joueur introuvable. Vérifie son tag.")
        if response.status_code == 429:
            raise BrawlAPIError("Trop de requêtes. Attends un peu avant de réessayer.")
        if not response.ok:
            raise BrawlAPIError(f"Erreur API {response.status_code} : {response.text[:250]}")
        try:
            return response.json()
        except ValueError as exc:
            raise BrawlAPIError("La réponse de l'API n'est pas un JSON valide.") from exc

    def get_player(self, tag: str) -> dict[str, Any]:
        normalized = self.normalize_tag(tag)
        encoded_tag = normalized.replace("#", "%23")
        return self._get(f"/players/{encoded_tag}")

    def get_battle_log(self, tag: str) -> dict[str, Any]:
        normalized = self.normalize_tag(tag)
        encoded_tag = normalized.replace("#", "%23")
        return self._get(f"/players/{encoded_tag}/battlelog")


class BrawlStarsApp(tk.Tk):
    BG = "#101116"
    PANEL = "#1a1c25"
    RED = "#e53955"
    TEXT = "#f4f4f6"
    MUTED = "#a6a8b3"

    def __init__(self):
        super().__init__()
        self.title("Brawl Stars Stats")
        self.geometry("900x680")
        self.minsize(760, 580)
        self.configure(bg=self.BG)

        self.client = BrawlStarsClient(API_TOKEN) if API_TOKEN else None
        self.player_data = None

        self._style()
        self._build_ui()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=self.PANEL,
                        foreground=self.TEXT,
                        fieldbackground=self.PANEL,
                        rowheight=28,
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background="#292c38",
                        foreground=self.TEXT,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", self.RED)])
        style.configure("TProgressbar", troughcolor=self.PANEL,
                        background=self.RED, bordercolor=self.PANEL)

    def _build_ui(self):
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill="x", padx=26, pady=(22, 12))

        tk.Label(header, text="BRAWL STARS", bg=self.BG, fg=self.RED,
                 font=("Segoe UI Black", 25)).pack(anchor="w")
        tk.Label(header, text="PLAYER STATISTICS DASHBOARD",
                 bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 0))

        search = tk.Frame(self, bg=self.PANEL, padx=16, pady=14)
        search.pack(fill="x", padx=26, pady=10)

        tk.Label(search, text="TAG DU JOUEUR", bg=self.PANEL, fg=self.TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.tag_entry = tk.Entry(search, bg="#292c38", fg=self.TEXT,
                                  insertbackground=self.TEXT, relief="flat",
                                  font=("Segoe UI", 12), width=25)
        self.tag_entry.pack(side="left", padx=12, ipady=7)
        self.tag_entry.bind("<Return>", lambda _event: self.search_player())

        self.search_button = tk.Button(
            search, text="RECHERCHER", command=self.search_player,
            bg=self.RED, fg="white", activebackground="#c62843",
            activeforeground="white", relief="flat", padx=18, pady=9,
            font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.search_button.pack(side="left")

        self.status = tk.Label(self, text=self._initial_status(),
                               bg=self.BG, fg=self.MUTED,
                               font=("Segoe UI", 9))
        self.status.pack(anchor="w", padx=28, pady=(2, 8))

        self.profile = tk.Frame(self, bg=self.PANEL, padx=18, pady=16)
        self.profile.pack(fill="x", padx=26, pady=8)

        self.player_name = tk.Label(self.profile, text="Aucun joueur chargé",
                                    bg=self.PANEL, fg=self.TEXT,
                                    font=("Segoe UI", 19, "bold"))
        self.player_name.pack(anchor="w")
        self.player_meta = tk.Label(self.profile, text="Entre un tag pour afficher les statistiques.",
                                    bg=self.PANEL, fg=self.MUTED,
                                    font=("Segoe UI", 10))
        self.player_meta.pack(anchor="w", pady=(5, 0))

        stats = tk.Frame(self, bg=self.BG)
        stats.pack(fill="x", padx=26, pady=8)
        self.stat_labels = {}
        for key, title in [
            ("trophies", "TROPHÉES"),
            ("highest", "RECORD"),
            ("victories", "VICTOIRES 3c3"),
            ("solo", "VICTOIRES SOLO"),
        ]:
            card = tk.Frame(stats, bg=self.PANEL, padx=13, pady=13)
            card.pack(side="left", expand=True, fill="x", padx=(0, 8))
            tk.Label(card, text=title, bg=self.PANEL, fg=self.MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            value = tk.Label(card, text="--", bg=self.PANEL, fg=self.RED,
                             font=("Segoe UI", 20, "bold"))
            value.pack(anchor="w", pady=(5, 0))
            self.stat_labels[key] = value

        section = tk.Frame(self, bg=self.BG)
        section.pack(fill="both", expand=True, padx=26, pady=(12, 22))
        tk.Label(section, text="BRAWLERS DU JOUEUR", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        columns = ("name", "trophies", "highest", "power", "rank")
        self.tree = ttk.Treeview(section, columns=columns, show="headings")
        headings = {
            "name": "Brawler", "trophies": "Trophées",
            "highest": "Record", "power": "Puissance", "rank": "Rang"
        }
        widths = {"name": 280, "trophies": 110, "highest": 110, "power": 110, "rank": 90}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center")
        self.tree.column("name", anchor="w")
        self.tree.pack(fill="both", expand=True)

        footer = tk.Label(self, text="Projet fan-made. Non affilié à Supercell.",
                          bg=self.BG, fg="#777985", font=("Segoe UI", 8))
        footer.pack(anchor="e", padx=28, pady=(0, 10))

    def _initial_status(self):
        if self.client:
            return "API configurée. Prêt à rechercher un joueur."
        return "Token manquant. Ajoute BRAWL_STARS_API_TOKEN dans le fichier .env."

    def search_player(self):
        if not self.client:
            messagebox.showerror(
                "Configuration manquante",
                "Crée un fichier .env à côté de app.py et ajoute ton token API."
            )
            return
        tag = self.tag_entry.get().strip()
        if not tag:
            messagebox.showinfo("Tag requis", "Entre le tag d'un joueur.")
            return

        self.search_button.config(state="disabled", text="CHARGEMENT...")
        self.status.config(text="Récupération des données...", fg=self.MUTED)
        threading.Thread(target=self._load_player, args=(tag,), daemon=True).start()

    def _load_player(self, tag):
        try:
            data = self.client.get_player(tag)
            self.after(0, lambda: self._show_player(data))
        except (BrawlAPIError, ValueError) as exc:
            self.after(0, lambda: self._show_error(str(exc)))
        finally:
            self.after(0, lambda: self.search_button.config(
                state="normal", text="RECHERCHER"
            ))

    def _show_error(self, message):
        self.status.config(text=message, fg="#ff788b")
        messagebox.showerror("Erreur", message)

    def _show_player(self, data):
        self.player_data = data
        club = data.get("club") or {}
        club_text = f"Club : {club.get('name', 'Aucun')}"
        self.player_name.config(text=data.get("name", "Joueur inconnu"))
        self.player_meta.config(
            text=f"Tag : #{data.get('tag', '')}   |   {club_text}"
        )

        self.stat_labels["trophies"].config(text=f"{data.get('trophies', 0):,}".replace(",", " "))
        self.stat_labels["highest"].config(text=f"{data.get('highestTrophies', 0):,}".replace(",", " "))
        self.stat_labels["victories"].config(text=f"{data.get('3vs3Victories', 0):,}".replace(",", " "))
        self.stat_labels["solo"].config(text=f"{data.get('soloVictories', 0):,}".replace(",", " "))

        for item in self.tree.get_children():
            self.tree.delete(item)

        brawlers = data.get("brawlers", [])
        for brawler in sorted(brawlers, key=lambda b: b.get("trophies", 0), reverse=True):
            self.tree.insert("", "end", values=(
                brawler.get("name", "Inconnu"),
                brawler.get("trophies", 0),
                brawler.get("highestTrophies", 0),
                brawler.get("power", 0),
                brawler.get("rank", 0),
            ))

        self.status.config(
            text=f"Profil chargé. {len(brawlers)} brawlers trouvés.",
            fg="#69d69b"
        )


if __name__ == "__main__":
    app = BrawlStarsApp()
    app.mainloop()
