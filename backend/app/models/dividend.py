"""
Dividend announcements scraped from Maya mandatory disclosures.
One row per declared dividend event.
"""
from datetime import date, datetime

from sqlalchemy import Integer, Date, Numeric, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Dividend(Base):
    __tablename__ = "dividends"
    __table_args__ = (
        # A company can only declare one dividend on a given ex-date
        UniqueConstraint("stock_id", "ex_date", name="uq_dividend_stock_exdate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)

    # Core dividend fields (all from Maya mandatory filings)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date)
    record_date: Mapped[date | None] = mapped_column(Date)
    declared_date: Mapped[date | None] = mapped_column(Date)

    amount_ils: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)   # per share, ILS

    # Derived
    frequency: Mapped[str | None] = mapped_column(String(20))  # quarterly | annual | irregular
    dividend_yield_at_declaration: Mapped[float | None] = mapped_column(Numeric(8, 4))  # %

    # Maya filing reference
    maya_filing_id: Mapped[str | None] = mapped_column(String(50), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    stock = relationship("Stock", back_populates="dividends")

    def __repr__(self) -> str:
        return f"<Dividend stock_id={self.stock_id} ex={self.ex_date} amount={self.amount_ils}>"
