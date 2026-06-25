from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


SOURCE_URL = "https://www.nascar.com/drivers/nascar-cup-series/"
ENTRY_LIST_URL = "https://www.nascar.com/news-media/2026/06/22/2026-nascar-cup-series-entry-list-for-sonoma-raceway/"
SCHEDULE_PATH = Path("cup-series-schedule.json")
OUTPUT_PATH = Path("cup-series-drivers.json")

DRIVER_AVERAGES_TRACK_URL = "https://www.driveraverages.com/nascar/track_avg.php?trk_id={track_id}"
DRIVER_AVERAGES_ALLSTAR_URL = "https://www.driveraverages.com/nascar/allstar.php"

DRIVER_AVERAGES_TRACK_IDS = {
    "Atlanta Motor Speedway": 1,
    "Bristol Motor Speedway": 2,
    "Charlotte Motor Speedway": 13,
    "Chicagoland Speedway": 4,
    "Circuit of The Americas": 211,
    "Darlington Raceway": 5,
    "Daytona International Speedway": 6,
    "Homestead-Miami Speedway": 8,
    "Indianapolis Motor Speedway": 9,
    "Iowa Speedway": 55,
    "Kansas Speedway": 11,
    "Las Vegas Motor Speedway": 12,
    "Martinsville Speedway": 14,
    "Michigan International Speedway": 15,
    "Nashville Superspeedway": 57,
    "New Hampshire Motor Speedway": 16,
    "North Wilkesboro Speedway": 24,
    "Phoenix Raceway": 17,
    "Pocono Raceway": 18,
    "Richmond Raceway": 19,
    "Sonoma Raceway": 10,
    "Talladega Superspeedway": 20,
    "Texas Motor Speedway": 21,
    "Watkins Glen International": 22,
    "World Wide Technology Raceway": 61,
}

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


def load_driver_averages_track_page(track_id: int) -> BeautifulSoup:
    response = requests.get(
        DRIVER_AVERAGES_TRACK_URL.format(track_id=track_id),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def load_driver_averages_race_page(race_url: str) -> BeautifulSoup:
    response = requests.get(
        race_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def load_driver_averages_allstar_page() -> BeautifulSoup:
    response = requests.get(
        DRIVER_AVERAGES_ALLSTAR_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        },
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


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))

    return re.sub(r"[^a-z0-9]+", "", ascii_value.lower())


def parse_int(value: str) -> int:
    cleaned = clean_text(value).replace(",", "")
    return int(cleaned) if cleaned.isdigit() else 0


def parse_driver_averages_track_stats(soup: BeautifulSoup) -> dict[str, dict[str, int]]:
    stats_by_driver: dict[str, dict[str, int]] = {}
    active_heading = soup.find(string=re.compile(r"Active Driver Career History", re.IGNORECASE))

    if active_heading is None:
        return stats_by_driver

    current = active_heading.parent
    while current is not None:
        current = current.find_next()
        if current is None:
            break

        if current.name in {"h1", "h2", "h3"}:
            break

        if current.name != "tr":
            continue

        cells = [clean_text(cell.get_text(" ")) for cell in current.find_all(["th", "td"])]
        if len(cells) < 11 or not cells[0].isdigit():
            continue

        driver_name = cells[1]
        stats_by_driver[normalize_name(driver_name)] = {
            "starts": parse_int(cells[3]),
            "wins": parse_int(cells[4]),
            "top5": parse_int(cells[5]),
            "top10": parse_int(cells[6]),
            "poles": parse_int(cells[10]),
        }

    return stats_by_driver


def parse_driver_averages_allstar_stats(soup: BeautifulSoup) -> dict[str, dict[str, int]]:
    stats_by_driver: dict[str, dict[str, int]] = {}
    recent_heading = soup.find(string=re.compile(r"All-Star Race Recent Performance", re.IGNORECASE))

    if recent_heading is None:
        return stats_by_driver

    current = recent_heading.parent
    while current is not None:
        current = current.find_next()
        if current is None:
            break

        text = clean_text(current.get_text(" ")) if hasattr(current, "get_text") else ""
        if "Career Stats:" in text:
            break

        if current.name != "tr":
            continue

        cells = [clean_text(cell.get_text(" ")) for cell in current.find_all(["th", "td"])]
        if len(cells) < 7 or not cells[0].isdigit():
            continue

        driver_name = cells[1]
        stats_by_driver[normalize_name(driver_name)] = {
            "starts": parse_int(cells[3]),
            "wins": parse_int(cells[4]),
            "top5": parse_int(cells[5]),
            "top10": parse_int(cells[6]),
            "poles": 0,
        }

    return stats_by_driver


