from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime, timedelta

app = FastAPI()

# Joint state
joint_holder: str | None = None
last_pass_time: datetime | None = None
timeout_minutes = 5


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


def check_timeout():
    """Check if the current joint holder has timed out."""
    global joint_holder, last_pass_time
    if joint_holder and last_pass_time:
        if datetime.utcnow() - last_pass_time > timedelta(minutes=timeout_minutes):
            expired_user = joint_holder
            joint_holder = None
            last_pass_time = None
            return f"{expired_user} held the joint too long and it burned out 🔥"
    return None


# ---------- Routes ----------
@app.get("/spark")
def spark(user: str = Query(...)):
    global joint_holder, last_pass_time
    user = clean_user(user)

    expired = check_timeout()
    if expired:
        return text_response(expired)

    if joint_holder:
        return text_response(f"{user} tried to spark a joint, but {joint_holder} is already holding one")

    joint_holder = user
    last_pass_time = datetime.utcnow()
    return text_response(f"{user} sparked a joint💨")


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...)):
    global joint_holder, last_pass_time
    from_user = clean_user(from_user)
    to_user = clean_user(to_user)

    expired = check_timeout()
    if expired:
        return text_response(expired)

    if joint_holder != from_user:
        return text_response(f"{from_user} can’t pass the joint because they don’t have it 👀")

    # If passing to Nightbot → Nightbot smokes the whole joint
    if to_user.lower() == "nightbot":
        joint_holder = None
        last_pass_time = None
        return text_response(f"{from_user} passed the joint to Nightbot 🤖\n"
                             f"Nightbot puff puff... smoked the whole joint 🔥💨")

    # Normal pass
    joint_holder = to_user
    last_pass_time = datetime.utcnow()
    return text_response(f"{from_user} passed the joint to {to_user}")



@app.get("/status")
def status(silent: bool = False):
    expired = check_timeout()
    if expired:
        return text_response(expired)

    if not joint_holder:
        return text_response("Nobody has the joint right now. Spark one with !spark")

    if silent:
        # Timer check → stay quiet unless burned out
        return text_response("")

    return text_response(f"The joint is currently with {joint_holder} (passed {minutes_ago(last_pass_time)}).")

