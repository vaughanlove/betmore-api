from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from typing import Optional
import json
import re

app = FastAPI()
client = OpenAI()

class FactCheckRequest(BaseModel):
    query: str

class FactCheckResponse(BaseModel):
    fact_to_verify: str
    source_to_verify: Optional[str]
    boolean_result: bool

def extract_fact_from_query(query: str) -> str:
    """Extract the main fact from the user query."""
    cleaned_query = re.sub(r'^(i bet that|is it true that|did you know that)\s+', '', query.lower())
    return cleaned_query

async def verify_fact(fact: str) -> tuple[bool, Optional[str]]:
    """Verify a fact using OpenAI's API."""
    try:
        # Define the function that the model can call
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "verify_fact_and_provide_source",
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
                    "content": "You are a fact-checking assistant. Verify the given fact and provide a source if possible. Always respond using the verify_fact_and_provide_source function."
                },
                {
                    "role": "user",
                    "content": f"Please verify this fact: {fact}"
                }
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "verify_fact_and_provide_source"}}
        )

        # Get the tool call from the response
        tool_call = response.choices[0].message.tool_calls[0]
        result = json.loads(tool_call.function.arguments)

        return result.get('is_true', False), result.get('source_url')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying fact: {str(e)}")

@app.post("/verify-fact", response_model=FactCheckResponse)
async def verify_fact_endpoint(request: FactCheckRequest):
    """
    Endpoint to verify facts from user queries.
    
    Example query: "I bet that the New York Times started publishing in 1800"
    """
    try:
        fact = extract_fact_from_query(request.query)
        is_true, source = await verify_fact(fact)
        
        return FactCheckResponse(
            fact_to_verify=fact,
            source_to_verify=source,
            boolean_result=is_true
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)