from app.viz.contract import RecipeName, ArtifactMeta, UiPayload

def test_info_card_is_a_valid_recipe_name():
    # Pydantic Literal validation: instantiating UiPayload with the new
    # recipe name must succeed.
    payload = UiPayload(
        recipe="info_card",
        artifact=ArtifactMeta(
            identifier="info-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "info_card"


def test_concept_card_is_a_valid_recipe_name():
    payload = UiPayload(
        recipe="concept_card",
        artifact=ArtifactMeta(
            identifier="concept-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "concept_card"


def test_single_entity_card_is_a_valid_recipe_name():
    payload = UiPayload(
        recipe="single_entity_card",
        artifact=ArtifactMeta(
            identifier="single-entity-card-test",
            type="html",
            title="Test",
        ),
        raw="<div>test</div>",
    )
    assert payload.recipe == "single_entity_card"
