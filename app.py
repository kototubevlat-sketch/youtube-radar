import os
import json
import tkinter as tk
import re
import base64
import subprocess
import requests
from datetime import datetime, timedelta

import customtkinter as ctk


# ============================================================
# НАСТРОЙКИ
# ============================================================

SNAPSHOTS_FILE = os.path.join(
    "data",
    "snapshots.json"
)

AUTO_REFRESH_SECONDS = 30
CHANNELS_FILE = "channels.json"

# GitHub cloud sync. Keep the token OUT of the code.
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")  # e.g. username/youtube-radar
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.getenv("YOUTUBE_RADAR_GITHUB_TOKEN", "")


def load_channels():
    """Загружает список каналов. Старые данные в snapshots.json не трогаются."""
    if not os.path.exists(CHANNELS_FILE):
        return {}

    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print("Ошибка чтения channels.json:", e)
        return {}


def save_channels(channels):
    """Сохраняет список конкурентов без изменения истории."""
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def extract_channel_id(value):
    """Принимает ID канала или обычную ссылку YouTube на канал."""
    value = value.strip()

    if re.fullmatch(r"UC[\w-]{20,}", value):
        return value

    patterns = [
        r"youtube\.com/channel/(UC[\w-]+)",
        r"youtube\.com/@[^/]+",
    ]

    match = re.search(patterns[0], value)
    if match:
        return match.group(1)

    # Для @handle нужен API lookup; пока сохраняем только channel ID,
    # поэтому интерфейс подскажет пользователю использовать ID/URL /channel/.
    return None


def github_configured():
    return bool(GITHUB_REPOSITORY and GITHUB_TOKEN)


def github_update_file(path, content, message):
    """Updates one file in GitHub without touching snapshots/history."""
    if not github_configured():
        return False, "GitHub sync не настроен: нужны GITHUB_REPOSITORY и YOUTUBE_RADAR_GITHUB_TOKEN."

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        # Read the current SHA so updates don't overwrite a newer version blindly.
        response = requests.get(
            url,
            headers=headers,
            params={"ref": GITHUB_BRANCH},
            timeout=15,
        )

        sha = None
        if response.status_code == 200:
            sha = response.json().get("sha")
        elif response.status_code != 404:
            return False, f"GitHub GET: {response.status_code} {response.text[:200]}"

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        if response.status_code in (200, 201):
            return True, "Изменения отправлены в GitHub."

        return False, f"GitHub PUT: {response.status_code} {response.text[:250]}"

    except requests.RequestException as e:
        return False, f"Ошибка соединения с GitHub: {e}"


def sync_channels_to_github(channels):
    content = json.dumps(channels, ensure_ascii=False, indent=2) + "\n"
    return github_update_file(
        CHANNELS_FILE,
        content,
        "Update YouTube Radar channels",
    )


def pull_latest_data_from_github():
    """Pulls cloud snapshots/channels into the local app folder.

    The app remains open; this is a normal git pull, not a restart.
    """
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", GITHUB_BRANCH],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=os.getcwd(),
        )
        if result.returncode == 0:
            return True, (result.stdout or "").strip()
        return False, (result.stderr or result.stdout or "git pull failed").strip()
    except FileNotFoundError:
        return False, "Git не найден в PATH. Установи Git или открой проект через GitHub Desktop."
    except subprocess.TimeoutExpired:
        return False, "git pull превысил лимит времени."
    except Exception as e:
        return False, str(e)


# ============================================================
# ТЕМА
# ============================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================================
# ЦВЕТА
# ============================================================

BG = "#0b0d10"
CARD = "#11151a"
CARD_HOVER = "#171c22"
HEADER = "#151a20"
BORDER = "#242a32"

TEXT = "#f1f5f9"
SECONDARY = "#8b95a3"

GREEN = "#4ade80"
RED = "#f87171"
BLUE = "#60a5fa"
YELLOW = "#facc15"


# ============================================================
# DATA
# ============================================================

def load_snapshots():

    if not os.path.exists(SNAPSHOTS_FILE):
        return []

    try:

        with open(
            SNAPSHOTS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, list):
            return data

        return []

    except Exception as e:

        print(
            "Ошибка чтения истории:",
            e
        )

        return []


