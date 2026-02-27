import { Platform } from 'react-native';

// API Configuration
const API_BASE_URL = Platform.select({
  web: 'http://localhost:8000/api',
  default: 'http://10.0.2.2:8000/api', // Android emulator
  // For iOS simulator, use 'http://localhost:8000/api'
  // For physical device, use your machine's IP address
});

const WS_BASE_URL = Platform.select({
  web: 'ws://localhost:8000',
  default: 'ws://10.0.2.2:8000',
});

// Types
export interface College {
  id: string;
  name: string;
  short: string;
  department?: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  college: College;
  department?: string;
  semester?: number;
  location?: string;
  ecoScore: number;
  carbonSaved: number;
  verified: boolean;
  isDriving: boolean;
  isDriver: boolean;
  homeLocation?: string;
  rating: number;
  totalRides: number;
  driverStreak: number;
  created_at: string;
}

export interface DriverRoute {
  id: string;
  driver_id: string;
  driver_name: string;
  origin: string;
  destination: string;
  departure_time: string;
  direction: string;
  available_seats: number;
  price_per_seat: number;
  amenities: string[];
  is_active: boolean;
  created_at: string;
}

export interface RideRequest {
  id: string;
  rider_id: string;
  rider_name: string;
  driver_id: string;
  driver_name: string;
  route_id: string;
  pickup_location: string;
  status: string;
  tokens: number;
  created_at: string;
}

export interface RideMatch {
  id: string;
  ride_request_id: string;
  rider_id: string;
  driver_id: string;
  route_id: string;
  status: string;
  carbon_saved: number;
  split_cost: number;
  created_at: string;
}

export interface Rating {
  smoothness: number;
  comfort: number;
  amenities: string[];
  match_reason?: string;
  trust_score: number;
  comment?: string;
}

export interface SubscriptionTier {
  id: string;
  name: string;
  price: number;
  rides: number;
  validity: string;
  features: string[];
}

// API Client Class
class ApiService {
  private baseUrl: string;
  private wsUrl: string;
  private ws: WebSocket | null = null;
  private messageHandlers: Map<string, (data: any) => void> = new Map();

  constructor() {
    this.baseUrl = API_BASE_URL!;
    this.wsUrl = WS_BASE_URL!;
  }

  // ===== HTTP Methods =====
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    try {
      const response = await fetch(url, { ...options, headers });
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      
      return response.json();
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  }

