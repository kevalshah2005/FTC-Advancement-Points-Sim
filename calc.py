import requests
import json
from datetime import datetime
import constants
import os
import math
from scipy.special import erfinv
from collections import defaultdict



HEADERS = {"Authorization": f"Basic {constants.API_TOKEN}"}
BASE_URL = "https://ftc-api.firstinspires.org/v2.0"

SEASON = 2024 # Change to the desired season
EVENT_CODE = "USNCCMP" # Change to the desired event code


def get_json(url, cache_file=None):
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return json.load(f)
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"Error fetching {url}: {response.status_code}")
        return {}
    data = response.json()
    if cache_file:
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
    return data

def get_all_teams(season, cache_file="teams.json"):
     # Check if the cache file exists
    if os.path.exists(cache_file):
        # If the cache file exists, read from it
        print(f"Reading data from cache file: {cache_file}")
        with open(cache_file, "r") as f:
            cached_data = json.load(f)
        
        return {team["teamNumber"]: team for team in cached_data}
    
    all_teams = []
    page = 1
    while True:
        url = f"{BASE_URL}/{season}/teams?page={page}"
        data = get_json(url)
        teams = data.get("teams", [])
        if not teams:
            break
        all_teams.extend(teams)
        if page >= data.get("pageTotal", 1):
            break
        page += 1

    # Save the data to the cache file for future use
    print(f"Saving data to cache file: {cache_file}")
    with open(cache_file, "w") as f:
        json.dump(all_teams, f, indent=2)

    # Return the data as a dictionary with team numbers as keys
    return {team["teamNumber"]: team for team in all_teams}

def parse_event_data(event_code):
    matches_url = f"{BASE_URL}/{SEASON}/matches/{event_code}"
    teams_url = f"{BASE_URL}/{SEASON}/teams?eventCode={event_code}"
    rankings_url = f"{BASE_URL}/{SEASON}/rankings/{event_code}"
    alliances_url = f"{BASE_URL}/{SEASON}/alliances/{event_code}"

    matches_data = get_json(matches_url)
    teams_data = get_json(teams_url)
    rankings_data = get_json(rankings_url)
    alliances_data = get_json(alliances_url)

    # Number of teams
    event_teams = teams_data.get("teams", [])
    num_teams = len(event_teams)

    # Rank per team
    rankings = {entry["teamNumber"]: entry["rank"] for entry in rankings_data.get("rankings", [])}

    # Alliance number
    alliance_map = {}
    for i, alliance in enumerate(alliances_data.get("alliances", []), start=1):
        alliance_map[alliance.get("captain", {})] = i
        alliance_map[alliance.get("round1", {})] = i

    # Awards
    def get_team_awards(team_number, event_code=None):
        # Fetch awards for a specific team at a specific event
        url = f"{BASE_URL}/{SEASON}/awards/{team_number}"
        if event_code:
            url += f"?eventCode={event_code}"
        awards_data = get_json(url)
        
        # Extract award information
        awards = []
        for award in awards_data.get("awards", []):
            award_name = award.get("name")
            if award_name:
                awards.append(award_name)
        
        return awards


    with open("matches.json", "w") as f:
        json.dump(matches_data, f, indent=2)

    playoff_matches = [match for match in matches_data.get("matches", []) if match.get("tournamentLevel") == "PLAYOFF"]

    def get_team_placements(matches):
        losses = {}          # teamNumber -> number of losses
        eliminated = {}      # teamNumber -> actualStartTime of elimination
        still_in = set()     # teams still in bracket
        all_teams = set()

        def get_alliance(match, color):
            return [team["teamNumber"] for team in match["teams"] if team["station"].startswith(color)]

        for match in matches:
            red = get_alliance(match, "Red")
            blue = get_alliance(match, "Blue")
            all_teams.update(red + blue)
            still_in.update(red + blue)

            red_score = match["scoreRedFinal"]
            blue_score = match["scoreBlueFinal"]

            winner = red if red_score > blue_score else blue
            loser = blue if red_score > blue_score else red

            for team in loser:
                if team not in losses:
                    losses[team] = 0
                losses[team] += 1
                if losses[team] == 2:
                    still_in.discard(team)
                    eliminated[team] = match["actualStartTime"]

        def get_alliance_by_team(team):
            for match in matches:
                for color in ["Red", "Blue"]:
                    alliance = get_alliance(match, color)
                    if team in alliance:
                        if all(member in eliminated or member == team or member in still_in for member in alliance):
                            return tuple(sorted(alliance))
            return None

        alliances = set()
        # First place = team(s) still in
        if still_in:
            first_alliance = get_alliance_by_team(list(still_in)[0])
            alliances.add(first_alliance)
        else:
            first_alliance = None

        # Then sort all eliminated teams by elimination time descending
        eliminated_sorted = sorted(eliminated.items(), key=lambda x: x[1], reverse=True)
        ordered_alliances = []
        for team, _ in eliminated_sorted:
            alliance = get_alliance_by_team(team)
            if alliance and alliance not in alliances:
                ordered_alliances.append(alliance)
                alliances.add(alliance)
            if len(ordered_alliances) >= 3:
                break

        placements = {
            1 : list(first_alliance) if first_alliance else None,
            2 : list(ordered_alliances[0]) if len(ordered_alliances) > 0 else None,
            3 : list(ordered_alliances[1]) if len(ordered_alliances) > 1 else None,
            4 : list(ordered_alliances[2]) if len(ordered_alliances) > 2 else None,
        }

        return placements

    team_alliance_rank = {}
    placements = get_team_placements(playoff_matches)
    for rank, teams in placements.items():
        if teams == None:
            continue
        for team in teams:
            team_alliance_rank[team] = rank
    
    # Compile data for each team
    result = {}
    for team in event_teams:
        num = team["teamNumber"]
        awards = get_team_awards(num, event_code)
        result[num] = {
            "rank": rankings.get(num),
            "alliance": alliance_map.get(num),
            "awards": awards,
            "allianceRank": team_alliance_rank.get(num),
        }

    return result, num_teams

