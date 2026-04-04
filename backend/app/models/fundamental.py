"""
Annual fundamental data per stock.
Sourced from Maya PDF filings and bizportal.co.il.
One row per (stock, fiscal_year).
"""
from datetime import datetime

from sqlalchemy import Integer, Numeric, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        UniqueConstraint("stock_id", "fiscal_year", name="uq_fundamental_stock_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Income Statement (thousands ILS)
    revenue: Mapped[float | None] = mapped_column(Numeric(18, 2))
    gross_profit: Mapped[float | None] = mapped_column(Numeric(18, 2))
    operating_income: Mapped[float | None] = mapped_column(Numeric(18, 2))
    net_income: Mapped[float | None] = mapped_column(Numeric(18, 2))
    eps: Mapped[float | None] = mapped_column(Numeric(10, 4))                   # ILS per share

    # Cash Flow (thousands ILS)
    operating_cash_flow: Mapped[float | None] = mapped_column(Numeric(18, 2))
    capex: Mapped[float | None] = mapped_column(Numeric(18, 2))
    free_cash_flow: Mapped[float | None] = mapped_column(Numeric(18, 2))        # OCF - capex
    dividends_paid: Mapped[float | None] = mapped_column(Numeric(18, 2))        # total cash paid to shareholders

    # Balance Sheet (thousands ILS)
    total_assets: Mapped[float | None] = mapped_column(Numeric(18, 2))
    total_liabilities: Mapped[float | None] = mapped_column(Numeric(18, 2))
    shareholders_equity: Mapped[float | None] = mapped_column(Numeric(18, 2))
    total_debt: Mapped[float | None] = mapped_column(Numeric(18, 2))

    # Derived ratios (stored for screener performance)
    payout_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))          # dividends_paid / net_income
    fcf_payout_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))      # dividends_paid / FCF
    debt_to_equity: Mapped[float | None] = mapped_column(Numeric(8, 4))        # total_debt / equity

    # Data quality
    data_source: Mapped[str | None] = mapped_column(String(50))                # maya_pdf | bizportal | tase_api
    is_complete: Mapped[bool] = mapped_column(default=False)                   # all key fields populated

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    stock = relationship("Stock", back_populates="fundamentals")

    def __repr__(self) -> str:
        return f"<Fundamental stock_id={self.stock_id} year={self.fiscal_year}>"
