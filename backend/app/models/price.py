"""
Daily price data for each stock.
"""
from datetime import date, datetime

from sqlalchemy import Integer, Date, Numeric, BigInteger, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_price_stock_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)

    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # OHLCV
    open: Mapped[float | None] = mapped_column(Numeric(12, 4))
    high: Mapped[float | None] = mapped_column(Numeric(12, 4))
    low: Mapped[float | None] = mapped_column(Numeric(12, 4))
    close: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)

    # Derived / stored for performance
    market_cap: Mapped[float | None] = mapped_column(Numeric(18, 2))   # in thousands ILS
    week52_high: Mapped[float | None] = mapped_column(Numeric(12, 4))
    week52_low: Mapped[float | None] = mapped_column(Numeric(12, 4))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock = relationship("Stock", back_populates="prices")

    def __repr__(self) -> str:
        return f"<Price stock_id={self.stock_id} date={self.trade_date} close={self.close}>"