# === MAIN ===
team_data = get_all_teams(SEASON)

event_results = {}

# First, build up event_results with all relevant event info:
team_results, total_teams = parse_event_data(EVENT_CODE)

for team_num, stats in team_results.items():
    if team_num not in event_results:
        event_results[team_num] = {
            "events": []
        }

    # Fetch event metadata (type & date) from the original event list
    # Reuse the filtered list from get_events_by_region
    matching_event = next(
        (e for e in get_json(f"{BASE_URL}/{SEASON}/events", "events.json")["events"] if e["code"] == EVENT_CODE),
        None
    )
    event_type = matching_event.get("type") if matching_event else None
    event_date = matching_event.get("dateStart") if matching_event else None

    event_entry = {
        "eventCode": EVENT_CODE,
        "type": event_type,
        "date": event_date,
        "num_teams": total_teams,
        **stats
    }

    event_results[team_num]["events"].append(event_entry)

# --- Now run advancement points calculations ---
def qualification_points(rank, num_teams, alpha=1.07):
    return math.ceil(erfinv((num_teams - 2 * rank + 2) / (alpha * num_teams)) * (7 / (erfinv(1 /  alpha))) + 9)

def calculate_district_points(event_results):
    team_points = {}

    for team_num, info in event_results.items():
        event_scores = []
        for _, event in enumerate(info["events"]):
            q_points = 0
            rank = event.get("rank")
            num_teams = event.get("num_teams", 0)
            if rank:
                q_points = qualification_points(rank, num_teams)

            alliance_bonus = 0
            if event.get("alliance") is not None:
                alliance_bonus = 21 - event["alliance"]

            playoff_bonus = 0
            if event.get("allianceRank") is not None:
                if event["allianceRank"] == 1:
                    playoff_bonus = 40
                elif event["allianceRank"] == 2:
                    playoff_bonus = 20
                elif event["allianceRank"] == 3:
                    playoff_bonus = 10
                elif event["allianceRank"] == 4:
                    playoff_bonus = 5

            awards = event.get("awards", [])
            award_bonus = 0
            for a in awards:
                if a == "Inspire Award":
                    award_bonus = max(award_bonus, 60)
                    break;
                elif a in ("Inspire Award 2nd Place"):
                    award_bonus = max(award_bonus, 30)
                    break;
                elif a in ("Inspire Award 3rd Place"):
                    award_bonus = max(award_bonus, 15)
                    break;
                elif ("2nd Place" in a):
                    award_bonus = max(award_bonus, 6)
                    break;
                elif ("3rd Place" in a):
                    award_bonus = max(award_bonus, 3)
                    break;
                elif ("Think" in a or "Connect" in a or "Innovate" in a or "Control" in a or "Motivate" in a or "Design" in a or "Judge" in a): # Must be 1st Place
                    award_bonus = max(award_bonus, 12)

            total = q_points + alliance_bonus + playoff_bonus + award_bonus

            event_scores.append((event["type"], total))

        # Calculate total district points
        total_points = total


        team_points[team_num] = {
            "qualification_points": q_points,
            "alliance_bonus": alliance_bonus,
            "playoff_bonus": playoff_bonus,
            "award_bonus": award_bonus,
            "total": total_points
        }

    return team_points

# Calculate and display results

team_district_points = calculate_district_points(event_results)
team_district_points = dict(sorted(team_district_points.items(), key=lambda item: item[1]["total"], reverse=True))

print(f"\nAdvancement Points Calculation for event {EVENT_CODE}:")

# Print header
print(f"{'Rank':<5} {'Team':<7} {'Qual':<8} {'Alliance':<10} {'Playoff':<8} {'Award':<6} {'Total':<6}")
print("-" * 50)

# Initialize variables for rank calculation
rank = 0
prev_score = None
ties = 0

# Print ranked teams with ties handled
for i, (team, scores) in enumerate(team_district_points.items()):
    total = scores['total']

    # If the current total is different from the previous total, assign a new rank
    if total != prev_score:
        rank = i + 1  # Rank starts from 1, so add 1 to the index
        ties = 0
    else:
        ties += 1  # Same score, same rank

    prev_score = total

    # Print the team data
    print(f"{rank:<5} {team:<7} {scores['qualification_points']:<8} {scores['alliance_bonus']:<10} {scores['playoff_bonus']:<8} {scores['award_bonus']:<6} {total:<6}")
    # print(team if scores['championship_points'] > 0 else "")


with open("team_district_points.json", "w") as f:
    json.dump(team_district_points, f, indent=2)



# print(json.dumps(team_district_points, indent=2))
