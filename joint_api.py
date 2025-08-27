from fastapi import FastAPI, Query
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI()

joint_holder: Optional[str] = None
last_pass_time: Optional[datetime] = None
pass_count: int = 0

JOINT_TIMEOUT = 2   # minutes
MAX_PASSES = 10     # passes before joint burns out


def check_timeout():
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
    global joint_holder, last_pass_time, pass_count
    expired = check_timeout()
    if expired:
        return {"message": expired}
    if joint_holder:
        return {"message": f"{user} tried to spark a joint, but {joint_holder} is already holding one 🚬"}
    joint_holder = user
    last_pass_time = datetime.utcnow()
    pass_count = 0
    return {"message": f"{user} sparked a joint💨"}


@app.get("/pass")
def pass_joint(from_user: str = Query(...), to_user: str = Query(...)):
    global joint_holder, last_pass_time, pass_count
    expired = check_timeout()
    if expired:
        return {"message": expired}
    if joint_holder != from_user:
        return {"message": f"{from_user} can’t pass the joint because they don’t have it 👀"}

    pass_count += 1
    burned = check_pass_limit()
    if burned:
        return {"message": burned}

    joint_holder = to_user
    last_pass_time = datetime.utcnow()
    return {"message": f"{from_user} passed the joint to {to_user} 🚬 (Pass {pass_count}/{MAX_PASSES})"}


@app.get("/status")
def status():
    expired = check_timeout()
    if expired:
        return {"message": expired}
    burned = check_pass_limit()
    if burned:
        return {"message": burned}

    if not joint_holder:
        return {"message": "Nobody has the joint right now. Spark one with !spark"}

    minutes_ago = int((datetime.utcnow() - last_pass_time).total_seconds() // 60)
    return {"message": f"The joint is currently with {joint_holder} (passed {minutes_ago} min ago, {pass_count}/{MAX_PASSES} passes)."}
