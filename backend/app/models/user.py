"""
Incident DB model and shared DB infrastructure.

Stores every incident report produced by the multi-agent pipeline so the
Dashboard can show a live feed of real detections instead of only keeping
session-state from /testing/run.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False)
    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    # ---- per-user settings ----
    email_alerts_critical = Column(Boolean, default=False)
    flow_window_seconds = Column(Integer, default=5)
    risk_threshold = Column(String, default="High")  # "High" | "Critical"


class IncidentRecord(Base):
    """Persisted incident reports from the multi-agent detection pipeline."""

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, unique=True, nullable=False, index=True)
    timestamp = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    # Detection fields
    source_ip = Column(String, nullable=True)          # target IP from monitoring
    attack_type = Column(String, nullable=False)        # prediction label
    confidence = Column(Float, nullable=False)
    risk_label = Column(String, nullable=False)         # Low|Medium|High|Critical
    risk_score = Column(Float, nullable=False, default=0.0)
    mitigated = Column(Boolean, default=False)

    # Source tag: "live" | "test" | "manual_simulate"
    source = Column(String, nullable=False, default="test", index=True)

    # Compact evidence summary (first statement) for list view
    evidence_summary = Column(Text, nullable=True)

    # Full pipeline report as JSON string for detail view
    full_report = Column(Text, nullable=True)

    # Total pipeline latency in ms
    pipeline_latency_ms = Column(Float, nullable=True)

    # SOC-style alert correlation: occurrence count and last-seen timestamp
    occurrence_count = Column(Integer, nullable=False, default=1)
    last_seen_at = Column(DateTime, nullable=True)


# ---- DB engine ----------------------------------------------------------------

db_path = Path(__file__).resolve().parents[2] / "data" / "kronos.db"
engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            result = conn.exec_driver_sql("PRAGMA table_info(users)")
            existing_columns = {row[1] for row in result.fetchall()}
            if existing_columns:
                if "email_alerts_critical" not in existing_columns:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email_alerts_critical BOOLEAN DEFAULT 0")
                if "flow_window_seconds" not in existing_columns:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN flow_window_seconds INTEGER DEFAULT 5")
                if "risk_threshold" not in existing_columns:
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN risk_threshold VARCHAR DEFAULT 'High'")
                conn.commit()
        except Exception:
            pass
        try:
            result = conn.exec_driver_sql("PRAGMA table_info(incidents)")
            inc_cols = {row[1] for row in result.fetchall()}
            if inc_cols:
                if "occurrence_count" not in inc_cols:
                    conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN occurrence_count INTEGER DEFAULT 1")
                if "last_seen_at" not in inc_cols:
                    conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN last_seen_at DATETIME")
                conn.commit()
        except Exception:
            pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
