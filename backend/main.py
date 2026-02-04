from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import os, requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from starlette.middleware.sessions import SessionMiddleware
from .database import engine, SessionLocal
from .models import Base, AthleteStats
import secrets


load_dotenv()

app = FastAPI()

IS_PREVIEW = os.getenv("RENDER_SERVICE_TYPE") == "preview"

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret"),
    same_site="lax",
    https_only=not IS_PREVIEW   # secure only in production
)

Base.metadata.create_all(bind=engine)

SESSION_TTL = timedelta(minutes=10)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = "https://for-the-kudos.onrender.com/callback"

print("SERVICE TYPE:", os.getenv("RENDER_SERVICE_TYPE")) # testing
print("IS_PREVIEW:", IS_PREVIEW) # testing
print("DATABASE_URL exists:", bool(os.getenv("DATABASE_URL"))) # testing

# ----------------------------
# OAuth functions
# ----------------------------
def ensure_valid_token(request: Request):
    access = request.session.get("access_token")
    refresh = request.session.get("refresh_token")
    expires_at = request.session.get("expires_at")

    if not access:
        raise HTTPException(401, "Not authenticated")

    # If we don't have refresh data yet, just trust access token
    if not refresh or not expires_at:
        return access

    # Token expired?
    if datetime.utcnow().timestamp() > expires_at:
        new = refresh_token(refresh)

        request.session["access_token"] = new["access_token"]
        request.session["refresh_token"] = new["refresh_token"]
        request.session["expires_at"] = new["expires_at"]

        return new["access_token"]

    return access



def refresh_token(refresh_token):
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    return r.json()


# ----------------------------
# Helper functions
# ----------------------------
def get_athlete(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers=headers,
        timeout=5
    )

    # Rate limit handling
    if response.status_code == 429:
        raise HTTPException(status_code=503, detail="Strava rate limit exceeded")

    data = response.json()

    # If Strava returns an error, stop immediately
    if "id" not in data:
        raise HTTPException(status_code=401, detail="Invalid or expired Strava token")

    return data


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

        # Rate limit handling
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="Strava rate limit exceeded")

        data = response.json()

        if not data or isinstance(data, dict) and data.get("message"):
            break

        activities.extend(data)
        page += 1

    return activities


def get_activity_detail(activity_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers=headers
    )

    # Rate limit handling
    if response.status_code == 429:
        raise HTTPException(status_code=503, detail="Strava rate limit exceeded")

    return response.json()

# ----------------------------
# Database functions
#-----------------------------
def get_cached_athlete_stats(db, athlete_id):
    record = db.get(AthleteStats, athlete_id)

    if not record:
        return None
    
    if datetime.utcnow() - record.last_updated < timedelta(hours=6):
        return {
            "total_activities": record.total_activities,
            "total_kudos": record.total_kudos,
            "average_kudos": record.average_kudos,
        }
    
    return None
        

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
def login(request: Request):

    # Generate and store state token
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state

    url = (
    "https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    "&response_type=code"
    f"&redirect_uri={REDIRECT_URI}"
    "&scope=read,activity:read,profile:read_all,activity:read_all"
    "&approval_prompt=force"
    f"&state={state}"
)

    return RedirectResponse(url)


@app.get("/callback")
def callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # Validate state token
    if state != request.session.get("oauth_state"):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

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

    # Handle OAuth failure
    if "access_token" not in token_response:
        print("OAuth error:", token_response)
        return RedirectResponse("/?error=oauth")

    # STORE ALL TOKENS HERE
    request.session["access_token"] = token_response["access_token"]
    request.session["refresh_token"] = token_response["refresh_token"]
    request.session["expires_at"] = token_response["expires_at"]

    return RedirectResponse("/dashboard")


@app.get("/dashboard")
def dashboard(request: Request):
    if "access_token" not in request.session:
        return RedirectResponse("/")

    return RedirectResponse("/")


@app.get("/api/athlete")
def api_athlete(request: Request):
    print("SESSION KEYS:", request.session.keys()) # testing
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
    print("SESSION KEYS:", request.session.keys()) # testing
    if IS_PREVIEW:
        return {
            "total_activities": 0,
            "total_kudos": 0,
            "average_kudos": 0,
            "top_activity_id": None
        }

    # ensure user is logged in
    if "access_token" not in request.session:
        return {"error": "unauthorized"}
    
    # refresh token if expired
    token = ensure_valid_token(request)

    # fetch athlete info
    athlete = get_athlete(token)

    db = SessionLocal()
    cached = get_cached_athlete_stats(db, athlete["id"])

    if cached:
        db.close()
        return {
            "total_activities": cached["total_activities"],
            "total_kudos": cached["total_kudos"],
            "average_kudos": cached["average_kudos"],
            "top_activity_id": None
        }
    
    db.close()

    activities = get_activities(token, per_page=50)
    
    if not activities:
        raise HTTPException(status_code=503, detail="No activities returned from Strava")

    print("fetching real stats from DB") # testing

    total_kudos = sum(a.get("kudos_count", 0) for a in activities)
    top_activity = max(activities, key=lambda a: a.get("kudos_count", 0))

    stats = {
        "total_activities": len(activities),
        "total_kudos": total_kudos,
        "average_kudos": round(total_kudos / len(activities), 1),
    }

    # SAVE TO DATABASE
    if total_kudos > 0 or len(activities) > 0:
        db = SessionLocal()
        upsert_athlete(db, athlete, stats)
        db.close()

    print("Stats payload:", stats) # testing

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


@app.get("/api/leaderboard/rank")
def leaderboard_rank(request: Request):
    if "access_token" not in request.session:
        return {"error": "unauthorized"}

    athlete = request.session.get("athlete")
    if not athlete:
        return {"error": "no athlete"}

    athlete_id = athlete["id"]

    db = SessionLocal()
    rows = (
        db.query(AthleteStats)
        .order_by(AthleteStats.total_kudos.desc())
        .all()
    )
    db.close()

    # Find index
    for i, row in enumerate(rows):
        if row.athlete_id == athlete_id:
            return {"rank": i + 1}

    return {"rank": None}