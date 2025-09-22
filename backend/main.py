import asyncio
import json
import logging
from consumer_agent.agent import ConsumerAgent
from bank_agents.bank1_agent import Bank1Agent
from bank_agents.bank2_agent import Bank2Agent
from bank_agents.bank3_agent import Bank3Agent
from shared.config import OllamaConfig

logging.basicConfig(
    filename='log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    print("🚀 WFAP Credit Negotiation System with Local Ollama")
    print("=" * 55)

    print("Checking Ollama connection...")
    try:
        import requests
        response = requests.get(f"{OllamaConfig.OLLAMA_BASE_URL}/api/tags")
        if response.status_code == 200:
            models = [model['name'] for model in response.json().get('models', [])]
            print(f"✅ Ollama connected. Available models: {', '.join(models)}")
        else:
            print("❌ Ollama is not running. Please start Ollama service.")
            return
    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        print("Please make sure Ollama is installed and running on http://localhost:11434")
        return

    selected_model = OllamaConfig.DEFAULT_MODEL
    print(f"Using default model: {selected_model}")

    print("\nInitializing agents...")
    consumer = ConsumerAgent(model_name=selected_model)
    bank1 = Bank1Agent(model_name=selected_model)
    bank2 = Bank2Agent(model_name=selected_model)
    bank3 = Bank3Agent(model_name=selected_model)

    banks = {
        "Bank 1 (Green Focus)": bank1,
        "Bank 2 (Traditional)": bank2,
        "Bank 3 (Tech Innovation)": bank3
    }

    print("\n" + "=" * 55)
    print("Enter Loan Details:")
    print("=" * 55)

    try:
        amount = float(input("Loan Amount: $"))
        duration = int(input("Duration (months): "))
        purpose = input("Loan Purpose: ")
    except ValueError:
        print("❌ Invalid input. Please enter numeric values for amount and duration.")
        return

    print(f"\n📨 Processing: ${amount:,.0f} for {duration} months")
    print(f"   Purpose: {purpose}")
    print("\nSending to 3 different banks...")

    from shared.utils import create_signed_intent
    intent_data = create_signed_intent("company_x", amount, duration, purpose)

    offers = []
    for bank_name, bank in banks.items():
        try:
            print(f"\n🔄 Getting offer from {bank_name}...")
            result = await bank.evaluate_loan_request(intent_data)

            if isinstance(result, dict) and 'output' in result:
                try:
                    offer_data = json.loads(result['output'])
                    if offer_data.get('amount_approved', 0) > 0:
                        offers.append(offer_data)
                        print(f"   ✅ Offer received: {offer_data.get('bank_id')}")
                    else:
                        print(f"   ❌ Offer rejected by {bank_name}: {offer_data.get('esg_summary', 'No reason provided')}")
                except:
                    offers.append(result)
                    print(f"   ✅ Offer received (raw)")
            else:
                offers.append(result)
                print(f"   ✅ Offer received")

        except Exception as e:
            print(f"   ❌ Error from {bank_name}: {e}")

    if not offers:
        print("\n❌ No offers received from any bank.")
        return

    print(f"\n📊 Received {len(offers)} offers. Evaluating using decision logic...")
    try:
        for i in offers:
            print("result: ", i, "\n\n")
        evaluation_result = await consumer.evaluate_offers(offers)

        print("\n" + "=" * 55)
        print("🏆 FINAL DECISION:")
        print("=" * 55)

        if 'error' in evaluation_result:
            print(f"❌ Error: {evaluation_result['error']}")
            return

        selected = evaluation_result['selected_offer']
        print(f"Selected Bank: {selected['bank_id']}")
        print(f"Total Score: {evaluation_result['total_score']:.3f}")
        print(f"\nCarbon-adjusted Rate: {selected['carbon_adjusted_rate']:.3%}")
        print(f"Amount Approved: ${selected['amount_approved']:,.2f}")
        print(f"Base Interest Rate: {selected['interest_rate']:.3%}")
        print(f"Repayment Period: {selected['repayment_period']} months")

        print(f"\n📈 SCORE BREAKDOWN:")
        for factor, scores in evaluation_result['score_breakdown'].items():
            print(f"  {factor}: {scores['weighted_score']:.3f} "
                  f"(normalized: {scores['normalized_score']:.3f}, weight: {scores['weight']:.3f})")

        print(f"\n💡 REASONING:")
        print(evaluation_result['reasoning'])

        print(f"\n📋 ALL OFFERS COMPARISON:")
        for offer in evaluation_result['all_offers_scores']:
            print(f"  {offer['bank_id']}: Score {offer['total_score']:.3f}, "
                  f"CAR: {offer['carbon_adjusted_rate']:.3%}, "
                  f"Amount: ${offer['amount_approved']:,.2f}")

    except Exception as e:
        print(f"❌ Error evaluating offers: {e}")


if __name__ == "__main__":
    asyncio.run(main())
