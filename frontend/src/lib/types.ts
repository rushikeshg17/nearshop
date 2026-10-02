// Shapes returned by the NearShop API (see backend/app/schemas/serializers.py).

export type Role = "customer" | "owner" | "admin";
export type StockStatus = "in_stock" | "low_stock" | "out_of_stock";

export interface User {
  id: number;
  name: string;
  email: string;
  phone: string | null;
  role: Role;
  home_lat: number | null;
  home_lng: number | null;
  home_label: string | null;
  shop: { id: number; slug: string; name: string } | null;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  icon: string;
  color_hue: number;
  description: string | null;
  in_stock_listings?: number;
}

export interface Locality {
  name: string;
  lat: number;
  lng: number;
  pincode?: string;
}

export interface Meta {
  city: {
    slug: string;
    name: string;
    state: string;
    center: { lat: number; lng: number };
    default_zoom: number;
    localities: Locality[];
  };
  categories: Category[];
  stats: { shops: number; listings: number; in_stock: number };
}

export interface ShopBrief {
  id: number;
  slug: string;
  name: string;
  tagline: string | null;
  locality: string | null;
  city: string;
  lat: number;
  lng: number;
  distance_km: number | null;
  is_open: boolean | null;
  hours_label: string;
  offers_pickup: boolean;
  offers_delivery: boolean;
  delivery_radius_km: number;
  delivery_fee: number;
  free_delivery_above: number | null;
  is_verified: boolean;
  image_url: string | null;
  inventory_updated_at: string | null;
  rating_avg: number | null;
  rating_count: number;
  categories: string[];
  in_stock_listings?: number;
}

export interface Reliability {
  inventory_updated_at: string | null;
  inventory_update_days_7d: number;
  frequently_updated: boolean;
  reservation_requests_90d: number;
  reservations_confirmed_90d: number;
  acceptance_rate: number | null;
  completion_rate: number | null;
  shop_cancellations_90d: number;
  median_response_minutes: number | null;
  orders_delivered_90d: number;
  rating_avg: number | null;
  rating_count: number;
  accuracy_avg: number | null;
  highlights: string[];
}

export interface ShopDetail extends ShopBrief {
  description: string | null;
  phone: string | null;
  address_line: string;
  pincode: string | null;
  opening_hours: string | null;
  closed_on: string | null;
  established_year: number | null;
  hold_minutes: number;
  is_active: boolean;
  reliability: Reliability;
  category_details: Category[];
  listing_counts?: { total: number; in_stock: number };
}

export interface Listing {
  id: number;
  catalog_item_id: number | null;
  name: string;
  brand: string | null;
  unit: string | null;
  icon: string;
  image_url: string | null;
  category: string | null;
  price: number;
  mrp: number | null;
  quantity: number;
  low_stock_threshold: number;
  stock_status: StockStatus;
  stock_updated_at: string | null;
  is_active: boolean;
  shop: ShopBrief | null;
}

export interface OwnerListing extends Listing {
  sku: string | null;
  description: string | null;
  specs: Record<string, string>;
  keywords: string;
}

export interface ResultGroup {
  key: string;
  catalog_item_id: number | null;
  name: string;
  brand: string | null;
  unit: string | null;
  icon: string;
  image_url: string | null;
  category: string;
  min_price: number;
  max_price: number;
  mrp: number | null;
  nearest_km: number;
  shop_count: number;
  in_stock_count: number;
  relevance: number;
  score: number;
  best_offer: Listing & { shop: ShopBrief };
  offers: (Listing & { shop: ShopBrief })[];
}

export interface MapPin extends ShopBrief {
  match_count: number;
  in_stock_count: number;
  min_price: number | null;
}

export interface SearchResponse {
  query: string;
  normalized_query: string;
  expanded_terms: string[];
  did_you_mean: string | null;
  corrected_from: string | null;
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  shops_in_radius: number;
  groups: ResultGroup[];
  shops: MapPin[];
  category_counts: Record<string, number>;
  engine: { semantic: string; keyword: string };
}

