from fastapi import FastAPI, Query
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI()

# Keep track of joint holder
joint_holder: Optional[str] = None
last_pass_time: Optional[datetime] = None

# Timeout (Nightbot's timer is 5 min, so match that)
JOINT_TIMEOUT = 5  # minutes


def check_timeout():
    """Check if the joint has timed out and burn it if so."""
    global joint_holder, last_pass_time
    if joint_holder and last_pass_time:
        if datetime.utcnow() - last_pass_time > timedelta(minutes=JOINT_TIMEOUT):
            expired_holder = joint_holder
            joint_holder = None
            last_pass_time = None
            return f"The joint burned out because {expired_holder} didn’t pass it in time 🔥"
    return None


@app.get("/spark")
def spark(user: str = Query(...)):
    global joint_holder, last_pass_time
    expired = check_timeout()
    if expired:
        return {"message": expired}

    if joint_holder:
        return {"message": f"{user} tried to spark a joint, but {joint_holder} is already holding one"}

    joint_holder = user
    last_pass_time = datetime.utcnow()
    return {"message": f"{user} sparked a joint💨"}


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...)):
    global joint_holder, last_pass_time
    expired = check_timeout()
    if expired:
        return {"message": expired}

    if joint_holder != from_user:
        return {"message": f"{from_user} can’t pass the joint because they don’t have it 👀"}

    joint_holder = to_user
    last_pass_time = datetime.utcnow()
    return {"message": f"{from_user} passed the joint to {to_user}"}


@app.get("/status")
def status(silent: bool = Query(False)):
    """
    Show joint status. 
    If silent=true, only report burnouts (used by Nightbot timers).
    """
    expired = check_timeout()
    if expired:
        return {"message": expired}

    if not joint_holder:
        if silent:
            return {"message": ""}  # silent mode, no message if empty
        return {"message": "Nobody has the joint right now. Spark one with !spark"}

    if silent:
        return {"message": ""}  # silent mode, only show timeouts

    minutes_ago = int((datetime.utcnow() - last_pass_time).total_seconds() // 60)
    return {"message": f"The joint is currently with {joint_holder} (passed {minutes_ago} min ago)."}
