"""Central settings. All secrets come from environment variables — never hardcoded.

Copy backend/.env.example to backend/.env and fill in ANTHROPIC_API_KEY before
running Phase 2+ (the pipeline calls Claude starting at Step 1).
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    # Override to point at an Anthropic-compatible endpoint (e.g. z.ai's
    # https://api.z.ai/api/anthropic for GLM models) instead of api.anthropic.com.
    # Deliberately NOT named ANTHROPIC_BASE_URL: some hosting/dev environments
    # (including this repo's own CI/dev shells) set that generic name as an
    # ambient var for unrelated tooling, which would silently shadow this.
    anthropic_base_url: str | None = Field(default=None, alias="CLIO_ANTHROPIC_BASE_URL")

    sqlite_path: Path = Field(default=REPO_ROOT / "data" / "clio.db", alias="SQLITE_PATH")
    chroma_path: Path = Field(default=REPO_ROOT / "data" / "chroma", alias="CHROMA_PATH")
    cow_data_dir: Path = Field(default=REPO_ROOT / "data" / "cow", alias="COW_DATA_DIR")

    wikipedia_api_base: str = Field(default="https://en.wikipedia.org/api/rest_v1", alias="WIKIPEDIA_API_BASE")
    wikidata_sparql_endpoint: str = Field(
        default="https://query.wikidata.org/sparql", alias="WIKIDATA_SPARQL_ENDPOINT"
    )
    ucdp_api_base: str = Field(default="https://ucdpapi.pcr.uu.se/api", alias="UCDP_API_BASE")

    contact_email: str = Field(default="clio-app@example.com", alias="CLIO_CONTACT_EMAIL")

    @property
    def user_agent(self) -> str:
        return f"CLIO-HistoricalDecisionIntelligence/1.0 ({self.contact_email})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
