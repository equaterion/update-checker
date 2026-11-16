import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont
from steam.client import SteamClient

APPID = 1049800
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "@blyakadaL"
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "state.json"
MSK = timezone(timedelta(hours=3))
DAILY_HOUR = 0


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_app_info():
    client = SteamClient()
    try:
        client.anonymous_login()
        data = client.get_product_info(apps=[APPID], timeout=30)
    finally:
        try:
            client.logout()
        except Exception:
            pass
    app = data["apps"][APPID]
    branch = app["depots"]["branches"]["public"]
    manifests = {}
    for depot_id, depot in app["depots"].items():
        if not str(depot_id).isdigit():
            continue
        gid = depot.get("manifests", {}).get("public", {}).get("gid")
        if gid:
            manifests[str(depot_id)] = str(gid)
    return {
        "buildid": str(branch["buildid"]),
        "timeupdated": int(branch["timeupdated"]),
        "manifests": manifests,
    }


def get_store_info():
    response = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": APPID, "l": "english", "cc": "us"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()[str(APPID)]["data"]
    text = "".join(
        data.get(key, "")
        for key in ("detailed_description", "short_description", "about_the_game")
    )
    price = data.get("price_overview")
    packages = sorted(
        str(sub.get("packageid"))
        for group in data.get("package_groups") or []
        for sub in group.get("subs") or []
        if sub.get("packageid") is not None
    )
    return {
        "version": 2,
        "categories": {
            f"category_{category.get('id')}": category.get("description")
            for category in data.get("categories") or []
        },
        "genres": {
            f"genre_{genre.get('id')}": genre.get("description")
            for genre in data.get("genres") or []
        },
        "movies": {
            f"movie_{movie.get('id')}": movie.get("name")
            for movie in data.get("movies") or []
        },
        "screenshots": [shot.get("path_full") for shot in data.get("screenshots") or []],
        "description": {
            "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "length": len(text),
        },
        "images": {
            "header": data.get("header_image"),
            "capsule": data.get("capsule_image"),
            "capsule_v5": data.get("capsule_imagev5"),
            "background": data.get("background"),
            "background_raw": data.get("background_raw"),
        },
        "details": {
            "name": data.get("name"),
            "release_date": data.get("release_date"),
            "developers": data.get("developers"),
            "publishers": data.get("publishers"),
            "platforms": data.get("platforms"),
            "supported_languages": hashlib.sha256(
                str(data.get("supported_languages", "")).encode("utf-8")
            ).hexdigest(),
            "website": data.get("website"),
            "legal_notice": hashlib.sha256(
                str(data.get("legal_notice", "")).encode("utf-8")
            ).hexdigest(),
            "pc_requirements": hashlib.sha256(
                str(data.get("pc_requirements", "")).encode("utf-8")
            ).hexdigest(),
            "mac_requirements": hashlib.sha256(
                str(data.get("mac_requirements", "")).encode("utf-8")
            ).hexdigest(),
            "linux_requirements": hashlib.sha256(
                str(data.get("linux_requirements", "")).encode("utf-8")
            ).hexdigest(),
            "content_descriptors": data.get("content_descriptors"),
            "ratings": data.get("ratings"),
            "required_age": data.get("required_age"),
            "type": data.get("type"),
        },
        "monetization": {
            "is_free": data.get("is_free"),
            "price": {
                "currency": price.get("currency"),
                "initial": price.get("initial"),
            }
            if price
            else None,
            "packages": packages,
            "dlc": sorted(str(item) for item in data.get("dlc") or []),
        },
    }


HASHED_DETAILS = {
    "supported_languages",
    "legal_notice",
    "pc_requirements",
    "mac_requirements",
    "linux_requirements",
}


