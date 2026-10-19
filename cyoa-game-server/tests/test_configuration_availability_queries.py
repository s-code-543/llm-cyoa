"""Player startup loads availability dependencies in a fixed number of queries."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from game.config_utils import configuration_models_available, with_model_availability
from game.models import Configuration
from tests.conftest import ConfigurationFactory, JudgeStepFactory, LLMModelFactory, PromptFactory

pytestmark = pytest.mark.django_db


def make_configuration():
    config = ConfigurationFactory(
        enable_refusal_detection=True, enable_image_generation=True,
        classifier_model=LLMModelFactory(), turn_correction_model=LLMModelFactory(),
        image_model=LLMModelFactory(),
    )
    for _ in range(2):
        JudgeStepFactory(configuration=config, classifier_model=LLMModelFactory(),
                         classifier_prompt=PromptFactory(prompt_type='classifier'))
    # A disabled step must neither block the adventure nor trigger lazy lookups.
    JudgeStepFactory(configuration=config, enabled=False,
                     rewrite_model=LLMModelFactory(is_available=False))
    return config


@pytest.mark.parametrize('count', [1, 5])
def test_batched_availability_uses_two_queries(count, django_assert_num_queries):
    configs = [make_configuration() for _ in range(count)]
    with django_assert_num_queries(2):
        loaded = list(with_model_availability(Configuration.objects.all()))
    with django_assert_num_queries(0):
        assert {c.pk for c in loaded if configuration_models_available(c)} == {c.pk for c in configs}


@pytest.mark.parametrize('endpoint', ['/api/v1/home', '/api/v1/chat/bootstrap'])
def test_startup_query_count_does_not_grow_with_configurations(auth_client, endpoint):
    first = make_configuration()
    with CaptureQueriesContext(connection) as small:
        response = auth_client.get(endpoint)
        assert response.status_code == 200
        assert [c['id'] for c in response.json()['configurations']] == [first.pk]

    more = [make_configuration() for _ in range(4)]
    broken = make_configuration()
    step = broken.judge_steps.filter(enabled=True).first()
    step.compare_model.is_available = False
    step.compare_model.save()
    with CaptureQueriesContext(connection) as large:
        response = auth_client.get(endpoint)
        assert response.status_code == 200
        assert {c['id'] for c in response.json()['configurations']} == {first.pk, *(c.pk for c in more)}
    assert len(large) == len(small)
