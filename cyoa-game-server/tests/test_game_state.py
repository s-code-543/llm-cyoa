"""
Unit tests for extract_game_state — pure logic, no auth needed.
"""
import pytest
from game.chat_views import extract_game_state


@pytest.mark.unit
class TestExtractGameState:
    """Unit tests for the extract_game_state function."""

    def test_extracts_turn_numbers(self):
        state = extract_game_state("**Turn 5 of 10**\n\nSome story content.")
        assert state['turn_current'] == 5
        assert state['turn_max'] == 10

    def test_extracts_turn_with_slash_format(self):
        state = extract_game_state("Turn 3/15\n\nThe adventure continues.")
        assert state['turn_current'] == 3
        assert state['turn_max'] == 15

    def test_extracts_choices_with_parenthesis(self):
        text = "Turn 1 of 10\n\nSome story.\n\n1) Go left into the cave\n2) Go right toward the mountain"
        state = extract_game_state(text)
        assert 'Go left into the cave' in state['choice1']
        assert 'Go right toward the mountain' in state['choice2']

    def test_extracts_choices_with_period(self):
        text = "Turn 1 of 10\n\nSome story.\n\n1. Enter the dark forest\n2. Follow the river downstream"
        state = extract_game_state(text)
        assert 'Enter the dark forest' in state['choice1']
        assert 'Follow the river downstream' in state['choice2']

    def test_handles_missing_turn_info(self):
        state = extract_game_state("Some story without turn numbers.")
        assert state['turn_current'] == 0
        assert state['turn_max'] == 20

    def test_handles_missing_choices(self):
        state = extract_game_state("Turn 5 of 10\n\nStory with no choices.")
        assert state['choice1'] == ''
        assert state['choice2'] == ''

    def test_handles_multiline_choices(self):
        text = (
            "Turn 2 of 10\n\nThe path splits.\n\n"
            "1) Take the left path which leads\n   through the dark forest\n"
            "2) Take the right path toward\n   the sunny meadow"
        )
        state = extract_game_state(text)
        assert 'left path' in state['choice1']
        assert 'right path' in state['choice2']

    def test_returns_inventory_list(self):
        state = extract_game_state("Turn 1 of 10\n\n1) Option A\n2) Option B")
        assert 'inventory' in state
        assert isinstance(state['inventory'], list)

    def test_extracts_choices_with_dash_separator(self):
        text = "Turn 1 of 10\n\nSome story.\n\n1- Climb the mountain\n2- Cross the river"
        state = extract_game_state(text)
        assert 'Climb the mountain' in state['choice1']
        assert 'Cross the river' in state['choice2']

    def test_extracts_choices_with_colon_separator(self):
        text = "Turn 1 of 10\n\nSome story.\n\n1: Enter the cave\n2: Stay outside"
        state = extract_game_state(text)
        assert 'Enter the cave' in state['choice1']
        assert 'Stay outside' in state['choice2']

    def test_extracts_choices_with_bold_wrapping(self):
        text = "Turn 1 of 10\n\nSome story.\n\n**1)** Fight the dragon\n**2)** Run away"
        state = extract_game_state(text)
        assert 'Fight the dragon' in state['choice1']
        assert 'Run away' in state['choice2']

    def test_extracts_choices_with_bold_number_only(self):
        text = "Turn 1 of 10\n\nSome story.\n\n**1.** Open the door\n**2.** Go back"
        state = extract_game_state(text)
        assert 'Open the door' in state['choice1']
        assert 'Go back' in state['choice2']

    def test_extracts_choices_with_indentation(self):
        text = "Turn 1 of 10\n\nSome story.\n\n  1) Search the room\n  2) Leave quickly"
        state = extract_game_state(text)
        assert 'Search the room' in state['choice1']
        assert 'Leave quickly' in state['choice2']

    def test_extracts_choices_mixed_formatting(self):
        """Test various combinations of formatting in same response."""
        text = (
            "Turn 1 of 10\n\nSome story.\n\n"
            "  **1-** Take the left path\n"
            "**2:** Take the right path"
        )
        state = extract_game_state(text)
        assert 'Take the left path' in state['choice1']
        assert 'Take the right path' in state['choice2']

    def test_extracts_choices_with_bold_and_colon(self):
        text = "Turn 1 of 10\n\nSome story.\n\n**1:** Attack\n**2:** Defend"
        state = extract_game_state(text)
        assert 'Attack' in state['choice1']
        assert 'Defend' in state['choice2']
