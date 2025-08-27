from fastapi import FastAPI, Query
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI()

# Global state
joint_holder: Optional[str] = None
last_pass_time: Optional[datetime] = None
pass_count: int = 0

# Config
JOINT_TIMEOUT = 2   # minutes before joint burns out
MAX_PASSES = 10     # max passes before joint burns out


def check_timeout():
    """Check if joint timed out due to inactivity."""
    global joint_holder, last_pass_time, pass_count
    if joint_holder and last_pass_time:
        if datetime.utcnow() - last_pass_time > timedelta(minutes=JOINT_TIMEOUT):
            expired_holder = joint_holder
            joint_holder = None
            last_pass_time = None
            pass_count = 0
            return f"The joint burned out because {expired_holder} didn’t pass it in time 🔥"
    return None


def check_pass_limit():
    """Check if joint exceeded max passes."""
    global joint_holder, last_pass_time, pass_count
    if pass_count >= MAX_PASSES:
        expired_holder = joint_holder
        joint_holder = None
        last_pass_time = None
        pass_count = 0
        return f"The joint burned out after {MAX_PASSES} passes 💨🔥 Spark a new one with !spark."
    return None


@app.get("/spark")
def spark(user: str = Query(...)):
    """Start a new joint."""
    global joint_holder, last_pass_time, pass_count
    expired = check_timeout()
    if expired:
        return expired
    if joint_holder:
        return f"{user} tried to spark a joint, but {joint_holder} is already holding one 🚬"
    joint_holder = user
    last_pass_time = datetime.utcnow()
    pass_count = 0
    return f"{user} sparked a joint💨"


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...)):
    """Pass the joint to another user."""
    global joint_holder, last_pass_time, pass_count
    expired = check_timeout()
    if expired:
        return expired
    if joint_holder != from_user:
        return f"{from_user} can’t pass the joint because they don’t have it 👀"

    pass_count += 1
    burned = check_pass_limit()
    if burned:
        return burned

    joint_holder = to_user
    last_pass_time = datetime.utcnow()
    return f"{from_user} passed the joint to {to_user} 🚬"


@app.get("/status")
def status():
    """Check who currently has the joint."""
    expired = check_timeout()
    if expired:
        return expired
    burned = check_pass_limit()
    if burned:
        return burned
    if not joint_holder:
        return "Nobody has the joint right now. Spark one with !spark"

    minutes_ago = int((datetime.utcnow() - last_pass_time).total_seconds() // 60)
    return f"The joint is currently with {joint_holder} (last pass {minutes_ago} min ago)."
