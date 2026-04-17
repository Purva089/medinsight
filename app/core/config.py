from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (two levels up from app/core/)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Central configuration object for MedInsight.

    Secrets (database_url, groq_api_key, secret_key) are read from the
    .env file.  All other values have sensible Python defaults here and can
    be overridden via environment variables if needed.

    Prompts live in app/core/prompts.py — import them directly from there.
    Data look-up tables (lab_tests_categories, medlineplus_slugs, …) are
    defined as Python defaults below — edit this file to change them.
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Secrets (required in .env) ────────────────────────────────────────
    database_url: str
    groq_api_key: str = ""
    secret_key: str

    # ── Auth ─────────────────────────────────────────────────────────────
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # ── App metadata ──────────────────────────────────────────────────────
    app_name: str = "MedInsight"
    app_version: str = "1.0.0"
    app_debug: bool = False

    # ── LLM ───────────────────────────────────────────────────────────────
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_fallback_model: str = "llama-3.1-8b-instant"
    # legacy aliases — kept so any code that reads reasoning_model still works
    reasoning_model: str = "llama-3.3-70b-versatile"
    fallback_reasoning_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.1
    max_tokens_classification: int = 30
    max_tokens_extraction: int = 1000
    max_tokens_self_heal: int = 1000
    max_tokens_text_to_sql: int = 300
    max_tokens_ltm_summary: int = 200
    max_tokens_report: int = 600

    # ── Embedding ─────────────────────────────────────────────────────────
    embedding_provider: str = "huggingface"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimensions: int = 768
    embedding_chunk_size: int = 512
    embedding_chunk_overlap: int = 50

    # ── Database connection pool ──────────────────────────────────────────
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    # ── Server ────────────────────────────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_port: int = 8501
    # ── Rate limiting ─────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = 30

    # ── Seeding ───────────────────────────────────────────────────────────
    seed_demo_patient_count: int = 10
    seed_demo_password: str = "demo1234"

    # ── Patient CSV columns ───────────────────────────────────────────────
    patient_columns: list[str] = Field(
        default=[
            "Name", "Age", "Gender", "Blood Type", "Medical Condition",
            "Doctor", "Hospital", "Insurance Provider",
            "Billing Amount", "Room Number", "Admission Type",
            "Medication",
        ]
    )

    # ── Lab test configuration ────────────────────────────────────────────
    lab_tests_excluded: list[str] = Field(
        default=["Test Results", "Medical Condition", "Medication"]
    )
    lab_tests_categories: dict[str, list[str]] = Field(
        default={
            "blood_count": [
                "Hemoglobin", "Hematocrit", "RBC Count", "WBC Count",
                "Platelet Count", "Neutrophils", "Lymphocytes", "Eosinophils",
                "Basophils", "Monocytes", "MCV", "MCH", "MCHC", "RDW",
            ],
            "metabolic": [
                "Fasting Blood Glucose", "HbA1c", "Random Blood Sugar",
                "Insulin", "Sodium", "Potassium", "Chloride",
            ],
            "liver": [
                "SGPT", "ALT", "SGOT", "AST", "Total Bilirubin",
                "Direct Bilirubin", "Alkaline Phosphatase", "ALP",
                "Albumin", "Total Protein", "GGT",
            ],
            "thyroid": ["TSH", "Free T3", "Free T4", "T3", "T4"],
        }
    )

    # ── MedlinePlus slug mapping ──────────────────────────────────────────
    medlineplus_slugs: dict[str, str] = Field(
        default={
            "Hemoglobin": "hemoglobintest",
            "WBC": "bloodcountcbc",
            "RBC": "bloodcountcbc",
            "Platelets": "plateletcounttest",
            "Glucose": "bloodglucose",
            "HbA1c": "a1ctest",
            "Total Cholesterol": "cholesterollevelswhatyouneedtoknow",
            "LDL": "ldlthebadcholesterol",
            "HDL": "hdlgoodcholesterol",
            "Triglycerides": "triglycerides",
            "Creatinine": "creatineandcreatinine",
            "eGFR": "kidneytests",
            "TSH": "thyroidtests",
            "ALT": "liverfunctiontests",
            "AST": "liverfunctiontests",
        }
    )

    # ── Vector store ──────────────────────────────────────────────────────
    vector_store_provider: str = "pgvector"
    vector_store_collection_name: str = "medical_knowledge_base"
    vector_store_distance_metric: str = "cosine"

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"]
    )

    # ── Evaluation fixtures ───────────────────────────────────────────────
    evaluation_rag_questions: list[str] = Field(
        default=[
            "What is a normal hemoglobin level?",
            "What does high LDL cholesterol mean?",
            "What is the normal range for blood glucose?",
        ]
    )
    evaluation_sql_questions: list[dict] = Field(
        default=[
            {"question": "Show my last 5 lab results", "expected_tables": ["lab_results"]},
            {"question": "What was my glucose level last month?", "expected_tables": ["lab_results"]},
        ]
    )

    # ── Validators ────────────────────────────────────────────────────────
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure the DB URL uses the asyncpg driver."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg:// driver"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton. Safe to call anywhere."""
    return Settings()  # type: ignore[call-arg]  # pydantic-settings reads required fields from .env


settings = get_settings()
