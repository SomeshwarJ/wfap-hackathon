from shared.mcp_tools_base import BaseMCPTools
from langchain.tools import tool
from shared.utils import validate_signature
from shared.utils import ProtocolUtils, LoggingUtils
import json


class ConsumerMCPTools(BaseMCPTools):
    def __init__(self):
        super().__init__()

    def _create_tools(self):
        """Create LangChain tools for consumer agent"""

        @tool
        async def verify_bank_identity(bank_id: str, signature: str) -> str:
            """Verify bank identity using signature validation"""
            try:
                # Create mock data for signature validation
                mock_data = {"bank_id": bank_id, "timestamp": "2024-01-15T00:00:00Z"}
                is_valid = validate_signature(mock_data, signature)

                return json.dumps({
                    "valid": is_valid,
                    "bank_id": bank_id,
                    "reason": "Signature validated successfully" if is_valid else "Invalid signature"
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def validate_offer(offer: dict) -> str:
            """Validate offer against WFAP protocol"""
            try:
                is_valid, reason = ProtocolUtils.validate_offer(offer)
                return json.dumps({
                    "valid": is_valid,
                    "offer_id": offer.get('offer_id'),
                    "bank_id": offer.get('bank_id'),
                    "reason": reason if not is_valid else "Offer is valid"
                })
            except Exception as e:
                return json.dumps({"valid": False, "error": str(e)})

        @tool
        async def log_consumer_trace(action: str, details: str) -> str:
            """Log consumer agent reasoning trace"""
            log_entry = LoggingUtils.create_audit_log("consumer", action, {"details": details})
            signed_log = LoggingUtils.sign_audit_log(log_entry)

            return json.dumps({
                "status": "logged",
                "log_id": signed_log['log_id'],
                "timestamp": signed_log['timestamp']
            })

        @tool
        async def select_best_offer(offers: list, decision_criteria: dict) -> str:
            import re
            try:
                if not offers:
                    return json.dumps({"error": "No offers provided for evaluation"})

                # Default criteria weights if not provided
                criteria = {
                    'carbon_adjusted_rate_weight': 0.35,
                    'amount_approved_weight': 0.30,
                    'esg_score_weight': 0.20,
                    'interest_rate_weight': 0.10,
                    'repayment_period_weight': 0.05  # new: prefer longer repayment (flexibility)
                }
                criteria.update(decision_criteria or {})

                # Extract repayment weight separately handled in normalization below
                weight_keys = [k for k in criteria.keys() if k.endswith('_weight')]
                total_weight = sum([criteria[k] for k in weight_keys]) if weight_keys else 0
                if total_weight == 0:
                    return json.dumps({"error": "All criteria weights cannot be zero"})

                normalized_criteria = {k: (criteria[k] / total_weight) for k in weight_keys}

                parsed_offers = []
                parse_errors = []

                # Helper to try parse any JSON embedded in text
                def try_parse_json_like(value):
                    if isinstance(value, dict):
                        return value
                    if not isinstance(value, str):
                        return None
                    try:
                        return json.loads(value)
                    except Exception:
                        m = re.search(r'\{.*\}', value, flags=re.DOTALL)
                        if m:
                            try:
                                return json.loads(m.group(0))
                            except Exception:
                                return None
                        return None

                for idx, raw in enumerate(offers):
                    if raw is None:
                        parse_errors.append({"index": idx, "reason": "offer is None"})
                        continue
                    offer_obj = try_parse_json_like(raw)
                    if offer_obj is None:
                        # If it's already a pydict-like object but not JSON string, accept it
                        if isinstance(raw, dict):
                            offer_obj = raw
                        else:
                            parse_errors.append({"index": idx, "raw": raw, "reason": "unable to parse JSON"})
                            continue

                    # Safely extract numeric fields with defaults
                    try:
                        offer_id = offer_obj.get('offer_id') if isinstance(offer_obj, dict) else None
                        bank_id = offer_obj.get('bank_id') if isinstance(offer_obj, dict) else None

                        carbon_adj = float(offer_obj.get('carbon_adjusted_rate', offer_obj.get('carbon_rate', 1.0)))
                        amount = float(offer_obj.get('amount_approved', offer_obj.get('amount', 0.0)))
                        interest = float(offer_obj.get('interest_rate', offer_obj.get('rate', 100.0)))
                        esg_summary = str(offer_obj.get('esg_summary', offer_obj.get('esg', '') or ''))
                        repayment_period = int(offer_obj.get('repayment_period', offer_obj.get('duration', 0)))
                    except Exception as e:
                        parse_errors.append({"index": idx, "reason": f"field extraction error: {e}"})
                        continue

                    # Apply safe bounds/defaults: missing rates -> penalize by giving large rate
                    if carbon_adj is None or carbon_adj <= 0:
                        carbon_adj = 1.0  # penalize (higher carbon-adjusted rate)
                    if interest is None or interest <= 0:
                        interest = 100.0  # large interest => penalize
                    if amount is None or amount < 0:
                        amount = 0.0
                    if repayment_period is None or repayment_period < 0:
                        repayment_period = 0

                    parsed_offers.append({
                        'raw': offer_obj,
                        'offer_id': offer_id,
                        'bank_id': bank_id,
                        'carbon_adjusted_rate': carbon_adj,
                        'amount_approved': amount,
                        'interest_rate': interest,
                        'esg_summary': esg_summary,
                        'repayment_period': repayment_period
                    })

                if not parsed_offers:
                    return json.dumps({"error": "No valid offers parsed", "parse_errors": parse_errors})

                # Pre-compute min/max for interest to score relative to min interest
                interest_values = [po['interest_rate'] for po in parsed_offers]
                min_interest = min(interest_values) if interest_values else 0.0
                max_interest = max(interest_values) if interest_values else min_interest
                interest_range = (max_interest - min_interest) if (max_interest - min_interest) > 0 else 1e-6

                # Compute base scores for each parsed offer
                scored_offers = []
                for po in parsed_offers:
                    # Carbon: lower better -> reciprocal
                    carbon_score = 1.0 / (po['carbon_adjusted_rate'] + 0.001)
                    # Amount: higher better
                    amount_score = po['amount_approved']
                    # ESG: extracted 0-1
                    esg_score = self._extract_esg_score(po['esg_summary'] or '')
                    # Interest: score is 1.0 for min interest, 0.0 for max interest (linear)
                    interest_norm = (max_interest - po['interest_rate']) / interest_range
                    interest_norm = max(0.0, min(1.0, interest_norm))
                    # Repayment: prefer longer repayment (flexibility) -> higher is better
                    repayment_score = float(po['repayment_period'] or 0)

                    scored_offers.append({
                        'offer': po,
                        'raw_scores': {
                            'carbon_adjusted_rate': carbon_score,
                            'amount_approved': amount_score,
                            'esg_score': esg_score,
                            'interest_rate': interest_norm,
                            'repayment_period': repayment_score
                        }
                    })

                # Determine max values across scored_offers (avoid using original raw offers)
                max_values = {
                    'carbon_adjusted_rate': max([s['raw_scores']['carbon_adjusted_rate'] for s in scored_offers]) or 1.0,
                    'amount_approved': max([s['raw_scores']['amount_approved'] for s in scored_offers]) or 1.0,
                    'esg_score': 1.0,  # esg already normalized 0-1
                    'interest_rate': max([s['raw_scores']['interest_rate'] for s in scored_offers]) or 1.0,
                    'repayment_period': max([s['raw_scores']['repayment_period'] for s in scored_offers]) or 1.0
                }

                # Compute final normalized & weighted scores
                for s in scored_offers:
                    total = 0.0
                    breakdown = {}
                    for factor_weight_key, weight in normalized_criteria.items():
                        base = factor_weight_key.replace('_weight', '')
                        # Skip if factor not computed
                        raw_val = s['raw_scores'].get(base, 0)
                        denom = max_values.get(base, 1.0) or 1.0
                        normalized_score = raw_val / denom
                        weighted = normalized_score * weight
                        breakdown[base] = {
                            'raw_score': raw_val,
                            'normalized_score': round(normalized_score, 3),
                            'weight': weight,
                            'weighted_score': round(weighted, 3)
                        }
                        total += weighted

                    # Small penalty if bank_id missing (reduce confidence)
                    if not s['offer'].get('bank_id'):
                        total *= 0.9
                        breakdown['meta_penalty'] = 'missing_bank_id'

                    s['total_score'] = round(total, 3)
                    s['score_breakdown'] = breakdown

                if not scored_offers:
                    return json.dumps({"error": "No valid scored offers", "parse_errors": parse_errors})

                # Choose best by total_score, tie-breaker: amount approved, then lower interest
                def selection_key(x):
                    offer = x.get('offer') or {}
                    return (
                        x.get('total_score', 0),
                        offer.get('amount_approved', 0),
                        # for tie-breaker prefer lower numeric interest_rate
                        -float(offer.get('interest_rate', 0) or 0)
                    )

                best = max(scored_offers, key=selection_key)

                # Reasoning
                reasoning = self._generate_reasoning(best, scored_offers, normalized_criteria)

                accepted = best.get('total_score', 0) >= normalized_criteria.get('carbon_adjusted_rate_weight', 0) * 0  # keep acceptance decision outside if needed
                reason_for_accept = "selected by scoring" if accepted else "selected by scoring (no acceptance threshold applied)"

                return json.dumps({
                    "selected_offer": best.get('offer', {}),
                    "total_score": best.get('total_score', 0),
                    "accepted": accepted,
                    "accept_reason": reason_for_accept,
                    "score_breakdown": best.get('score_breakdown', {}),
                    "reasoning": reasoning,
                    "parse_errors": parse_errors,
                    "all_offers_scores": [{
                        'bank_id': s.get('offer', {}).get('bank_id'),
                        'total_score': s.get('total_score'),
                        'carbon_adjusted_rate': s.get('offer', {}).get('carbon_adjusted_rate'),
                        'amount_approved': s.get('offer', {}).get('amount_approved'),
                        'interest_rate': s.get('offer', {}).get('interest_rate'),
                        'repayment_period': s.get('offer', {}).get('repayment_period')
                    } for s in scored_offers]
                })
            except Exception as e:
                return json.dumps({"error": f"Error in offer selection: {str(e)}"})
            

        @tool
        async def negotiate_with_bank(bank_id: str, current_offer: dict, target_rate: float) -> str:
            """Negotiate interest rate reduction with a specific bank"""
            try:
                # Get the appropriate bank agent
                from bank_agents.bank1_agent import Bank1Agent
                from bank_agents.bank2_agent import Bank2Agent
                from bank_agents.bank3_agent import Bank3Agent

                bank_agents = {
                    "bank_1": Bank1Agent,
                    "bank_2": Bank2Agent,
                    "bank_3": Bank3Agent
                }

                if bank_id not in bank_agents:
                    return json.dumps({"error": f"Unknown bank_id: {bank_id}"})

                # Create bank agent instance
                bank_agent = bank_agents[bank_id]()
                negotiate_tool = None

                # Find the negotiate tool
                for tool in bank_agent.mcp_tools.get_tools():
                    if getattr(tool, "name", "") == "negotiate_interest_rate":
                        negotiate_tool = tool
                        break

                if not negotiate_tool:
                    return json.dumps({"error": "Negotiation tool not found for bank"})

                # Call the bank's negotiation tool
                result = await negotiate_tool.ainvoke({
                    "current_offer": current_offer,
                    "requested_rate": target_rate
                })

                return result

            except Exception as e:
                return json.dumps({"error": str(e)})

        return [verify_bank_identity, validate_offer, log_consumer_trace, select_best_offer, negotiate_with_bank]

    def _extract_esg_score(self, esg_summary: str) -> float:
        """Extract ESG score from summary text"""
        # Simple heuristic to extract score from text
        import re

        # Look for numeric patterns in the summary
        patterns = [
            r'esg[\s_-]*score[\s:]*([0-9.]+)',
            r'score[\s:]*([0-9.]+)[\s/]*[0-9.]*',
            r'rating[\s:]*([0-9.]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, esg_summary.lower())
            if match:
                try:
                    score = float(match.group(1))
                    return min(1.0, max(0.1, score / 10.0 if score > 1.0 else score))
                except:
                    continue

        # Default score based on keywords
        positive_keywords = ['excellent', 'outstanding', 'strong', 'good', 'positive']
        negative_keywords = ['poor', 'weak', 'negative', 'concern', 'risk']

        score = 0.5  # Neutral base score

        for keyword in positive_keywords:
            if keyword in esg_summary.lower():
                score += 0.1

        for keyword in negative_keywords:
            if keyword in esg_summary.lower():
                score -= 0.1

        return max(0.1, min(1.0, score))

    def _generate_reasoning(self, best_offer: dict, all_offers: list, criteria: dict) -> str:
        """Generate detailed reasoning for the selected offer"""
        offer = best_offer['offer']
        scores = best_offer['score_breakdown']

        reasoning = f"Selected offer from Bank {offer['bank_id']} with total score: {best_offer['total_score']:.3f}\n\n"
        reasoning += "Primary factors influencing this decision:\n"

        # Sort factors by contribution to score
        sorted_factors = sorted(scores.items(), key=lambda x: x[1]['weighted_score'], reverse=True)

        for factor, score_info in sorted_factors:
            if score_info['weighted_score'] > 0:
                reasoning += f"- {factor.replace('_', ' ').title()}: {score_info['weighted_score']:.3f} "
                reasoning += f"(normalized: {score_info['normalized_score']:.3f}, weight: {score_info['weight']:.3f})\n"

        reasoning += f"\nKey offer details:\n"
        reasoning += f"- Carbon-adjusted rate: {offer['carbon_adjusted_rate']:.3%}\n"
        reasoning += f"- Amount approved: ${offer['amount_approved']:,.2f}\n"
        reasoning += f"- Base interest rate: {offer['interest_rate']:.3%}\n"
        reasoning += f"- Repayment period: {offer['repayment_period']} months\n"

        # Compare with other offers
        other_offers = [o for o in all_offers if o['offer']['bank_id'] != offer['bank_id']]
        if other_offers:
            reasoning += f"\nComparison with other offers:\n"
            for other in other_offers:
                diff = best_offer['total_score'] - other['total_score']
                reasoning += f"- Bank {other['offer']['bank_id']}: score {other['total_score']:.3f} "
                reasoning += f"(difference: {diff:+.3f})\n"

        reasoning += f"\nESG considerations:\n{offer['esg_summary']}\n"

        return reasoning
