from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os
from typing import List, Optional
from supabase import create_client
import dotenv
import json
import re
from datetime import datetime
from constants import TOKEN_ADDRESS
dotenv.load_dotenv()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

client = OpenAI()
# Create Supabase client singleton
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
MARKET_WALLET_ADDRESS = "mock wallet address"  # TODO: add our crossmint

""" MARKET RESOLUTION -- VERIFICATION"""

class ClaimCheckRequest(BaseModel):
    query: str

class ClaimCheckResponse(BaseModel):
    claim_to_verify: str
    source_to_verify: Optional[str]
    boolean_result: bool
    explanation: Optional[str]

def extract_claim_from_query(query: str) -> str:
    """Extract the main claim from the user query."""
    cleaned_query = re.sub(r'^(i bet that|is it true that|did you know that)\s+', '', query.lower())
    return cleaned_query

async def verify_claim(claim: str) -> tuple[bool, Optional[str]]:
    """Verify a claim using OpenAI's API."""
    if os.getenv("MOCK_VERIFY_CLAIM") == "true":
        return True, "example.com", "Mock explanation"

    try:
        # Define the function that the model can call
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_claim_and_provide_source",
                    "description": "Verify if a given claim is true or false and provide a source",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "is_true": {
                                "type": "boolean",
                                "description": "Whether the claim is true or false"
                            },
                            "source_url": {
                                "type": "string",
                                "description": "URL of the source that verifies this claim"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Brief explanation of why the claim is true or false"
                            }
                        },
                        "required": ["is_true", "explanation"]
                    }
                }
            }
        ]

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are a claim-checking assistant. Verify the given claim and provide a source if possible. Always respond using the verify_claim_and_provide_source function."
                },
                {
                    "role": "user",
                    "content": f"Please verify this claim: {claim}"
                }
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "verify_claim_and_provide_source"}}
        )

        # Get the tool call from the response
        tool_call = response.choices[0].message.tool_calls[0]
        result = json.loads(tool_call.function.arguments)

        return result.get('is_true', False), result.get('source_url'), result.get('explanation')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying claim: {str(e)}")


async def verify_claim_wrapper(claim: str) -> tuple[bool, Optional[str], Optional[str]]:
    # is_true, source, explanation = await verify_claim(claim)

    from bet_script import perplexity_resolver
    response = await perplexity_resolver(claim)
    is_true, source, explanation = response.result, response.source, response.justification
    print(f"\nResolved the claim: `{claim}` to be `{is_true}` with source `{source}` and explanation `{explanation}`\n")
    return is_true, source, explanation


