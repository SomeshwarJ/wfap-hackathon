from shared.mcp_tools_base import BaseMCPTools
from langchain.tools import tool
from shared.utils import validate_signature
from shared.models import Intent
from shared.utils import ESGUtils
import random
import json

class BankMCPTools(BaseMCPTools):
    def __init__(self, bank_id: str):
        self.bank_id = bank_id
        super().__init__()

    def _create_tools(self):
        """Create LangChain tools for bank agent"""

        bank_id = self.bank_id  # Capture for closure

        @tool
        async def verify_consumer_identity(company_id: str, signature: str) -> str:
            """Verify consumer identity using signature validation"""
            try:
                # Create mock data for signature validation
                mock_data = {"company_id": company_id}
                is_valid = validate_signature(company_id, mock_data)

                # Bank-specific verification standards
                if bank_id == "bank_2":  # Traditional bank - strict
                    established_companies = ["company_x", "established_corp_y", "reliable_business_z"]
                    is_valid = is_valid and company_id in established_companies

                return json.dumps({
                    "valid": is_valid,
                    "company_id": company_id,
                    "reason": "Signature validated successfully" if is_valid else "Invalid signature or doesn't meet bank standards"
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def assess_risk(intent: dict) -> str:
            """Assess credit risk with bank-specific risk appetite"""
            try:
                # Ensure intent is a dict
                print("intent:", intent)
                if isinstance(intent, str):
                    intent = json.loads(intent)
                if not isinstance(intent, dict):
                    return json.dumps({"error": "Intent must be a dict or JSON string representing a dict."})

                # Defensive: check required fields and types
                required_fields = ["amount", "purpose"]
                for field in required_fields:
                    if field not in intent:
                        return json.dumps({"error": f"Missing required field: {field}"})
                amount = intent["amount"]
                purpose = intent["purpose"]

                # Type checks
                if not isinstance(amount, (int, float)):
                    try:
                        amount = float(amount)
                    except Exception:
                        return json.dumps({"error": f"Amount must be a number, got {type(amount)}"})
                if not isinstance(purpose, str):
                    return json.dumps({"error": f"Purpose must be a string, got {type(purpose)}"})

                purpose_lower = purpose.lower()

                # Base risk score calculation
                base_risk = min(100, max(0, 100 - (amount / 100000)))

                # Bank-specific risk adjustments
                if bank_id == "bank_1":  # Green-focused
                    if any(word in purpose_lower for word in ['solar', 'renewable', 'sustainable']):
                        base_risk += 15  # Bonus for green projects

                elif bank_id == "bank_2":  # Traditional - conservative
                    if any(word in purpose_lower for word in ['new', 'experimental', 'startup']):
                        base_risk -= 20  # Penalty for innovation
                    if amount > 300000:
                        base_risk -= 10  # Penalty for large amounts

                elif bank_id == "bank_3":  # Innovative - risk-tolerant
                    if any(word in purpose_lower for word in ['tech', 'ai', 'innovation', 'digital']):
                        base_risk += 25  # Significant bonus for innovation

                risk_score = max(0, min(100, base_risk))

                # Bank-specific approval thresholds
                approval_threshold = {
                    "bank_1": 55,  # Green-focused - moderate risk tolerance
                    "bank_2": 70,  # Traditional - high threshold
                    "bank_3": 45  # Innovative - low threshold
                }

                return json.dumps({
                    "risk_score": risk_score,
                    "approval_recommendation": risk_score >= approval_threshold.get(bank_id, 60),
                    "reason": f"Risk assessment based on amount: {amount}, purpose: {purpose_lower}, bank policy: {bank_id}"
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def generate_esg_summary(purpose: str) -> str:
            """Generate ESG summary with bank-specific emphasis"""
            purpose_lower = purpose.lower()
            esg_score = ESGUtils.generate_esg_score(purpose)

            # Bank-specific summary approaches
            summary_templates = {
                "bank_1": [
                    "EXCELLENT ESG ALIGNMENT! This project demonstrates outstanding environmental leadership.",
                    "STRONG SUSTAINABILITY PROFILE! Significant positive impact expected.",
                    "GOOD ESG FOUNDATION! Meets high environmental standards."
                ],
                "bank_2": [
                    "STANDARD ESG COMPLIANCE. Project meets basic environmental requirements.",
                    "MODERATE ESG ASSESSMENT. Requires standard due diligence.",
                    "ACCEPTABLE ESG PROFILE. No significant concerns identified."
                ],
                "bank_3": [
                    "INNOVATION-FOCUSED ESG! High potential for future sustainability impact.",
                    "TECH-DRIVEN ESG PROFILE! Combines innovation with environmental considerations.",
                    "MODERN ESG APPROACH! Aligns with contemporary sustainability standards."
                ]
            }

            templates = summary_templates.get(bank_id, ["Standard ESG assessment completed."])
            summary = random.choice(templates)

            # Add purpose-specific details
            if 'solar' in purpose_lower:
                summary += " Solar energy investment provides excellent environmental benefits."
            elif 'tech' in purpose_lower:
                summary += " Technology projects offer innovation potential with moderate ESG impact."

            return json.dumps({
                "esg_summary": summary,
                "esg_score": esg_score,
                "bank_id": bank_id
            })

        return [verify_consumer_identity, assess_risk, generate_esg_summary]