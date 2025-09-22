# ...existing imports...
from shared.mcp_tools_base import BaseMCPTools
from langchain.tools import tool
from shared.utils import validate_signature
from shared.models import Intent
from shared.utils import ESGUtils
from shared.config import OllamaConfig
import random
import json
import logging

logger = logging.getLogger(__name__)

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
                mock_data = {"company_id": company_id}
                is_valid = validate_signature(mock_data, signature)
                return json.dumps({
                    "valid": is_valid,
                    "company_id": company_id,
                    "reason": "Signature validated successfully" if is_valid else "Invalid signature or doesn't meet bank standards"
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def assess_risk(intent=None, amount=None, duration=None, purpose=None,
                              json_payload=None, full_intent_json=None, parameters=None, **kwargs) -> str:
            try:
                import re, json as _json

                def extract_balanced_json(s: str):
                    """Return the first balanced {...} substring of s, or None."""
                    if not isinstance(s, str):
                        return None
                    s = s.strip()
                    # strip surrounding matching quotes
                    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                        s = s[1:-1]
                    # unescape common escaped quotes
                    s = s.replace('\\"', '"').replace("\\'", "'")
                    start = s.find('{')
                    if start == -1:
                        return None
                    depth = 0
                    for i in range(start, len(s)):
                        ch = s[i]
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                return s[start:i+1]
                    return None

                def _to_dict(v):
                    if v is None:
                        return None
                    if isinstance(v, dict):
                        return v
                    if isinstance(v, str):
                        # direct json
                        try:
                            return _json.loads(v)
                        except Exception:
                            # try to extract balanced json substring
                            sub = extract_balanced_json(v)
                            if sub:
                                try:
                                    return _json.loads(sub)
                                except Exception:
                                    # try a looser replacement of single quotes with double quotes
                                    try:
                                        candidate = sub.replace("'", '"')
                                        return _json.loads(candidate)
                                    except Exception:
                                        return None
                            return None
                    return None

                # Build intent_obj from various possible inputs
                intent_obj = None

                if intent is not None:
                    intent_obj = _to_dict(intent) or (intent if isinstance(intent, dict) else None)

                if intent_obj is None and json_payload is not None:
                    intent_obj = _to_dict(json_payload)

                if intent_obj is None and full_intent_json is not None:
                    intent_obj = _to_dict(full_intent_json) or (full_intent_json if isinstance(full_intent_json, dict) else None)

                if intent_obj is None and parameters:
                    if isinstance(parameters, dict):
                        if 'intent' in parameters:
                            intent_obj = _to_dict(parameters['intent']) or (parameters['intent'] if isinstance(parameters['intent'], dict) else None)
                        elif 'json' in parameters:
                            intent_obj = _to_dict(parameters['json'])

                # fallback to scalar args and kwargs
                if intent_obj is None:
                    composed = {}
                    if amount is not None:
                        composed['amount'] = amount
                    if purpose is not None:
                        composed['purpose'] = purpose
                    if duration is not None:
                        composed['duration'] = duration
                    for k in ('amount', 'purpose', 'duration', 'company_id', 'request_id'):
                        if k in kwargs and k not in composed:
                            composed[k] = kwargs.get(k)
                    if composed:
                        intent_obj = composed

                # Final check
                if not isinstance(intent_obj, dict):
                    return _json.dumps({
                        "error": "Intent must be a dict or JSON string (or provide amount/purpose/duration).",
                        "received_type": str(type(intent_obj))
                    })

                # Extract fields with safe defaults
                amt = intent_obj.get('amount', 0.0)
                purp = intent_obj.get('purpose', '') or ''
                dur = intent_obj.get('duration', intent_obj.get('repayment_period', None))

                # Defensive type coercion
                try:
                    amt = float(amt)
                except Exception:
                    amt = 0.0
                try:
                    dur = int(dur) if dur is not None else None
                except Exception:
                    dur = None
                purp = str(purp).lower()

                # Simple, stable scoring heuristic (higher = better)
                base_score = 100 - int(amt / 100000)
                base_score = max(0, min(100, base_score))

                # Bank-specific adjustments
                if bank_id == "bank_1":
                    if any(k in purp for k in ['solar', 'renewable', 'sustainable', 'clean energy']):
                        base_score += 12
                elif bank_id == "bank_2":
                    if any(k in purp for k in ['new', 'experimental', 'startup']):
                        base_score -= 15
                    if amt > 300000:
                        base_score -= 8
                elif bank_id == "bank_3":
                    if any(k in purp for k in ['tech', 'ai', 'innovation', 'digital']):
                        base_score += 18

                # Term adjustments
                if dur is not None:
                    if dur <= 12:
                        base_score += 5
                    elif dur >= 60 and bank_id == "bank_2":
                        base_score -= 5

                risk_score = max(0, min(100, int(base_score)))
                thresholds = {"bank_1": 55, "bank_2": 70, "bank_3": 50}
                threshold = thresholds.get(bank_id, 60)
                approval = risk_score >= threshold

                reason = f"risk_score={risk_score} (amount={amt}, purpose='{purp}', duration={dur}, threshold={threshold})"

                return _json.dumps({
                    "risk_score": risk_score,
                    "approval_recommendation": approval,
                    "reason": reason
                })

            except Exception as e:
                return _json.dumps({"error": str(e)})
        
        @tool
        async def generate_esg_summary(purpose: str) -> str:
            """Generate ESG summary with bank-specific emphasis using LLM"""
            try:
                esg_score = ESGUtils.generate_esg_score(purpose)

                # Bank-specific prompts for ESG summary generation
                bank_prompts = {
                    "bank_1": f"""You are an ESG analyst for EcoGreen Financial, a bank focused on environmental sustainability.
                    Generate a concise ESG summary (2-3 sentences) for a loan purpose: "{purpose}".
                    Emphasize environmental impact, sustainability alignment, and green financing aspects.
                    Be positive and highlight potential benefits.

                    Output format: Provide only the summary text, no additional formatting or labels.""",

                    "bank_2": f"""You are an ESG analyst for Standard Bank, a traditional bank with standard ESG practices.
                    Generate a concise ESG summary (2-3 sentences) for a loan purpose: "{purpose}".
                    Focus on compliance, risk assessment, and standard environmental requirements.
                    Be balanced and professional.

                    Output format: Provide only the summary text, no additional formatting or labels.""",

                    "bank_3": f"""You are an ESG analyst for Innovation Bank, a bank focused on technology and innovation.
                    Generate a concise ESG summary (2-3 sentences) for a loan purpose: "{purpose}".
                    Emphasize innovation, technological advancement, and future sustainability potential.
                    Be forward-thinking and highlight innovation aspects.

                    Output format: Provide only the summary text, no additional formatting or labels."""
                }

                prompt = bank_prompts.get(bank_id, f"""Generate a concise ESG summary (2-3 sentences) for the loan purpose: "{purpose}". Focus on environmental, social, and governance aspects.

                Output format: Provide only the summary text, no additional formatting or labels.""")

                # Use LLM to generate the summary
                llm = OllamaConfig.get_chat_model(temperature=0.3)
                response = await llm.ainvoke(prompt)
                summary = response.content.strip()

                return json.dumps({
                    "esg_summary": summary,
                    "esg_score": esg_score,
                    "bank_id": bank_id
                })

            except Exception as e:
                logger.error(f"Error generating ESG summary with LLM: {e}")
                # Fallback to template-based generation
                summary_templates = {
                    "bank_1": [
                        "Excellent ESG alignment with outstanding environmental leadership.",
                        "Strong sustainability profile with significant positive impact expected.",
                        "Good ESG foundation meeting high environmental standards."
                    ],
                    "bank_2": [
                        "Standard ESG compliance meeting basic environmental requirements.",
                        "Moderate ESG assessment requiring standard due diligence.",
                        "Acceptable ESG profile with no significant concerns identified."
                    ],
                    "bank_3": [
                        "Innovation-focused ESG with high potential for future sustainability impact.",
                        "Tech-driven ESG profile combining innovation with environmental considerations.",
                        "Modern ESG approach aligning with contemporary sustainability standards."
                    ]
                }

                templates = summary_templates.get(bank_id, ["Standard ESG assessment completed."])
                summary = f"ESG assessment for {purpose}: {random.choice(templates)}"

                return json.dumps({
                    "esg_summary": summary,
                    "esg_score": esg_score,
                    "bank_id": bank_id
                })

        @tool
        async def negotiate_interest_rate(current_offer: dict, requested_rate: float) -> str:
            """Negotiate interest rate reduction for an approved offer"""
            try:
                current_rate = current_offer.get('interest_rate', 0)
                bank_policy = {
                    "bank_1": {"min_rate": 0.045, "max_reduction": 0.005},
                    "bank_2": {"min_rate": 0.05, "max_reduction": 0.003},
                    "bank_3": {"min_rate": 0.04, "max_reduction": 0.007}
                }

                policy = bank_policy.get(bank_id, {"min_rate": 0.05, "max_reduction": 0.005})

                # Bank may agree to reduce rate if above minimum and within max reduction
                max_allowed_rate = current_rate - policy["max_reduction"]
                new_rate = max(policy["min_rate"], min(requested_rate, max_allowed_rate))

                # Simple negotiation logic: bank agrees if reduction is reasonable
                agreed = new_rate < current_rate and new_rate >= policy["min_rate"]

                if agreed:
                    # Update the offer with new rate
                    updated_offer = current_offer.copy()
                    updated_offer['interest_rate'] = round(new_rate, 4)
                    updated_offer['carbon_adjusted_rate'] = round(new_rate, 4)  # Assuming same for simplicity
                    updated_offer['esg_summary'] += f" Interest rate negotiated down to {new_rate*100:.2f}%."

                    return json.dumps({
                        "agreed": True,
                        "new_rate": new_rate,
                        "updated_offer": updated_offer,
                        "reason": f"Bank agreed to reduce interest rate to {new_rate*100:.2f}%"
                    })
                else:
                    return json.dumps({
                        "agreed": False,
                        "reason": f"Bank cannot reduce rate below {policy['min_rate']*100:.2f}% or more than {policy['max_reduction']*100:.2f}% reduction"
                    })

            except Exception as e:
                return json.dumps({"error": str(e)})

        return [verify_consumer_identity, assess_risk, generate_esg_summary, negotiate_interest_rate]
