from main import calculate_winners, disburse_winnings, resolve_market, create_market, place_bet, CreateMarketRequest, PlaceBetRequest
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

BETS = [
    {"wallet_address": "0x1234567890123456789012345678901234567890", "amount": 1000000, "side": False},
    {"wallet_address": "0x1234567890123456789012345678901234567891", "amount": 1000000, "side": True},
    {"wallet_address": "0x1234567890123456789012345678901234567892", "amount": 1000000, "side": False},
]

async def test():
    create_market_result = await create_market(CreateMarketRequest(
        claim_to_verify="The moon is made of green cheese",
        creator_wallet_address="0x1234567890123456789012345678901234560000"
    ))
    print("create_market_result", create_market_result)
    print()
    market_id = create_market_result.market_id

    for bet in BETS:
        await place_bet(PlaceBetRequest(
            market_id=market_id,
            wallet_address=bet["wallet_address"],
            amount=bet["amount"],
            side=bet["side"]
        ))

    # market_id = "9740f271-b328-4ba2-8a2f-7b16fddaedea"

    resolve_market_result = await resolve_market(market_id)
    print("resolve_market_result", resolve_market_result)

    winners, source, explanation = await calculate_winners(market_id)
    print("CALCULATE_WINNERS", winners)

    disbursement_success = await disburse_winnings(market_id, winners)
    print(disbursement_success)

# Create an util using the Anon.com client to verify that User A is followed by User B on Twitter
ANON_API_KEY = os.getenv("ANON_API_KEY")




if __name__ == "__main__":
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
    # print all supabase tables
    print(supabase.table("markets").select("*").execute().data)

    import asyncio
    asyncio.run(test())


# if __name__ == "__main__":
#     import requests

#     url = "https://svc.sandbox.anon.com/actions/linkedin/getProfile"

#     ANON_API_KEY = "anon_eIneN8pqYtIllHWb64WAOlpzGgoxNKEXGENzmzu2lMmUV3vAKs1PuqV7AIkk9qr/ep1s1MqZKo41RXhK"
#     headers = {"Authorization": f"Bearer {ANON_API_KEY}"}

#     response = requests.request("GET", url, headers=headers)

#     print(response.text)