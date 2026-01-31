from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import os, requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://for-the-kudos.onrender.com/callback"

# ----------------------------
# Helper functions
# ----------------------------
def get_activities(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=headers,
        params={"per_page": 50}
    )
    return response.json()


def kudos_stats(activities):
    if not activities:
        return {"total_activities": 0, "total_kudos": 0, "average_kudos": 0, "most_loved_activity": {}}
    
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


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "stats": None})


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
def callback(request: Request, code: str):
    # Exchange code for access token
    token_response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code"
        }
    )
    token_json = token_response.json()
    access_token = token_json.get("access_token")

    # Fetch activities and calculate stats
    activities = get_activities(access_token)
    stats = kudos_stats(activities)

    # Render template with real stats
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})