def get_video_history(
    snapshots,
    video_id
):

    history = []

    for snapshot in snapshots:

        video = snapshot.get(
            "videos",
            {}
        ).get(video_id)

        if not video:
            continue

        try:

            history.append({
                "timestamp":
                    datetime.fromisoformat(
                        snapshot["timestamp"]
                    ),

                "views":
                    int(
                        video.get(
                            "views",
                            0
                        )
                    )
            })

        except Exception:
            pass

    history.sort(
        key=lambda x: x["timestamp"]
    )

    return history


# ============================================================
# РАСЧЁТЫ
# ============================================================

def find_snapshot_for_interval(
    history,
    interval_minutes
):

    if len(history) < 2:
        return None

    current = history[-1]

    target = (
        current["timestamp"]
        - timedelta(
            minutes=interval_minutes
        )
    )

    tolerance = max(
        5,
        interval_minutes * 0.10
    )

    best = None
    best_difference = None

    for item in history[:-1]:

        difference = abs(
            (
                item["timestamp"]
                - target
            ).total_seconds() / 60
        )

        if difference > tolerance:
            continue

        if (
            best_difference is None
            or difference < best_difference
        ):

            best = item
            best_difference = difference

    return best


def calculate_growth(
    history,
    interval_minutes
):

    if len(history) < 2:
        return None

    current = history[-1]

    previous = find_snapshot_for_interval(
        history,
        interval_minutes
    )

    if previous is None:
        return None

    actual_minutes = (
        current["timestamp"]
        - previous["timestamp"]
    ).total_seconds() / 60

    if actual_minutes <= 0:
        return None

    growth = (
        current["views"]
        - previous["views"]
    )

    if growth < 0:
        growth = 0

    speed = (
        growth
        / actual_minutes
    )

    return {
        "growth": growth,
        "speed": speed
    }


def calculate_acceleration(history):

    if len(history) < 3:
        return None

    a = history[-3]
    b = history[-2]
    c = history[-1]

    time1 = (
        b["timestamp"]
        - a["timestamp"]
    ).total_seconds() / 60

    time2 = (
        c["timestamp"]
        - b["timestamp"]
    ).total_seconds() / 60

    if time1 <= 0 or time2 <= 0:
        return None

    growth1 = max(
        0,
        b["views"] - a["views"]
    )

    growth2 = max(
        0,
        c["views"] - b["views"]
    )

    speed1 = growth1 / time1
    speed2 = growth2 / time2

    if speed1 == 0:

        if speed2 > 0:
            return "рост"

        return 0

    return (
        (speed2 - speed1)
        / speed1
    ) * 100


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================

def format_number(number):

    if number is None:
        return "—"

    number = int(number)

    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"

    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"

    if number >= 1_000:
        return f"{number / 1_000:.1f}K"

    return str(number)


def format_growth(result):

    if result is None:
        return "—"

    return (
        "+"
        + format_number(
            result["growth"]
        )
    )


def format_speed(result):

    if result is None:
        return "—"

    speed = result["speed"]

    if speed >= 1_000_000:
        return (
            f"{speed / 1_000_000:.1f}M"
            "/мин"
        )

    if speed >= 1_000:
        return (
            f"{speed / 1_000:.1f}K"
            "/мин"
        )

    return f"{speed:.1f}/мин"


def format_acceleration(value):

    if value is None:
        return "—"

    if value == "рост":
        return "↑ Рост"

    sign = "+"

    if value < 0:
        sign = ""

    return (
        f"{sign}{value:.1f}%"
    )


def acceleration_color(value):

    if value is None:
        return SECONDARY

    if value == "рост":
        return GREEN

    if value > 0:
        return GREEN

    if value < 0:
        return RED

    return SECONDARY


# ============================================================
# ПОДГОТОВКА ВИДЕО
# ============================================================

def get_latest_videos(
    snapshots
):

    if not snapshots:
        return []

    latest = snapshots[-1]

    videos = []

    for video_id, video in latest.get(
        "videos",
        {}
    ).items():

        history = get_video_history(
            snapshots,
            video_id
        )

        growth_5m = calculate_growth(
            history,
            5
        )

        growth_1h = calculate_growth(
            history,
            60
        )

        acceleration = (
            calculate_acceleration(
                history
            )
        )

        videos.append({

            "id": video_id,

            "title": video.get(
                "title",
                "Без названия"
            ),

            "channel": video.get(
                "channel",
                "?"
            ),

            "views": int(
                video.get(
                    "views",
                    0
                )
            ),

            "likes": int(
                video.get(
                    "likes",
                    0
                )
            ),

            "comments": int(
                video.get(
                    "comments",
                    0
                )
            ),

            "published": video.get(
                "published",
                ""
            ),

            "growth_5m": growth_5m,

            "growth_1h": growth_1h,

            "acceleration":
                acceleration,

            "history": history
        })

    return videos


