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
            """
            Select the best offer from multiple bank offers based on decision criteria.

            Args:
                offers: List of bank offers in WFAP format
                decision_criteria: Dictionary with weights for different factors:
                    - carbon_adjusted_rate_weight: Weight for carbon-adjusted rate (0.0-1.0)
                    - amount_approved_weight: Weight for amount approved (0.0-1.0)
                    - esg_score_weight: Weight for ESG score (0.0-1.0)
                    - interest_rate_weight: Weight for base interest rate (0.0-1.0)

            Returns:
                JSON with selected offer and detailed reasoning
            """
            try:
                # Validate inputs
                if not offers:
                    return json.dumps({"error": "No offers provided for evaluation"})

                # Default criteria weights if not provided
                criteria = {
                    'carbon_adjusted_rate_weight': 0.4,
                    'amount_approved_weight': 0.3,
                    'esg_score_weight': 0.2,
                    'interest_rate_weight': 0.1
                }
                criteria.update(decision_criteria)

                # Normalize weights to sum to 1.0
                total_weight = sum(criteria.values())
                if total_weight == 0:
                    return json.dumps({"error": "All criteria weights cannot be zero"})

                normalized_criteria = {k: v / total_weight for k, v in criteria.items()}

                # Score each offer
                scored_offers = []
                for offer in offers:
                    try:
                        # Extract offer details
                        offer_data = {
                            'offer_id': offer.get('offer_id'),
                            'bank_id': offer.get('bank_id'),
                            'carbon_adjusted_rate': float(offer.get('carbon_adjusted_rate', 0)),
                            'amount_approved': float(offer.get('amount_approved', 0)),
                            'interest_rate': float(offer.get('interest_rate', 0)),
                            'esg_summary': offer.get('esg_summary', ''),
                            'repayment_period': int(offer.get('repayment_period', 0))
                        }

                        # Calculate individual scores (lower is better for rates, higher for others)
                        carbon_score = 1.0 / (offer_data['carbon_adjusted_rate'] + 0.001)  # Avoid division by zero
                        amount_score = offer_data['amount_approved']
                        esg_score = self._extract_esg_score(offer_data['esg_summary'])
                        interest_score = 1.0 / (offer_data['interest_rate'] + 0.001)

                        # Normalize scores to 0-1 range
                        scores = {
                            'carbon_adjusted_rate': carbon_score,
                            'amount_approved': amount_score,
                            'esg_score': esg_score,
                            'interest_rate': interest_score
                        }

                        # Find max values for normalization (except rates where we want min)
                        max_values = {
                            'carbon_adjusted_rate': max(
                                [1.0 / (o.get('carbon_adjusted_rate', 0.001) + 0.001) for o in offers]),
                            'amount_approved': max([float(o.get('amount_approved', 0)) for o in offers]),
                            'esg_score': 1.0,  # ESG score is already 0-1
                            'interest_rate': max([1.0 / (o.get('interest_rate', 0.001) + 0.001) for o in offers])
                        }

                        # Normalize and weight scores
                        total_score = 0
                        score_breakdown = {}

                        for factor, weight in normalized_criteria.items():
                            base_factor = factor.replace('_weight', '')
                            normalized_score = scores[base_factor] / max_values[base_factor] if max_values[
                                                                                                    base_factor] > 0 else 0
                            weighted_score = normalized_score * weight
                            total_score += weighted_score
                            score_breakdown[base_factor] = {
                                'raw_score': scores[base_factor],
                                'normalized_score': round(normalized_score, 3),
                                'weight': weight,
                                'weighted_score': round(weighted_score, 3)
                            }

                        scored_offers.append({
                            'offer': offer_data,
                            'total_score': round(total_score, 3),
                            'score_breakdown': score_breakdown
                        })

                    except Exception as e:
                        print(f"Error processing offer {offer.get('offer_id')}: {e}")
                        continue

                if not scored_offers:
                    return json.dumps({"error": "No valid offers to evaluate"})

                # Select best offer
                best_offer = max(scored_offers, key=lambda x: x['total_score'])

                # Generate detailed reasoning
                reasoning = self._generate_reasoning(best_offer, scored_offers, normalized_criteria)

                return json.dumps({
                    "selected_offer": best_offer['offer'],
                    "total_score": best_offer['total_score'],
                    "score_breakdown": best_offer['score_breakdown'],
                    "reasoning": reasoning,
                    "all_offers_scores": [{
                        'bank_id': o['offer']['bank_id'],
                        'total_score': o['total_score'],
                        'carbon_adjusted_rate': o['offer']['carbon_adjusted_rate'],
                        'amount_approved': o['offer']['amount_approved'],
                        'interest_rate': o['offer']['interest_rate']
                    } for o in scored_offers]
                })

            except Exception as e:
                return json.dumps({"error": f"Error in offer selection: {str(e)}"})

        return [verify_bank_identity, validate_offer, log_consumer_trace, select_best_offer]

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