def find_previous_season_driver_averages_race_urls(soup: BeautifulSoup, season_year: int) -> list[str]:
    recent_heading = soup.find(string=re.compile(r"Recent Races at", re.IGNORECASE))
    if recent_heading is None or recent_heading.parent is None:
        return []

    race_urls: list[str] = []
    current = recent_heading.parent
    while current is not None:
        current = current.find_next()
        if current is None:
            break

        if current.name in {"h1", "h2", "h3"}:
            break

        if current.name != "a":
            continue

        href = current.get("href", "")
        race_year_match = re.search(r"\b(20\d{2})\b", clean_text(current.get_text(" ")))
        race_year = parse_int(race_year_match.group(1)) if race_year_match else 0

        if "race.php?sked_id=" in href and race_year and race_year < season_year:
            race_urls.append(urljoin("https://www.driveraverages.com/nascar/", href))

    return race_urls


def extract_race_year(soup: BeautifulSoup) -> int:
    text = soup.get_text("\n")
    match = re.search(r"Date:\s*[^\n,]+,\s+[A-Za-z]+\s+\d{1,2},\s+(\d{4})", text)
    if match:
        return parse_int(match.group(1))

    match = re.search(r"\b(20\d{2})\b", text)
    return parse_int(match.group(1)) if match else 0


def parse_driver_averages_previous_race(soup: BeautifulSoup) -> tuple[int, dict[str, dict[str, int]]]:
    year = extract_race_year(soup)
    results_by_driver: dict[str, dict[str, int]] = {}

    for row in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ")) for cell in row.find_all(["th", "td"])]
        if len(cells) < 12:
            continue

        if cells[0].isdigit() and cells[1].isdigit():
            driver_name = cells[3]
            results_by_driver.setdefault(normalize_name(driver_name), {})
            results_by_driver[normalize_name(driver_name)].update(
                {
                    "year": year,
                    "qualifyingPosition": parse_int(cells[1]),
                    "stage1FinishPosition": parse_int(cells[10]) if len(cells) > 10 else 0,
                    "stage2FinishPosition": parse_int(cells[11]) if len(cells) > 11 else 0,
                    "finishPosition": parse_int(cells[0]),
                    "lapsLed": parse_int(cells[7]),
                }
            )

        if cells[0].isdigit() and not cells[1].isdigit():
            driver_name = cells[1]
            results_by_driver.setdefault(normalize_name(driver_name), {"year": year})
            results_by_driver[normalize_name(driver_name)]["fastestLaps"] = parse_int(cells[11])

    return year, results_by_driver


def load_previous_race_results(
    track_name: str,
    track_soup: BeautifulSoup,
    season_year: int,
) -> dict[str, dict[str, int]]:
    race_urls = find_previous_season_driver_averages_race_urls(track_soup, season_year)
    if not race_urls:
        print(f"Skipping previous race results for {track_name}: no prior-season race link found")
        return {}

    results_by_driver: dict[str, dict[str, int]] = {}
    for race_url in race_urls:
        try:
            race_soup = load_driver_averages_race_page(race_url)
            _year, race_results = parse_driver_averages_previous_race(race_soup)
        except requests.RequestException as error:
            print(f"Skipping previous race result page for {track_name}: {error}")
            continue

        for driver_key, result in race_results.items():
            results_by_driver.setdefault(driver_key, result)

    if not results_by_driver:
        print(f"Skipping previous race results for {track_name}: no results found")

    return results_by_driver


def load_schedule_track_names(schedule_path: Path) -> list[str]:
    if not schedule_path.exists():
        return []

    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    track_names = {
        clean_text(race.get("trackName", ""))
        for race in schedule.get("races", [])
        if clean_text(race.get("trackName", ""))
    }

    return sorted(track_names)


