from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
import logging
import os
from datetime import datetime
from consumer_agent.agent import ConsumerAgent
from bank_agents.bank1_agent import Bank1Agent
from bank_agents.bank2_agent import Bank2Agent
from bank_agents.bank3_agent import Bank3Agent
from shared.config import OllamaConfig
from shared.utils import create_signed_intent

logging.basicConfig(
    filename='log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WFAP Credit Negotiation System", description="AI-powered loan evaluation system")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

class LoanRequest(BaseModel):
    amount: float
    duration: int
    purpose: str
    expected_income: float = 0.0

class LoanResponse(BaseModel):
    selected_bank: str
    total_score: float
    carbon_adjusted_rate: float
    amount_approved: float
    interest_rate: float
    repayment_period: int
    score_breakdown: dict
    reasoning: str
    all_offers_comparison: list

@app.on_event("startup")
async def startup_event():
    global consumer, banks
    selected_model = OllamaConfig.DEFAULT_MODEL

    consumer = ConsumerAgent(model_name=selected_model)
    bank1 = Bank1Agent(model_name=selected_model)
    bank2 = Bank2Agent(model_name=selected_model)
    bank3 = Bank3Agent(model_name=selected_model)

    banks = {
        "Bank 1 (Green Focus)": bank1,
        "Bank 2 (Traditional)": bank2,
        "Bank 3 (Tech Innovation)": bank3
    }

    logger.info("FastAPI service initialized with agents")

OFFERS_FILE = "offers.json"

def save_offers_to_file(all_offers, request_data):
    """Save all offers (including rejected) to a JSON file"""
    try:
        data = {
            "timestamp": datetime.now().isoformat(),
            "request": request_data.dict(),
            "offers": all_offers
        }

        if os.path.exists(OFFERS_FILE):
            with open(OFFERS_FILE, 'r') as f:
                existing_data = json.load(f)
        else:
            existing_data = {"loan_requests": []}

        existing_data["loan_requests"].append(data)

        with open(OFFERS_FILE, 'w') as f:
            json.dump(existing_data, f, indent=2)

    except Exception as e:
        logger.error(f"Error saving offers to file: {e}")

@app.options("/process_loan")
async def options_process_loan():
    return {"message": "OK"}

@app.post("/process_loan", response_model=LoanResponse)
async def process_loan(request: LoanRequest):
    try:
        intent_data = create_signed_intent("company_x", request.amount, request.duration, request.purpose)

        all_offers = []
        valid_offers = []

        for bank_name, bank in banks.items():
            try:
                result = await bank.evaluate_loan_request(intent_data)

                if isinstance(result, dict) and 'output' in result:
                    try:
                        offer_data = json.loads(result['output'])
                        all_offers.append({
                            "bank_name": bank_name,
                            "bank_id": offer_data.get('bank_id'),
                            "offer": offer_data
                        })
                        if offer_data.get('amount_approved', 0) > 0:
                            valid_offers.append(offer_data)
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error from {bank_name}: {e}")

        save_offers_to_file(all_offers, request)

        if not valid_offers:
            raise HTTPException(status_code=400, detail="No valid offers received from any bank")

        evaluation_result = await consumer.evaluate_offers(valid_offers)

        if 'error' in evaluation_result:
            raise HTTPException(status_code=500, detail=evaluation_result['error'])

        selected = evaluation_result['selected_offer']

        return LoanResponse(
            selected_bank=selected['bank_id'],
            total_score=round(evaluation_result['total_score'], 3),
            carbon_adjusted_rate=round(selected['carbon_adjusted_rate'], 4),
            amount_approved=selected['amount_approved'],
            interest_rate=round(selected['interest_rate'], 4),
            repayment_period=selected['repayment_period'],
            score_breakdown=evaluation_result['score_breakdown'],
            reasoning=evaluation_result['reasoning'],
            all_offers_comparison=evaluation_result['all_offers_scores']
        )

    except Exception as e:
        logger.error(f"Error processing loan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/offers")
async def get_offers():
    """Get all stored loan offers"""
    try:
        if not os.path.exists(OFFERS_FILE):
            return {"loan_requests": []}

        with open(OFFERS_FILE, 'r') as f:
            data = json.load(f)

        return data
    except Exception as e:
        logger.error(f"Error reading offers file: {e}")
        raise HTTPException(status_code=500, detail="Error reading offers data")

@app.post("/negotiate_offer")
async def negotiate_offer(request: dict):
    try:
        bank_id = request.get("bank_id")
        current_offer = request.get("current_offer")
        target_rate = request.get("target_rate")

        if not bank_id or not current_offer or target_rate is None:
            raise HTTPException(status_code=400, detail="Missing required fields: bank_id, current_offer, target_rate")

        negotiate_tool = None
        for tool in consumer.mcp_tools.get_tools():
            if getattr(tool, "name", "") == "negotiate_with_bank":
                negotiate_tool = tool
                break

        if not negotiate_tool:
            raise HTTPException(status_code=500, detail="Negotiation tool not available")

        result = await negotiate_tool.ainvoke({
            "bank_id": bank_id,
            "current_offer": current_offer,
            "target_rate": target_rate
        })

        try:
            negotiation_result = json.loads(result)
            return negotiation_result
        except:
            return {"error": "Failed to parse negotiation result", "raw_result": result}

    except Exception as e:
        logger.error(f"Error negotiating offer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "WFAP Credit Negotiation System"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
