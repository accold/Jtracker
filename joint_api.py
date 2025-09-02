from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta
import json
import os
import random
import urllib.request

app = FastAPI()

DATA_FILE = "joints.json"
timeout_minutes = 5
fumble_chance = 0.05
portal_chance = 0.05
fuzzy_threshold = 0.6  # similarity ratio for username matching

# ---------- Persistent Data ----------
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
else:
    data = {"channels": {}}


def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def clean_user(name: str) -> str:
    if not name:
        return "UnknownUser"
    return name.split()[0].lstrip("@").strip()


def get_channel(channel: str):
    channel = channel.lower()
    if channel not in data["channels"]:
        data["channels"][channel] = {
            "joint": {"holder": None, "passes": 0, "burned": True, "last_pass_time": None},
            "stats": {"total_joints": 0, "nightbot_joints": 0, "users": {}}
        }
    else:
        if "nightbot_joints" not in data["channels"][channel]["stats"]:
            data["channels"][channel]["stats"]["nightbot_joints"] = 0
    return data["channels"][channel]


# ---------- Twitch chatters fetch ----------
def populate_users_from_twitch(channel: str):
    ch = get_channel(channel)
    try:
        url = f"https://tmi.twitch.tv/group/user/{channel}/chatters"
        with urllib.request.urlopen(url) as response:
            data_json = json.load(response)
        chatter_lists = data_json.get("chatters", {})
        all_users = []
        for group in chatter_lists.values():
            all_users.extend(group)
        for username in all_users:
            uname_clean = clean_user(username)
            if uname_clean.lower() not in ch["stats"]["users"]:
                ch["stats"]["users"][uname_clean.lower()] = {"sparks": 0, "passes": 0, "burned_out": 0, "original_name": uname_clean}
        save_data()
    except Exception:
        pass  # fail silently if Twitch endpoint unavailable