  private get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  private post<T>(endpoint: string, data: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  private put<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  // ===== User Endpoints =====
  async createUser(userData: {
    name: string;
    email: string;
    college: College;
    department?: string;
    semester?: number;
  }): Promise<User> {
    return this.post<User>('/users', userData);
  }

  async getUser(userId: string): Promise<User> {
    return this.get<User>(`/users/${userId}`);
  }

  async getUserByEmail(email: string): Promise<User> {
    return this.get<User>(`/users/email/${email}`);
  }

  async updateUser(
    userId: string,
    updates: { name?: string; department?: string; semester?: number; location?: string }
  ): Promise<User> {
    return this.put<User>(`/users/${userId}`, updates);
  }

  async updateDrivingStatus(userId: string, isDriving: boolean): Promise<{ success: boolean }> {
    return this.put(`/users/${userId}/driving-status?is_driving=${isDriving}`);
  }

  async getActiveDrivers(skip = 0, limit = 20): Promise<{ drivers: User[]; total: number }> {
    return this.get(`/users/active-drivers/list?skip=${skip}&limit=${limit}`);
  }

  // ===== Driver Routes =====
  async createRoute(routeData: {
    driver_id: string;
    driver_name: string;
    origin: string;
    destination: string;
    departure_time: string;
    direction?: string;
    available_seats?: number;
    price_per_seat?: number;
    amenities?: string[];
  }): Promise<DriverRoute> {
    return this.post<DriverRoute>('/driver-routes', routeData);
  }

  async getActiveRoutes(skip = 0, limit = 20): Promise<DriverRoute[]> {
    return this.get<DriverRoute[]>(`/driver-routes/active?skip=${skip}&limit=${limit}`);
  }

  async getDriverRoutes(
    driverId: string,
    activeOnly = true
  ): Promise<{ routes: DriverRoute[]; total: number }> {
    return this.get(`/driver-routes/driver/${driverId}?active_only=${activeOnly}`);
  }

  async deactivateRoute(routeId: string): Promise<{ success: boolean }> {
    return this.put(`/driver-routes/${routeId}/deactivate`);
  }

  async updateSeats(routeId: string, seats: number): Promise<{ success: boolean }> {
    return this.put(`/driver-routes/${routeId}/seats?seats=${seats}`);
  }

  // ===== Ride Requests =====
  async createRideRequest(requestData: {
    rider_id: string;
    rider_name: string;
    driver_id: string;
    driver_name: string;
    route_id: string;
    pickup_location: string;
    tokens?: number;
  }): Promise<RideRequest> {
    return this.post<RideRequest>('/ride-requests', requestData);
  }

  async getDriverRequests(
    driverId: string,
    status = 'pending'
  ): Promise<{ requests: RideRequest[]; total: number }> {
    return this.get(`/ride-requests/driver/${driverId}?status=${status}`);
  }

  async getRiderRequests(
    riderId: string,
    status?: string
  ): Promise<{ requests: RideRequest[]; total: number }> {
    const statusParam = status ? `?status=${status}` : '';
    return this.get(`/ride-requests/rider/${riderId}${statusParam}`);
  }

  async acceptRideRequest(requestId: string): Promise<{ success: boolean; match: RideMatch }> {
    return this.put(`/ride-requests/${requestId}/accept`);
  }

  async rejectRideRequest(requestId: string): Promise<{ success: boolean }> {
    return this.put(`/ride-requests/${requestId}/reject`);
  }

  async cancelRideRequest(requestId: string): Promise<{ success: boolean }> {
    return this.put(`/ride-requests/${requestId}/cancel`);
  }

  // ===== Ride Matches =====
  async getRideMatch(matchId: string): Promise<RideMatch> {
    return this.get<RideMatch>(`/ride-matches/${matchId}`);
  }

  async startRide(matchId: string): Promise<{ success: boolean }> {
    return this.put(`/ride-matches/${matchId}/start`);
  }

  async completeRide(matchId: string): Promise<{ success: boolean }> {
    return this.put(`/ride-matches/${matchId}/complete`);
  }

  async getRideHistory(
    userId: string,
    skip = 0,
    limit = 20
  ): Promise<{ rides: RideMatch[]; total: number }> {
    return this.get(`/ride-matches/user/${userId}/history?skip=${skip}&limit=${limit}`);
  }

  // ===== Ratings =====
  async submitRating(ratingData: {
    ride_id: string;
    rider_id: string;
    driver_id: string;
    smoothness: number;
    comfort: number;
    amenities?: string[];
    match_reason?: string;
    trust_score?: number;
    comment?: string;
  }): Promise<Rating> {
    return this.post<Rating>('/ratings', ratingData);
  }

  async getDriverRatings(
    driverId: string
  ): Promise<{ ratings: Rating[]; total: number; avg_smoothness: number; avg_comfort: number }> {
    return this.get(`/ratings/driver/${driverId}`);
  }

  // ===== Authentication =====
  private authToken: string | null = null;

  setAuthToken(token: string): void {
    this.authToken = token;
  }

  clearAuthToken(): void {
    this.authToken = null;
  }

  async register(userData: {
    name: string;
    email: string;
    password: string;
    college: College;
    department?: string;
    semester?: number;
  }): Promise<{ access_token: string; user: User }> {
    const result = await this.post<{ access_token: string; user: User }>('/auth/register', userData);
    this.authToken = result.access_token;
    return result;
  }

  async login(email: string, password: string): Promise<{ access_token: string; user: User }> {
    const result = await this.post<{ access_token: string; user: User }>('/auth/login', { email, password });
    this.authToken = result.access_token;
    return result;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/auth/me', {
      method: 'GET',
      headers: this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {},
    });
  }

  // ===== Car Management =====
  async registerCar(carData: {
    driver_id: string;
    model: string;
    plate_number: string;
    color?: string;
    total_seats?: number;
  }): Promise<any> {
    return this.post('/cars', carData);
  }

  async getDriverCars(driverId: string): Promise<{ cars: any[] }> {
    return this.get(`/cars/driver/${driverId}`);
  }

  async bookCarSeat(carId: string): Promise<{ success: boolean; available_seats: number }> {
    return this.put(`/cars/${carId}/book-seat`);
  }

  async releaseCarSeat(carId: string): Promise<{ success: boolean; available_seats: number }> {
    return this.put(`/cars/${carId}/release-seat`);
  }

  // ===== Payments (Stripe) =====
  async createPaymentIntent(
    amount: number,
    rideRequestId: string
  ): Promise<{
    client_secret: string;
    payment_intent_id: string;
    base_fare: number;
    service_fee: number;
    total_amount: number;
  }> {
    return this.request(`/payments/create-intent?amount=${amount}&ride_request_id=${rideRequestId}`, {
      method: 'POST',
      headers: this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {},
    });
  }

  async refundPayment(
    paymentIntentId: string,
    reason?: string
  ): Promise<{ success: boolean; refund_id: string; amount: number; status: string }> {
    return this.post(`/payments/refund?payment_intent_id=${paymentIntentId}&reason=${reason || 'driver_cancelled'}`, {});
  }

  // ===== Driver Recommendations =====
  async getRecommendedDrivers(
    userId: string,
    pickupLat: number,
    pickupLon: number,
    maxDistanceKm = 5
  ): Promise<{
    recommended: any[];
    nearby: any[];
    total: number;
  }> {
    return this.get(
      `/drivers/recommended?user_id=${userId}&pickup_lat=${pickupLat}&pickup_lon=${pickupLon}&max_distance_km=${maxDistanceKm}`
    );
  }

  async updateDriverLocation(
    driverId: string,
    latitude: number,
    longitude: number,
    address?: string
  ): Promise<{ success: boolean }> {
    const addressParam = address ? `&address=${encodeURIComponent(address)}` : '';
    return this.put(`/drivers/${driverId}/location?latitude=${latitude}&longitude=${longitude}${addressParam}`);
  }

  async updateLastDropLocation(
    driverId: string,
    latitude: number,
    longitude: number,
    address?: string
  ): Promise<{ success: boolean }> {
    const addressParam = address ? `&address=${encodeURIComponent(address)}` : '';
    return this.put(`/drivers/${driverId}/last-drop?latitude=${latitude}&longitude=${longitude}${addressParam}`);
  }

  // ===== Ride Summary =====
  async getRideSummary(matchId: string): Promise<{
    ride_id: string;
    status: string;
    route: { origin: string; destination: string; distance_km?: number };
    rider: { id: string; name: string };
    driver: { id: string; name: string; rating?: number };
    billing: { base_fare: number; service_fee: number; total_amount: number; payment_status: string };
    eco_impact: { carbon_saved_kg: number };
    timestamps: { created_at?: string; started_at?: string; completed_at?: string; duration_minutes?: number };
  }> {
    return this.get(`/rides/${matchId}/summary`);
  }

  // ===== TomTom Maps =====
  async searchLocation(
    query: string,
    lat?: number,
    lon?: number,
    limit = 5
  ): Promise<{
    results: Array<{ name: string; address: string; position: { lat: number; lon: number } }>;
  }> {
    const latParam = lat ? `&lat=${lat}` : '';
    const lonParam = lon ? `&lon=${lon}` : '';
    return this.get(`/maps/search?query=${encodeURIComponent(query)}${latParam}${lonParam}&limit=${limit}`);
  }

  async getRoute(
    startLat: number,
    startLon: number,
    endLat: number,
    endLon: number
  ): Promise<{
    distance_km: number;
    duration_minutes: number;
    traffic_delay_minutes?: number;
  }> {
    return this.get(
      `/maps/route?start_lat=${startLat}&start_lon=${startLon}&end_lat=${endLat}&end_lon=${endLon}`
    );
  }

  // ===== Subscriptions =====
  async getSubscriptionTiers(): Promise<{ tiers: SubscriptionTier[] }> {
    return this.get('/subscriptions/tiers');
  }

  async subscribeUser(
    userId: string,
    tierId: string
  ): Promise<{ success: boolean; subscription: any }> {
    return this.post(`/subscriptions/subscribe?user_id=${userId}&tier_id=${tierId}`, {});
  }

  async getUserSubscription(
    userId: string
  ): Promise<{ active: boolean; subscription: any }> {
    return this.get(`/subscriptions/user/${userId}`);
  }

  // ===== Admin =====
  async getCollegeStats(collegeId: string): Promise<{
    total_users: number;
    active_drivers: number;
    active_riders: number;
    total_rides: number;
    pending_verifications: number;
    carbon_saved: number;
  }> {
    return this.get(`/admin/college/${collegeId}/stats`);
  }

  async getCollegeLeaderboard(
    collegeId: string,
    limit = 10
  ): Promise<{ leaderboard: any[] }> {
    return this.get(`/admin/college/${collegeId}/leaderboard?limit=${limit}`);
  }

  // ===== Health Check =====
  async healthCheck(): Promise<{ status: string; database: string }> {
    return this.get('/health');
  }

  // ===== WebSocket =====
  connectWebSocket(userId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    this.ws = new WebSocket(`${this.wsUrl}/ws/${userId}`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const handler = this.messageHandlers.get(data.type);
        if (handler) {
          handler(data);
        }
      } catch (error) {
        console.error('WebSocket message error:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      // Attempt reconnection after 3 seconds
      setTimeout(() => {
        if (userId) {
          this.connectWebSocket(userId);
        }
      }, 3000);
    };
  }

  disconnectWebSocket(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  onMessage(type: string, handler: (data: any) => void): void {
    this.messageHandlers.set(type, handler);
  }

  offMessage(type: string): void {
    this.messageHandlers.delete(type);
  }

  sendLocationUpdate(location: { latitude: number; longitude: number }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'location_update',
        location,
      }));
    }
  }

  sendPing(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }
}

// Export singleton instance
export const apiService = new ApiService();
export default apiService;
