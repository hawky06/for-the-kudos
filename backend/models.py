from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from database import Base

class AthleteStats(Base):
    __tablename__ = "athlete_stats"

    athlete_id = Column(Integer, primary_key=True, index=True)
    firstname = Column(String)
    lastname = Column(String)
    profile = Column(String)

    total_kudos = Column(Integer)
    total_activities = Column(Integer)
    average_kudos = Column(Float)

    last_updated = Column(DateTime, default=datetime.utcnow)
