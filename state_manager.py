import os, json

STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_zone": None,
        "last_cat1_status": None,
        "last_cat1_range": None
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)