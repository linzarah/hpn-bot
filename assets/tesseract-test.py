import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\jose-miguel\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

COORDS = {
    "mine": (800, 140, 1110, 320),
    "opponent": (1480, 140, 1690, 320),
    "date": (1810, 140, 2015, 180),
    "total": (1105, 175, 1350, 217),
    "rank": (400, 310, 710, 430),
}


def extract_league():
    league_image = Image.open("C:/Users/jose-miguel/downloads/league.jpg")

    crop = league_image.crop(COORDS["total"])
    crop.save("C:/Users/jose-miguel/downloads/test.jpg")

    total_points = pytesseract.image_to_string(crop).replace(" ", "").removesuffix("\n")
    print(total_points)

    rank = (
        pytesseract.image_to_string(league_image.crop(COORDS["rank"]))
        .replace("\n", " ")
        .removesuffix(" ")
    )
    print(rank)

    return total_points, rank


print(extract_league())
