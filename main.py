import os
import json
from datetime import datetime, timedelta

from googleapiclient.discovery import build


# ============================================================
# НАСТРОЙКИ
# ============================================================

API_KEY = os.getenv("YOUTUBE_API_KEY")

if not API_KEY:
    raise RuntimeError("Не задан YOUTUBE_API_KEY. Добавь его в переменные окружения/GitHub Secrets.")

# Сюда добавляй ID нужных YouTube-каналов
def load_channels():
    """Загружает список конкурентов из channels.json."""
    channels_file = "channels.json"

    if not os.path.exists(channels_file):
        raise FileNotFoundError(
            f"Не найден {channels_file}. Создай его в корне проекта."
        )

    with open(channels_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or not data:
        raise ValueError("channels.json должен содержать непустой объект: {\"Название\": \"CHANNEL_ID\"}")

    return data


CHANNEL_IDS = load_channels()


VIDEOS_PER_CHANNEL = 10

CHECK_INTERVAL_MINUTES = 5
HISTORY_DAYS = 7

DATA_DIR = "data"
SNAPSHOTS_FILE = os.path.join(DATA_DIR, "snapshots.json")


# ============================================================
# НАСТРОЙКА API
# ============================================================

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)


# ============================================================
# РАБОТА С ИСТОРИЕЙ
# ============================================================

def load_snapshots():
    """Загружает историю из JSON."""

    if not os.path.exists(SNAPSHOTS_FILE):
        return []

    try:
        with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        print("⚠ Не удалось прочитать историю. Создаём новую.")
        return []


def save_snapshots(snapshots):
    """Сохраняет историю."""

    os.makedirs(DATA_DIR, exist_ok=True)

    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            snapshots,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_old_snapshots(snapshots):
    """Удаляет снимки старше HISTORY_DAYS."""

    limit = datetime.now() - timedelta(days=HISTORY_DAYS)

    cleaned = []

    for snapshot in snapshots:

        try:
            snapshot_time = datetime.fromisoformat(
                snapshot["timestamp"]
            )

            if snapshot_time >= limit:
                cleaned.append(snapshot)

        except Exception:
            continue

    return cleaned


# ============================================================
# YOUTUBE
# ============================================================

def get_channel_videos(channel_id, channel_name):
    """Получает последние видео канала через uploads playlist."""

    # Получаем информацию о канале
    channel_response = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()

    items = channel_response.get("items", [])

    if not items:
        print(f"⚠ Канал {channel_name} не найден")
        return []

    uploads_playlist_id = (
        items[0]["contentDetails"]
        ["relatedPlaylists"]["uploads"]
    )

    # Получаем последние видео из uploads playlist
    playlist_response = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=VIDEOS_PER_CHANNEL
    ).execute()

    video_ids = []

    for item in playlist_response.get("items", []):

        video_id = item["contentDetails"].get("videoId")

        if video_id:
            video_ids.append(video_id)

    if not video_ids:
        return []

    # Получаем статистику видео
    stats_response = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids)
    ).execute()

    videos = []

    for item in stats_response.get("items", []):

        statistics = item.get("statistics", {})
        snippet = item.get("snippet", {})

        videos.append({
            "video_id": item["id"],

            "title": snippet.get(
                "title",
                "Без названия"
            ),

            "channel": channel_name,

            "published": snippet.get(
                "publishedAt",
                ""
            ),

            "views": int(
                statistics.get(
                    "viewCount",
                    0
                )
            ),

            "likes": int(
                statistics.get(
                    "likeCount",
                    0
                )
            ),

            "comments": int(
                statistics.get(
                    "commentCount",
                    0
                )
            )
        })

    return videos


# ============================================================
# СОЗДАНИЕ СНИМКА
# ============================================================

def add_snapshot(snapshots, videos):
    """Добавляет текущие данные в историю."""

    now = datetime.now().isoformat()

    snapshot = {
        "timestamp": now,
        "videos": {}
    }

    for video in videos:

        video_id = video["video_id"]

        snapshot["videos"][video_id] = {
            "title": video["title"],
            "channel": video["channel"],
            "published": video["published"],

            "views": video["views"],
            "likes": video["likes"],
            "comments": video["comments"]
        }

    snapshots.append(snapshot)

    return snapshots


# ============================================================
# ПОЛУЧЕНИЕ ИСТОРИИ КОНКРЕТНОГО ВИДЕО
# ============================================================

