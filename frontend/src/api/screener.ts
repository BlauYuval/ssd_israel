import api from "./client";
import type { ScreenerResponse, ScreenerFilters, StockDetail, DividendRow } from "./types";

export async function fetchScreener(filters: ScreenerFilters): Promise<ScreenerResponse> {
  const { data } = await api.get<ScreenerResponse>("/screener", { params: filters });
  return data;
}

export async function fetchStockDetail(ticker: string): Promise<StockDetail> {
  const { data } = await api.get<StockDetail>(`/stock/${ticker}`);
  return data;
}

export async function fetchStockDividends(ticker: string, limit = 20): Promise<DividendRow[]> {
  const { data } = await api.get<DividendRow[]>(`/stock/${ticker}/dividends`, {
    params: { limit },
  });
  return data;
}
