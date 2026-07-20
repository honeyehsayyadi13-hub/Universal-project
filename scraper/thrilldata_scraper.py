import re
import json



def extract_wait_times(html_file):

    with open(html_file, "r", encoding="utf-8") as file:
        html = file.read()


    matches = re.findall(
        r'Plotly\.newPlot\(\s*".*?",\s*(\[.*?\]),\s*\{',
        html,
        re.DOTALL
    )


    if not matches:
        print("Could not find Plotly data")
        return []


    graphs = []

    for match in matches:
        try:
            graphs.extend(json.loads(match))
        except json.JSONDecodeError:
            continue


    wait_data = []


    for graph in graphs:

        print(
            "Graph:",
            graph.get("name"),
            "Type:",
            graph.get("type")
        )

        if graph.get("name") != "Posted Wait":
            continue

        for time, wait in zip(graph["x"], graph["y"]):

           wait_data.append({
                "timestamp": time,
                "waittime": wait,
                "issue_with_ride": False,
                "ride_id": 1
            })


    return wait_data



data = extract_wait_times("thrill-data.html")


print("Number of wait records:", len(data))


for item in data[:10]:
    print(item)
    
with open("wait_times.json", "w") as file:
    json.dump(data, file, indent=4)

print("Saved wait_times.json")