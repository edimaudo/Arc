from app.services.api_errors import classify_api_error, error_payload, friendly_api_error


def test_missing_provider_key_has_actionable_vercel_guidance():
    category, message = classify_api_error(RuntimeError('GEMINI_API_KEY is not configured'))
    assert category == 'provider_configuration'
    assert 'API key' in message
    assert 'Vercel Environment Variables' in message


def test_quota_is_distinguished_from_invalid_credentials():
    category, message = classify_api_error(RuntimeError('Gemini API request failed (429): quota exceeded'))
    assert category == 'provider_quota'
    assert 'usage limit' in message
    assert 'quota and billing' in message


def test_provider_400_is_not_misreported_as_a_generic_key_or_quota_issue():
    category, message = classify_api_error(RuntimeError('Gemini API request failed (400): Invalid argument: generation_config'))
    assert category == 'provider_rejected_request'
    assert 'model or API configuration' in message
    assert 'API key, model setting, and quota' not in message


def test_unparseable_research_output_has_a_recovery_message():
    category, message = classify_api_error(RuntimeError('Grounded company research returned no valid structured result after one format-recovery attempt.'))
    assert category == 'provider_invalid_response'
    assert 'incomplete result' in message
    assert 'API key, model setting, and quota' not in message


def test_timeout_mentions_function_duration_and_preserves_selection():
    category, message = classify_api_error(RuntimeError('Gemini request timed out after 60s'))
    assert category == 'research_timeout'
    assert 'selected company is preserved' in message
    assert 'Vercel function duration' in message


def test_unknown_error_has_reference_id_without_exposing_raw_exception():
    payload = error_payload(RuntimeError('secret payload should not be shown to user'), 'Discovery service', 'DISC-ABC123')
    assert payload['reference_id'] == 'DISC-ABC123'
    assert 'DISC-ABC123' in payload['error']
    assert 'secret payload' not in payload['error']
    assert payload['error_code'] == 'unexpected_research_error'


def test_friendly_error_can_append_reference_id():
    message = friendly_api_error(RuntimeError('API server unavailable'), 'Discovery service', 'DISC-123ABC')
    assert message.endswith('Reference ID: DISC-123ABC.')


def test_grounded_search_repairs_non_json_once_before_failing():
    import asyncio
    from app.services.agent_service import ArcAgent

    class RepairableAgent(ArcAgent):
        def __init__(self):
            self.api_key = 'test-key'
            self.model = 'gemini-3.5-flash'
            self.requests = []
            self.responses = [
                {'id': 'interaction-first', 'output_text': 'Here is the answer in prose.', 'steps': []},
                {'id': 'interaction-repaired', 'output_text': '{"comparables": [{"name": "Peer Co"}]}', 'steps': []},
            ]

        async def _post_interaction(self, payload):
            self.requests.append(payload)
            return self.responses.pop(0)

    agent = RepairableAgent()
    result = asyncio.run(agent._web_search_json('Find comparable companies. Return JSON.'))
    assert result['data']['comparables'][0]['name'] == 'Peer Co'
    assert len(agent.requests) == 2
    assert agent.requests[1]['previous_interaction_id'] == 'interaction-first'
    assert agent.requests[1]['tools'] == []
