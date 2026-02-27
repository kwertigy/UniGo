from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import json
import jwt
import stripe
import hashlib
import re
import math

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


# ===== Environment Variable Validation =====
def get_env_var(key: str, default: str = None) -> str:
    """Get environment variable with optional default"""
    value = os.environ.get(key, default)
    if value is None:
        logger.warning(f"Environment variable {key} not set, using fallback")
        if key == 'MONGO_URL':
            return 'mongodb://localhost:27017'
        elif key == 'DB_NAME':
            return 'unigo_db'
        elif key == 'JWT_SECRET':
            return 'unigo-super-secret-jwt-key-change-in-production'
        elif key == 'STRIPE_SECRET_KEY':
            return ''
        elif key == 'TOMTOM_API_KEY':
            return ''
    return value


mongo_url = get_env_var('MONGO_URL')
db_name = get_env_var('DB_NAME')
jwt_secret = get_env_var('JWT_SECRET')
jwt_algorithm = "HS256"
stripe_secret = get_env_var('STRIPE_SECRET_KEY')
tomtom_api_key = get_env_var('TOMTOM_API_KEY')

# Initialize Stripe
if stripe_secret:
    stripe.api_key = stripe_secret

# College domain mappings
COLLEGE_DOMAINS = {
    "nhce": ["nhce.edu.in", "newhorizonindia.edu"],
    "rvce": ["rvce.edu.in"],
    "pesit": ["pes.edu", "pesu.pes.edu"],
    "bmsce": ["bmsce.ac.in"],
    "msrit": ["msrit.edu"],
    "christ": ["christuniversity.in"],
    "jain": ["jainuniversity.ac.in"],
    "mit": ["manipal.edu"],
}

# Security
security = HTTPBearer(auto_error=False)

# MongoDB client (will be initialized in lifespan)
client: AsyncIOMotorClient = None
db = None


# ===== Lifespan Management =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown"""
    global client, db
    try:
        logger.info(f"Connecting to MongoDB at {mongo_url}")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        # Create indexes for better query performance
        await create_indexes()
        logger.info("MongoDB connection established successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    finally:
        if client:
            client.close()
            logger.info("MongoDB connection closed")


async def create_indexes():
    """Create database indexes for better performance"""
    try:
        await db.users.create_index("id", unique=True)
        await db.users.create_index("email", unique=True)
        await db.users.create_index("college.id")
        await db.users.create_index("isDriving")
        await db.users.create_index("current_location")
        await db.driver_routes.create_index("id", unique=True)
        await db.driver_routes.create_index("is_active")
        await db.driver_routes.create_index("driver_id")
        await db.ride_requests.create_index("id", unique=True)
        await db.ride_requests.create_index("driver_id")
        await db.ride_requests.create_index("rider_id")
        await db.ride_requests.create_index("status")
        await db.ride_matches.create_index("id", unique=True)
        await db.ride_matches.create_index("payment_intent_id")
        await db.ratings.create_index("driver_id")
        await db.ratings.create_index("rider_id")
        # Car indexes
        await db.cars.create_index("id", unique=True)
        await db.cars.create_index("driver_id")
        await db.cars.create_index([("available_seats", 1), ("is_active", 1)])
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


# Create the main app with lifespan management
app = FastAPI(
    title="UniGo Campus Pool API",
    description="Multi-College Carpooling Ecosystem",
    version="2.0.0",
    lifespan=lifespan
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ===== WebSocket Connection Manager =====
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        try:
            await websocket.accept()
            self.active_connections[user_id] = websocket
            logger.info(f"WebSocket connected for user: {user_id}")
        except Exception as e:
            logger.error(f"WebSocket connection failed for {user_id}: {e}")
            raise

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"WebSocket disconnected for user: {user_id}")

    async def send_personal_message(self, message: str, user_id: str) -> bool:
        """Send message to specific user, returns success status"""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send message to {user_id}: {e}")
                self.disconnect(user_id)
                return False
        return False

    async def broadcast(self, message: str):
        """Broadcast message to all connected users"""
        disconnected = []
        for user_id, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Broadcast failed for {user_id}: {e}")
                disconnected.append(user_id)
        
        # Clean up disconnected clients
        for user_id in disconnected:
            self.disconnect(user_id)


manager = ConnectionManager()


# ===== Helper Functions =====
def get_utc_now() -> datetime:
    """Get current UTC datetime (Python 3.12+ compatible)"""
    return datetime.now(timezone.utc)


def model_to_dict(model: BaseModel) -> dict:
    """Convert Pydantic model to dict with datetime serialization"""
    data = model.model_dump()
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, datetime):
                    value[k] = v.isoformat()
    return data


# ===== JWT Authentication Functions =====
def validate_college_email(email: str, college_id: str) -> bool:
    """Validate that email domain matches the college"""
    email_domain = email.split('@')[-1].lower()
    college_key = college_id.lower()
    
    # Check if college is in our domain mappings
    if college_key in COLLEGE_DOMAINS:
        return email_domain in COLLEGE_DOMAINS[college_key]
    
    # Fallback: check if college short name appears in domain
    return college_key in email_domain


def create_jwt_token(user_id: str, email: str, college_id: str) -> str:
    """Create a JWT token for authenticated user"""
    payload = {
        "sub": user_id,
        "email": email,
        "college_id": college_id,
        "iat": get_utc_now(),
        "exp": get_utc_now() + timedelta(days=7)
    }
    return jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[Dict[str, Any]]:
    """Dependency to get current authenticated user"""
    if not credentials:
        return None
    
    payload = verify_jwt_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 (use bcrypt in production)"""
    return hashlib.sha256(password.encode()).hexdigest()


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates using Haversine formula"""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


# ===== Models with Validation =====

class College(BaseModel):
    id: str
    name: str
    short: str
    domain: Optional[str] = None  # e.g., "nhce.edu.in"
    department: Optional[str] = None


class Location(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password_hash: Optional[str] = None  # Hashed password for auth
    college: College
    department: Optional[str] = None
    semester: Optional[int] = Field(default=None, ge=1, le=10)
    location: Optional[str] = None
    current_location: Optional[Location] = None  # Live location
    last_drop_location: Optional[Location] = None  # For drivers
    ecoScore: int = Field(default=0, ge=0)
    carbonSaved: float = Field(default=0.0, ge=0)
    verified: bool = True
    isDriving: bool = False
    isDriver: bool = False
    homeLocation: Optional[str] = None
    rating: float = Field(default=5.0, ge=0, le=5)
    totalRides: int = Field(default=0, ge=0)
    driverStreak: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=get_utc_now)


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    college: College
    department: Optional[str] = None
    semester: Optional[int] = Field(default=None, ge=1, le=10)
    location: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email_domain(cls, v, info):
        """Email validation will be done with college context in the endpoint"""
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    department: Optional[str] = None
    semester: Optional[int] = Field(default=None, ge=1, le=10)
    location: Optional[str] = None
    homeLocation: Optional[str] = None


