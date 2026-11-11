import json
import os
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont
from steam.client import SteamClient

APPID = 1049800
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "@blyakadaL"
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
    client.anonymous_login()
    try:
        data = client.get_product_info(apps=[APPID], timeout=30)
    finally:
        client.logout()
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


def main():
    state = load_state()
    info = get_app_info()
    now = datetime.now(MSK)
    today = now.date().isoformat()

    if not state.get("buildid"):
        state["buildid"] = info["buildid"]
        state["manifests"] = info["manifests"]
        state["last_update"] = datetime.fromtimestamp(info["timeupdated"], MSK).date().isoformat()
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
        save_state(state)

    if now.hour >= DAILY_HOUR and state.get("last_daily") != today:
        last_update = date.fromisoformat(state["last_update"])
        days = (now.date() - last_update).days + 1
        send_photo("Обнова не вышла", f"День {days} без обновления.")
        state["last_daily"] = today
        save_state(state)


if __name__ == "__main__":
    main()