def display(value):
    if value is None:
        return "none"
    if isinstance(value, dict):
        return ", ".join(f"{key}={value[key]}" for key in value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def display_price(price):
    if not price or price.get("initial") is None:
        return "none"
    return f"{price['initial'] / 100:.2f} {price.get('currency')}"


def diff_named(old, new):
    lines = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if key not in old:
            lines.append(f"Added {key}: {new[key]}")
        elif key not in new:
            lines.append(f"Removed {key}: {old[key]}")
        else:
            lines.append(f"Changed {key}: {old[key]} -> {new[key]}")
    return lines


def diff_keys(old, new):
    lines = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if key not in old:
            lines.append(f"Added {key}")
        elif key not in new:
            lines.append(f"Removed {key}")
        else:
            lines.append(f"Changed {key}")
    return lines


def diff_details(old, new):
    lines = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if key in HASHED_DETAILS:
            lines.append(f"Changed {key}")
        elif key not in old:
            lines.append(f"Added {key}: {display(new[key])}")
        elif key not in new:
            lines.append(f"Removed {key}: {display(old[key])}")
        else:
            lines.append(f"Changed {key}: {display(old[key])} -> {display(new[key])}")
    return lines


def describe_store_changes(old, new):
    sections = []

    for key, title in (
        ("categories", "Changed Store Categories"),
        ("genres", "Changed Store Genres"),
        ("movies", "Changed Store Trailers"),
    ):
        lines = diff_named(old.get(key) or {}, new.get(key) or {})
        if lines:
            sections.append((title, lines))

    old_shots = old.get("screenshots") or []
    new_shots = new.get("screenshots") or []
    if old_shots != new_shots:
        added = len(set(new_shots) - set(old_shots))
        removed = len(set(old_shots) - set(new_shots))
        lines = []
        if added:
            lines.append(f"Added {added} ({len(new_shots)} total)")
        if removed:
            lines.append(f"Removed {removed} ({len(new_shots)} total)")
        if lines:
            sections.append(("Changed Store Screenshots", lines))

    if old.get("description") != new.get("description"):
        old_length = (old.get("description") or {}).get("length")
        new_length = (new.get("description") or {}).get("length")
        sections.append(
            (
                "Changed Store Description",
                [f"Changed description ({old_length} -> {new_length} chars)"],
            )
        )

    lines = diff_keys(old.get("images") or {}, new.get("images") or {})
    if lines:
        sections.append(("Changed Store Images", lines))

    lines = diff_details(old.get("details") or {}, new.get("details") or {})
    if lines:
        sections.append(("Changed Store Details", lines))

    old_money = old.get("monetization") or {}
    new_money = new.get("monetization") or {}
    lines = []
    for key in ("is_free", "price"):
        if old_money.get(key) != new_money.get(key):
            if key == "price":
                old_value = display_price(old_money.get(key))
                new_value = display_price(new_money.get(key))
            else:
                old_value = display(old_money.get(key))
                new_value = display(new_money.get(key))
            lines.append(f"Changed {key}: {old_value} -> {new_value}")
    for key in ("packages", "dlc"):
        old_items = old_money.get(key) or []
        new_items = new_money.get(key) or []
        for item in sorted(set(new_items) - set(old_items)):
            lines.append(f"Added {key}: {item}")
        for item in sorted(set(old_items) - set(new_items)):
            lines.append(f"Removed {key}: {item}")
    if lines:
        sections.append(("Changed Store Monetization", lines))

    return sections


def format_store_sections(sections):
    blocks = ["Store page updated"]
    for title, lines in sections:
        blocks.append(title + "\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def retry(func, attempts=3, delay=10):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return func(), attempt
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(delay)
    raise RuntimeError(f"{func.__name__} failed after {attempts} attempts: {last_error}") from last_error


def load_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_image(text):
    width = 1080
    height = 1080
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    size = 120
    font = load_font(size)
    while size > 40:
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= 900:
            break
        size -= 10
        font = load_font(size)
    box = draw.textbbox((0, 0), text, font=font)
    x = (width - (box[2] - box[0])) / 2 - box[0]
    y = (height - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def send_photo(text, caption):
    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
        data={"chat_id": CHAT_ID, "caption": caption},
        files={"photo": ("blyakada.png", make_image(text), "image/png")},
        timeout=30,
    )
    response.raise_for_status()


def send_message(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=30,
    )
    response.raise_for_status()


def send_log(text):
    if not ADMIN_CHAT_ID:
        return
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": ADMIN_CHAT_ID, "text": text},
            timeout=30,
        )
        response.raise_for_status()
    except Exception:
        pass


def main():
    state = load_state()
    now = datetime.now(MSK)
    today = now.date().isoformat()
    info, steam_attempt = retry(get_app_info)
    store_error = None
    try:
        store, store_attempt = retry(get_store_info)
    except Exception as error:
        store = None
        store_attempt = 3
        store_error = str(error)

    updated = False
    daily = False
    store_sections = []
    old_build = None

    if not state.get("buildid"):
        state["buildid"] = info["buildid"]
        state["manifests"] = info["manifests"]
        state["last_update"] = datetime.fromtimestamp(info["timeupdated"], MSK).date().isoformat()
        if store:
            state["store"] = store
        save_state(state)
    elif state["buildid"] != info["buildid"] or state.get("manifests") != info["manifests"]:
        old_build = state["buildid"]
        send_photo(
            "Обнова вышла!!!",
            f"build {old_build} → {info['buildid']}\nhttps://steamdb.info/app/{APPID}/history/",
        )
        state["buildid"] = info["buildid"]
        state["manifests"] = info["manifests"]
        state["last_update"] = today
        state["last_daily"] = today
        if store:
            state["store"] = store
        save_state(state)
        updated = True
    elif store:
        old_store = state.get("store") or {}
        if old_store.get("version") == store["version"]:
            store_sections = describe_store_changes(old_store, store)
        state["store"] = store
        public_sections = [
            section
            for section in store_sections
            if section[0] != "Changed Store Monetization"
        ]
        if public_sections:
            send_message(format_store_sections(public_sections))
        save_state(state)

    if now.hour >= DAILY_HOUR and state.get("last_daily") != today:
        last_update = date.fromisoformat(state["last_update"])
        days = (now.date() - last_update).days + 1
        send_photo("Обнова не вышла", f"День {days} без обновления.")
        state["last_daily"] = today
        save_state(state)
        daily = True

    last_update_date = date.fromisoformat(state["last_update"])
    days_without_update = (now.date() - last_update_date).days + 1
    update_line = f"update: yes ({old_build} -> {info['buildid']})" if updated else "update: no"

    lines = [
        f"Check {now.strftime('%Y-%m-%d %H:%M:%S')} MSK / {now.astimezone(timezone.utc).strftime('%H:%M:%S')} UTC",
        "",
        f"appid: {APPID}",
        f"build: {info['buildid']}",
        "manifests: " + ", ".join(f"{key}={value}" for key, value in info["manifests"].items()),
        f"steam_attempt: {steam_attempt}/3",
        f"store_attempt: {store_attempt}/3",
        "",
        f"store: {'error' if store_error else 'ok'}",
    ]
    if store:
        lines.append(f"trailers: {len(store['movies'])}")
        lines.append(f"screenshots: {len(store['screenshots'])}")
        lines.append(f"is_free: {display(store['monetization']['is_free'])}")
        lines.append(f"packages: {len(store['monetization']['packages'])}")
        lines.append(f"dlc: {len(store['monetization']['dlc'])}")
        lines.append(f"price: {display_price(store['monetization']['price'])}")
    lines.append(
        "changed: "
        + (
            ", ".join(title for title, _ in store_sections)
            if store_sections
            else "none"
        )
    )
    for title, section_lines in store_sections:
        if title == "Changed Store Monetization":
            lines.extend(["", title + "\n" + "\n".join(section_lines)])
    if store_error:
        lines.append(f"store_error: {store_error}")
    lines.extend(
        [
            "",
            update_line,
            f"last_update: {state['last_update']}",
            f"days_without_update: {days_without_update}",
            "",
            f"daily: {'yes' if daily else 'no'}",
            f"last_daily: {state.get('last_daily') or 'none'}",
            f"today: {today}",
        ]
    )
    send_log("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        send_log(f"Check failed\n\n{error}")
        raise