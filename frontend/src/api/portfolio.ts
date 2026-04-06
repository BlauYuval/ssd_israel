import api from "./client";
import type { HoldingIn, PortfolioSummary } from "./types";

export async function fetchPortfolio(holdings: HoldingIn[]): Promise<PortfolioSummary> {
  const { data } = await api.post<PortfolioSummary>("/portfolio", holdings);
  return data;
}
