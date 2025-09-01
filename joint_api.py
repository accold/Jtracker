from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta
import json
import os

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
        data["channels"][channel] = {
            "joint": {"holder": None, "passes": 0, "burned": True, "last_pass_time": None},
            "stats": {"total_joints": 0, "nightbot_joints": 0, "users": {}}
        }
    else:
        # Ensure new field exists for old data
        if "nightbot_joints" not in data["channels"][channel]["stats"]:
            data["channels"][channel]["stats"]["nightbot_joints"] = 0
    return data["channels"][channel]


def get_user(channel_data, user: str):
    user = user.lower()
    if user not in channel_data["stats"]["users"]:
        channel_data["stats"]["users"][user] = {"sparks": 0, "passes": 0, "burned_out": 0}
    return channel_data["stats"]["users"][user]


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
    if "stats" not in ch:
        ch["stats"] = {"total_joints": 0, "nightbot_joints": 0, "users": {}}
    if "total_joints" not in ch["stats"]:
        ch["stats"]["total_joints"] = 0
    ch["stats"]["total_joints"] += 1
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


# ---------- Pass Endpoint ----------
@app.get("/pass")
def pass_joint(
    from_user: str = Query(..., min_length=1),
    to_user: str = Query(..., min_length=1),
    channel: str = Query(..., min_length=1)
):
    from_user = clean_user(from_user)
    to_user = clean_user(to_user)
    channel = clean_user(channel)
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch, channel)
    if expired:
        return text_response(expired)

    if joint["holder"] != from_user:
        return text_response(f"{from_user} can’t pass the joint because they don’t have it 👀")

    # Nightbot smokes the joint
    if to_user.lower() == "nightbot":
        u = get_user(ch, from_user)
        u["passes"] += 1

        # Increment Nightbot-only counter
        ch["stats"]["nightbot_joints"] += 1

        # Reset joint
        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint["last_pass_time"] = None

        save_data()
        return text_response(f"{from_user} passed the joint to Nightbot 🤖\n"
                             f"Nightbot puff puff... smoked the whole joint, sorry 🔥💨")

    # Normal pass
    joint["holder"] = to_user
    joint["passes"] += 1
    joint["last_pass_time"] = datetime.utcnow().isoformat()
    u = get_user(ch, from_user)
    u["passes"] += 1

    if joint["passes"] >= 10:
        last_user = to_user
        increment_total_joints(channel)

        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint["last_pass_time"] = None

        save_data()
        return text_response(f"{last_user} takes a couple last puffs and puts the roach in the ashtray 🔥💨")

    save_data()
    return text_response(f"{from_user} passed the joint to {to_user}")


# ---------- Status Endpoint ----------
@app.get("/status")
def status(channel: str = Query(..., min_length=1), silent: bool = False):
    channel = clean_user(channel)
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch, channel)
    if expired:
        return text_response(expired)

    if not joint["holder"] or joint["burned"]:
        if silent:
            return text_response("")
        return text_response("Nobody has the joint right now. Spark one with !spark ")

    if silent:
        return text_response("")

    last_pass_time_str = joint.get("last_pass_time")
    minutes_text = minutes_ago(datetime.fromisoformat(last_pass_time_str)) if last_pass_time_str else "just now"
    return text_response(f"The joint is currently with {joint['holder']} (passed {minutes_text}).")


# ---------- Stats Endpoint ----------
@app.get("/stats")
def stats(channel: str = Query(..., min_length=1), user: str = Query(None)):
    channel = clean_user(channel)
    ch = get_channel(channel)

    if user:
        u = get_user(ch, clean_user(user))
        return text_response(
            f"{user}'s stats → Sparks: {u['sparks']}, Passes: {u['passes']}, "
            f"Let it burn out: {u['burned_out']}"
        )
    else:
        total_joints = ch['stats']['total_joints']
        nightbot_joints = ch['stats'].get('nightbot_joints', 0)

        burned_list = [
            (uname, u['burned_out'])
            for uname, u in ch['stats']['users'].items()
            if u['burned_out'] > 0
        ]
        burned_list.sort(key=lambda x: (-x[1], x[0]))
        top10 = burned_list[:10]

        if top10:
            dropout_lines = " | ".join([f"{name}: {count}" for name, count in top10])
            dropouts_text = f"Doink Dropouts → {dropout_lines}"
        else:
            dropouts_text = "Doink Dropouts → None yet, impressive. 👍"

        return text_response(
            f"{channel}'s Channel → Total joints smoked: {total_joints} | "
            f"Nightbot smoked: {nightbot_joints} | {dropouts_text}"
        )
