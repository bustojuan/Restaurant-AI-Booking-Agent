from test_ai_agents import sample

from app.ai.agents import NegotiationAgent, VerificationAgent


def test_non_deposit_financial_obligations_require_exact_human_approval():
    config, offer, evidence = sample()
    economic = offer.model_copy(update={"financial_conditions": ["Cargo por cancelación de 20 EUR"]})
    evidence = evidence.model_copy(update={"details": economic})
    assert NegotiationAgent().evaluate(config, economic).evaluation == "REQUIRES_USER_APPROVAL"
    verifier = VerificationAgent()
    assert verifier.verify(config, "restaurant", "attempt", economic, evidence).status == "NEEDS_USER_ACTION"
    assert (
        verifier.verify(config, "restaurant", "attempt", economic, evidence, approved=True).status
        == "CONFIRMED"
    )
    changed = evidence.model_copy(
        update={"details": economic.model_copy(update={"financial_conditions": ["Cargo de 50 EUR"]})}
    )
    assert (
        verifier.verify(config, "restaurant", "attempt", economic, changed, approved=True).status
        == "REJECTED"
    )
