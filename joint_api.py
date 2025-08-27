from fastapi import FastAPI, Query
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI()

# Global state
joint_holder: Optional[str] = None
last_pass_time: Optional[datetime] = None
pass_count: int = 0
burnout_announced: bool = False  # flag to prevent duplicate announcements

# Config
JOINT_TIMEOUT = 2   # minutes
MAX_PASSES = 10


def check_timeout():
    """Check if joint timed out due to inactivity."""
    global joint_holder, last_pass_time, pass_count, burnout_announced
    if joint_holder and last_pass_time:
        if datetime.utcnow() - last_pass_time > timedelta(minutes=JOINT_TIMEOUT):
            expired_holder = joint_holder
            joint_holder = None
            last_pass_time = None
            pass_count = 0
            burnout_announced = False
            return f"The joint burned out because {expired_holder} didn’t pass it in time 🔥"
    return None


def check_pass_limit():
    """Check if joint exceeded max passes."""
    global joint_holder, last_pass_time, pass_count, burnout_announced
    if pass_count >= MAX_PASSES:
        expired_holder = joint_holder
        joint_holder = None
        last_pass_time = None
        pass_count = 0
        burnout_announced = False
        return f"The joint burned out after {MAX_PASSES} passes 💨🔥 Spark a new one with !spark."
    return None


@app.get("/spark")
def spark(user: str = Query(...)):
    global joint_holder, last_pass_time, pass_count, burnout_announced
    expired = check_timeout()
    burned = check_pass_limit()
    if expired or burned:
        # Reset burnout flag for new joint
        burnout_announced = False

    if joint_holder:
        return f"{user} tried to spark a joint, but {joint_holder} is already holding one"
    joint_holder = user
    last_pass_time = datetime.utcnow()
    pass_count = 0
    burnout_announced = False
    return f"{user} sparked a joint💨"


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...)):
    global joint_holder, last_pass_time, pass_count, burnout_announced

    to_user_clean = to_user.lstrip("@").strip()
    expired = check_timeout()
    burned = check_pass_limit()
    if expired or burned:
        burnout_announced = False

    if joint_holder != from_user:
        return f"{from_user} can’t pass the joint because they don’t have it 👀"

    pass_count += 1
    burned_now = check_pass_limit()
    if burned_now:
        return burned_now

    joint_holder = to_user_clean
    last_pass_time = datetime.utcnow()
    return f"{from_user} passed the joint to {to_user_clean}"


@app.get("/status")
def status():
    """Used for Nightbot timer: only returns a message if the joint just burned out."""
    global burnout_announced
    expired = check_timeout()
    burned = check_pass_limit()

    # Only announce once
    if (expired or burned) and not burnout_announced:
        burnout_announced = True
        return expired or burned
    return ""  # no message if joint is active or already announced
