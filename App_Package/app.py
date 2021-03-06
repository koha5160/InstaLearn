import os
import pickle

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from crontab import CronTab
from .database import SessionLocal, engine
from .models import Account, User, Base

# Create a FastAPI instance
# redoc_url=None, docs_url=None
app = FastAPI()

Base.metadata.create_all(bind=engine)


class SignIn(BaseModel):
    username: str
    password: str


class CreateUser(BaseModel):
    username: str
    password: str


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


templates = Jinja2Templates(directory="templates")


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(Account)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "accounts": accounts,
            "count": accounts.count(),
            "status": get_status(),
        },
    )


@app.post("/add_user")
async def add_user(
    create_user: CreateUser,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = User()
    user.username = create_user.username
    user.password = create_user.password
    try:
        db.add(user)
        db.commit()
        context = {"code": "success", "message": "user created"}
    except IntegrityError:
        context = {"code": "failed", "message": "username is already taken"}
    return context


def create_cronjob():
    with CronTab(user=os.environ.get("user")) as cron:
        job = cron.new(command="python3 cronjob.py", comment="Scrape")
        job.minute.every(5)


def get_status(context=None):
    with open("bot.pickle", "rb") as fv:
        bot = pickle.load(fv)
    running = False
    cron = CronTab(user=os.environ.get("user"))
    for _ in cron:
        running = True
    d = {
        "cooldown": bot.cooldown,
        "date_stamp": bot.date_stamp,
        "current_user": bot.users.peek(),
        "running": running,
        "stop_date": bot.stop_date,
    }
    if context:
        context.update(d)
        return context
    return d


def stop_cronjob():
    with CronTab(user=os.environ.get("user")) as cron:
        cron.remove_all(comment="Scrape")


def start_up():
    stop_cronjob()
    with open("bot.pickle", "rb") as fv:
        bot = pickle.load(fv)
    bot.add_users()
    create_cronjob()


@app.post("/run")
async def run_cron(
    signin_request: SignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    users = db.query(User)
    user = (
        users.filter(User.username == signin_request.username)
        .filter(User.password == signin_request.password)
        .first()
    )
    if user:
        background_tasks.add_task(start_up)
        return {"code": "success"}
    return {"code": "failed"}


@app.post("/status")
async def status(
    signin_request: SignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    users = db.query(User)
    user = (
        users.filter(User.username == signin_request.username)
        .filter(User.password == signin_request.password)
        .first()
    )
    if user:
        return get_status({"code": "success"})

    return {"code": "failed", "message": "incorrect username or password"}


@app.post("/stop")
async def stop_cron(
    signin_request: SignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    users = db.query(User)
    user = (
        users.filter(User.username == signin_request.username)
        .filter(User.password == signin_request.password)
        .first()
    )
    if user:
        background_tasks.add_task(stop_cronjob)
        return {"code": "success"}
    return {"code": "failed"}


@app.post("/stats")
async def stats(
    signin_request: SignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    users = db.query(User)
    user = (
        users.filter(User.username == signin_request.username)
        .filter(User.password == signin_request.password)
        .first()
    )
    if user:
        return {"code": "success", "entries": db.query(Account).count()}
    return {"code": "failed"}