# ---------- Fuzzy username matching ----------
def similar(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / max(len(a), len(b))


def get_user(ch, user_input: str):
    user_input_clean = clean_user(user_input)
    users = ch["stats"]["users"]
    # try fuzzy match
    best_match = None
    best_score = 0
    for uname in users:
        score = similar(user_input_clean, uname)
        if score > best_score:
            best_score = score
            best_match = uname
    if best_score >= fuzzy_threshold:
        return users[best_match]
    # else create new user
    users[user_input_clean.lower()] = {"sparks": 0, "passes": 0, "burned_out": 0, "original_name": user_input}
    return users[user_input_clean.lower()]


def text_response(msg: str):
    return PlainTextResponse(msg)


def minutes_ago(ts: datetime) -> str:
    mins = int((datetime.utcnow() - ts).total_seconds() // 60)
    if mins <= 0:
        return "just now"
    if mins == 1:
        return "1 minute ago"
    return f"{mins} minutes ago"


def increment_total_joints(channel: str):
    ch = get_channel(channel)
    ch["stats"]["total_joints"] = ch["stats"].get("total_joints", 0) + 1
    save_data()


# ---------- Timeout ----------
def check_timeout(ch, channel_name):
    joint = ch["joint"]
    if joint["holder"] and not joint["burned"] and joint["last_pass_time"]:
        last_pass_time = datetime.fromisoformat(joint["last_pass_time"])
        if datetime.utcnow() - last_pass_time > timedelta(minutes=timeout_minutes):
            expired_user = joint["holder"]
            u = get_user(ch, expired_user)
            u["burned_out"] += 1
            joint.update({"holder": None, "burned": True, "passes": 0, "last_pass_time": None})
            save_data()
            return f"{expired_user} held the joint too long and it burned out 🔥"
    return None


# ---------- Spark Endpoint ----------
@app.get("/spark")
def spark(user: str = Query(..., min_length=1), channel: str = Query(..., min_length=1)):
    channel_clean = clean_user(channel)
    populate_users_from_twitch(channel_clean)  # ensure users list is updated
    user_clean = clean_user(user)
    ch = get_channel(channel_clean)
    joint = ch["joint"]

    expired = check_timeout(ch, channel_clean)
    if expired:
        return text_response(expired)

    if joint["burned"] or joint["holder"] is None:
        joint.update({"holder": None, "passes": 0, "last_pass_time": None, "burned": False})

    if joint["holder"] is not None:
        return text_response(f"{user_clean} tried to spark a joint, but {joint['holder']} is already holding one")

    joint.update({"holder": user_clean, "passes": 0, "burned": False, "last_pass_time": datetime.utcnow().isoformat()})
    u = get_user(ch, user_clean)
    u["sparks"] += 1

    save_data()
    return text_response(f"{user_clean} sparked a joint💨")


# ---------- Pass Endpoint ----------
@app.get("/pass")
def pass_joint(from_user: str = Query(..., min_length=1),
               to_user: str = Query(..., min_length=1),
               channel: str = Query(..., min_length=1)):

    channel_clean = clean_user(channel)
    populate_users_from_twitch(channel_clean)  # update users
    from_clean = clean_user(from_user)
    to_clean = clean_user(to_user)
    ch = get_channel(channel_clean)
    joint = ch["joint"]

    expired = check_timeout(ch, channel_clean)
    if expired:
        return text_response(expired)

    if joint["holder"] != from_clean:
        return text_response(f"{from_user} can’t pass the joint because they don’t have it 👀")

    u = get_user(ch, from_clean)

    # ---------- Fumble ----------
    if random.random() < fumble_chance:
        other_users = [info["original_name"] for uname, info in ch["stats"]["users"].items() if uname != from_clean.lower()]
        stepped_user = random.choice(other_users) if other_users else "someone unlucky"
        joint.update({"holder": None, "burned": True, "passes": 0, "last_pass_time": None})
        u["burned_out"] += 1
        save_data()
        return text_response(f"Oh no! {from_user} fumbled the joint and {stepped_user} accidentally stepped on it 🔥💀")

    # ---------- Portal Mishap ----------
    if random.random() < portal_chance:
        joint.update({"holder": from_clean, "last_pass_time": datetime.utcnow().isoformat()})
        u["passes"] += 1
        save_data()
        return text_response(f"A portal opens! The joint comes back to {from_user} 😵‍💫💨")

    # ---------- Nightbot ----------
    if to_clean.lower() == "nightbot":
        u["passes"] += 1
        ch["stats"]["nightbot_joints"] += 1
        joint.update({"holder": None, "burned": True, "passes": 0, "last_pass_time": None})
        save_data()
        return text_response(f"{from_user} passed the joint to Nightbot 🤖\nNightbot puff puff... smoked the whole joint, sorry 🔥💨")

    # ---------- Normal Pass ----------
    joint.update({"holder": to_clean, "passes": joint["passes"] + 1, "last_pass_time": datetime.utcnow().isoformat()})
    u["passes"] += 1

    if joint["passes"] >= 10:
        increment_total_joints(channel_clean)
        last_user = to_clean
        joint.update({"holder": None, "burned": True, "passes": 0, "last_pass_time": None})
        save_data()
        return text_response(f"{last_user} takes a couple last puffs and puts the roach in the ashtray 🔥💨")

    save_data()
    return text_response(f"{from_user} passed the joint to {to_user}💨")


# ---------- Status Endpoint ----------
@app.get("/status")
def status(channel: str = Query(..., min_length=1), silent: bool = False):
    channel_clean = clean_user(channel)
    ch = get_channel(channel_clean)
    joint = ch["joint"]

    expired = check_timeout(ch, channel_clean)
    if expired:
        return text_response(expired)

    if not joint["holder"] or joint["burned"]:
        return text_response("") if silent else text_response("Nobody has the joint right now. Spark one with !spark ")

    if silent:
        return text_response("")  # only silent if joint is active

    last_pass_time_str = joint.get("last_pass_time")
    minutes_text = minutes_ago(datetime.fromisoformat(last_pass_time_str)) if last_pass_time_str else "just now"
    return text_response(f"The joint is currently with {joint['holder']} (passed {minutes_text}).")


# ---------- Stats Endpoint ----------
@app.get("/stats")
def stats(channel: str = Query(..., min_length=1), user: str = Query(None)):
    channel_clean = clean_user(channel)
    ch = get_channel(channel_clean)

    if user:
        u = get_user(ch, clean_user(user))
        return text_response(f"{user}'s stats → Sparks: {u['sparks']}, Passes: {u['passes']}, Let it burn out: {u['burned_out']}")

    total_joints = ch['stats'].get('total_joints', 0)
    nightbot_joints = ch['stats'].get('nightbot_joints', 0)
    burned_list = [(info["original_name"], u['burned_out']) for uname, u in ch['stats']['users'].items() for info in [u] if u['burned_out'] > 0]
    burned_list.sort(key=lambda x: (-x[1], x[0]))
    top10 = burned_list[:10]

    dropouts_text = f"Doink Dropouts → {' | '.join([f'{name}: {count}' for name, count in top10])}" if top10 else "Doink Dropouts → None yet, impressive. 👍"

    return text_response(f"{channel_clean}'s Channel → Total joints smoked: {total_joints} | Nightbot smoked: {nightbot_joints} | {dropouts_text}")
