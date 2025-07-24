import os
import re

import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\jose-miguel\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)


COORDS = {
    "mine": (0.318, 0.13, 0.462, 0.3),
    "opponent": (0.617, 0.13, 0.765, 0.3),
    "date": (0.76, 0.13, 0.85, 0.167),
    "total": (0.44, 0.15, 0.65, 0.21),
    "rank": (0.142, 0.287, 0.3, 0.39),
    "rank2": (0.35, 0.288, 0.45, 0.39),
}

DIR = "C:\\Users\jose-miguel\Documents\Dev\Python\hpn-bot\images"


def get_coords(name, size):
    W, H = size
    rat = W / H
    x1, y1, x2, y2 = COORDS[name]
    left = x1 * W
    top = y1 * H
    right = x2 * W
    bottom = y2 * H
    if rat < 1.5:
        left -= W / 25
        right -= W / 30
        top += H / 22
        bottom += H / 22
    elif rat < 2:
        left -= W / 12
        right -= W / 30
        bottom *= 1.1
    return left, top, right, bottom


def get_info_from_title(text: str) -> tuple[int, str, int]:
    print(text)
    n = 0
    for line in text.split("\n"):
        if not line:
            continue
        if n == 0:
            server_number = int(re.search(r"\d+\.?\d*", line).group())
        if n == 1:
            guild = line
        if n == 2:
            points = int(re.search(r"\d+\.?\d*", line).group())
        n += 1
    return server_number, guild, points


def extract_war():
    war_image = Image.open(
        "C:/Users/jose-miguel/documents/dev/python/hpn-bot/images/war5.png"
    )

    mytext = pytesseract.image_to_string(
        war_image.crop(get_coords("mine", war_image.size))
    )
    opptext = pytesseract.image_to_string(
        war_image.crop(get_coords("opponent", war_image.size))
    )

    server_number, guild_name, points_scored = get_info_from_title(mytext)
    opponent_server, opponent_guild, opponent_scored = get_info_from_title(opptext)

    date = pytesseract.image_to_string(
        war_image.crop(get_coords("date", war_image.size))
    ).removesuffix("\n")
    return (
        server_number,
        guild_name,
        points_scored,
        opponent_server,
        opponent_guild,
        opponent_scored,
        date,
    )


def get_label(image: Image.Image, name) -> str:
    crop = image.crop(get_coords(name, image.size))
    crop.show()
    return pytesseract.image_to_string(crop, config="--psm 6").strip("\n]*-\|[()-_ ")


def extract_league(fp):
    image = Image.open(f"C:/Users/jose-miguel/documents/dev/python/hpn-bot/images/{fp}")

    result = {}
    rank = get_label(image, "rank")
    chars = 5 if "Marquis" in rank and "4" not in rank else 4
    if not rank or not any(
        [w in rank for w in ("Duke", "Duca", "Marquis", "Earl", "Viscount")]
    ):
        chars = 5
        rank = get_label(image, "rank2")
    result["rank"] = rank.replace("\n", " ")
    total = get_label(image, "total")
    print(total)
    result["total"] = int(
        re.search(r"\d+ ?\d*", total).group().replace(" ", "")[:chars]
    )

    print(result)

    return result


for fp in os.listdir(DIR):
    if fp.startswith("war"):
        continue
    if any(w in fp for w in ("0", "1", "2", "3", "4", "5", "6", "7", "8")):
        continue
    extract_league(fp)
    break


def print_sizes():
    for image_fp in os.listdir(DIR):
        if image_fp.startswith("league"):
            continue
        image = Image.open(os.path.join(DIR, image_fp))
        coords = get_coords("mine", image.size)
        image = image.crop(coords)
        print(image_fp, coords)
        print("===========")
        image.show(image_fp)
        print(get_info_from_title(pytesseract.image_to_string(image)))


def ratio():
    ratios = {}
    for image_fp in os.listdir(DIR):
        image = Image.open(os.path.join(DIR, image_fp))
        rat = image.size[0] / image.size[1]
        if rat < 2:
            print(image)
        f_rat = f"{rat:.2f}"
        if f_rat in ratios:
            ratios[f_rat] += 1
        else:
            ratios[f_rat] = 1
    print(ratios)


def print_size():
    image_fp = "war5.png"
    image = Image.open(os.path.join(DIR, image_fp))
    coords = get_coords("mine", image.size)
    print(image_fp, image.size[0] / image.size[1])
    image = image.crop(coords)
    print("===========")
    image.show(image_fp)
    print(pytesseract.image_to_string(image))
