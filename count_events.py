import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings
from app.db.models import Event

async def main():
    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    async with SessionLocal() as session:
        # Group by type and count
        stmt = select(Event.type, func.count(Event.id)).group_by(Event.type)
        result = await session.execute(stmt)
        for row in result:
            print(f"Type: {row[0]}, Count: {row[1]}")
            
        # Print the last 30 events of any type
        print("\nLast 30 events:")
        stmt_all = select(Event).order_by(Event.created_at.desc()).limit(30)
        result_all = await session.execute(stmt_all)
        for e in result_all.scalars().all():
            print(f"ID: {e.id}, Created: {e.created_at}, Type: {e.type}, Payload: {e.payload_json}")

if __name__ == "__main__":
    asyncio.run(main())