export interface Suggestions {
  queries: string[];
  items: { id: number; name: string; brand: string | null; icon: string; category: string }[];
  categories: { slug: string; name: string; icon: string }[];
}

export interface Review {
  id: number;
  rating: number;
  accuracy_rating: number | null;
  delivery_rating: number | null;
  comment: string | null;
  created_at: string;
  customer_name: string;
  product_name: string | null;
  source: "pickup" | "delivery";
}

export interface DeliveryQuote {
  eligible: boolean;
  distance_km: number;
  delivery_fee: number | null;
  free_delivery_above: number | null;
  reason: string | null;
  subtotal?: number;
}

export interface PriceInsight {
  peer_count: number;
  median: number | null;
  min: number;
  max: number;
  deviation_pct?: number;
  statement: string | null;
}

export interface ProductDetail extends Listing {
  description: string | null;
  specs: Record<string, string>;
  sku: string | null;
  category_detail: { slug: string; name: string; icon: string; color_hue: number };
  subcategory: string | null;
  shop: ShopDetail;
  other_offers: (Listing & { shop: ShopBrief })[];
  price_insight: PriceInsight | null;
  delivery_quote: DeliveryQuote | null;
  reviews: Review[];
  sold_last_30d: number;
  my_reservation: { id: number; code: string; status: ReservationStatus } | null;
}

export interface Recommendation {
  confidence: number | null;
  lift: number | null;
  support?: number | null;
  same_shop?: boolean;
  offer: Listing & { shop: ShopBrief };
}

export type ReservationStatus =
  | "REQUESTED"
  | "CONFIRMED"
  | "READY_FOR_PICKUP"
  | "COMPLETED"
  | "REJECTED"
  | "CANCELLED"
  | "EXPIRED";

export type OrderStatus =
  | "PENDING"
  | "SHOP_CONFIRMED"
  | "PREPARING"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED"
  | "DELIVERY_FAILED"
  | "RETURNED_TO_SHOP";

export interface TimelineEvent {
  from_status: string | null;
  to_status: string;
  actor_role: string;
  note: string | null;
  at: string;
}

export interface Person {
  id: number;
  name: string;
  phone: string | null;
}

export interface Reservation {
  id: number;
  code: string;
  kind: "reservation";
  status: ReservationStatus;
  quantity: number;
  unit_price: number;
  total: number;
  note: string | null;
  hold_minutes: number;
  expires_at: string;
  created_at: string;
  confirmed_at: string | null;
  ready_at: string | null;
  completed_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  product: {
    id: number;
    name: string;
    brand: string | null;
    unit: string | null;
    icon: string;
    image_url: string | null;
    quantity_in_stock: number;
  };
  shop: {
    id: number;
    slug: string;
    name: string;
    locality: string | null;
    address_line: string;
    phone: string | null;
    lat: number;
    lng: number;
    hours_label: string;
  };
  actions: string[];
  reviewed: boolean;
  customer?: Person;
  timeline?: TimelineEvent[];
}

export interface Order {
  id: number;
  code: string;
  kind: "order";
  status: OrderStatus;
  payment_method: string;
  payment_status: string;
  delivery_address: string;
  delivery_lat: number;
  delivery_lng: number;
  contact_phone: string | null;
  distance_km: number;
  subtotal: number;
  delivery_fee: number;
  total: number;
  note: string | null;
  created_at: string;
  delivered_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  items: {
    product_id: number;
    name: string;
    unit_price: number;
    quantity: number;
    icon: string;
    image_url: string | null;
  }[];
  shop: { id: number; slug: string; name: string; locality: string | null; phone: string | null; lat: number; lng: number };
  actions: string[];
  reviewed: boolean;
  customer?: Person;
  timeline?: TimelineEvent[];
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read: boolean;
  created_at: string;
}

export interface CustomerDashboard {
  active_reservations: Reservation[];
  active_orders: Order[];
  history: (Reservation | Order)[];
  to_review: (Reservation | Order)[];
  recent_searches: string[];
  recommendations: Recommendation[];
  stats: { completed_pickups: number; delivered_orders: number; shops_visited: number };
}