def get_video_history(snapshots, video_id):
    """Возвращает историю конкретного видео."""

    history = []

    for snapshot in snapshots:

        if video_id not in snapshot.get("videos", {}):
            continue

        video_data = snapshot["videos"][video_id]

        try:
            timestamp = datetime.fromisoformat(
                snapshot["timestamp"]
            )

            views = int(
                video_data.get("views", 0)
            )

            history.append({
                "timestamp": timestamp,
                "views": views
            })

        except Exception:
            continue

    history.sort(
        key=lambda x: x["timestamp"]
    )

    return history


# ============================================================
# ПОИСК СНИМКА ДЛЯ ИНТЕРВАЛА
# ============================================================

def find_snapshot_for_interval(
    history,
    current_time,
    interval_minutes
):
    """
    Ищет старый снимок примерно нужного возраста.

    Например:
    1 час -> ищем снимок примерно час назад.

    Допускаем небольшую погрешность, потому что
    программа проверяется каждые 5 минут.
    """

    if len(history) < 2:
        return None

    target_time = (
        current_time -
        timedelta(minutes=interval_minutes)
    )

    # Допустимая погрешность.
    tolerance = max(
        5,
        interval_minutes * 0.10
    )

    best_snapshot = None
    best_difference = None

    for item in history[:-1]:

        difference = abs(
            (item["timestamp"] - target_time).total_seconds()
            / 60
        )

        # Снимок должен находиться
        # примерно около нужного времени.
        if difference > tolerance:
            continue

        # Он должен быть действительно старше текущего.
        if item["timestamp"] >= current_time:
            continue

        if (
            best_difference is None
            or difference < best_difference
        ):
            best_snapshot = item
            best_difference = difference

    return best_snapshot


# ============================================================
# РАСЧЁТ ПРИРОСТА
# ============================================================

def calculate_growth(
    history,
    interval_minutes
):
    """
    Возвращает:

    {
        "growth": прирост просмотров,
        "per_minute": средний прирост в минуту,
        "actual_minutes": реальная длина интервала
    }

    Если данных недостаточно -> None
    """

    if len(history) < 2:
        return None

    current = history[-1]

    previous = find_snapshot_for_interval(
        history,
        current["timestamp"],
        interval_minutes
    )

    if previous is None:
        return None

    actual_minutes = (
        current["timestamp"] -
        previous["timestamp"]
    ).total_seconds() / 60

    if actual_minutes <= 0:
        return None

    growth = (
        current["views"] -
        previous["views"]
    )

    # YouTube иногда может корректировать
    # количество просмотров вниз.
    if growth < 0:
        growth = 0

    per_minute = (
        growth / actual_minutes
    )

    return {
        "growth": growth,
        "per_minute": per_minute,
        "actual_minutes": actual_minutes
    }


# ============================================================
# УСКОРЕНИЕ
# ============================================================

def calculate_acceleration(history):
    """
    Сравнивает скорость последних двух интервалов.

    Например:

    предыдущие 5 минут:
    +100 просмотров

    последние 5 минут:
    +200 просмотров

    ускорение = +100%

    Нужно минимум 3 снимка.
    """

    if len(history) < 3:
        return None

    last = history[-1]
    previous = history[-2]
    before_previous = history[-3]

    # -----------------------------------------
    # ПОСЛЕДНЯЯ СКОРОСТЬ
    # -----------------------------------------

    current_minutes = (
        last["timestamp"] -
        previous["timestamp"]
    ).total_seconds() / 60

    if current_minutes <= 0:
        return None

    current_growth = (
        last["views"] -
        previous["views"]
    )

    if current_growth < 0:
        current_growth = 0

    current_speed = (
        current_growth /
        current_minutes
    )

    # -----------------------------------------
    # ПРЕДЫДУЩАЯ СКОРОСТЬ
    # -----------------------------------------

    previous_minutes = (
        previous["timestamp"] -
        before_previous["timestamp"]
    ).total_seconds() / 60

    if previous_minutes <= 0:
        return None

    previous_growth = (
        previous["views"] -
        before_previous["views"]
    )

    if previous_growth < 0:
        previous_growth = 0

    previous_speed = (
        previous_growth /
        previous_minutes
    )

    # Если раньше скорость была 0,
    # процент ускорения математически определить нельзя.
    if previous_speed == 0:
        if current_speed > 0:
            return "рост"

        return "0%"

    acceleration = (
        (current_speed - previous_speed)
        / previous_speed
    ) * 100

    return acceleration


# ============================================================
# ФОРМАТИРОВАНИЕ ЧИСЕЛ
# ============================================================

def format_number(number):

    if number is None:
        return "—"

    number = int(number)

    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"

    if number >= 1_000:
        return f"{number / 1_000:.1f}K"

    return str(number)


def format_growth(result):

    if result is None:
        return "нет данных"

    return (
        f"+{format_number(result['growth'])}"
    )


