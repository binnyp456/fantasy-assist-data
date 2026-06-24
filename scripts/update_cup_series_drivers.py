from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


SOURCE_URL = "https://www.nascar.com/drivers/nascar-cup-series/"
OUTPUT_PATH = Path("cup-series-drivers.json")


def clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def split_driver_name(full_name: str) -> tuple[str, str]:
    parts = clean_text(full_name).split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""

    return parts[0], parts[1]


def absolute_url(value: str | None) -> str:
    if not value:
        return ""

    return urljoin(SOURCE_URL, value)


def detect_manufacturer(card) -> str:
    manufacturers = {
        "chevrolet": "Chevrolet",
        "chv": "Chevrolet",
        "ford": "Ford",
        "frd": "Ford",
        "toyota": "Toyota",
        "tyt": "Toyota",
    }

    for image in card.find_all("img"):
        text = " ".join(
            [
                image.get("alt", ""),
                image.get("src", ""),
                image.get("data-src", ""),
                image.get("data-lazy-src", ""),
            ]
        ).lower()

        for token, manufacturer in manufacturers.items():
            if token in text:
                return manufacturer

    return ""


def find_driver_card(image):
    current = image
    for _ in range(8):
        if current is None:
            break

        if current.name in {"article", "li"}:
            return current

        class_text = " ".join(current.get("class", [])).lower()
        if "driver" in class_text and "card" in class_text:
            return current

        current = current.parent

    return image.parent or image


def load_driver_page() -> BeautifulSoup:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "FantasyAssist data updater"},
        timeout=30,
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def parse_drivers(soup: BeautifulSoup) -> list[dict[str, object]]:
    anchors_by_name: dict[str, str] = {}
    for anchor in soup.find_all("a"):
        name = clean_text(anchor.get_text(" "))
        if name:
            anchors_by_name.setdefault(name.lower(), absolute_url(anchor.get("href")))

    drivers_by_number: dict[str, dict[str, object]] = {}
    badge_pattern = re.compile(r"^(?P<name>.+?)\s+Badge\s+Number\s+(?P<number>[A-Za-z0-9-]+)$")

    for image in soup.find_all("img"):
        alt = clean_text(image.get("alt", ""))
        match = badge_pattern.match(alt)
        if not match:
            continue

        full_name = clean_text(match.group("name"))
        car_number = clean_text(match.group("number"))
        first_name, last_name = split_driver_name(full_name)
        card = find_driver_card(image)

        driver = {
            "firstName": first_name,
            "lastName": last_name,
            "displayName": full_name,
            "carNumber": car_number,
            "teamName": "",
            "manufacturer": detect_manufacturer(card),
            "headshotUrl": "",
            "driverPageUrl": anchors_by_name.get(full_name.lower(), ""),
        }

        drivers_by_number[car_number] = driver

    drivers = list(drivers_by_number.values())
    drivers.sort(key=lambda driver: int(driver["carNumber"]) if str(driver["carNumber"]).isdigit() else 999)

    return drivers


def main() -> None:
    parser = argparse.ArgumentParser(description="Update NASCAR Cup Series driver data.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    soup = load_driver_page()
    drivers = parse_drivers(soup)

    if len(drivers) < 20:
        raise RuntimeError(f"Expected at least 20 Cup drivers, found {len(drivers)}.")

    output = {
        "season": datetime.now(timezone.utc).year,
        "series": "Cup",
        "sourceUrl": SOURCE_URL,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "drivers": drivers,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(drivers)} Cup drivers to {output_path}")


if __name__ == "__main__":
    main()