export interface SalesPoint {
  date: string;
  revenue: number;
  units: number;
}

export interface OwnerOverview {
  today: { revenue: number; units: number; reservations: number; orders: number };
  revenue_7d: number;
  revenue_prev_7d: number;
  revenue_30d: number;
  queue: {
    reservation_requests: number;
    pickups_waiting: number;
    orders_pending: number;
    deliveries_in_progress: number;
  };
  inventory: { listings: number; in_stock: number; low_stock: number; out_of_stock: number; updated_at: string | null };
  sales_series: SalesPoint[];
  top_products: (Listing & { units: number; revenue: number })[];
  low_stock: (Listing & { days_to_stockout: number | null; recommended_restock: number | null })[];
  rating: { avg: number | null; count: number };
  includes_demo_data: boolean;
  reservation_requests: Reservation[];
  pending_orders: Order[];
  shop: { id: number; name: string; slug: string; offers_delivery: boolean };
}

export interface ForecastItem extends Listing {
  predicted_7d: number;
  daily_rate: number;
  days_to_stockout: number | null;
  recommended_restock: number;
  trend: "rising" | "steady" | "falling";
  confidence: "low" | "medium" | "high";
  is_demo: boolean;
}

export interface ModelSummary {
  algorithm: string;
  trained_at: string;
  uses_demo_data: boolean;
  metrics: Record<string, unknown>;
  note: string | null;
}

export interface OwnerInsights {
  restock: ForecastItem[];
  rising: ForecastItem[];
  price_flags: {
    id: number;
    product: Listing;
    price: number;
    reference_price: number;
    deviation_pct: number;
    direction: "high" | "low";
    peer_count: number;
  }[];
  area_demand: { query: string; searches: number; you_stock_it: boolean }[];
  missed_demand: { query: string; searches: number }[];
  bundle_gaps: {
    item: { id: number; name: string; icon: string; typical_price: number | null };
    because_of: string;
    confidence: number;
    lift: number;
  }[];
  models: Record<string, ModelSummary>;
}

export interface CatalogEntry {
  id: number;
  name: string;
  brand: string | null;
  unit: string | null;
  icon: string;
  mrp: number | null;
  typical_price: number | null;
  local_median: number | null;
  category: string;
  subcategory: string | null;
  already_listed: boolean;
}

export interface AdminOverview {
  totals: {
    customers: number;
    owners: number;
    shops: number;
    shops_verified: number;
    listings: number;
    in_stock: number;
    reservations: number;
    orders: number;
    revenue_30d: number;
    revenue_30d_real: number;
    searches_30d: number;
    open_price_flags: number;
  };
  reservations_by_status: Record<string, number>;
  orders_by_status: Record<string, number>;
  sales_series: SalesPoint[];
  categories: { name: string; slug: string; color_hue: number; revenue_30d: number; searches: number }[];
  top_shops: {
    id: number;
    name: string;
    slug: string;
    locality: string | null;
    revenue_30d: number;
    baskets: number;
    rating_avg: number | null;
  }[];
  popular_searches: { query: string; count: number; avg_results: number }[];
  zero_result_searches: { query: string; count: number }[];
  activity: { date: string; inventory_updates: number; searches: number }[];
}

export interface PriceFlag {
  id: number;
  price: number;
  reference_price: number;
  deviation_pct: number;
  score: number;
  direction: "high" | "low";
  peer_count: number;
  status: "open" | "reviewed" | "dismissed";
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  product: Listing;
  shop: { id: number; name: string; slug: string; locality: string | null };
}

export interface AiModel {
  name: string;
  title: string;
  purpose: string;
  algorithm: string | null;
  trained_at: string | null;
  n_samples: number;
  metrics: Record<string, unknown>;
  note: string;
  uses_demo_data: boolean;
  duration_ms: number;
  runs: { at: string; n_samples: number; duration_ms: number }[];
}

export interface SearchCompare {
  query: string;
  normalized: string;
  methods: {
    key: string;
    title: string;
    note: string;
    results: { name: string; icon: string; category: string; score: number }[];
  }[];
}