def format_speed(result):

    if result is None:
        return "нет данных"

    return (
        f"+{result['per_minute']:.1f}/мин"
    )


def format_acceleration(acceleration):

    if acceleration is None:
        return "нет данных"

    if acceleration == "рост":
        return "рост ↑"

    if acceleration == "0%":
        return "0%"

    sign = "+" if acceleration > 0 else ""

    return f"{sign}{acceleration:.1f}%"


# ============================================================
# ВЫВОД ИНФОРМАЦИИ
# ============================================================

def print_video_stats(video, snapshots):

    video_id = video["video_id"]

    history = get_video_history(
        snapshots,
        video_id
    )

    print("\n" + "=" * 80)

    print(
        f"🎬 {video['title']}"
    )

    print(
        f"📺 Канал: {video['channel']}"
    )

    print(
        f"👁 Просмотры: {format_number(video['views'])}"
    )

    print(
        f"👍 Лайки: {format_number(video['likes'])}"
    )

    print(
        f"💬 Комментарии: {format_number(video['comments'])}"
    )

    print()

    print(
        f"{'ПЕРИОД':<10}"
        f"{'ПРИРОСТ':<15}"
        f"{'СРЕДНИЙ / МИН':<18}"
    )

    print("-" * 45)

    intervals = [
        ("5 мин", 5),
        ("1 час", 60),
        ("6 часов", 360),
        ("12 часов", 720),
        ("24 часа", 1440),
        ("3 дня", 4320),
        ("7 дней", 10080)
    ]

    for name, minutes in intervals:

        result = calculate_growth(
            history,
            minutes
        )

        print(
            f"{name:<10}"
            f"{format_growth(result):<15}"
            f"{format_speed(result):<18}"
        )

    acceleration = calculate_acceleration(
        history
    )

    print()

    print(
        f"⚡ Ускорение: "
        f"{format_acceleration(acceleration)}"
    )

    print(
        f"📊 Снимков истории: "
        f"{len(history)}"
    )


# ============================================================
# ОДНА ПРОВЕРКА
# ============================================================

def run_check():

    print("\n" + "#" * 80)

    print(
        f"🔄 НОВАЯ ПРОВЕРКА — "
        f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    print("#" * 80)

    snapshots = load_snapshots()

    all_videos = []

    # -----------------------------------------
    # Получаем видео всех каналов
    # -----------------------------------------

    for channel_name, channel_id in CHANNEL_IDS.items():

        try:

            videos = get_channel_videos(
                channel_id,
                channel_name
            )

            print(
                f"\n📺 {channel_name} — "
                f"{len(videos)} видео"
            )

            all_videos.extend(videos)

        except Exception as e:

            print(
                f"❌ Ошибка канала "
                f"{channel_name}: {e}"
            )

    if not all_videos:

        print("❌ Видео не получены.")

        return

    # -----------------------------------------
    # Добавляем новый snapshot
    # -----------------------------------------

    snapshots = add_snapshot(
        snapshots,
        all_videos
    )

    # -----------------------------------------
    # Удаляем историю старше 7 дней
    # -----------------------------------------

    snapshots = clean_old_snapshots(
        snapshots
    )

    # -----------------------------------------
    # Сохраняем
    # -----------------------------------------

    save_snapshots(
        snapshots
    )

    # -----------------------------------------
    # Выводим статистику
    # -----------------------------------------

    for video in all_videos:

        print_video_stats(
            video,
            snapshots
        )

    # -----------------------------------------
    # Общая информация
    # -----------------------------------------

    print("\n" + "=" * 80)

    print(
        f"📊 Всего видео: "
        f"{len(all_videos)}"
    )

    print(
        f"💾 История сохранена в: "
        f"{SNAPSHOTS_FILE}"
    )

    print(
        f"🗂 Всего snapshots: "
        f"{len(snapshots)}"
    )

    print("☁️ Следующая проверка будет запущена GitHub Actions по расписанию.")

    print("=" * 80)


# ============================================================
# ЗАПУСК
# ============================================================

def main():
    print()
    print("=" * 80)
    print("🚀 YOUTUBE RADAR — ОДНА ПРОВЕРКА")
    print("=" * 80)

    print(f"🗑 История хранится {HISTORY_DAYS} дней")
    print(f"📺 Каналов: {len(CHANNEL_IDS)}")
    print(f"🎬 Видео с каждого канала: {VIDEOS_PER_CHANNEL}")
    print("☁️ Режим: GitHub Actions / одноразовый запуск")
    print("=" * 80)

    try:
        run_check()
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        raise


if __name__ == "__main__":
    main()