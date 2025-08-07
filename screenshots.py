import io
import re

import cv2
import numpy as np
import pytesseract
from PIL import Image

WAR_COORDS = {
    "server_number": (0.37, 0.1, 0.457, 0.14),
    "guild_name": (0.23, 0.15, 0.457, 0.2),
    "points_scored": (0.335, 0.21, 0.405, 0.26),
    "opponent_server": (0.67, 0.1, 0.766, 0.14),
    "opponent_guild": (0.67, 0.15, 0.87, 0.2),
    "opponent_scored": (0.705, 0.21, 0.79, 0.26),
    "date": (0.84, 0.09, 0.955, 0.135),
}
LEAGUE_COORDS = {
    "medium": {
        "total": (0.45, 0.15, 0.6, 0.21),
        "total2": (0.5, 0.16, 0.66, 0.22),
        "rank": (0.15, 0.287, 0.32, 0.39),
        "rank2": (0.31, 0.288, 0.43, 0.39),
    },
    "slim": {
        "total": (0.45, 0.15, 0.6, 0.21),
        "total2": (0.5, 0.17, 0.67, 0.22),
        "rank": (0.1, 0.287, 0.25, 0.39),
        "rank2": (0.25, 0.288, 0.42, 0.39),
    },
    "skinny": {
        "total": (0.45, 0.2, 0.6, 0.28),
        "total2": (0.5, 0.21, 0.66, 0.26),
        "rank": (0.14, 0.33, 0.3, 0.41),
        "rank2": (0.31, 0.33, 0.43, 0.41),
    },
}


def extract_war(img_bytes):
    img_array = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (10, 50, 50), (30, 255, 255))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = (
        cv2.boundingRect(max(contours, key=cv2.contourArea))
        if contours
        else (0, 0, image.shape[1], image.shape[0])
    )

    panel = Image.fromarray(
        cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2RGB)
    )
    W, H = panel.size
    W = H * 1.8260105448154658

    result = {}

    for key, (x1, y1, x2, y2) in WAR_COORDS.items():
        crop = panel.crop((x1 * W, y1 * H, x2 * W, y2 * H))
        label: str = pytesseract.image_to_string(crop, config="--psm 6").strip()
        if key in (
            "points_scored",
            "opponent_scored",
            "server_number",
            "opponent_server",
        ):
            s_number = re.search(r"\d+", label)
            if not s_number:
                raise ValueError(f"{key} not found in screenshot")
            data = int(s_number.group())
        else:
            data = label
            if data == "LOADS OF AAGIIAAOK":
                data = "LORDS OF RAGNAROK"
        result[key] = data

    return result


def get_coords(name, size):
    W, H = size
    print(W / H)
    category = "medium"
    if W / H < 1.5:
        category = "skinny"
    elif W / H < 2:
        print(1)
        category = "slim"
    x1, y1, x2, y2 = LEAGUE_COORDS[category][name]
    left = x1 * W
    top = y1 * H
    right = x2 * W
    bottom = y2 * H
    return left, top, right, bottom


def get_label(image: Image.Image, name) -> str:
    crop = image.crop(get_coords(name, image.size))
    # crop.show()
    return pytesseract.image_to_string(crop, config="--psm 6").strip(
        "\n]*-\|[()-_ —.>»"
    )


def extract_league(img_bytes):
    image = Image.open(io.BytesIO(img_bytes))
    result = {}

    rank = get_label(image, "rank")
    chars = 5 if "Marquis" in rank and "4" not in rank else 4
    if not rank or not any([w in rank for w in ("Marquis", "Earl", "Viscount")]):
        chars = 5
        rank = get_label(image, "rank2")
        total = get_label(image, "total2")
    else:
        total = get_label(image, "total")
    result["rank"] = rank.replace("\n", " ")
    result["total_points"] = int(
        re.search(r"\d+ ?\d*", total).group().replace(" ", "")[:chars]
    )

    return result


"""# TESTING

import asyncio
import os
from collections import defaultdict

from database import add_submission, close_db, connect_db

DIR = "C:/Users/jose-miguel/documents/dev/python/hpn-bot/fails"

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\\Users\jose-miguel\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

di = defaultdict(dict)
for image in os.listdir(DIR):
    n = int(image.split(".")[0][-1:])
    with open(os.path.join(DIR, image), "rb") as f:
        bytes_ = f.read()
    if image.startswith("war"):
        di[n]["war"] = extract_war(bytes_)
    else:
        di[n]["league"] = extract_league(bytes_)
    
print(di)


async def main(war, league):
    await connect_db()
    await add_submission(**war, **league, submitted_by="Fused")
    await close_db()


for n, data in di.items():
   asyncio.run(main(data["war"], data["league"]))
"""
