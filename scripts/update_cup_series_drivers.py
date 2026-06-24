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
ENTRY_LIST_URL = "https://www.nascar.com/news-media/2026/06/22/2026-nascar-cup-series-entry-list-for-sonoma-raceway/"
OUTPUT_PATH = Path("cup-series-drivers.json")

TEAM_MANUFACTURERS = {
    "23XI Racing": "Toyota",
    "Front Row Motorsports": "Ford",
    "Garage 66": "Ford",
    "Haas Factory Team": "Chevrolet",
    "Hendrick Motorsports": "Chevrolet",
    "HYAK Motorsports": "Chevrolet",
    "Hyak Motorsports": "Chevrolet",
    "Joe Gibbs Racing": "Toyota",
    "Kaulig Racing": "Chevrolet",
    "Legacy Motor Club": "Toyota",
    "RFK Racing": "Ford",
    "Richard Childress Racing": "Chevrolet",
    "Rick Ware Racing": "Chevrolet",
    "Spire Motorsports": "Chevrolet",
    "Team Penske": "Ford",
    "Trackhouse Racing": "Chevrolet",
    "Wood Brothers Racing": "Ford",
}

FULL_TIME_TEAMS_BY_NUMBER = {
    "1": "Trackhouse Racing",
    "2": "Team Penske",
    "3": "Richard Childress Racing",
    "4": "Front Row Motorsports",
    "5": "Hendrick Motorsports",
    "6": "RFK Racing",
    "7": "Spire Motorsports",
    "9": "Hendrick Motorsports",
    "10": "Kaulig Racing",
    "11": "Joe Gibbs Racing",
    "12": "Team Penske",
    "16": "Kaulig Racing",
    "17": "RFK Racing",
    "19": "Joe Gibbs Racing",
    "20": "Joe Gibbs Racing",
    "21": "Wood Brothers Racing",
    "22": "Team Penske",
    "23": "23XI Racing",
    "24": "Hendrick Motorsports",
    "34": "Front Row Motorsports",
    "35": "23XI Racing",
    "38": "Front Row Motorsports",
    "41": "Haas Factory Team",
    "42": "Legacy Motor Club",
    "43": "Legacy Motor Club",
    "45": "23XI Racing",
    "47": "HYAK Motorsports",
    "48": "Hendrick Motorsports",
    "51": "Rick Ware Racing",
    "54": "Joe Gibbs Racing",
    "60": "RFK Racing",
    "71": "Spire Motorsports",
    "77": "Spire Motorsports",
    "88": "Trackhouse Racing",
    "97": "Trackhouse Racing",
}


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


def load_entry_list_page() -> BeautifulSoup:
    response = requests.get(
        ENTRY_LIST_URL,
        headers={"User-Agent": "FantasyAssist data updater"},
        timeout=30,
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def extract_car_number(text: str) -> str:
    match = re.search(r"Car number\s+([A-Za-z0-9-]+)", text, re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""


def parse_entry_list_teams(soup: BeautifulSoup) -> dict[str, str]:
    lines = [clean_text(line) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]
    teams_by_number: dict[str, str] = {}

    known_teams = set(TEAM_MANUFACTURERS)

    for index, line in enumerate(lines):
        car_number = extract_car_number(line)
        if not car_number:
            continue

        for candidate in lines[index + 1:index + 12]:
            if candidate in known_teams:
                teams_by_number[car_number] = candidate
                break

    return teams_by_number


def parse_drivers(soup: BeautifulSoup, teams_by_number: dict[str, str]) -> list[dict[str, object]]:
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
        team_name = teams_by_number.get(car_number, FULL_TIME_TEAMS_BY_NUMBER.get(car_number, ""))

        driver = {
            "firstName": first_name,
            "lastName": last_name,
            "displayName": full_name,
            "carNumber": car_number,
            "teamName": team_name,
            "manufacturer": TEAM_MANUFACTURERS.get(team_name, detect_manufacturer(card)),
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
    entry_list_soup = load_entry_list_page()
    teams_by_number = parse_entry_list_teams(entry_list_soup)
    drivers = parse_drivers(soup, teams_by_number)

    if len(drivers) < 20:
        raise RuntimeError(f"Expected at least 20 Cup drivers, found {len(drivers)}.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output = {
        "season": datetime.now(timezone.utc).year,
        "series": "Cup",
        "sourceUrl": SOURCE_URL,
        "entryListUrl": ENTRY_LIST_URL,
        "generatedAtUtc": generated_at,
        "drivers": drivers,
    }

    output_path = Path(args.output)
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        existing_compare = dict(existing)
        output_compare = dict(output)
        existing_compare.pop("generatedAtUtc", None)
        output_compare.pop("generatedAtUtc", None)

        if existing_compare == output_compare:
            output["generatedAtUtc"] = existing.get("generatedAtUtc", generated_at)

    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(drivers)} Cup drivers to {output_path}")


if __name__ == "__main__":
    main()
