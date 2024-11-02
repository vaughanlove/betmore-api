from openai import OpenAI
from pydantic import BaseModel
from typing import Union
from fastapi import FastAPI
import os
import dotenv
dotenv.load_dotenv()

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """
You are an AI designed to verify and resolve bets based on factual information. Your task is to:

1. Interpret the Bet Statement: Read and understand the user's betting statement to determine what needs verification.
2. Retrieve Information: Access reliable, up-to-date sources to gather information necessary for verifying the statement. You must cite the link where the specific information is accessed.
3. Analyze and Reason: Use the retrieved information to determine if the statement is true or false. Analyze the context carefully and consider any relevant nuances.
4. Provide a Conclusion: Based on your analysis, conclude whether the statement resolves to 'true' or 'false.'
5. Offer a Justification: Explain your reasoning in a clear and concise manner, detailing how the information supports the conclusion.
6. Return the answer in the following format -> {"fact_to_verify": <BET_STATEMENT>, "source": <SOURCE_LINK>, "result": <STATEMENT_OUTCOME>, "explanation": <JUSTIFICATION>}

Prioritize accuracy and clarity to ensure that the resolution is based on verifiable, objective data.
"""

class BetResolvedContext(BaseModel):
    statement: str
    source: list[str]
    result: bool
    justification: str

def restructure_output(raw_json_str: str) ->BetResolvedContext:
    client = OpenAI(api_key=OPENAI_API_KEY)
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": "You are an expert at structured data extraction. You will be given unstructured or semi-structured JSON and should convert it into the given structure."},
            {"role": "user", "content": raw_json_str}
        ],
        response_format=BetResolvedContext,
    )
    return completion


async def perplexity_resolver(bet_statment: str) -> BetResolvedContext:
    client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": bet_statment,
        },
    ]

    # chat completion without streaming
    response = client.chat.completions.create(
        model="llama-3.1-70b-instruct",
        messages=messages,
    )
    response_id = response.id
    resolved_context = restructure_output(response.choices[0].message.content)
    return resolved_context.choices[0].message.parsed

app = FastAPI()

class BetRequest(BaseModel):
    bet_statement: str

@app.get("/check-market-result")
async def check_market_result(bet_request: BetRequest) -> BetResolvedContext:
    return await perplexity_resolver(bet_request.bet_statement)