@app.post("/verify-claim", response_model=ClaimCheckResponse)
async def verify_claim_endpoint(request: ClaimCheckRequest):
    """
    Endpoint to verify claims from user queries.

    Example query: "I bet that the New York Times started publishing in 1800"
    """
    try:
        claim = extract_claim_from_query(request.query)
        is_true, source, explanation = await verify_claim_wrapper(claim)

        return ClaimCheckResponse(
            claim_to_verify=claim,
            source_to_verify=source,
            boolean_result=is_true,
            explanation=explanation
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


""" MARKET CREATION """
class CreateMarketRequest(BaseModel):
    claim_to_verify: str
    creator_wallet_address: str

class CreateMarketResponse(BaseModel):
    market_id: str
    claim_to_verify: str
    created_at: datetime

@app.post("/create-market", response_model=CreateMarketResponse)
async def create_market(request: CreateMarketRequest):
    """Create a new market"""
    try:
        # Create market in database
        result = supabase.table("markets").insert({
            "claim_to_verify": request.claim_to_verify,
            "creator_wallet_address": request.creator_wallet_address,
            "created_at": datetime.now().isoformat(),
            "resolved_at": None,
            "disbursed_at": None,
            "result_boolean": None,
            "result_source": None,
            "result_explanation": None
        }).execute()

        created_market = result.data[0]
        print("inside create_market, created_market", created_market)

        # Also place the first bet (TRUE)
        await place_bet(PlaceBetRequest(
            market_id=created_market["id"],
            wallet_address=request.creator_wallet_address,
            token=TOKEN_ADDRESS,
            amount=1000000,
            side=True
        ))

        return CreateMarketResponse(
            market_id=created_market["id"],
            claim_to_verify=created_market["claim_to_verify"],
            created_at=datetime.fromisoformat(created_market["created_at"])
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

""" BETTING """
class PlaceBetRequest(BaseModel):
    market_id: str
    wallet_address: str
    amount: float
    side: bool  # True for "yes", False for "no"

class PlaceBetResponse(BaseModel):
    bet_id: str
    market_id: str
    wallet_address: str
    amount: float
    side: bool
    created_at: datetime

@app.post("/place-bet", response_model=PlaceBetResponse)
async def place_bet(request: PlaceBetRequest):
    """Place a bet on a market"""
    try:
        # Get market details
        market = supabase.table("markets").select("*").eq("id", request.market_id).execute()
        if not market.data:
            raise HTTPException(status_code=404, detail="Market not found")

        market = market.data[0]

        # Create bet in database
        result = supabase.table("bets").insert({
            "market_id": request.market_id,
            "wallet_address": request.wallet_address,
            "amount": request.amount,
            "side": request.side,
            "created_at": datetime.now().isoformat()
        }).execute()

        created_bet = result.data[0]

        # Use datetime.fromisoformat() with string cleanup
        timestamp_str = created_bet["created_at"].replace('Z', '+00:00')
        created_at = datetime.fromisoformat(timestamp_str)

        return PlaceBetResponse(
            bet_id=created_bet["id"],
            market_id=created_bet["market_id"],
            wallet_address=created_bet["wallet_address"],
            amount=created_bet["amount"],
            side=created_bet["side"],
            created_at=created_at
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


""" MARKET RESOLUTION -- CALCULATION + DISBURSEMENT """

class MarketWinner(BaseModel):
    winner_wallet_address: str
    winning_amount: float

class ResolveMarketRequest(BaseModel):
    market_id: str

class ResolveMarketResponse(BaseModel):
    winners: List[MarketWinner]
    source: str
    explanation: str

@app.post("/resolve-market", response_model=ResolveMarketResponse)
async def resolve_market_endpoint(request: ResolveMarketRequest):
    """ For a single market, resolve the market by calculating the winners and disbursing the winnings """
    # First resolve the market
    await resolve_market(request.market_id)
    # Then calculate and disburse winnings
    winners, source, explanation = await calculate_winners(request.market_id)
    await disburse_winnings(request.market_id, winners)
    return ResolveMarketResponse(winners=winners, source=source, explanation=explanation)

# Create a function to resolve a market
async def resolve_market(market_id: str) -> bool:
    market = supabase.table("markets").select("*").eq("id", market_id).execute().data[0]

    # If already resolved, log + return
    if market["resolved_at"]:
        print(f"Market {market_id} already resolved")
        return False

    # call the above verify_claim endpoint on the Market Claim
    claim_to_verify = market["claim_to_verify"]
    is_true, source, explanation = await verify_claim_wrapper(claim_to_verify)

    # Update the market with the result
    supabase.table("markets").update({
        "result_boolean": is_true,
        "result_source": source,
        "result_explanation": explanation,
        "resolved_at": datetime.now().isoformat()
    }).eq("id", market_id).execute()


# Create a function to calculate the winners
async def calculate_winners(market_id: str) -> tuple[List[MarketWinner], str, str]:
    """ For a single market, call the verify_claim endpoint and return the list of {winners + amount won} """
    market = supabase.table("markets").select("*").eq("id", market_id).execute().data[0]
    is_true = market["result_boolean"]
    source = market["result_source"]
    explanation = market["result_explanation"]

    # winners are the people whose bets match `is_true`
    bets = supabase.table("bets").select("*").eq("market_id", market_id).execute().data
    winners = supabase.table("bets").select("*").eq("market_id", market_id).eq("side", is_true).execute().data

    # find the list of winners, assign them their winnings equally from the Market pool
    total_pool = sum([bet["amount"] for bet in bets])
    if len(winners) == 0:
        win_amount = total_pool / len(bets)
    else:
        win_amount = total_pool / len(winners)
    winners = [MarketWinner(winner_wallet_address=winner["wallet_address"], winning_amount=win_amount) for winner in winners]

    # return the list of {winners + amount won}
    return winners, source, explanation


async def send_crossmint_txn(from_address: str, to_address: str, amount: float):
    """ TODO (vaughan) """
    pass


async def disburse_winnings(market_id: str, winners: List[MarketWinner]) -> bool:
    """ For a single market, disburse the winnings to the winners """
    market = supabase.table("markets").select("*").eq("id", market_id).execute().data[0]

    # if already resolved, log + return
    if market["disbursed_at"]:
        print(f"Market {market_id} already disbursed")
        return False

    # for each winner, send their winnings from our Crossmint wallet to their Crossmint wallet
    for winner in winners:
        await send_crossmint_txn(MARKET_WALLET_ADDRESS, winner.winner_wallet_address, winner.winning_amount)

    # mark market as resolved in Supabase markets table (todo: transaction)
    supabase.table("markets").update({
        "disbursed_at": datetime.now().isoformat()
    }).eq("id", market_id).execute()
    return True


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
