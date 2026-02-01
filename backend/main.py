from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import os, requests
from dotenv import load_dotenv
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware


load_dotenv()

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret")
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://for-the-kudos.onrender.com/callback"

# ----------------------------
# Helper functions
# ----------------------------
def get_activities(access_token, per_page=50):
    headers = {"Authorization": f"Bearer {access_token}"}
    activities = []
    page = 1

    while True:
        response = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params={"per_page": per_page, "page": page}
        )
        data = response.json()

        # Stop if no more activities or error
        if not data or isinstance(data, dict) and data.get("message"):
            break

        activities.extend(data)
        page += 1

    return activities


def kudos_stats(activities, access_token):
    if not activities:
        return {"total_activities": 0, "total_kudos": 0, "average_kudos": 0, "most_loved_activity": {}}
    
    total_kudos = sum(a["kudos_count"] for a in activities)
    most_loved = max(activities, key=lambda a: a["kudos_count"])

    full_activity = get_activity_detail(most_loved["id"], access_token)

    return {
        "total_activities": len(activities),
        "total_kudos": total_kudos,
        "average_kudos": round(total_kudos / len(activities), 1),
        "most_loved_activity": {
            "name": most_loved["name"],
            "kudos": most_loved["kudos_count"],
            "distance_km": round(most_loved["distance"] / 1000, 2),
            "date": most_loved["start_date_local"][:10],
            "polyline": full_activity["map"]["polyline"]
        }
    }


def get_activity_detail(activity_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers=headers
    )
    return response.json()


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
def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/")

    token_response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code"
        },
        timeout=10
    ).json()

    # IMPORTANT: handle OAuth failure
    access_token = token_response.get("access_token")
    if not access_token:
        print("OAuth error:", token_response)
        return RedirectResponse("/?error=oauth")

    request.session["access_token"] = access_token

    return RedirectResponse("/dashboard")


@app.get("/dashboard")
def dashboard(request: Request):
    if "access_token" not in request.session:
        return RedirectResponse("/")

    return RedirectResponse("/")


@app.get("/api/stats")
def api_stats(request: Request):
    access_token = request.session.get("access_token")
    if not access_token:
        return {"error": "unauthorized"}

    # cache hit
    if "stats" in request.session:
        return request.session["stats"]

    # slow work
    activities = get_activities(access_token)
    stats = kudos_stats(activities, access_token)

    # cache result
    request.session["stats"] = stats

    return stats