class DriverRoute(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str
    driver_name: str
    origin: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    departure_time: str
    direction: str = Field(default="to_college", pattern="^(to_college|from_college)$")
    available_seats: int = Field(default=4, ge=1, le=10)
    price_per_seat: int = Field(default=50, ge=0, le=10000)
    amenities: List[str] = []
    is_active: bool = True
    estimated_duration: Optional[int] = None  # minutes
    distance_km: Optional[float] = None
    created_at: datetime = Field(default_factory=get_utc_now)


class DriverRouteCreate(BaseModel):
    driver_id: str
    driver_name: str
    origin: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    departure_time: str
    direction: str = Field(default="to_college", pattern="^(to_college|from_college)$")
    available_seats: int = Field(default=4, ge=1, le=10)
    price_per_seat: int = Field(default=50, ge=0, le=10000)
    amenities: List[str] = []


# ===== Car Model (for seat management) =====
class Car(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    driver_id: str
    model: str = Field(..., min_length=1, max_length=100)
    plate_number: str = Field(..., min_length=1, max_length=20)
    color: Optional[str] = None
    total_seats: int = Field(default=4, ge=1, le=10)
    available_seats: int = Field(default=4, ge=0, le=10)
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_utc_now)


class CarCreate(BaseModel):
    driver_id: str
    model: str = Field(..., min_length=1, max_length=100)
    plate_number: str = Field(..., min_length=1, max_length=20)
    color: Optional[str] = None
    total_seats: int = Field(default=4, ge=1, le=10)


class RideRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rider_id: str
    rider_name: str
    driver_id: str
    driver_name: str
    route_id: str
    pickup_location: str = Field(..., min_length=1, max_length=200)
    status: str = Field(default="pending", pattern="^(pending|accepted|rejected|completed|cancelled)$")
    tokens: int = Field(default=100, ge=0)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class RideRequestCreate(BaseModel):
    rider_id: str
    rider_name: str
    driver_id: str
    driver_name: str
    route_id: str
    pickup_location: str = Field(..., min_length=1, max_length=200)
    tokens: int = Field(default=100, ge=0)


class RideMatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ride_request_id: str
    rider_id: str
    driver_id: str
    route_id: str
    status: str = Field(default="matched", pattern="^(matched|in_progress|completed|cancelled)$")
    carbon_saved: float = Field(default=2.5, ge=0)  # kg CO2
    split_cost: int = Field(default=50, ge=0)
    # Payment fields
    payment_intent_id: Optional[str] = None  # Stripe payment intent
    payment_status: str = Field(default="pending", pattern="^(pending|captured|refunded|failed)$")
    base_fare: int = Field(default=0, ge=0)
    service_fee: int = Field(default=0, ge=0)
    total_amount: int = Field(default=0, ge=0)
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=get_utc_now)


class Rating(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ride_id: str
    rider_id: str
    driver_id: str
    smoothness: int = Field(..., ge=1, le=5)
    comfort: int = Field(..., ge=1, le=5)
    amenities: List[str] = []
    match_reason: Optional[str] = None
    trust_score: int = Field(default=5, ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=get_utc_now)


class RatingCreate(BaseModel):
    ride_id: str
    rider_id: str
    driver_id: str
    smoothness: int = Field(..., ge=1, le=5)
    comfort: int = Field(..., ge=1, le=5)
    amenities: List[str] = []
    match_reason: Optional[str] = None
    trust_score: int = Field(default=5, ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=500)


class SubscriptionTier(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    price: int = Field(..., ge=0)
    rides: int = Field(..., ge=0)
    validity: str
    features: List[str] = []


class UserSubscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    tier_id: str
    tier_name: str
    rides_remaining: int = Field(..., ge=0)
    expires_at: datetime
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_utc_now)


# ===== Pagination Helper =====
class PaginationParams:
    def __init__(
        self,
        skip: int = Query(default=0, ge=0, description="Number of records to skip"),
        limit: int = Query(default=20, ge=1, le=100, description="Max records to return")
    ):
        self.skip = skip
        self.limit = limit


# ===== Authentication Models =====
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


class RegisterRequest(BaseModel):
    """Registration request with required password"""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    college: College
    department: Optional[str] = None
    semester: Optional[int] = Field(default=None, ge=1, le=10)
    location: Optional[str] = None


# ===== Authentication Endpoints =====

@api_router.post("/auth/register", response_model=AuthResponse)
async def register(user_input: RegisterRequest):
    """Register a new user with email domain validation"""
    try:
        # Validate college email domain
        if not validate_college_email(user_input.email, user_input.college.id):
            raise HTTPException(
                status_code=400, 
                detail=f"Email domain must match your college ({user_input.college.id}). "
                       f"Expected domains: {COLLEGE_DOMAINS.get(user_input.college.id.lower(), ['college domain'])}"
            )
        
        # Check if email already exists
        existing = await db.users.find_one({"email": user_input.email})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user with hashed password
        user_data = user_input.model_dump()
        password = user_data.pop('password')
        user_obj = User(**user_data, password_hash=hash_password(password))
        
        await db.users.insert_one(model_to_dict(user_obj))
        
        # Generate JWT token
        token = create_jwt_token(user_obj.id, user_obj.email, user_obj.college.id)
        
        logger.info(f"Registered user: {user_obj.id}")
        return AuthResponse(access_token=token, user=user_obj)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register user: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(login_request: LoginRequest):
    """Login with email and password"""
    try:
        user = await db.users.find_one({"email": login_request.email})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if user.get("password_hash") != hash_password(login_request.password):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Generate JWT token
        token = create_jwt_token(user["id"], user["email"], user["college"]["id"])
        
        logger.info(f"User logged in: {user['id']}")
        return AuthResponse(access_token=token, user=User(**user))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@api_router.get("/auth/me", response_model=User)
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current authenticated user info"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user = await db.users.find_one({"id": current_user["sub"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return User(**user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user info")


# ===== User Endpoints =====

@api_router.post("/users", response_model=User)
async def create_user(user_input: UserCreate):
    """Create a new user (legacy endpoint - prefer /auth/register)"""
    try:
        # Note: Email domain validation is optional for legacy endpoint
        # This allows easier onboarding; use /auth/register for strict validation
        
        # Check if email already exists
        existing = await db.users.find_one({"email": user_input.email})
        if existing:
            # Return existing user instead of error for easier onboarding
            return User(**existing)
        
        user_data = user_input.model_dump()
        password = user_data.pop('password', None)
        user_obj = User(**user_data, password_hash=hash_password(password) if password else None)
        await db.users.insert_one(model_to_dict(user_obj))
        logger.info(f"Created user: {user_obj.id}")
        return user_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@api_router.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    """Get user by ID"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return User(**user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user")


@api_router.get("/users/email/{email}", response_model=User)
async def get_user_by_email(email: str):
    """Get user by email"""
    try:
        user = await db.users.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return User(**user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user by email: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user")


@api_router.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, user_update: UserUpdate):
    """Update user profile"""
    try:
        update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = await db.users.find_one({"id": user_id})
        return User(**user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user")


@api_router.put("/users/{user_id}/driving-status")
async def update_driving_status(user_id: str, is_driving: bool):
    """Update user's driving status"""
    try:
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": {"isDriving": is_driving, "isDriver": True}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Broadcast to all connected riders
        await manager.broadcast(json.dumps({
            "type": "driver_status_update",
            "user_id": user_id,
            "is_driving": is_driving
        }))
        
        logger.info(f"User {user_id} driving status: {is_driving}")
        return {"success": True, "isDriving": is_driving}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update driving status for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update driving status")


@api_router.get("/users/active-drivers/list")
async def get_active_drivers(pagination: PaginationParams = Depends()):
    """Get all users who are currently driving with pagination"""
    try:
        drivers = await db.users.find({"isDriving": True}).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.users.count_documents({"isDriving": True})
        return {
            "drivers": [User(**driver) for driver in drivers],
            "total": total,
            "skip": pagination.skip,
            "limit": pagination.limit
        }
    except Exception as e:
        logger.error(f"Failed to get active drivers: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve drivers")


