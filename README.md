# **For the Kudos**

A lightweight, independent, open‑source project that uses the Strava API to display athlete activity data through a lightweight, Python backend and a minimal, responsive frontend.
This project is not affiliated with Strava.

## 🚴‍♂️ Overview
For the Kudos provides a simple way to authenticate with Strava, retrieve activity data, and present it cleanly on a personal website or dashboard.
The backend handles API communication and data processing, while the frontend displays the results.
The project is designed to be:
- Easy to deploy
- Easy to customise
- Fully open‑source under GPL‑3.0

## ✨ Features
- Strava OAuth + token refresh flow
- Fetches athlete activities and metadata
- Python backend (FastAPI/Flask‑style structure)
- Clean HTML/CSS frontend
- Environment‑based configuration
- Lightweight and fast
  
## 🛠️ Tech Stack  
Backend
- Python
- FastAPI / Flask‑style routing
- Jinja2 templates
- Requests / HTTPX
- Environment variables for secrets  
Frontend
- HTML
- CSS
- JavaScript (Fetch API)
  
## 📦 Setup
### 1. Clone the repository  
`git clone https://github.com/hawky06/for-the-kudos`  
`cd for-the-kudos/backend`

### 2. Create your .env file  
Inside backend/, create a file named .env:  
`STRAVA_CLIENT_ID=your_id`  
`STRAVA_CLIENT_SECRET=your_secret`  
`STRAVA_REFRESH_TOKEN=your_refresh_token`  
Never commit this file.

### 3. Install backend dependencies:  
`pip install -r requirements.txt`

### 4. Run the backend:  
Depending on your framework:  
`python main.py`  
or  
`uvicorn main:app --reload`

### 5. Open the frontend:  
Serve your frontend files (any static server works):  
`npx serve ../`

## 🔑 Strava API Notes
You must create a Strava API application to obtain your credentials:  
Visit: https://www.strava.com/settings/api  
Ensure your redirect URL matches your local or deployed environment.

## 📁 Project Structure
for-the-kudos/  
│  
├── backend/  
│   ├── __init__.py  
│   ├── main.py  
│   ├── models.py  
│   ├── database.py  
│   ├── requirements.txt  
│   ├── templates/  
│   │   ├── index.html    
│   └── .env        # not committed  
│   
└── README.md  


## 🤝 Contributing
Contributions are welcome.
Feel free to open issues or submit pull requests.

## 📜 License
This project is licensed under the GNU General Public License v3.0 (GPL‑3.0).
See the LICENSE file for full details.

