from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os
from typing import List, Optional
from supabase import create_client
import dotenv
import json
import re
dotenv.load_dotenv()

app = FastAPI()
client = OpenAI()

""" WAGER RESOLUTION -- VERIFICATION"""
class FactCheckRequest(BaseModel):
    query: str

class FactCheckResponse(BaseModel):
    fact_to_verify: str
    source_to_verify: Optional[str]
    boolean_result: bool
    explanation: Optional[str]

def extract_fact_from_query(query: str) -> str:
    """Extract the main fact from the user query."""
    cleaned_query = re.sub(r'^(i bet that|is it true that|did you know that)\s+', '', query.lower())
    return cleaned_query

async def verify_claim(fact: str) -> tuple[bool, Optional[str]]:
    """Verify a fact using OpenAI's API."""
    if os.getenv("MOCK_verify_claim") == "true":
        return True, "example.com", "Mock explanation"

    try:
        # Define the function that the model can call
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_claim_and_provide_source",
                    "description": "Verify if a given fact is true or false and provide a source",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "is_true": {
                                "type": "boolean",
                                "description": "Whether the fact is true or false"
                            },
                            "source_url": {
                                "type": "string",
                                "description": "URL of the source that verifies this fact"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Brief explanation of why the fact is true or false"
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
                    "content": "You are a fact-checking assistant. Verify the given fact and provide a source if possible. Always respond using the verify_claim_and_provide_source function."
                },
                {
                    "role": "user",
                    "content": f"Please verify this fact: {fact}"
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
        raise HTTPException(status_code=500, detail=f"Error verifying fact: {str(e)}")

@app.post("/verify-fact", response_model=FactCheckResponse)
async def verify_claim_endpoint(request: FactCheckRequest):
    """
    Endpoint to verify facts from user queries.

    Example query: "I bet that the New York Times started publishing in 1800"
    """
    try:
        fact = extract_fact_from_query(request.query)
        is_true, source, explanation = await verify_claim(fact)

        return FactCheckResponse(
            fact_to_verify=fact,
            source_to_verify=source,
            boolean_result=is_true,
            explanation=explanation
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


""" WAGER RESOLUTION -- CALCULATION + DISBURSEMENT """
class WagerWinner(BaseModel):
    winner_wallet_address: str
    winning_amount: float

class ResolveWagerResponse(BaseModel):
    winners: List[WagerWinner]

@app.post("/resolve-wager", response_model=ResolveWagerResponse)
async def resolve_wager(wager_id: str):
    """ For a single wager, resolve the wager by calculating the winners and disbursing the winnings """
    winners = await calculate_winners(wager_id)
    await disburse_winnings(wager_id, winners)
    return ResolveWagerResponse(winners=winners)

# Create an endpoint to calculate the winners
async def calculate_winners(wager_id: str) -> List[WagerWinner]:
    """ For a single wager, call the verify_claim endpoint and return the list of {winners + amount won} """
    # query the wager from Supabase wagers table, using our .env API key
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

    wager = supabase.table("wagers").select("*").eq("id", wager_id).execute().data[0]

    # call the above verify_claim endpoint on the Wager Fact
    fact_to_verify = wager["claim_to_verify"]
    is_true, source, explanation = await verify_claim(fact_to_verify)

    # winners are the people whose bets match `is_true`
    bets = supabase.table("bets").select("*").eq("wager_id", wager_id).execute().data
    winners = supabase.table("bets").select("*").eq("wager_id", wager_id).eq("side", is_true).execute().data

    # find the list of winners, assign them their winnings equally from the Wager pool
    total_pool = sum([bet["amount"] for bet in bets])
    win_amount = total_pool / len(winners)
    winners = [WagerWinner(winner_wallet_address=winner["wallet_address"], winning_amount=win_amount) for winner in winners]

    # return the list of {winners + amount won}
    return winners


async def disburse_winnings(wager_id: str, winners: List[WagerWinner]):
    """ For a single wager, disburse the winnings to the winners """
    # for each winner, send their winnings from our Crossmint wallet to their Crossmint wallet

    # mark wager as resolved in Supabase wagers table (todo: transaction)

    return



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