# ===== Driver Routes Endpoints =====

@api_router.post("/driver-routes", response_model=DriverRoute)
async def create_driver_route(route_input: DriverRouteCreate):
    """Publish a new driver route"""
    try:
        # Verify driver exists
        driver = await db.users.find_one({"id": route_input.driver_id})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        route_obj = DriverRoute(**route_input.model_dump())
        await db.driver_routes.insert_one(model_to_dict(route_obj))
        
        # Update user driving status and increment streak
        await db.users.update_one(
            {"id": route_input.driver_id},
            {
                "$set": {"isDriving": True, "isDriver": True},
                "$inc": {"driverStreak": 1}
            }
        )
        
        # Broadcast to all riders
        await manager.broadcast(json.dumps({
            "type": "new_route",
            "route": model_to_dict(route_obj)
        }, default=str))
        
        logger.info(f"Created route: {route_obj.id} by driver {route_input.driver_id}")
        return route_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create route: {e}")
        raise HTTPException(status_code=500, detail="Failed to create route")


@api_router.get("/driver-routes/active", response_model=List[DriverRoute])
async def get_active_routes(pagination: PaginationParams = Depends()):
    """Get all active driver routes with pagination"""
    try:
        routes = await db.driver_routes.find({"is_active": True}).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        return [DriverRoute(**route) for route in routes]
    except Exception as e:
        logger.error(f"Failed to get active routes: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve routes")


@api_router.get("/driver-routes/driver/{driver_id}")
async def get_driver_routes(driver_id: str, active_only: bool = True, pagination: PaginationParams = Depends()):
    """Get all routes for a specific driver"""
    try:
        query = {"driver_id": driver_id}
        if active_only:
            query["is_active"] = True
        
        routes = await db.driver_routes.find(query).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.driver_routes.count_documents(query)
        return {
            "routes": [DriverRoute(**route) for route in routes],
            "total": total
        }
    except Exception as e:
        logger.error(f"Failed to get routes for driver {driver_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve routes")