# ============================================================
# MAIN APP
# ============================================================

class YouTubeRadar(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title(
            "YouTube Radar"
        )

        self.geometry(
            "1500x850"
        )

        self.minsize(
            1100,
            700
        )

        self.configure(
            fg_color=BG
        )

        self.videos = []

        self.filtered_videos = []

        self.selected_channel = "Все"

        self.create_interface()

        self.refresh_data()

        self.after(
            AUTO_REFRESH_SECONDS * 1000,
            self.auto_refresh
        )


    # ========================================================
    # INTERFACE
    # ========================================================

    def create_interface(self):

        # ====================================================
        # HEADER
        # ====================================================

        header = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        header.pack(
            fill="x",
            padx=28,
            pady=(25, 12)
        )


        title_frame = ctk.CTkFrame(
            header,
            fg_color="transparent"
        )

        title_frame.pack(
            side="left"
        )


        title = ctk.CTkLabel(
            title_frame,
            text="🚀  YouTube Radar",
            font=ctk.CTkFont(
                size=30,
                weight="bold"
            ),
            text_color=TEXT
        )

        title.pack(
            anchor="w"
        )


        subtitle = ctk.CTkLabel(
            title_frame,
            text=(
                "Мониторинг роста YouTube "
                "в реальном времени"
            ),
            font=ctk.CTkFont(
                size=13
            ),
            text_color=SECONDARY
        )

        subtitle.pack(
            anchor="w",
            pady=(2, 0)
        )


        # LIVE

        live = ctk.CTkLabel(
            header,
            text="●  LIVE",
            text_color=GREEN,
            font=ctk.CTkFont(
                size=14,
                weight="bold"
            )
        )

        live.pack(
            side="left",
            padx=30
        )


        sync_button = ctk.CTkButton(
            header,
            text="☁  Синхронизировать",
            width=170,
            height=40,
            corner_radius=8,
            command=self.sync_now
        )
        sync_button.pack(side="right", padx=(8, 0))

        refresh_button = ctk.CTkButton(
            header,
            text="⟳  Обновить",
            width=140,
            height=40,
            corner_radius=8,
            command=self.refresh_data
        )

        refresh_button.pack(
            side="right"
        )


        # ====================================================
        # STAT CARDS
        # ====================================================

        cards = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        cards.pack(
            fill="x",
            padx=28,
            pady=10
        )

        self.total_card = self.create_stat_card(
            cards,
            "📊",
            "Видео",
            "0"
        )

        self.total_card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8)
        )


        self.channel_card = self.create_stat_card(
            cards,
            "📺",
            "Каналы",
            "0"
        )

        self.channel_card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=8
        )


        self.breakout_card = self.create_stat_card(
            cards,
            "🔥",
            "Активный рост",
            "0"
        )

        self.breakout_card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=8
        )


        self.snapshot_card = self.create_stat_card(
            cards,
            "⏱",
            "Snapshots",
            "0"
        )

        self.snapshot_card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(8, 0)
        )


        # ====================================================
        # CONTROLS
        # ====================================================

        controls = ctk.CTkFrame(
            self,
            fg_color="transparent"
        )

        controls.pack(
            fill="x",
            padx=28,
            pady=(12, 10)
        )


        self.search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="🔎  Поиск видео...",
            width=360,
            height=42,
            corner_radius=8
        )

        self.search_entry.pack(
            side="left"
        )

        self.search_entry.bind(
            "<KeyRelease>",
            lambda event:
            self.apply_filters()
        )


        self.channel_menu = ctk.CTkOptionMenu(
            controls,
            values=["Все"],
            width=160,
            height=42,
            corner_radius=8,
            command=self.change_channel
        )

        self.channel_menu.pack(
            side="left",
            padx=10
        )


        self.sort_menu = ctk.CTkOptionMenu(
            controls,
            values=[
                "Рост за 5 минут",
                "Просмотры",
                "Рост за час",
                "Ускорение"
            ],
            width=200,
            height=42,
            corner_radius=8,
            command=lambda x:
            self.apply_filters()
        )

        self.sort_menu.set(
            "Рост за 5 минут"
        )

        self.sort_menu.pack(
            side="left"
        )

        self.manage_channels_button = ctk.CTkButton(
            controls,
            text="⚙  Конкуренты",
            width=150,
            height=42,
            corner_radius=8,
            command=self.open_channel_manager
        )

        self.manage_channels_button.pack(
            side="left",
            padx=10
        )


        self.results_label = ctk.CTkLabel(
            controls,
            text="",
            text_color=SECONDARY
        )

        self.results_label.pack(
            side="right"
        )


        # ====================================================
        # TABLE
        # ====================================================

        table = ctk.CTkFrame(
            self,
            fg_color=CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER
        )

        table.pack(
            fill="both",
            expand=True,
            padx=28,
            pady=(0, 15)
        )


        # HEADER

        header_row = ctk.CTkFrame(
            table,
            fg_color=HEADER,
            height=48,
            corner_radius=8
        )

        header_row.pack(
            fill="x",
            padx=1,
            pady=1
        )


        # Фиксированные ширины!
        self.column_widths = {
            "rank": 55,
            "title": 550,
            "channel": 120,
            "views": 120,
            "growth": 120,
            "speed": 150,
            "acceleration": 140
        }


        headers = [
            ("", "rank"),
            ("ВИДЕО", "title"),
            ("КАНАЛ", "channel"),
            ("ПРОСМОТРЫ", "views"),
            ("+5 МИН", "growth"),
            ("СКОРОСТЬ", "speed"),
            ("⚡ УСКОРЕНИЕ", "acceleration")
        ]


        for text, key in headers:

            label = ctk.CTkLabel(
                header_row,
                text=text,
                anchor="w",
                text_color=SECONDARY,
                font=ctk.CTkFont(
                    size=11,
                    weight="bold"
                )
            )

            label.pack(
                side="left",
                padx=8,
                pady=12,
                ipadx=(
                    self.column_widths[key]
                    - 16
                )
            )


        # SCROLL

        self.table = ctk.CTkScrollableFrame(
            table,
            fg_color="transparent"
        )

        self.table.pack(
            fill="both",
            expand=True,
            padx=4,
            pady=4
        )


        # FOOTER

        self.footer = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            text_color=SECONDARY,
            font=ctk.CTkFont(
                size=12
            )
        )

        self.footer.pack(
            fill="x",
            padx=30,
            pady=(0, 12)
        )


    # ========================================================
    # STAT CARD
    # ========================================================

    def create_stat_card(
        self,
        parent,
        icon,
        name,
        value
    ):

        card = ctk.CTkFrame(
            parent,
            fg_color=CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            height=90
        )


        icon_label = ctk.CTkLabel(
            card,
            text=icon,
            font=ctk.CTkFont(
                size=25
            )
        )

        icon_label.pack(
            side="left",
            padx=(18, 10)
        )


        text_frame = ctk.CTkFrame(
            card,
            fg_color="transparent"
        )

        text_frame.pack(
            side="left"
        )


        name_label = ctk.CTkLabel(
            text_frame,
            text=name,
            text_color=SECONDARY,
            font=ctk.CTkFont(
                size=12
            )
        )

        name_label.pack(
            anchor="w"
        )


        value_label = ctk.CTkLabel(
            text_frame,
            text=value,
            text_color=TEXT,
            font=ctk.CTkFont(
                size=23,
                weight="bold"
            )
        )

        value_label.pack(
            anchor="w"
        )


        card.value_label = value_label

        return card


    # ========================================================
    # DATA
    # ========================================================

    def refresh_data(self):

        snapshots = load_snapshots()

        self.videos = get_latest_videos(
            snapshots
        )


        channels = sorted(
            set(
                video["channel"]
                for video in self.videos
            )
        )


        self.channel_menu.configure(
            values=["Все"] + channels
        )


        # Stats

        self.total_card.value_label.configure(
            text=str(
                len(self.videos)
            )
        )


        self.channel_card.value_label.configure(
            text=str(
                len(channels)
            )
        )


        active_growth = 0

        for video in self.videos:

            growth = video[
                "growth_5m"
            ]

            if (
                growth
                and growth["growth"] > 0
            ):

                active_growth += 1


        self.breakout_card.value_label.configure(
            text=str(
                active_growth
            )
        )


        self.snapshot_card.value_label.configure(
            text=str(
                len(snapshots)
            )
        )


        self.apply_filters()


        if snapshots:

            try:

                dt = datetime.fromisoformat(
                    snapshots[-1][
                        "timestamp"
                    ]
                )

                time_text = dt.strftime(
                    "%H:%M:%S"
                )

            except Exception:

                time_text = "?"


            self.footer.configure(
                text=(
                    f"Последнее обновление "
                    f"{time_text}"
                    f"   •   "
                    f"История: "
                    f"{len(snapshots)} snapshots"
                    f"   •   "
                    f"Автообновление: "
                    f"{AUTO_REFRESH_SECONDS} сек."
                )
            )


    # ========================================================
    # FILTERS
    # ========================================================

    def change_channel(
        self,
        value
    ):

        self.selected_channel = value

        self.apply_filters()


    def apply_filters(self):

        search = (
            self.search_entry
            .get()
            .lower()
            .strip()
        )


        videos = []


        for video in self.videos:

            if (
                self.selected_channel
                != "Все"
                and video["channel"]
                != self.selected_channel
            ):
                continue


            if search:

                title = video[
                    "title"
                ].lower()

                channel = video[
                    "channel"
                ].lower()

                if (
                    search not in title
                    and search not in channel
                ):
                    continue


            videos.append(video)


        # SORT

        sort_type = self.sort_menu.get()


        if sort_type == "Просмотры":

            videos.sort(
                key=lambda x:
                x["views"],
                reverse=True
            )


        elif sort_type == "Рост за 5 минут":

            videos.sort(
                key=lambda x:
                (
                    x["growth_5m"]
                    ["growth"]
                    if x["growth_5m"]
                    else 0
                ),
                reverse=True
            )


        elif sort_type == "Рост за час":

            videos.sort(
                key=lambda x:
                (
                    x["growth_1h"]
                    ["growth"]
                    if x["growth_1h"]
                    else 0
                ),
                reverse=True
            )


        elif sort_type == "Ускорение":

            def acceleration_value(
                video
            ):

                value = video[
                    "acceleration"
                ]

                if isinstance(
                    value,
                    (int, float)
                ):
                    return value

                if value == "рост":
                    return 999999

                return -999999


            videos.sort(
                key=acceleration_value,
                reverse=True
            )


        self.filtered_videos = videos

        self.draw_table()


    # ========================================================
    # TABLE
    # ========================================================

    def draw_table(self):

        for widget in (
            self.table.winfo_children()
        ):

            widget.destroy()


        for index, video in enumerate(
            self.filtered_videos
        ):

            self.create_video_row(
                index + 1,
                video
            )


        self.results_label.configure(
            text=(
                f"{len(self.filtered_videos)} "
                f"из {len(self.videos)} видео"
            )
        )


    # ========================================================
    # VIDEO ROW
    # ========================================================

    def create_video_row(
        self,
        rank,
        video
    ):

        row = ctk.CTkFrame(
            self.table,
            fg_color=(
                CARD
                if rank % 2
                else "#0f1317"
            ),
            corner_radius=8,
            height=62
        )

        row.pack(
            fill="x",
            pady=3
        )


        # Hover

        def enter(event):

            row.configure(
                fg_color=CARD_HOVER
            )


        def leave(event):

            row.configure(
                fg_color=(
                    CARD
                    if rank % 2
                    else "#0f1317"
                )
            )


        row.bind(
            "<Enter>",
            enter
        )

        row.bind(
            "<Leave>",
            leave
        )


        # ====================================================
        # RANK
        # ====================================================

        rank_label = ctk.CTkLabel(
            row,
            text=str(rank),
            width=45,
            text_color=(
                YELLOW
                if rank <= 3
                else SECONDARY
            ),
            font=ctk.CTkFont(
                size=14,
                weight="bold"
            )
        )

        rank_label.pack(
            side="left",
            padx=5
        )


        # ====================================================
        # TITLE
        # ====================================================

        title = video["title"]

        if len(title) > 62:

            title = (
                title[:62]
                + "..."
            )


        title_label = ctk.CTkLabel(
            row,
            text=title,
            width=530,
            anchor="w",
            justify="left",
            text_color=TEXT,
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        )

        title_label.pack(
            side="left",
            padx=8
        )


        # ====================================================
        # CHANNEL
        # ====================================================

        channel_label = ctk.CTkLabel(
            row,
            text=video["channel"],
            width=105,
            anchor="w",
            text_color=BLUE,
            font=ctk.CTkFont(
                size=12,
                weight="bold"
            )
        )

        channel_label.pack(
            side="left",
            padx=8
        )


        # ====================================================
        # VIEWS
        # ====================================================

        views_label = ctk.CTkLabel(
            row,
            text=format_number(
                video["views"]
            ),
            width=105,
            anchor="e",
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        )

        views_label.pack(
            side="left",
            padx=8
        )


        # ====================================================
        # GROWTH
        # ====================================================

        growth = video[
            "growth_5m"
        ]

        growth_label = ctk.CTkLabel(
            row,
            text=format_growth(
                growth
            ),
            width=105,
            anchor="e",
            text_color=(
                GREEN
                if growth
                and growth["growth"] > 0
                else SECONDARY
            ),
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        )

        growth_label.pack(
            side="left",
            padx=8
        )


        # ====================================================
        # SPEED
        # ====================================================

        speed_label = ctk.CTkLabel(
            row,
            text=format_speed(
                growth
            ),
            width=135,
            anchor="e",
            text_color=(
                GREEN
                if growth
                and growth["speed"] > 0
                else SECONDARY
            )
        )

        speed_label.pack(
            side="left",
            padx=8
        )


        # ====================================================
        # ACCELERATION
        # ====================================================

        acceleration = video[
            "acceleration"
        ]


        acceleration_label = ctk.CTkLabel(
            row,
            text=format_acceleration(
                acceleration
            ),
            width=120,
            anchor="e",
            text_color=acceleration_color(
                acceleration
            ),
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        )

        acceleration_label.pack(
            side="left",
            padx=8
        )


        # CLICK

        widgets = [
            row,
            rank_label,
            title_label,
            channel_label,
            views_label,
            growth_label,
            speed_label,
            acceleration_label
        ]


        for widget in widgets:

            widget.bind(
                "<Button-1>",
                lambda event,
                v=video:
                self.open_video(v)
            )


    # ========================================================
    # VIDEO PAGE
    # ========================================================

    def open_video(
        self,
        video
    ):

        window = ctk.CTkToplevel(
            self
        )

        window.title(
            "YouTube Radar — "
            + video["title"]
        )

        window.geometry(
            "1000x720"
        )

        window.configure(
            fg_color=BG
        )


        # ====================================================
        # HEADER
        # ====================================================

        header = ctk.CTkFrame(
            window,
            fg_color="transparent"
        )

        header.pack(
            fill="x",
            padx=30,
            pady=25
        )


        title = ctk.CTkLabel(
            header,
            text=video["title"],
            wraplength=850,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(
                size=25,
                weight="bold"
            )
        )

        title.pack(
            anchor="w"
        )


        channel = ctk.CTkLabel(
            header,
            text=(
                "📺 "
                + video["channel"]
            ),
            text_color=BLUE,
            font=ctk.CTkFont(
                size=15,
                weight="bold"
            )
        )

        channel.pack(
            anchor="w",
            pady=(7, 0)
        )


        # ====================================================
        # MAIN STATS
        # ====================================================

        stats = ctk.CTkFrame(
            window,
            fg_color="transparent"
        )

        stats.pack(
            fill="x",
            padx=30
        )


        stats_data = [

            (
                "👁 Просмотры",
                format_number(
                    video["views"]
                ),
                TEXT
            ),

            (
                "📈 За 5 минут",
                format_growth(
                    video["growth_5m"]
                ),
                GREEN
            ),

            (
                "⚡ Скорость",
                format_speed(
                    video["growth_5m"]
                ),
                GREEN
            ),

            (
                "🚀 Ускорение",
                format_acceleration(
                    video[
                        "acceleration"
                    ]
                ),
                acceleration_color(
                    video[
                        "acceleration"
                    ]
                )
            )
        ]


        for index, (
            name,
            value,
            color
        ) in enumerate(
            stats_data
        ):

            box = ctk.CTkFrame(
                stats,
                fg_color=CARD,
                corner_radius=10,
                border_width=1,
                border_color=BORDER
            )

            box.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=5
            )


            stats.grid_columnconfigure(
                index,
                weight=1
            )


            name_label = ctk.CTkLabel(
                box,
                text=name,
                text_color=SECONDARY
            )

            name_label.pack(
                pady=(15, 3)
            )


            value_label = ctk.CTkLabel(
                box,
                text=value,
                text_color=color,
                font=ctk.CTkFont(
                    size=21,
                    weight="bold"
                )
            )

            value_label.pack(
                pady=(0, 15)
            )


        # ====================================================
        # GRAPH
        # ====================================================

        graph_frame = ctk.CTkFrame(
            window,
            fg_color=CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER
        )

        graph_frame.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=25
        )


        graph_title = ctk.CTkLabel(
            graph_frame,
            text="📈 История просмотров",
            font=ctk.CTkFont(
                size=16,
                weight="bold"
            )
        )

        graph_title.pack(
            anchor="w",
            padx=20,
            pady=(15, 5)
        )


        canvas = tk.Canvas(
            graph_frame,
            bg=CARD,
            highlightthickness=0
        )

        canvas.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=10
        )


        def draw_graph(event=None):

            canvas.delete(
                "all"
            )

            history = video[
                "history"
            ]

            if len(history) < 2:

                canvas.create_text(
                    canvas.winfo_width() / 2,
                    canvas.winfo_height() / 2,
                    text=(
                        "Недостаточно "
                        "истории для графика"
                    ),
                    fill=SECONDARY,
                    font=(
                        "Arial",
                        14
                    )
                )

                return


            width = canvas.winfo_width()
            height = canvas.winfo_height()

            padding = 45


            points = history[-50:]


            min_views = min(
                x["views"]
                for x in points
            )

            max_views = max(
                x["views"]
                for x in points
            )


            if max_views == min_views:
                max_views += 1


            coords = []


            for index, item in enumerate(
                points
            ):

                x = (
                    padding
                    +
                    index
                    *
                    (
                        width
                        - padding * 2
                    )
                    /
                    max(
                        1,
                        len(points) - 1
                    )
                )


                y = (
                    height
                    - padding
                    -
                    (
                        item["views"]
                        - min_views
                    )
                    /
                    (
                        max_views
                        - min_views
                    )
                    *
                    (
                        height
                        - padding * 2
                    )
                )


                coords.append(
                    (x, y)
                )


            # Axes

            canvas.create_line(
                padding,
                padding,
                padding,
                height - padding,
                fill=BORDER
            )


            canvas.create_line(
                padding,
                height - padding,
                width - padding,
                height - padding,
                fill=BORDER
            )


            # Graph

            for i in range(
                len(coords) - 1
            ):

                canvas.create_line(
                    coords[i][0],
                    coords[i][1],
                    coords[i + 1][0],
                    coords[i + 1][1],
                    fill=GREEN,
                    width=3
                )


            # Current point

            x, y = coords[-1]

            canvas.create_oval(
                x - 5,
                y - 5,
                x + 5,
                y + 5,
                fill=GREEN,
                outline=""
            )


            # Labels

            canvas.create_text(
                padding,
                15,
                text=format_number(
                    max_views
                ),
                fill=SECONDARY,
                anchor="w"
            )


            canvas.create_text(
                padding,
                height - padding + 20,
                text=format_number(
                    min_views
                ),
                fill=SECONDARY,
                anchor="w"
            )


        canvas.bind(
            "<Configure>",
            draw_graph
        )


        # ====================================================
        # EXTRA INFO
        # ====================================================

        bottom = ctk.CTkFrame(
            window,
            fg_color="transparent"
        )

        bottom.pack(
            fill="x",
            padx=30,
            pady=(0, 20)
        )


        info = ctk.CTkLabel(
            bottom,
            text=(
                f"👍 "
                f"{format_number(video['likes'])}"
                f"   •   "
                f"💬 "
                f"{format_number(video['comments'])}"
                f"   •   "
                f"📊 "
                f"{len(video['history'])} "
                f"snapshots"
            ),
            text_color=SECONDARY
        )

        info.pack(
            side="left"
        )


    # ========================================================
    # CLOUD SYNC
    # ========================================================

    def sync_now(self):
        ok, msg = pull_latest_data_from_github()
        if ok:
            self.refresh_data()
            print("☁ GitHub sync:", msg)
        else:
            print("❌ GitHub sync:", msg)


    # ========================================================
    # CHANNEL MANAGER
    # ========================================================

    def open_channel_manager(self):
        window = ctk.CTkToplevel(self)
        window.title("YouTube Radar — Конкуренты")
        window.geometry("620x620")
        window.configure(fg_color=BG)
        window.transient(self)

        title = ctk.CTkLabel(
            window,
            text="⚙  Управление конкурентами",
            font=ctk.CTkFont(size=23, weight="bold"),
            text_color=TEXT
        )
        title.pack(anchor="w", padx=25, pady=(22, 4))

        subtitle = ctk.CTkLabel(
            window,
            text="Добавление каналов не удаляет старую историю.",
            text_color=SECONDARY
        )
        subtitle.pack(anchor="w", padx=25, pady=(0, 18))

        list_frame = ctk.CTkScrollableFrame(
            window,
            fg_color=CARD,
            corner_radius=10
        )
        list_frame.pack(fill="both", expand=True, padx=25, pady=(0, 15))

        def redraw():
            for widget in list_frame.winfo_children():
                widget.destroy()

            channels = load_channels()

            for name, channel_id in channels.items():
                row = ctk.CTkFrame(
                    list_frame,
                    fg_color=HEADER,
                    corner_radius=8
                )
                row.pack(fill="x", pady=4)

                label = ctk.CTkLabel(
                    row,
                    text=f"{name}\n{channel_id}",
                    justify="left",
                    anchor="w",
                    text_color=TEXT
                )
                label.pack(side="left", fill="x", expand=True, padx=12, pady=8)

                def remove_channel(n=name):
                    channels_now = load_channels()
                    if n in channels_now:
                        del channels_now[n]
                        save_channels(channels_now)
                        ok, msg = sync_channels_to_github(channels_now)
                        if ok:
                            status.configure(text="✓ Канал удалён и список синхронизирован с GitHub.", text_color=GREEN)
                        else:
                            status.configure(text=f"Локально удалён. GitHub: {msg}", text_color=YELLOW)
                    redraw()

                delete = ctk.CTkButton(
                    row,
                    text="Удалить",
                    width=85,
                    fg_color="#3a2020",
                    hover_color="#552828",
                    command=remove_channel
                )
                delete.pack(side="right", padx=10)

        form = ctk.CTkFrame(window, fg_color="transparent")
        form.pack(fill="x", padx=25, pady=(0, 25))

        name_entry = ctk.CTkEntry(
            form,
            placeholder_text="Название канала",
            width=180,
            height=40
        )
        name_entry.pack(side="left", padx=(0, 8))

        id_entry = ctk.CTkEntry(
            form,
            placeholder_text="Channel ID (UC...)",
            width=220,
            height=40
        )
        id_entry.pack(side="left", padx=(0, 8))

        status = ctk.CTkLabel(
            window,
            text="",
            text_color=SECONDARY
        )
        status.pack(pady=(0, 8))

        def add_channel():
            name = name_entry.get().strip()
            channel_id = id_entry.get().strip()

            if not name:
                status.configure(text="Введите название канала.", text_color=RED)
                return

            if not re.fullmatch(r"UC[\w-]{20,}", channel_id):
                status.configure(
                    text="Нужен настоящий Channel ID, начинающийся с UC.",
                    text_color=RED
                )
                return

            channels_now = load_channels()
            channels_now[name] = channel_id
            save_channels(channels_now)

            ok, msg = sync_channels_to_github(channels_now)

            name_entry.delete(0, "end")
            id_entry.delete(0, "end")

            if ok:
                status.configure(
                    text="✓ Канал добавлен и отправлен в GitHub. История сохранена.",
                    text_color=GREEN
                )
            else:
                status.configure(
                    text=f"✓ Канал добавлен локально. GitHub: {msg}",
                    text_color=YELLOW
                )
            redraw()

        add_button = ctk.CTkButton(
            form,
            text="+ Добавить",
            width=120,
            height=40,
            command=add_channel
        )
        add_button.pack(side="left")

        redraw()


    # ========================================================
    # AUTO REFRESH
    # ========================================================

    def auto_refresh(self):

        try:
            if GITHUB_REPOSITORY:
                pull_latest_data_from_github()
            self.refresh_data()

        except Exception as e:

            print(
                "Ошибка автообновления:",
                e
            )


        self.after(
            AUTO_REFRESH_SECONDS * 1000,
            self.auto_refresh
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    app = YouTubeRadar()

    app.mainloop()