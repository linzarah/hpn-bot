import io
import logging
import re
from datetime import date

import cv2
import numpy as np
import pytesseract
from PIL import Image

WAR_COORDS = {
    "points_scored": (0.335, 0.21, 0.405, 0.26),
    "opponent_server": (0.67, 0.1, 0.766, 0.14),
    "opponent_guild": (0.67, 0.15, 0.87, 0.2),
    "opponent_scored": (0.705, 0.21, 0.79, 0.26),
    "date": (0.84, 0.09, 0.955, 0.135),
}
LEAGUE_COORDS = {
    "large": {
        "total": (0.465, 0.15, 0.6, 0.21),
        "total2": (0.545, 0.16, 0.66, 0.22),
        "rank": (0.09, 0.287, 0.32, 0.38),
        "rank2": (0.31, 0.288, 0.43, 0.39),
    },
    "medium": {
        "total": (0.464, 0.15, 0.6, 0.21),
        "total2": (0.54, 0.16, 0.66, 0.22),
        "rank": (0.145, 0.287, 0.32, 0.38),
        "rank2": (0.31, 0.288, 0.43, 0.39),
    },
    "slim": {
        "total": (0.464, 0.16, 0.64, 0.21),
        "total2": (0.56, 0.16, 0.67, 0.22),
        "rank": (0.1, 0.287, 0.3, 0.39),
        "rank2": (0.26, 0.288, 0.435, 0.39),
    },
    "skinny": {
        "total": (0.464, 0.2, 0.6, 0.28),
        "total2": (0.555, 0.21, 0.66, 0.26),
        "rank": (0.14, 0.33, 0.3, 0.41),
        "rank2": (0.31, 0.33, 0.43, 0.41),
    },
    "zflip": {
        "total": (0.54, 0.435, 0.6, 0.46),
        "total2": (0.58, 0.435, 0.66, 0.46),
        "rank": (0.14, 0.51, 0.3, 0.6),
        "rank2": (0.31, 0.51, 0.43, 0.6),
    },
}
LEAGUES = {
    "Baron": {"Baron"},
    "Viscount": {"Viscount", "Vicomte", "Visconte"},
    "Earl": {"Earl", "Comte"},
    "Marquis": {"Marquis", "Marchese"},
}


def extract_war(img_bytes, debug=False):
    panel, W, H = _adjust_screenshot(img_bytes)

    result = {}
    for key, (x1, y1, x2, y2) in WAR_COORDS.items():
        crop = panel.crop((x1 * W, y1 * H, x2 * W, y2 * H))
        if debug:
            crop.show()
        label: str = pytesseract.image_to_string(crop, config="--psm 7").strip()
        if key in (
            "points_scored",
            "opponent_scored",
            "opponent_server",
        ):
            number = re.search(r"\d+", label)
            data = int(number.group()) if number and number.group().isdigit() else None
        elif key == "date":
            day, month, year = label.removesuffix(" J").split("/")
            try:
                data = date(int(year), int(month), int(day))
            except Exception as e:
                logging.error(e)
                data = None
        else:
            data = label
        result[key] = data

    return result


def _adjust_screenshot(img_bytes):
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
    return panel, W, H


def _get_coords(name, size):
    W, H = size
    rat = W / H
    if rat < 1.3:
        category = "zflip"
    elif rat < 1.5:
        category = "skinny"
    elif rat < 2:
        category = "slim"
    elif rat < 2.2:
        category = "medium"
    else:
        category = "large"
    x1, y1, x2, y2 = LEAGUE_COORDS[category][name]
    left = x1 * W
    top = y1 * H
    right = x2 * W
    bottom = y2 * H
    return left, top, right, bottom


def get_label(image: Image.Image, name: str, debug: bool) -> str:
    crop = image.crop(_get_coords(name, image.size))
    if debug:
        crop.show()
    config = (
        "--psm 7 -c tessedit_char_whitelist=0123456789/"
        if name.startswith("total")
        else "--psm 6"
    )
    return pytesseract.image_to_string(crop, config=config)


def extract_league(img_bytes, debug=False):
    image = Image.open(io.BytesIO(img_bytes))
    if debug:
        print(image.width / image.height)

    league = None
    total = None
    rank = get_label(image, "rank", debug)
    for e_league, translations in LEAGUES.items():
        if any(w in rank for w in translations):
            league = e_league
    if league is None:
        rank = get_label(image, "rank2", debug)
        if "Duke" in rank or "Duc" in rank:
            league = "Duke"
            total = get_label(image, "total2", debug)
    if total is None:
        total = get_label(image, "total", debug)

    matches = re.findall(r"\d+", rank)
    division = int(matches[-1]) if matches else None
    result = {"league": league, "division": division, "total_points": None}
    points = re.search(r"\d+ ?\d*", total)
    if points is not None:
        points = points.group().replace(" ", "")
        result["total_points"] = int(points[: _get_chars(league, division, points)])

    return result


def _get_chars(league: str, division: int, points: str):
    if league == "Duke" or (league == "Marquis" and points.startswith("1")):
        return 5
    if league == "Baron" and (
        (division == 3 and not points.startswith("1")) or division == 4
    ):
        return 3
    return 4