@api_router.put("/driver-routes/{route_id}/deactivate")
async def deactivate_route(route_id: str):
    """Deactivate a route"""
    try:
        result = await db.driver_routes.update_one(
            {"id": route_id},
            {"$set": {"is_active": False}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Route not found")
        
        logger.info(f"Deactivated route: {route_id}")
        return {"success": True, "route_id": route_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate route {route_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to deactivate route")


@api_router.put("/driver-routes/{route_id}/seats")
async def update_available_seats(route_id: str, seats: int = Query(..., ge=0, le=10)):
    """Update available seats for a route"""
    try:
        result = await db.driver_routes.update_one(
            {"id": route_id},
            {"$set": {"available_seats": seats}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Route not found")
        
        return {"success": True, "available_seats": seats}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update seats for route {route_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update seats")


# ===== Ride Request Endpoints (Handshake Logic) =====

@api_router.post("/ride-requests", response_model=RideRequest)
async def create_ride_request(request_input: RideRequestCreate):
    """Create a ride request (Step A: User clicks 'Request')"""
    try:
        # Verify route exists and is active
        route = await db.driver_routes.find_one({"id": request_input.route_id, "is_active": True})
        if not route:
            raise HTTPException(status_code=404, detail="Route not found or inactive")
        
        # Check available seats
        if route.get("available_seats", 0) < 1:
            raise HTTPException(status_code=400, detail="No seats available")
        
        # Check for existing pending request
        existing = await db.ride_requests.find_one({
            "rider_id": request_input.rider_id,
            "route_id": request_input.route_id,
            "status": "pending"
        })
        if existing:
            raise HTTPException(status_code=400, detail="You already have a pending request for this route")
        
        request_obj = RideRequest(**request_input.model_dump())
        await db.ride_requests.insert_one(model_to_dict(request_obj))
        
        # Send real-time notification to driver
        await manager.send_personal_message(
            json.dumps({
                "type": "new_ride_request",
                "request": model_to_dict(request_obj)
            }, default=str),
            request_input.driver_id
        )
        
        logger.info(f"Created ride request: {request_obj.id}")
        return request_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ride request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create ride request")


@api_router.get("/ride-requests/driver/{driver_id}")
async def get_driver_requests(driver_id: str, status: Optional[str] = "pending", pagination: PaginationParams = Depends()):
    """Get all requests for a driver with optional status filter"""
    try:
        query = {"driver_id": driver_id}
        if status:
            query["status"] = status
        
        requests = await db.ride_requests.find(query).sort("created_at", -1).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.ride_requests.count_documents(query)
        return {
            "requests": [RideRequest(**req) for req in requests],
            "total": total
        }
    except Exception as e:
        logger.error(f"Failed to get requests for driver {driver_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve requests")


@api_router.get("/ride-requests/rider/{rider_id}")
async def get_rider_requests(rider_id: str, status: Optional[str] = None, pagination: PaginationParams = Depends()):
    """Get all ride requests made by a rider"""
    try:
        query = {"rider_id": rider_id}
        if status:
            query["status"] = status
        
        requests = await db.ride_requests.find(query).sort("created_at", -1).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.ride_requests.count_documents(query)
        return {
            "requests": [RideRequest(**req) for req in requests],
            "total": total
        }
    except Exception as e:
        logger.error(f"Failed to get requests for rider {rider_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve requests")


@api_router.put("/ride-requests/{request_id}/accept")
async def accept_ride_request(request_id: str):
    """Accept a ride request (Step C: Driver clicks 'Accept')"""
    try:
        request = await db.ride_requests.find_one({"id": request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if request["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Request already {request['status']}")
        
        # Update request status
        await db.ride_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "accepted", "updated_at": get_utc_now().isoformat()}}
        )
        
        # Decrease available seats
        await db.driver_routes.update_one(
            {"id": request["route_id"]},
            {"$inc": {"available_seats": -1}}
        )
        
        # Create ride match
        match = RideMatch(
            ride_request_id=request_id,
            rider_id=request["rider_id"],
            driver_id=request["driver_id"],
            route_id=request["route_id"]
        )
        await db.ride_matches.insert_one(model_to_dict(match))
        
        # Update carbon credits and eco scores
        carbon_saved = 2.5  # Base value, could be calculated from distance
        await db.users.update_one(
            {"id": request["rider_id"]},
            {"$inc": {"carbonSaved": carbon_saved, "ecoScore": 10, "totalRides": 1}}
        )
        await db.users.update_one(
            {"id": request["driver_id"]},
            {"$inc": {"carbonSaved": carbon_saved, "ecoScore": 15, "totalRides": 1}}
        )
        
        # Send success notification to rider
        await manager.send_personal_message(
            json.dumps({
                "type": "ride_accepted",
                "match": model_to_dict(match)
            }, default=str),
            request["rider_id"]
        )
        
        logger.info(f"Accepted ride request: {request_id}")
        return {"success": True, "match": match}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to accept request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept request")


@api_router.put("/ride-requests/{request_id}/reject")
async def reject_ride_request(request_id: str):
    """Reject a ride request"""
    try:
        request = await db.ride_requests.find_one({"id": request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if request["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Request already {request['status']}")
        
        await db.ride_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "rejected", "updated_at": get_utc_now().isoformat()}}
        )
        
        # Notify rider
        await manager.send_personal_message(
            json.dumps({
                "type": "ride_rejected",
                "request_id": request_id
            }),
            request["rider_id"]
        )
        
        logger.info(f"Rejected ride request: {request_id}")
        return {"success": True, "request_id": request_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject request")


@api_router.put("/ride-requests/{request_id}/cancel")
async def cancel_ride_request(request_id: str, cancelled_by: str = Query(default="rider", pattern="^(rider|driver)$")):
    """Cancel a ride request (by rider or driver)"""
    try:
        request = await db.ride_requests.find_one({"id": request_id})
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if request["status"] not in ["pending", "accepted"]:
            raise HTTPException(status_code=400, detail=f"Cannot cancel {request['status']} request")
        
        await db.ride_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "cancelled", "updated_at": get_utc_now().isoformat(), "cancelled_by": cancelled_by}}
        )
        
        refund_result = None
        
        # If was accepted, restore the seat and handle refund
        if request["status"] == "accepted":
            await db.driver_routes.update_one(
                {"id": request["route_id"]},
                {"$inc": {"available_seats": 1}}
            )
            
            # Get the match to check for payment
            match = await db.ride_matches.find_one({"ride_request_id": request_id})
            if match:
                await db.ride_matches.update_one(
                    {"ride_request_id": request_id},
                    {"$set": {"status": "cancelled"}}
                )
                
                # If driver cancelled and payment was made, trigger refund
                if cancelled_by == "driver" and match.get("payment_intent_id") and stripe_secret:
                    try:
                        refund = stripe.Refund.create(
                            payment_intent=match["payment_intent_id"],
                            reason="requested_by_customer"
                        )
                        await db.ride_matches.update_one(
                            {"id": match["id"]},
                            {"$set": {"payment_status": "refunded"}}
                        )
                        refund_result = {
                            "refund_id": refund.id,
                            "amount": refund.amount,
                            "status": refund.status
                        }
                        logger.info(f"Refunded payment for cancelled ride: {refund.id}")
                    except stripe.error.StripeError as e:
                        logger.error(f"Refund failed: {e}")
        
        # Notify the other party
        notify_user_id = request["driver_id"] if cancelled_by == "rider" else request["rider_id"]
        await manager.send_personal_message(
            json.dumps({
                "type": "ride_cancelled",
                "request_id": request_id,
                "cancelled_by": cancelled_by,
                "refund": refund_result
            }),
            notify_user_id
        )
        
        logger.info(f"Cancelled ride request: {request_id} by {cancelled_by}")
        return {"success": True, "request_id": request_id, "refund": refund_result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel request")


# ===== Ride Match Endpoints =====

@api_router.get("/ride-matches/{match_id}")
async def get_ride_match(match_id: str):
    """Get a specific ride match"""
    try:
        match = await db.ride_matches.find_one({"id": match_id})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        return RideMatch(**match)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get match {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve match")


@api_router.put("/ride-matches/{match_id}/start")
async def start_ride(match_id: str):
    """Mark ride as in progress"""
    try:
        match = await db.ride_matches.find_one({"id": match_id})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        
        if match["status"] != "matched":
            raise HTTPException(status_code=400, detail=f"Cannot start {match['status']} ride")
        
        await db.ride_matches.update_one(
            {"id": match_id},
            {"$set": {"status": "in_progress", "started_at": get_utc_now().isoformat()}}
        )
        
        # Notify rider
        await manager.send_personal_message(
            json.dumps({"type": "ride_started", "match_id": match_id}),
            match["rider_id"]
        )
        
        logger.info(f"Started ride: {match_id}")
        return {"success": True, "status": "in_progress"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start ride {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start ride")


@api_router.put("/ride-matches/{match_id}/complete")
async def complete_ride(match_id: str):
    """Mark ride as completed"""
    try:
        match = await db.ride_matches.find_one({"id": match_id})
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        
        if match["status"] != "in_progress":
            raise HTTPException(status_code=400, detail=f"Cannot complete {match['status']} ride")
        
        await db.ride_matches.update_one(
            {"id": match_id},
            {"$set": {"status": "completed", "completed_at": get_utc_now().isoformat()}}
        )
        
        # Update the ride request status
        await db.ride_requests.update_one(
            {"id": match["ride_request_id"]},
            {"$set": {"status": "completed", "updated_at": get_utc_now().isoformat()}}
        )
        
        # Restore seat availability
        await db.driver_routes.update_one(
            {"id": match["route_id"]},
            {"$inc": {"available_seats": 1}}
        )
        
        # Notify rider
        await manager.send_personal_message(
            json.dumps({"type": "ride_completed", "match_id": match_id}),
            match["rider_id"]
        )
        
        logger.info(f"Completed ride: {match_id}")
        return {"success": True, "status": "completed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete ride {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete ride")


@api_router.get("/ride-matches/user/{user_id}/history")
async def get_ride_history(user_id: str, pagination: PaginationParams = Depends()):
    """Get ride history for a user (as rider or driver)"""
    try:
        query = {"$or": [{"rider_id": user_id}, {"driver_id": user_id}]}
        matches = await db.ride_matches.find(query).sort("created_at", -1).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.ride_matches.count_documents(query)
        return {
            "rides": [RideMatch(**m) for m in matches],
            "total": total
        }
    except Exception as e:
        logger.error(f"Failed to get ride history for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ride history")


# ===== Car Endpoints (Atomic Seat Management) =====

@api_router.post("/cars", response_model=Car)
async def create_car(car_input: CarCreate):
    """Register a car for a driver"""
    try:
        # Verify driver exists
        driver = await db.users.find_one({"id": car_input.driver_id})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Check if driver already has a car
        existing = await db.cars.find_one({"driver_id": car_input.driver_id, "is_active": True})
        if existing:
            raise HTTPException(status_code=400, detail="Driver already has an active car registered")
        
        car_obj = Car(
            **car_input.model_dump(),
            available_seats=car_input.total_seats
        )
        await db.cars.insert_one(model_to_dict(car_obj))
        
        # Mark user as driver
        await db.users.update_one(
            {"id": car_input.driver_id},
            {"$set": {"isDriver": True}}
        )
        
        logger.info(f"Registered car: {car_obj.id} for driver {car_input.driver_id}")
        return car_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create car: {e}")
        raise HTTPException(status_code=500, detail="Failed to register car")


@api_router.get("/cars/driver/{driver_id}", response_model=Car)
async def get_driver_car(driver_id: str):
    """Get car info for a driver"""
    try:
        car = await db.cars.find_one({"driver_id": driver_id, "is_active": True})
        if not car:
            raise HTTPException(status_code=404, detail="No car found for this driver")
        return Car(**car)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get car for driver {driver_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get car info")


@api_router.post("/cars/{car_id}/book-seat")
async def book_seat_atomic(car_id: str, seats_to_book: int = Query(default=1, ge=1, le=4)):
    """Atomically book a seat (prevents overbooking)"""
    try:
        # Atomic update - only succeeds if seats available
        result = await db.cars.find_one_and_update(
            {"id": car_id, "available_seats": {"$gte": seats_to_book}},
            {"$inc": {"available_seats": -seats_to_book}},
            return_document=True
        )
        
        if not result:
            # Check if car exists
            car = await db.cars.find_one({"id": car_id})
            if not car:
                raise HTTPException(status_code=404, detail="Car not found")
            raise HTTPException(status_code=400, detail="Not enough seats available")
        
        logger.info(f"Booked {seats_to_book} seat(s) in car {car_id}")
        return {
            "success": True,
            "seats_booked": seats_to_book,
            "available_seats": result["available_seats"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to book seat: {e}")
        raise HTTPException(status_code=500, detail="Failed to book seat")


@api_router.post("/cars/{car_id}/release-seat")
async def release_seat(car_id: str, seats_to_release: int = Query(default=1, ge=1, le=4)):
    """Release a seat (after ride completion or cancellation)"""
    try:
        car = await db.cars.find_one({"id": car_id})
        if not car:
            raise HTTPException(status_code=404, detail="Car not found")
        
        # Don't exceed total seats
        new_available = min(car["available_seats"] + seats_to_release, car["total_seats"])
        
        await db.cars.update_one(
            {"id": car_id},
            {"$set": {"available_seats": new_available}}
        )
        
        return {"success": True, "available_seats": new_available}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to release seat: {e}")
        raise HTTPException(status_code=500, detail="Failed to release seat")


# ===== Payment Endpoints (Stripe Integration) =====

@api_router.post("/payments/create-intent")
async def create_payment_intent(
    amount: int = Query(..., ge=100, description="Amount in paisa (min 100 = ₹1)"),
    rider_id: str = Query(...),
    driver_id: str = Query(...),
    route_id: str = Query(...)
):
    """Create a Stripe payment intent for ride booking"""
    try:
        if not stripe_secret:
            raise HTTPException(status_code=503, detail="Payment service not configured")
        
        # Calculate fees
        base_fare = amount
        service_fee = int(amount * 0.1)  # 10% service fee
        total_amount = base_fare + service_fee
        
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=total_amount,
            currency="inr",
            metadata={
                "rider_id": rider_id,
                "driver_id": driver_id,
                "route_id": route_id,
                "base_fare": base_fare,
                "service_fee": service_fee
            },
            # Hold the payment, capture later when ride completes
            capture_method="manual"
        )
        
        logger.info(f"Created payment intent: {intent.id}")
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "base_fare": base_fare,
            "service_fee": service_fee,
            "total_amount": total_amount
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create payment intent: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment")


@api_router.post("/payments/{payment_intent_id}/capture")
async def capture_payment(payment_intent_id: str):
    """Capture a held payment (after ride completion)"""
    try:
        if not stripe_secret:
            raise HTTPException(status_code=503, detail="Payment service not configured")
        
        intent = stripe.PaymentIntent.capture(payment_intent_id)
        
        # Update the ride match with payment status
        await db.ride_matches.update_one(
            {"payment_intent_id": payment_intent_id},
            {"$set": {"payment_status": "captured"}}
        )
        
        logger.info(f"Captured payment: {payment_intent_id}")
        return {"success": True, "status": intent.status}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe capture error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to capture payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to capture payment")


@api_router.post("/payments/{payment_intent_id}/refund")
async def refund_payment(payment_intent_id: str, reason: str = Query(default="driver_cancelled")):
    """Refund a payment (if driver cancels)"""
    try:
        if not stripe_secret:
            raise HTTPException(status_code=503, detail="Payment service not configured")
        
        # Process refund
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason="requested_by_customer" if reason == "rider_cancelled" else "fraudulent"
        )
        
        # Update the ride match with refund status
        await db.ride_matches.update_one(
            {"payment_intent_id": payment_intent_id},
            {"$set": {"payment_status": "refunded"}}
        )
        
        logger.info(f"Refunded payment: {payment_intent_id}")
        return {"success": True, "refund_id": refund.id, "status": refund.status}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe refund error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to refund payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to refund payment")


# ===== Ride Summary / Receipt Endpoint =====

@api_router.get("/rides/{ride_id}/summary")
async def get_ride_summary(ride_id: str):
    """Get ride summary/receipt for completed ride"""
    try:
        match = await db.ride_matches.find_one({"id": ride_id})
        if not match:
            raise HTTPException(status_code=404, detail="Ride not found")
        
        # Get route details
        route = await db.driver_routes.find_one({"id": match["route_id"]})
        
        # Get rider and driver info
        rider = await db.users.find_one({"id": match["rider_id"]})
        driver = await db.users.find_one({"id": match["driver_id"]})
        
        # Calculate duration if timestamps available
        duration_minutes = None
        if match.get("started_at") and match.get("completed_at"):
            start = datetime.fromisoformat(match["started_at"]) if isinstance(match["started_at"], str) else match["started_at"]
            end = datetime.fromisoformat(match["completed_at"]) if isinstance(match["completed_at"], str) else match["completed_at"]
            duration_minutes = int((end - start).total_seconds() / 60)
        
        return {
            "ride_id": ride_id,
            "status": match["status"],
            "route": {
                "origin": route["origin"] if route else "N/A",
                "destination": route["destination"] if route else "N/A",
                "distance_km": route.get("distance_km") if route else None
            },
            "rider": {
                "id": rider["id"] if rider else None,
                "name": rider["name"] if rider else "Unknown"
            },
            "driver": {
                "id": driver["id"] if driver else None,
                "name": driver["name"] if driver else "Unknown",
                "rating": driver.get("rating", 5.0) if driver else None
            },
            "billing": {
                "base_fare": match.get("base_fare", match.get("split_cost", 0)),
                "service_fee": match.get("service_fee", 0),
                "total_amount": match.get("total_amount", match.get("split_cost", 0)),
                "payment_status": match.get("payment_status", "pending")
            },
            "eco_impact": {
                "carbon_saved_kg": match.get("carbon_saved", 2.5)
            },
            "timestamps": {
                "created_at": match.get("created_at"),
                "started_at": match.get("started_at"),
                "completed_at": match.get("completed_at"),
                "duration_minutes": duration_minutes
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ride summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ride summary")


# ===== Driver Recommendation Endpoint =====

@api_router.get("/drivers/recommended")
async def get_recommended_drivers(
    user_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=5.0, ge=0.5, le=50)
):
    """Get recommended drivers based on past ratings and proximity"""
    try:
        # Get user's previous positive ratings (4+ stars)
        high_rated_drivers = await db.ratings.find({
            "rider_id": user_id,
            "$expr": {"$gte": [{"$avg": ["$smoothness", "$comfort"]}, 4]}
        }).to_list(100)
        
        preferred_driver_ids = [r["driver_id"] for r in high_rated_drivers]
        
        # Get active drivers with locations
        all_active_drivers = await db.users.find({
            "isDriving": True,
            "current_location": {"$exists": True, "$ne": None}
        }).to_list(100)
        
        # Filter by distance and score
        recommended = []
        for driver in all_active_drivers:
            if driver.get("current_location"):
                loc = driver["current_location"]
                distance = calculate_distance_km(
                    latitude, longitude,
                    loc.get("latitude", 0), loc.get("longitude", 0)
                )
                
                if distance <= radius_km:
                    # Priority score: preferred drivers get boost
                    priority = 100 if driver["id"] in preferred_driver_ids else 0
                    priority += driver.get("rating", 5.0) * 10
                    priority -= distance * 5  # Closer is better
                    
                    recommended.append({
                        "driver_id": driver["id"],
                        "name": driver["name"],
                        "rating": driver.get("rating", 5.0),
                        "distance_km": round(distance, 2),
                        "is_preferred": driver["id"] in preferred_driver_ids,
                        "last_drop_location": driver.get("last_drop_location"),
                        "priority_score": round(priority, 1)
                    })
        
        # Sort by priority
        recommended.sort(key=lambda x: x["priority_score"], reverse=True)
        
        return {"drivers": recommended[:10]}  # Top 10
    except Exception as e:
        logger.error(f"Failed to get recommended drivers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@api_router.put("/users/{user_id}/location")
async def update_user_location(
    user_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    address: Optional[str] = None
):
    """Update user's current location (for live tracking)"""
    try:
        location = {
            "latitude": latitude,
            "longitude": longitude,
            "address": address
        }
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": {"current_location": location}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Broadcast location update for live tracking
        await manager.broadcast(json.dumps({
            "type": "location_update",
            "user_id": user_id,
            "location": location
        }))
        
        return {"success": True, "location": location}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update location: {e}")
        raise HTTPException(status_code=500, detail="Failed to update location")


@api_router.put("/drivers/{driver_id}/last-drop")
async def update_driver_last_drop(
    driver_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    address: Optional[str] = None
):
    """Update driver's last drop location (shown on profile)"""
    try:
        location = {
            "latitude": latitude,
            "longitude": longitude,
            "address": address
        }
        
        result = await db.users.update_one(
            {"id": driver_id},
            {"$set": {"last_drop_location": location}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return {"success": True, "last_drop_location": location}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update last drop: {e}")
        raise HTTPException(status_code=500, detail="Failed to update last drop location")


# ===== Ratings Endpoints =====

@api_router.post("/ratings", response_model=Rating)
async def create_rating(rating_input: RatingCreate):
    """Submit a ride rating"""
    try:
        # Verify ride exists and is completed
        match = await db.ride_matches.find_one({"id": rating_input.ride_id})
        if not match:
            raise HTTPException(status_code=404, detail="Ride not found")
        
        if match["status"] != "completed":
            raise HTTPException(status_code=400, detail="Can only rate completed rides")
        
        # Check if already rated
        existing = await db.ratings.find_one({
            "ride_id": rating_input.ride_id,
            "rider_id": rating_input.rider_id
        })
        if existing:
            raise HTTPException(status_code=400, detail="You have already rated this ride")
        
        rating_obj = Rating(**rating_input.model_dump())
        await db.ratings.insert_one(model_to_dict(rating_obj))
        
        # Update driver's average rating
        driver_ratings = await db.ratings.find({"driver_id": rating_input.driver_id}).to_list(1000)
        if driver_ratings:
            avg_rating = sum((r['smoothness'] + r['comfort']) / 2 for r in driver_ratings) / len(driver_ratings)
            await db.users.update_one(
                {"id": rating_input.driver_id},
                {"$set": {"rating": round(avg_rating, 1)}}
            )
        
        logger.info(f"Created rating for ride: {rating_input.ride_id}")
        return rating_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create rating: {e}")
        raise HTTPException(status_code=500, detail="Failed to create rating")


@api_router.get("/ratings/driver/{driver_id}")
async def get_driver_ratings(driver_id: str, pagination: PaginationParams = Depends()):
    """Get all ratings for a driver"""
    try:
        ratings = await db.ratings.find({"driver_id": driver_id}).sort("created_at", -1).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.ratings.count_documents({"driver_id": driver_id})
        
        # Calculate stats
        if ratings:
            avg_smoothness = sum(r['smoothness'] for r in ratings) / len(ratings)
            avg_comfort = sum(r['comfort'] for r in ratings) / len(ratings)
        else:
            avg_smoothness = avg_comfort = 0
        
        return {
            "ratings": [Rating(**r) for r in ratings],
            "total": total,
            "avg_smoothness": round(avg_smoothness, 1),
            "avg_comfort": round(avg_comfort, 1)
        }
    except Exception as e:
        logger.error(f"Failed to get ratings for driver {driver_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ratings")


# ===== Car Management Endpoints =====

@api_router.post("/cars", response_model=Car)
async def create_car(car_input: CarCreate):
    """Register a new car for a driver"""
    try:
        # Verify driver exists
        driver = await db.users.find_one({"id": car_input.driver_id})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Check if plate number already registered
        existing = await db.cars.find_one({"plate_number": car_input.plate_number})
        if existing:
            raise HTTPException(status_code=400, detail="Car with this plate number already registered")
        
        car_obj = Car(
            **car_input.model_dump(),
            available_seats=car_input.total_seats
        )
        await db.cars.insert_one(model_to_dict(car_obj))
        
        # Mark user as driver
        await db.users.update_one(
            {"id": car_input.driver_id},
            {"$set": {"isDriver": True}}
        )
        
        logger.info(f"Registered car: {car_obj.id} for driver {car_input.driver_id}")
        return car_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create car: {e}")
        raise HTTPException(status_code=500, detail="Failed to register car")


@api_router.get("/cars/driver/{driver_id}")
async def get_driver_cars(driver_id: str):
    """Get all cars registered by a driver"""
    try:
        cars = await db.cars.find({"driver_id": driver_id}).to_list(10)
        return {"cars": [Car(**c) for c in cars]}
    except Exception as e:
        logger.error(f"Failed to get cars for driver {driver_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cars")


@api_router.put("/cars/{car_id}/book-seat")
async def book_car_seat(car_id: str):
    """Atomically book a seat (decrement available_seats)"""
    try:
        # Atomic update: only decrement if seats > 0
        result = await db.cars.find_one_and_update(
            {"id": car_id, "available_seats": {"$gt": 0}, "is_active": True},
            {"$inc": {"available_seats": -1}},
            return_document=True
        )
        
        if not result:
            # Check why it failed
            car = await db.cars.find_one({"id": car_id})
            if not car:
                raise HTTPException(status_code=404, detail="Car not found")
            if car.get("available_seats", 0) <= 0:
                raise HTTPException(status_code=400, detail="No seats available")
            raise HTTPException(status_code=400, detail="Car is not active")
        
        return {"success": True, "available_seats": result["available_seats"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to book seat for car {car_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to book seat")


@api_router.put("/cars/{car_id}/release-seat")
async def release_car_seat(car_id: str):
    """Release a seat (increment available_seats)"""
    try:
        car = await db.cars.find_one({"id": car_id})
        if not car:
            raise HTTPException(status_code=404, detail="Car not found")
        
        if car["available_seats"] >= car["total_seats"]:
            raise HTTPException(status_code=400, detail="All seats already available")
        
        await db.cars.update_one(
            {"id": car_id},
            {"$inc": {"available_seats": 1}}
        )
        
        return {"success": True, "available_seats": car["available_seats"] + 1}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to release seat for car {car_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to release seat")


# ===== Stripe Payment Endpoints =====

@api_router.post("/payments/create-intent")
async def create_payment_intent(
    amount: int = Query(..., ge=100, description="Amount in paise (INR)"),
    ride_request_id: str = Query(...),
    current_user: Dict = Depends(get_current_user)
):
    """Create a Stripe payment intent for ride booking"""
    try:
        if not stripe_secret:
            raise HTTPException(status_code=503, detail="Payment service not configured")
        
        # Verify ride request exists
        ride_request = await db.ride_requests.find_one({"id": ride_request_id})
        if not ride_request:
            raise HTTPException(status_code=404, detail="Ride request not found")
        
        # Calculate fees
        base_fare = amount
        service_fee = int(amount * 0.10)  # 10% service fee
        total_amount = base_fare + service_fee
        
        # Create Stripe payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=total_amount,
            currency="inr",
            metadata={
                "ride_request_id": ride_request_id,
                "rider_id": ride_request["rider_id"],
                "driver_id": ride_request["driver_id"]
            },
            capture_method="automatic"  # Capture immediately
        )
        
        # Update ride request with payment info
        await db.ride_requests.update_one(
            {"id": ride_request_id},
            {"$set": {"payment_intent_id": payment_intent.id}}
        )
        
        logger.info(f"Created payment intent {payment_intent.id} for ride {ride_request_id}")
        return {
            "client_secret": payment_intent.client_secret,
            "payment_intent_id": payment_intent.id,
            "base_fare": base_fare,
            "service_fee": service_fee,
            "total_amount": total_amount
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create payment intent: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment")


@api_router.post("/payments/refund")
async def refund_payment(
    payment_intent_id: str,
    reason: str = "driver_cancelled"
):
    """Process refund when driver cancels ride"""
    try:
        if not stripe_secret:
            raise HTTPException(status_code=503, detail="Payment service not configured")
        
        # Create refund
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason="requested_by_customer"  # Stripe reason code
        )
        
        # Update ride match payment status
        await db.ride_matches.update_one(
            {"payment_intent_id": payment_intent_id},
            {"$set": {"payment_status": "refunded"}}
        )
        
        logger.info(f"Refunded payment {payment_intent_id}: {refund.id}")
        return {
            "success": True,
            "refund_id": refund.id,
            "amount": refund.amount,
            "status": refund.status
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe refund error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to process refund: {e}")
        raise HTTPException(status_code=500, detail="Failed to process refund")


# ===== Driver Recommendation & Search Endpoints =====

@api_router.get("/drivers/recommended")
async def get_recommended_drivers(
    user_id: str,
    pickup_lat: float = Query(..., ge=-90, le=90),
    pickup_lon: float = Query(..., ge=-180, le=180),
    max_distance_km: float = Query(default=5.0, ge=0.5, le=50)
):
    """Get recommended drivers based on previous ratings and proximity"""
    try:
        # Get user's previous high ratings (4+ stars)
        high_rated_drivers = await db.ratings.find({
            "rider_id": user_id,
            "$or": [
                {"smoothness": {"$gte": 4}},
                {"comfort": {"$gte": 4}}
            ]
        }).to_list(100)
        
        preferred_driver_ids = list(set(r["driver_id"] for r in high_rated_drivers))
        
        # Get all active drivers with their locations
        active_drivers = await db.users.find({
            "isDriving": True,
            "current_location": {"$exists": True, "$ne": None}
        }).to_list(100)
        
        recommended = []
        nearby = []
        
        for driver in active_drivers:
            loc = driver.get("current_location", {})
            if not loc:
                continue
            
            driver_lat = loc.get("latitude")
            driver_lon = loc.get("longitude")
            
            if driver_lat is None or driver_lon is None:
                continue
            
            distance = calculate_distance_km(pickup_lat, pickup_lon, driver_lat, driver_lon)
            
            if distance <= max_distance_km:
                driver_info = {
                    "id": driver["id"],
                    "name": driver["name"],
                    "rating": driver.get("rating", 5.0),
                    "distance_km": round(distance, 2),
                    "last_drop_location": driver.get("last_drop_location"),
                    "is_preferred": driver["id"] in preferred_driver_ids
                }
                
                if driver["id"] in preferred_driver_ids:
                    recommended.append(driver_info)
                else:
                    nearby.append(driver_info)
        
        # Sort by distance
        recommended.sort(key=lambda x: x["distance_km"])
        nearby.sort(key=lambda x: x["distance_km"])
        
        return {
            "recommended": recommended,
            "nearby": nearby,
            "total": len(recommended) + len(nearby)
        }
    except Exception as e:
        logger.error(f"Failed to get recommended drivers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@api_router.put("/drivers/{driver_id}/location")
async def update_driver_location(
    driver_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    address: Optional[str] = None
):
    """Update driver's live location"""
    try:
        location = {
            "latitude": latitude,
            "longitude": longitude,
            "address": address
        }
        
        result = await db.users.update_one(
            {"id": driver_id},
            {"$set": {"current_location": location}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Broadcast to connected riders
        await manager.broadcast(json.dumps({
            "type": "driver_location_update",
            "driver_id": driver_id,
            "location": location
        }))
        
        return {"success": True, "location": location}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update driver location: {e}")
        raise HTTPException(status_code=500, detail="Failed to update location")


@api_router.put("/drivers/{driver_id}/last-drop")
async def update_last_drop_location(
    driver_id: str,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    address: Optional[str] = None
):
    """Update driver's last drop location (shown on profile)"""
    try:
        location = {
            "latitude": latitude,
            "longitude": longitude,
            "address": address
        }
        
        result = await db.users.update_one(
            {"id": driver_id},
            {"$set": {"last_drop_location": location}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return {"success": True, "last_drop_location": location}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update last drop location: {e}")
        raise HTTPException(status_code=500, detail="Failed to update location")


# ===== Ride Summary Endpoint =====

@api_router.get("/rides/{match_id}/summary")
async def get_ride_summary(match_id: str):
    """Get detailed ride summary for receipt/billing"""
    try:
        match = await db.ride_matches.find_one({"id": match_id})
        if not match:
            raise HTTPException(status_code=404, detail="Ride not found")
        
        # Get related data
        ride_request = await db.ride_requests.find_one({"id": match["ride_request_id"]})
        route = await db.driver_routes.find_one({"id": match["route_id"]})
        driver = await db.users.find_one({"id": match["driver_id"]})
        rider = await db.users.find_one({"id": match["rider_id"]})
        
        # Calculate duration if completed
        duration_minutes = None
        if match.get("started_at") and match.get("completed_at"):
            start = datetime.fromisoformat(match["started_at"].replace("Z", "+00:00")) if isinstance(match["started_at"], str) else match["started_at"]
            end = datetime.fromisoformat(match["completed_at"].replace("Z", "+00:00")) if isinstance(match["completed_at"], str) else match["completed_at"]
            duration_minutes = int((end - start).total_seconds() / 60)
        
        return {
            "ride_id": match["id"],
            "status": match["status"],
            "route": {
                "origin": route.get("origin", "Unknown") if route else "Unknown",
                "destination": route.get("destination", "Unknown") if route else "Unknown",
                "distance_km": route.get("distance_km") if route else None
            },
            "rider": {
                "id": rider["id"] if rider else match["rider_id"],
                "name": rider.get("name", "Unknown") if rider else "Unknown"
            },
            "driver": {
                "id": driver["id"] if driver else match["driver_id"],
                "name": driver.get("name", "Unknown") if driver else "Unknown",
                "rating": driver.get("rating") if driver else None
            },
            "billing": {
                "base_fare": match.get("base_fare", match.get("split_cost", 0)),
                "service_fee": match.get("service_fee", 0),
                "total_amount": match.get("total_amount", match.get("split_cost", 0)),
                "payment_status": match.get("payment_status", "pending")
            },
            "eco_impact": {
                "carbon_saved_kg": match.get("carbon_saved", 2.5)
            },
            "timestamps": {
                "created_at": match.get("created_at"),
                "started_at": match.get("started_at"),
                "completed_at": match.get("completed_at"),
                "duration_minutes": duration_minutes
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ride summary for {match_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ride summary")


# ===== TomTom Maps Integration Endpoints =====

@api_router.get("/maps/search")
async def tomtom_search(
    query: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    limit: int = Query(default=5, ge=1, le=20)
):
    """Search for locations using TomTom Search API"""
    try:
        if not tomtom_api_key:
            # Fallback to mock data if no API key
            return {
                "results": [
                    {"name": query, "address": "Bangalore, Karnataka", "position": {"lat": 12.9716, "lon": 77.5946}},
                ],
                "warning": "TomTom API key not configured, returning mock data"
            }
        
        import aiohttp
        
        base_url = "https://api.tomtom.com/search/2/search"
        params = {
            "key": tomtom_api_key,
            "query": query,
            "limit": limit,
            "countrySet": "IN",  # India
        }
        
        if lat and lon:
            params["lat"] = lat
            params["lon"] = lon
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/{query}.json", params=params) as response:
                if response.status != 200:
                    raise HTTPException(status_code=response.status, detail="TomTom API error")
                data = await response.json()
        
        results = []
        for r in data.get("results", []):
            results.append({
                "name": r.get("poi", {}).get("name") or r.get("address", {}).get("freeformAddress"),
                "address": r.get("address", {}).get("freeformAddress"),
                "position": r.get("position")
            })
        
        return {"results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TomTom search failed: {e}")
        raise HTTPException(status_code=500, detail="Location search failed")


@api_router.get("/maps/route")
async def tomtom_route(
    start_lat: float = Query(..., ge=-90, le=90),
    start_lon: float = Query(..., ge=-180, le=180),
    end_lat: float = Query(..., ge=-90, le=90),
    end_lon: float = Query(..., ge=-180, le=180)
):
    """Get route between two points using TomTom Routing API"""
    try:
        if not tomtom_api_key:
            # Fallback to estimated data
            distance = calculate_distance_km(start_lat, start_lon, end_lat, end_lon)
            return {
                "distance_km": round(distance, 2),
                "duration_minutes": int(distance * 3),  # Estimate 3 min/km
                "warning": "TomTom API key not configured, returning estimated data"
            }
        
        import aiohttp
        
        base_url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
        params = {
            "key": tomtom_api_key,
            "traffic": "true",
            "travelMode": "car"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status != 200:
                    raise HTTPException(status_code=response.status, detail="TomTom API error")
                data = await response.json()
        
        route = data.get("routes", [{}])[0]
        summary = route.get("summary", {})
        
        return {
            "distance_km": round(summary.get("lengthInMeters", 0) / 1000, 2),
            "duration_minutes": int(summary.get("travelTimeInSeconds", 0) / 60),
            "traffic_delay_minutes": int(summary.get("trafficDelayInSeconds", 0) / 60)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TomTom routing failed: {e}")
        raise HTTPException(status_code=500, detail="Route calculation failed")


# ===== Subscription Endpoints =====

@api_router.get("/subscriptions/tiers")
async def get_subscription_tiers():
    """Get available subscription tiers"""
    tiers = [
        SubscriptionTier(
            id="tier_1",
            name="Quick Hitch",
            price=299,
            rides=10,
            validity="1 month",
            features=["10 rides", "Standard matching", "Basic support"]
        ),
        SubscriptionTier(
            id="tier_2",
            name="Mid-Terms",
            price=799,
            rides=30,
            validity="3 months",
            features=["30 rides", "Priority matching", "Premium support", "Pink Pool access"]
        ),
        SubscriptionTier(
            id="tier_3",
            name="Dean's List",
            price=1499,
            rides=100,
            validity="6 months",
            features=["100 rides", "VIP matching", "24/7 support", "All amenities", "Carbon credits"]
        ),
    ]
    return {"tiers": [t.model_dump() for t in tiers]}


@api_router.post("/subscriptions/subscribe")
async def subscribe_user(user_id: str, tier_id: str):
    """Subscribe a user to a plan"""
    try:
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get tier details
        tier_map = {
            "tier_1": {"name": "Quick Hitch", "rides": 10, "days": 30},
            "tier_2": {"name": "Mid-Terms", "rides": 30, "days": 90},
            "tier_3": {"name": "Dean's List", "rides": 100, "days": 180},
        }
        
        tier = tier_map.get(tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tier not found")
        
        from datetime import timedelta
        expires_at = get_utc_now() + timedelta(days=tier["days"])
        
        subscription = UserSubscription(
            user_id=user_id,
            tier_id=tier_id,
            tier_name=tier["name"],
            rides_remaining=tier["rides"],
            expires_at=expires_at
        )
        await db.subscriptions.insert_one(model_to_dict(subscription))
        
        logger.info(f"User {user_id} subscribed to {tier['name']}")
        return {"success": True, "subscription": subscription}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to subscribe user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")


@api_router.get("/subscriptions/user/{user_id}")
async def get_user_subscription(user_id: str):
    """Get active subscription for a user"""
    try:
        subscription = await db.subscriptions.find_one({
            "user_id": user_id,
            "is_active": True,
            "expires_at": {"$gt": get_utc_now().isoformat()}
        })
        if not subscription:
            return {"active": False, "subscription": None}
        return {"active": True, "subscription": UserSubscription(**subscription)}
    except Exception as e:
        logger.error(f"Failed to get subscription for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subscription")


# ===== College Admin Endpoints =====

@api_router.get("/admin/college/{college_id}/stats")
async def get_college_stats(college_id: str):
    """Get live stats for college admin dashboard"""
    try:
        total_users = await db.users.count_documents({"college.id": college_id})
        active_drivers = await db.users.count_documents({"college.id": college_id, "isDriving": True})
        active_riders = total_users - active_drivers
        
        # Get all users from college for carbon calculation
        college_users = await db.users.find({"college.id": college_id}).to_list(10000)
        user_ids = [u["id"] for u in college_users]
        
        total_rides = await db.ride_matches.count_documents({
            "$or": [
                {"rider_id": {"$in": user_ids}},
                {"driver_id": {"$in": user_ids}}
            ]
        })
        
        carbon_saved = sum(u.get("carbonSaved", 0) for u in college_users)
        pending_verifications = await db.users.count_documents({"college.id": college_id, "verified": False})
        
        return {
            "total_users": total_users,
            "active_drivers": active_drivers,
            "active_riders": active_riders,
            "total_rides": total_rides,
            "pending_verifications": pending_verifications,
            "carbon_saved": round(carbon_saved, 2)
        }
    except Exception as e:
        logger.error(f"Failed to get stats for college {college_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")


@api_router.get("/admin/college/{college_id}/users")
async def get_college_users(college_id: str, pagination: PaginationParams = Depends()):
    """Get all users from a specific college with pagination"""
    try:
        users = await db.users.find({"college.id": college_id}).skip(pagination.skip).limit(pagination.limit).to_list(pagination.limit)
        total = await db.users.count_documents({"college.id": college_id})
        return {
            "users": [User(**user) for user in users],
            "total": total
        }
    except Exception as e:
        logger.error(f"Failed to get users for college {college_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve users")


@api_router.get("/admin/college/{college_id}/leaderboard")
async def get_college_leaderboard(college_id: str, limit: int = Query(default=10, ge=1, le=50)):
    """Get eco-score leaderboard for a college"""
    try:
        users = await db.users.find({"college.id": college_id}).sort("ecoScore", -1).limit(limit).to_list(limit)
        return {
            "leaderboard": [
                {
                    "rank": i + 1,
                    "name": u["name"],
                    "ecoScore": u.get("ecoScore", 0),
                    "carbonSaved": u.get("carbonSaved", 0),
                    "totalRides": u.get("totalRides", 0)
                }
                for i, u in enumerate(users)
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get leaderboard for college {college_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve leaderboard")


# ===== WebSocket Endpoint =====

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif message.get("type") == "location_update":
                    # Broadcast driver location to their riders
                    await manager.broadcast(json.dumps({
                        "type": "driver_location",
                        "driver_id": user_id,
                        "location": message.get("location")
                    }))
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {user_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"WebSocket disconnected: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        manager.disconnect(user_id)


# ===== Health Check =====

@api_router.get("/")
async def root():
    return {
        "message": "UniGo Campus Pool API",
        "version": "2.0.0",
        "status": "active"
    }


@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# Include the router in the main app
app.include_router(api_router)

# CORS configuration - restrict in production
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