def load_track_data(
    track_names: list[str],
) -> tuple[dict[str, dict[str, dict[str, int]]], dict[str, dict[str, dict[str, int]]]]:
    track_stats: dict[str, dict[str, dict[str, int]]] = {}
    previous_race_results: dict[str, dict[str, dict[str, int]]] = {}

    for track_name in track_names:
        track_id = DRIVER_AVERAGES_TRACK_IDS.get(track_name)
        if track_id is None:
            print(f"Skipping DriverAverages stats for unmapped track: {track_name}")
            continue

        try:
            soup = load_driver_averages_track_page(track_id)
            stats = parse_driver_averages_track_stats(soup)
        except requests.RequestException as error:
            print(f"Skipping DriverAverages stats for {track_name}: {error}")
            continue

        if stats:
            track_stats[track_name] = stats
        else:
            if track_name == "North Wilkesboro Speedway":
                try:
                    allstar_soup = load_driver_averages_allstar_page()
                    stats = parse_driver_averages_allstar_stats(allstar_soup)
                except requests.RequestException as error:
                    print(f"Skipping All-Star stats for {track_name}: {error}")

            if stats:
                track_stats[track_name] = stats
            else:
                print(f"Skipping DriverAverages stats for {track_name}: no stats found")

        results = load_previous_race_results(track_name, soup, datetime.now(timezone.utc).year)
        if results:
            previous_race_results[track_name] = results

    return track_stats, previous_race_results


def attach_track_stats(
    drivers: list[dict[str, object]],
    track_stats: dict[str, dict[str, dict[str, int]]],
) -> None:
    for driver in drivers:
        driver_key = normalize_name(str(driver.get("displayName", "")))
        driver_track_stats = []

        for track_name, stats_by_driver in track_stats.items():
            stats = stats_by_driver.get(driver_key)
            if stats is None:
                continue

            driver_track_stats.append(
                {
                    "trackName": track_name,
                    "starts": stats["starts"],
                    "poles": stats["poles"],
                    "top10": stats["top10"],
                    "top5": stats["top5"],
                    "wins": stats["wins"],
                }
            )

        driver["trackStats"] = sorted(driver_track_stats, key=lambda stats: str(stats["trackName"]))


def attach_previous_race_results(
    drivers: list[dict[str, object]],
    previous_race_results: dict[str, dict[str, dict[str, int]]],
) -> None:
    for driver in drivers:
        driver_key = normalize_name(str(driver.get("displayName", "")))
        driver_results = []

        for track_name, results_by_driver in previous_race_results.items():
            result = results_by_driver.get(driver_key)
            if result is None:
                continue

            driver_results.append(
                {
                    "trackName": track_name,
                    "year": result.get("year", 0),
                    "qualifyingPosition": result.get("qualifyingPosition", 0),
                    "stage1FinishPosition": result.get("stage1FinishPosition", 0),
                    "stage2FinishPosition": result.get("stage2FinishPosition", 0),
                    "finishPosition": result.get("finishPosition", 0),
                    "lapsLed": result.get("lapsLed", 0),
                    "fastestLaps": result.get("fastestLaps", 0),
                }
            )

        driver["previousRaceResults"] = sorted(driver_results, key=lambda result: str(result["trackName"]))


def validate_driver_stats_output(drivers: list[dict[str, object]]) -> None:
    track_stats_count = sum(len(driver.get("trackStats", [])) for driver in drivers)
    previous_results_count = sum(len(driver.get("previousRaceResults", [])) for driver in drivers)

    if track_stats_count < 100:
        raise RuntimeError(
            f"Expected at least 100 driver track-stat rows, found {track_stats_count}. "
            "Refusing to overwrite driver data with an incomplete scrape."
        )

    if previous_results_count < 100:
        raise RuntimeError(
            f"Expected at least 100 previous-race result rows, found {previous_results_count}. "
            "Refusing to overwrite driver data with an incomplete scrape."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update NASCAR Cup Series driver data.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    soup = load_driver_page()
    entry_list_soup = load_entry_list_page()
    teams_by_number = parse_entry_list_teams(entry_list_soup)
    drivers = parse_drivers(soup, teams_by_number)
    track_names = load_schedule_track_names(SCHEDULE_PATH)
    track_stats, previous_race_results = load_track_data(track_names)
    attach_track_stats(drivers, track_stats)
    attach_previous_race_results(drivers, previous_race_results)
    validate_driver_stats_output(drivers)

    if len(drivers) < 20:
        raise RuntimeError(f"Expected at least 20 Cup drivers, found {len(drivers)}.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output = {
        "season": datetime.now(timezone.utc).year,
        "series": "Cup",
        "sourceUrl": SOURCE_URL,
        "entryListUrl": ENTRY_LIST_URL,
        "driverAveragesTrackUrl": DRIVER_AVERAGES_TRACK_URL,
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
