/** Shared traffic types (safe for client components — no Node imports). */

export type TrafficBucket = { visitors: number; views: number };

export type HourlyPoint = { bucket: string; visitors: number; views: number };

export type DailyPoint = { day: string; visitors: number; views: number };

export type PageRow = { path: string; visitors: number; views: number };

export type SourceRow = { source: string; visitors: number; views: number };

export type CountryRow = { country: string; visitors: number };

export type DeviceRow = { device: string; visitors: number };

export type CityRow = { city: string; region: string; country: string; visitors: number };

export type RecentVisit = { path: string; country: string; city?: string; region?: string; device: string; created_at: string };

/** A visitor active in the last five minutes. */
export type LiveVisitor = {
  id: string;
  path: string;
  city: string;
  region: string;
  country: string;
  timezone: string;
  device: string;
  lat: number | null;
  lng: number | null;
  last_seen: string;
};

/** Visitors in the last 24 hours, grouped by rounded coordinates. */
export type MapPoint = { lat: number; lng: number; city: string; country: string; visitors: number };

export type AnalyticsSummary = {
  live: TrafficBucket;
  last24h: TrafficBucket;
  today: TrafficBucket;
  yesterday: TrafficBucket;
  week: TrafficBucket;
  month: TrafficBucket;
  hourly: HourlyPoint[];
  daily: DailyPoint[];
  pages: PageRow[];
  referrers: SourceRow[];
  countries: CountryRow[];
  devices: DeviceRow[];
  recent: RecentVisit[];
  /** Added in migration 0004; absent until it runs. */
  cities?: CityRow[];
  live_visitors?: LiveVisitor[];
  map?: MapPoint[];
  generated_at: string;
};
