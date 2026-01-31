from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import requests
import os
from dotenv import load_dotenv

from fastapi.templating import Jinja2Templates
from fastapi import Request



load_dotenv()

app = FastAPI()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://for-the-kudos.onrender.com/callback"


templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
def login():
    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        "&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        "&scope=read,activity:read"
        "&approval_prompt=force"
    )
    return RedirectResponse(url)


@app.get("/callback")
def callback(code: str):
    token_response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code"
        }
    )

    access_token = token_response.json()["access_token"]
    activities = get_activities(access_token)
    stats = kudos_stats(activities)

    return stats




def get_activities(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=headers,
        params={"per_page": 50}
    )
    return response.json()


def kudos_stats(activities):
    total_kudos = sum(a["kudos_count"] for a in activities)
    most_loved = max(activities, key=lambda a: a["kudos_count"])

    return {
        "total_activities": len(activities),
        "total_kudos": total_kudos,
        "average_kudos": round(total_kudos / len(activities), 1),
        "most_loved_activity": {
            "name": most_loved["name"],
            "kudos": most_loved["kudos_count"],
            "distance_km": round(most_loved["distance"] / 1000, 2)
        }
    }

