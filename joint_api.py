from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta
import json
import os

app = FastAPI()

DATA_FILE = "joints.json"
timeout_minutes = 5
pass_count_global: int = 0  # tracks current joint passes


# ---------- Helpers ----------
def clean_user(name: str) -> str:
    """Strip leading @ from Twitch usernames (people tab-complete with @)."""
    return name.lstrip("@") if name else name


def text_response(message: str):
    """Return plain text for Nightbot."""
    return PlainTextResponse(message)


def minutes_ago(ts: datetime) -> str:
    """Format elapsed minutes nicely with pluralization."""
    mins = int((datetime.utcnow() - ts).total_seconds() // 60)
    if mins <= 0:
        return "just now"
    if mins == 1:
        return "1 minute ago"
    return f"{mins} minutes ago"


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
    """Get or create channel data"""
    if channel not in data["channels"]:
        data["channels"][channel] = {
            "joint": {"holder": None, "passes": 0, "burned": True},
            "stats": {"total_joints": 0, "users": {}}
        }
    return data["channels"][channel]


def get_user(channel_data, user: str):
    """Get or create user stats for a channel"""
    if user not in channel_data["stats"]["users"]:
        channel_data["stats"]["users"][user] = {"sparks": 0, "passes": 0}
    return channel_data["stats"]["users"][user]


# ---------- Timeout / Expiry ----------
def check_timeout(channel_data):
    """Check if the current joint holder has timed out."""
    joint = channel_data["joint"]
    if joint["holder"] and not joint["burned"]:
        last_pass_time_str = joint.get("last_pass_time")
        if last_pass_time_str:
            last_pass_time = datetime.fromisoformat(last_pass_time_str)
            if datetime.utcnow() - last_pass_time > timedelta(minutes=timeout_minutes):
                expired_user = joint["holder"]
                joint["holder"] = None
                joint["burned"] = True
                joint["passes"] = 0
                joint.pop("last_pass_time", None)
                save_data()
                return f"{expired_user} held the joint too long and it burned out 🔥"
    return None


# ---------- Routes ----------
@app.get("/spark")
def spark(user: str = Query(...), channel: str = Query(...)):
    user = clean_user(user)
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch)
    if expired:
        return text_response(expired)

    if joint["holder"] and not joint["burned"]:
        return text_response(f"{user} tried to spark a joint, but {joint['holder']} is already holding one")

    # New joint
    joint["holder"] = user
    joint["passes"] = 0
    joint["burned"] = False
    joint["last_pass_time"] = datetime.utcnow().isoformat()
    ch["stats"]["total_joints"] += 1
    u = get_user(ch, user)
    u["sparks"] += 1

    save_data()
    return text_response(f"{user} sparked a joint💨")


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...), channel: str = Query(...)):
    from_user = clean_user(from_user)
    to_user = clean_user(to_user)
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch)
    if expired:
        return text_response(expired)

    if joint["holder"] != from_user:
        return text_response(f"{from_user} can’t pass the joint because they don’t have it 👀")

    # If passing to Nightbot → Nightbot smokes it
    if to_user.lower() == "nightbot":
        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint.pop("last_pass_time", None)
        save_data()
        return text_response(f"{from_user} passed the joint to Nightbot 🤖\n"
                             f"Nightbot puff puff... smoked the whole joint, sorry :P 🔥💨")

    # Normal pass
    joint["holder"] = to_user
    joint["passes"] += 1
    joint["last_pass_time"] = datetime.utcnow().isoformat()

    u = get_user(ch, from_user)
    u["passes"] += 1

    # Check 10-pass limit
    if joint["passes"] >= 10:
        last_user = to_user
        joint["holder"] = None
        joint["burned"] = True
        joint["passes"] = 0
        joint.pop("last_pass_time", None)
        save_data()
        return text_response(f"{last_user} takes a couple last puffs and puts the roach in the ashtray 🔥💨")

    save_data()
    return text_response(f"{from_user} passed the joint to {to_user}")


@app.get("/status")
def status(channel: str = Query(...), silent: bool = False):
    ch = get_channel(channel)
    joint = ch["joint"]

    expired = check_timeout(ch)
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


@app.get("/stats")
def stats(channel: str = Query(...), user: str = Query(None)):
    ch = get_channel(channel)
    if user:
        u = get_user(ch, clean_user(user))
        return text_response(f"{user}'s stats → Sparks: {u['sparks']}, Passes: {u['passes']}")
    else:
        return text_response(f"Total joints smoked in {channel}'s stream: {ch['stats']['total_joints']}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)

