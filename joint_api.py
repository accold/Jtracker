from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta
import json, os, random, requests, difflib

app = FastAPI()

DATA_FILE = "joints.json"
timeout_minutes = 5

# ---------- Persistent Data ----------
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
else:
    data = {"channels": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_channel(channel: str):
    channel = channel.lower()
    if channel not in data["channels"]:
        data[channel] = {
            "joint": {"holder": None, "passes": 0, "burned": True, "last_pass_time": None},
            "stats": {"total_joints": 0, "nightbot_joints": 0, "users": {}}
        }
    else:
        if "nightbot_joints" not in data[channel]["stats"]:
            data[channel]["stats"]["nightbot_joints"] = 0
    return data[channel]

def get_user(channel_data, user: str):
    user_lower = user.lower()
    if user_lower not in channel_data["stats"]["users"]:
        channel_data["stats"]["users"][user_lower] = {"sparks": 0, "passes": 0, "burned_out": 0, "original_name": user}
    else:
        channel_data["stats"]["users"][user_lower]["original_name"] = user
    return channel_data["stats"]["users"][user_lower]

def add_user(channel_data, user: str):
    get_user(channel_data, user)

def clean_user(name: str) -> str:
    if not name:
        return "UnknownUser"
    return name.split()[0].lstrip("@").strip()

def text_response(message: str):
    return PlainTextResponse(message)

def minutes_ago(ts: datetime) -> str:
    mins = int((datetime.utcnow() - ts).total_seconds() // 60)
    if mins <= 0:
        return "just now"
    if mins == 1:
        return "1 minute ago"
    return f"{mins} minutes ago"

# ---------- Total joints increment helper ----------
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

            joint["holder"] = None
            joint["burned"] = True
            joint["passes"] = 0
            joint["last_pass_time"] = None

            save_data()
            return f"{expired_user} held the joint too long and it burned out 🔥"
    return None

# ---------- Fuzzy name resolution ----------
def get_live_chatters(channel: str):
    try:
        url = f"https://tmi.twitch.tv/group/user/{channel}/chatters"
        r = requests.get(url, timeout=5).json()
        return sum(r["chatters"].values(), [])
    except:
        return []

def resolve_username(channel: str, name: str):
    chatters = get_live_chatters(channel)
    for u in chatters:
        add_user(get_channel(channel), u)
    if name in chatters:
        return name
    matches = difflib.get_close_matches(name, chatters, n=1, cutoff=0.6)
    return matches[0] if matches else None

# ---------- Spark Endpoint ----------
@app.get("/spark")
def spark(user: str = Query(..., min_length=1), channel: str = Query(..., min_length=1)):
    user = clean_user(user)
    channel = clean_user(channel)
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch, channel)
    if expired:
        return text_response(expired)

    if joint["burned"] or joint["holder"] is None:
        joint["holder"] = None
        joint["passes"] = 0
        joint["last_pass_time"] = None
        joint["burned"] = False

    if joint["holder"] is not None:
        return text_response(f"{user} tried to spark a joint, but {joint['holder']} is already holding one")

    joint["holder"] = user
    joint["passes"] = 0
    joint["burned"] = False
    joint["last_pass_time"] = datetime.utcnow().isoformat()

    u = get_user(ch, user)
    u["sparks"] += 1

    save_data()
    return text_response(f"{user} sparked a joint💨")

# ---------- Pass Endpoint with fumble and portal ----------
@app.get("/pass")
def pass_joint(
    from_user: str = Query(..., min_length=1),
    to_user: str = Query(..., min_length=1),
    channel: str = Query(..., min_length=1)
):
    from_user_clean = clean_user(from_user)
    to_user_clean = clean_user(to_user)
    channel_clean = clean_user(channel)
    ch = get_channel(channel_clean)
    joint = ch["joint"]

    expired = check_timeout(ch, channel_clean)
    if expired:
        return text_response(expired)

    if joint["holder"] != from_user_clean:
        return text_response(f"{from_user} can’t pass the joint because they don’t have it 👀")

    u = get_user(ch, from_user)

    # ---------- Fuzzy resolution for target user ----------
    resolved = resolve_username(channel_clean, to_user_clean)
    if not resolved:
        return text_response(f"{from_user} tried to pass to {to_user}, but they aren’t in chat 👀")
    to_user_clean = resolved

    # ---------- Fumble Pass ----------
    if random.random() < 0.05:
        other_users = [info["original_name"] for uname, info in ch["stats"]["users"].items()
                       if uname != from_user_clean.lower()]
        stepped_user = random.choice(other_users) if other_users else "someone unlucky"

        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint["last_pass_time"] = None

        u["burned_out"] += 1
        save_data()
        return text_response(f"Oh no! {from_user} fumbled the joint and {stepped_user} accidentally stepped on it 🔥💀")

    # ---------- Portal Mishap ----------
    if random.random() < 0.05:
        joint["holder"] = from_user_clean
        joint["last_pass_time"] = datetime.utcnow().isoformat()
        u["passes"] += 1
        save_data()
        return text_response(f"A portal opens! The joint comes back to {from_user} 😵‍💫💨")

    # ---------- Nightbot ----------
    if to_user_clean.lower() == "nightbot":
        u["passes"] += 1
        ch["stats"]["nightbot_joints"] += 1

        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint["last_pass_time"] = None

        save_data()
        return text_response(f"{from_user} passed the joint to Nightbot 🤖\n"
                             f"Nightbot puff puff... smoked the whole joint, sorry 🔥💨")

    # ---------- Normal Pass ----------
    joint["holder"] = to_user_clean
    joint["passes"] += 1
    joint["last_pass_time"] = datetime.utcnow().isoformat()
    u["passes"] += 1

    if joint["passes"] >= 10:
        last_user = to_user_clean
        increment_total_joints(channel_clean)

        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint["last_pass_time"] = None

        save_data()
        return text_response(f"{last_user} takes a couple last puffs and puts the roach in the ashtray 🔥💨")

    save_data()
    return text_response(f"{from_user} passed the joint to {to_user_clean}💨")

# ---------- Status Endpoint ----------
@app.get("/status")
def status(channel: str = Query(..., min_length=1), silent: bool = False):
    channel_clean = clean_user(channel)
    ch = get_channel(channel_clean)
    joint = ch["joint"]

    expired = check_timeout(ch, channel_clean)
    if expired:
        return text_response(expired)

    # Silent logic: only show if joint burned out
    if silent and (not joint["holder"] or joint["burned"]):
        return text_response("") if joint["holder"] and not joint["burned"] else text_response(expired or "")

    if not joint["holder"] or joint["burned"]:
        return text_response("Nobody has the joint right now. Spark one with !spark ")

    last_pass_time_str = joint.get("last_pass_time")
    minutes_text = minutes_ago(datetime.fromisoformat(last_pass_time_str)) if last_pass_time_str else "just now"
    return text_response(f"The joint is currently with {joint['holder']} (passed {minutes_text}).")

# ---------- Stats Endpoint ----------
@app.get("/stats")
def stats(channel: str = Query(..., min_length=1), user: str = Query(None)):
    channel_clean = clean_user(channel)
    ch = get_channel(channel_clean
