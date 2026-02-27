import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'unigo_db')

async def test_connection():
    print(f"Connecting to: {mongo_url}")
    print(f"Database: {db_name}")
    
    try:
        client = AsyncIOMotorClient(mongo_url)
        # Ping the server
        await client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        
        # Get database
        db = client[db_name]
        
        # List collections
        collections = await db.list_collection_names()
        print(f"Collections in {db_name}: {collections if collections else '(none yet)'}")
        
        client.close()
        print("Connection closed.")
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("\nMake sure MongoDB is running. You can:")
        print("1. Start MongoDB locally: mongod")
        print("2. Or update MONGO_URL in .env with your MongoDB Atlas connection string")

if __name__ == "__main__":
    asyncio.run(test_connection())
