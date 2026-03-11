"""SQLAlchemy models for plugin marketplace."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class MarketplaceCache(db.Model):
    """Cached plugin entries fetched from the marketplace registry."""

    __tablename__ = "marketplace_cache"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="0.0.0")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    github_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    zip_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capabilities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    min_sublarr_version: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    is_official: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fetched: Mapped[str] = mapped_column(Text, nullable=False)


class InstalledPlugin(db.Model):
    """Record of locally installed plugins."""

    __tablename__ = "installed_plugins"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="0.0.0")
    plugin_dir: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capabilities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    installed_at: Mapped[str] = mapped_column(Text, nullable=False)
