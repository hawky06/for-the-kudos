from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import os, requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from starlette.middleware.sessions import SessionMiddleware
from .database import engine, SessionLocal
from .models import Base, AthleteStats


load_dotenv()

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret"),
    same_site="lax",
    https_only=True
)

Base.metadata.create_all(bind=engine)

SESSION_TTL = timedelta(minutes=10)

IS_PREVIEW = os.getenv("RENDER_SERVICE_TYPE") == "preview"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://for-the-kudos.onrender.com/callback"

print("SERVICE TYPE:", os.getenv("RENDER_SERVICE_TYPE"))
print("IS_PREVIEW:", IS_PREVIEW)
print("DATABASE_URL exists:", bool(os.getenv("DATABASE_URL")))


# ----------------------------
# Caching functions
# ----------------------------
def get_cached_stats(request: Request):
    stats = request.session.get("stats")
    ts = request.session.get("stats_ts")

    if stats and ts:
        if datetime.utcnow() - datetime.fromisoformat(ts) < SESSION_TTL:
            return stats

    return None


# ----------------------------
# Helper functions
# ----------------------------
def get_athlete(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers=headers,
        timeout=5
    )
    return r.json()


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
# Database functions
#-----------------------------
def upsert_athlete(db, athlete, stats):
    record = db.get(AthleteStats, athlete["id"])

    if not record:
        record = AthleteStats(athlete_id=athlete["id"])

    record.firstname = athlete["firstname"]
    record.lastname = athlete["lastname"]
    record.profile = athlete["profile"]
    record.total_kudos = stats["total_kudos"]
    record.total_activities = stats["total_activities"]
    record.average_kudos = stats["average_kudos"]
    record.last_updated = datetime.utcnow()

    db.add(record)
    db.commit()


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "logged_in": True if IS_PREVIEW else "access_token" in request.session,
            "IS_PREVIEW": IS_PREVIEW,
        }
    )


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


@app.get("/api/athlete")
def api_athlete(request: Request):
    token = request.session.get("access_token")
    if not token:
        return {"error": "unauthorized"}

    if "athlete" in request.session:
        return request.session["athlete"]

    athlete = get_athlete(token)
    request.session["athlete"] = athlete
    return athlete


@app.get("/api/stats/summary")
def stats_summary(request: Request):
    if IS_PREVIEW:
        return {
            "total_activities": 0,
            "total_kudos": 0,
            "average_kudos": 0,
            "top_activity_id": None
        }

    token = request.session.get("access_token")
    if not token:
        return {"error": "unauthorized"}

    activities = get_activities(token, per_page=50)
    athlete = get_athlete(token)

    if not activities:
        return {
            "total_activities": 0,
            "total_kudos": 0,
            "average_kudos": 0,
            "top_activity_id": None
        }

    total_kudos = sum(a.get("kudos_count", 0) for a in activities)
    top_activity = max(activities, key=lambda a: a.get("kudos_count", 0))

    stats = {
        "total_activities": len(activities),
        "total_kudos": total_kudos,
        "average_kudos": round(total_kudos / len(activities), 1),
    }

    # SAVE TO DATABASE
    db = SessionLocal()
    upsert_athlete(db, athlete, stats)
    db.close()

    return {
        **stats,
        "top_activity_id": top_activity["id"]
    }


@app.get("/api/stats/top-activity")
def top_activity(request: Request):
    if IS_PREVIEW:
        return {
            "name": "Preview Activity",
            "kudos": 0,
            "distance_km": 0,
            "date": "",
            "polyline": None
        }

    token = request.session.get("access_token")
    activity_id = request.query_params.get("id")

    if not token or not activity_id:
        return {"error": "bad request"}

    activity = get_activity_detail(activity_id, token)
    map_data = activity.get("map") or {}

    return {
        "name": activity.get("name"),
        "kudos": activity.get("kudos_count", 0),
        "distance_km": round(activity.get("distance", 0) / 1000, 2),
        "date": activity.get("start_date_local", "")[:10],
        "polyline": map_data.get("summary_polyline")
    }


@app.get("/api/leaderboard")
def leaderboard(
    sort: str = "total_kudos",
    limit: int = 20
):
    
    if IS_PREVIEW:
        return [
            {
                "athlete_id": i,
                "name": f"Preview User {i}",
                "profile": None,
                "total_kudos": 0,
                "average_kudos": 0,
                "total_activities": 0,
            }
            for i in range(1, 6)
        ]
    
    valid_sorts = {
        "total_kudos": AthleteStats.total_kudos,
        "average_kudos": AthleteStats.average_kudos,
        "total_activities": AthleteStats.total_activities,
    }

    order_col = valid_sorts.get(sort, AthleteStats.total_kudos)

    db = SessionLocal()
    rows = (
        db.query(AthleteStats)
        .order_by(order_col.desc())
        .limit(limit)
        .all()
    )
    db.close()

    return [
        {
            "athlete_id": r.athlete_id,
            "name": f"{r.firstname} {r.lastname}",
            "profile": r.profile,
            "total_kudos": r.total_kudos,
            "average_kudos": r.average_kudos,
            "total_activities": r.total_activities,
        }
        for r in rows
    ]

