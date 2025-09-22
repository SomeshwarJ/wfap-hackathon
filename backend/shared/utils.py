import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import base64


class CryptoUtils:
    """Cryptographic utilities for signature validation and generation"""

    # In a real implementation, this would use proper key management
    # For demo purposes, we'll use a simple shared secret
    SHARED_SECRET = "wfap_demo_secret_2024".encode('utf-8')

    @staticmethod
    def generate_signature(data: Dict[str, Any], secret: bytes = None) -> str:
        """
        Generate HMAC signature for data verification
        """
        secret = secret or CryptoUtils.SHARED_SECRET

        # Sort keys to ensure consistent ordering
        sorted_data = json.dumps(data, sort_keys=True)

        # Create HMAC signature
        signature = hmac.new(
            secret,
            sorted_data.encode('utf-8'),
            hashlib.sha256
        ).digest()

        # Return base64 encoded signature
        return base64.b64encode(signature).decode('utf-8')

    @staticmethod
    def validate_signature(data: Dict[str, Any], signature: str, secret: bytes = None) -> bool:
        """
        Validate HMAC signature against data
        """

        secret = secret or CryptoUtils.SHARED_SECRET

        # Generate expected signature
        expected_signature = CryptoUtils.generate_signature(data, secret)

        # Compare signatures (use constant time comparison to prevent timing attacks)
        return hmac.compare_digest(expected_signature, signature)

    @staticmethod
    def generate_agent_id(prefix: str) -> str:
        """Generate unique agent ID"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def get_current_timestamp() -> str:
        """Get current timestamp in ISO format"""
        return datetime.utcnow().isoformat() + "Z"


class ProtocolUtils:
    """Utilities for WFAP protocol compliance"""

    @staticmethod
    def validate_intent(intent_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate WFAP Intent structure
        """
        required_fields = ['request_id', 'company_id', 'amount', 'duration', 'purpose', 'timestamp']

        for field in required_fields:
            if field not in intent_data:
                return False, f"Missing required field: {field}"

            if intent_data[field] is None or intent_data[field] == "":
                return False, f"Field cannot be empty: {field}"

        # Validate data types
        if not isinstance(intent_data['amount'], (int, float)) or intent_data['amount'] <= 0:
            return False, "Amount must be a positive number"

        if not isinstance(intent_data['duration'], int) or intent_data['duration'] <= 0:
            return False, "Duration must be a positive integer"

        return True, None

    @staticmethod
    def validate_offer(offer_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate WFAP Offer structure
        """
        required_fields = [
            'offer_id', 'request_id', 'bank_id', 'interest_rate',
            'amount_approved', 'repayment_period', 'esg_summary',
            'carbon_adjusted_rate', 'timestamp'
        ]

        for field in required_fields:
            if field not in offer_data:
                return False, f"Missing required field: {field}"

            if offer_data[field] is None or offer_data[field] == "":
                return False, f"Field cannot be empty: {field}"

        # Validate financial values
        if not isinstance(offer_data['interest_rate'], (int, float)) or offer_data['interest_rate'] < 0:
            return False, "Interest rate must be a non-negative number"

        if not isinstance(offer_data['amount_approved'], (int, float)) or offer_data['amount_approved'] <= 0:
            return False, "Amount approved must be a positive number"

        if not isinstance(offer_data['carbon_adjusted_rate'], (int, float)) or offer_data['carbon_adjusted_rate'] < 0:
            return False, "Carbon adjusted rate must be a non-negative number"

        if not isinstance(offer_data['repayment_period'], int) or offer_data['repayment_period'] <= 0:
            return False, "Repayment period must be a positive integer"

        return True, None

    @staticmethod
    def create_signed_intent(company_id: str, amount: float, duration: int, purpose: str) -> Dict[str, Any]:
        """
        Create a signed WFAP Intent
        """
        intent_data = {
            "request_id": f"req_{uuid.uuid4().hex[:8]}",
            "company_id": company_id,
            "amount": amount,
            "duration": duration,
            "purpose": purpose,
            "timestamp": CryptoUtils.get_current_timestamp(),
            "signature": None  # Will be set after creation
        }
        company_id_dict = {"company_id": company_id}
        # Generate signature
        intent_data["signature"] = CryptoUtils.generate_signature(company_id_dict)

        return intent_data

    @staticmethod
    def create_signed_offer(request_id: str, bank_id: str, interest_rate: float,
                            amount_approved: float, repayment_period: int,
                            esg_summary: str, carbon_adjusted_rate: float) -> Dict[str, Any]:
        """
        Create a signed WFAP Offer
        """
        offer_data = {
            "offer_id": f"off_{uuid.uuid4().hex[:8]}",
            "request_id": request_id,
            "bank_id": bank_id,
            "interest_rate": interest_rate,
            "amount_approved": amount_approved,
            "repayment_period": repayment_period,
            "esg_summary": esg_summary,
            "carbon_adjusted_rate": carbon_adjusted_rate,
            "timestamp": CryptoUtils.get_current_timestamp(),
            "signature": None  # Will be set after creation
        }

        # Generate signature
        offer_data["signature"] = CryptoUtils.generate_signature(offer_data)

        return offer_data


class ESGUtils:
    """Utilities for ESG-related calculations"""

    @staticmethod
    def calculate_carbon_adjusted_rate(base_rate: float, esg_score: float, purpose: str) -> float:
        """
        Calculate carbon-adjusted interest rate based on ESG factors
        """
        # Base ESG discount (0-3% based on ESG score)
        esg_discount = esg_score * 0.03

        # Purpose-based additional discounts
        purpose_bonus = 0.0
        purpose = purpose.lower()

        if any(word in purpose for word in ['solar', 'wind', 'renewable']):
            purpose_bonus = 0.015  # 1.5% additional discount for renewable energy
        elif any(word in purpose for word in ['ev', 'electric vehicle', 'sustainable']):
            purpose_bonus = 0.010  # 1.0% discount for sustainability
        elif any(word in purpose for word in ['tech', 'innovation', 'digital']):
            purpose_bonus = 0.005  # 0.5% discount for technology

        total_discount = esg_discount + purpose_bonus
        adjusted_rate = max(0.0, base_rate - total_discount)

        return round(adjusted_rate, 4)

    @staticmethod
    def generate_esg_score(purpose: str) -> float:
        """
        Generate ESG score based on project purpose (0.0 to 1.0)
        """
        purpose = purpose.lower()
        base_score = 0.5  # Neutral base score

        # Positive impact keywords
        positive_keywords = {
            'solar': 0.3, 'wind': 0.25, 'renewable': 0.2,
            'sustainable': 0.15, 'green': 0.1, 'ev': 0.2,
            'electric vehicle': 0.2, 'carbon': 0.15, 'emission': 0.1,
            'environment': 0.1, 'clean': 0.15, 'energy efficiency': 0.2
        }

        # Negative impact keywords
        negative_keywords = {
            'fossil': -0.3, 'coal': -0.4, 'oil': -0.3,
            'mining': -0.25, 'pollution': -0.3, 'waste': -0.2,
            'deforestation': -0.4, 'high emission': -0.3
        }

        # Calculate score adjustments
        positive_adjustment = 0.0
        negative_adjustment = 0.0

        for keyword, adjustment in positive_keywords.items():
            if keyword in purpose:
                positive_adjustment += adjustment

        for keyword, adjustment in negative_keywords.items():
            if keyword in purpose:
                negative_adjustment += adjustment

        # Apply adjustments with bounds
        final_score = base_score + positive_adjustment + negative_adjustment
        final_score = max(0.1, min(1.0, final_score))  # Keep between 0.1 and 1.0

        return round(final_score, 2)


class LoggingUtils:
    """Utilities for audit logging and tracing"""

    @staticmethod
    def create_audit_log(agent_type: str, action: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create standardized audit log entry
        """
        return {
            "log_id": f"log_{uuid.uuid4().hex[:8]}",
            "timestamp": CryptoUtils.get_current_timestamp(),
            "agent_type": agent_type,
            "action": action,
            "details": details,
            "signature": None
        }

    @staticmethod
    def sign_audit_log(log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign an audit log entry
        """
        # Copy without signature for signing
        signing_data = log_entry.copy()
        if 'signature' in signing_data:
            del signing_data['signature']

        log_entry['signature'] = CryptoUtils.generate_signature(signing_data)
        return log_entry


# Simplified imports for external use
def validate_signature(data: Dict[str, Any], signature: str) -> bool:
    """Validate signature for external imports"""
    return CryptoUtils.validate_signature(data, signature)


def generate_signature(data: Dict[str, Any]) -> str:
    """Generate signature for external imports"""
    return CryptoUtils.generate_signature(data)


def create_signed_intent(company_id: str, amount: float, duration: int, purpose: str) -> Dict[str, Any]:
    """Create signed intent for external imports"""
    return ProtocolUtils.create_signed_intent(company_id, amount, duration, purpose)


def calculate_carbon_adjusted_rate(base_rate: float, esg_score: float, purpose: str) -> float:
    """Calculate carbon-adjusted rate for external imports"""
    return ESGUtils.calculate_carbon_adjusted_rate(base_rate, esg_score, purpose)