"""
Stock / company master table.
One row per TASE-listed company.
"""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # TASE identifiers
    tase_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name_he: Mapped[str | None] = mapped_column(String(200))   # Hebrew name
    name_en: Mapped[str | None] = mapped_column(String(200))   # English name
    isin: Mapped[str | None] = mapped_column(String(12), unique=True)

    # Classification
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))

    # Flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    pays_dividend: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    prices = relationship("Price", back_populates="stock", cascade="all, delete-orphan")
    dividends = relationship("Dividend", back_populates="stock", cascade="all, delete-orphan")
    fundamentals = relationship("Fundamental", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Stock {self.ticker} | {self.name_en}>"
