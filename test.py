from main import calculate_winners
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    pass

    winners = await calculate_winners("1")
    print(winners)

if __name__ == "__main__":
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
    # print all supabase tables
    print(supabase.table("markets").select("*").execute().data)

    import asyncio
    asyncio.run(test())
