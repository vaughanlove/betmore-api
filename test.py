from main import calculate_winners, disburse_winnings, resolve_market
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

async def test():
    await resolve_market("1")

    winners = await calculate_winners("1")
    print(winners)

    disbursement_success = await disburse_winnings("1", winners)
    print(disbursement_success)

if __name__ == "__main__":
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
    # print all supabase tables
    print(supabase.table("markets").select("*").execute().data)

    import asyncio
    asyncio.run(test())
