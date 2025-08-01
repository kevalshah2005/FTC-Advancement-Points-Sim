import json

# Load data from JSON file
with open("team_district_points.json", "r") as f:
    data = json.load(f)

# Sort teams by total points descending
sorted_teams = sorted(data.items(), key=lambda x: x[1]['total'], reverse=True)

# Print header
print(f"{'Rank':<5} {'Team':<7} {'Qual Points':<13} {'Champ Points':<14} {'Total':<6}")
print("-" * 50)

# Print ranked teams
for rank, (team, scores) in enumerate(sorted_teams, start=1):
    print(f"{rank:<5} {team:<7} {scores['qualifier_points']:<13} {scores['championship_points']:<14} {scores['total']:<6}")
