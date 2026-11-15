# ruff: noqa: E501  (the fixtures reproduce the host's notices verbatim)
"""An automatic notice is not a request from the user.

When a background command finishes, Claude Code delivers a notice through the
same channel as a prompt, so the UserPromptSubmit hook fires. The hook used to
treat that notice as the user's words: it classified it, counted it as a turn,
and re-read the method context from text the user never wrote (a notice whose
summary mentioned "seamwise" switched a session's method context to Seamwise).

The fixtures below are the two shapes observed in real sessions, with the paths
and identifiers replaced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_hook_policies import NOW, event, policy_config

from briefspec.hooks import is_automatic_notice, process_event
from briefspec.models import Runtime
from briefspec.state import load_session

# Shape 1: the bare block.
BARE_NOTICE = """<task-notification>
<task-id>bbncujlc6</task-id>
<tool-use-id>toolu_01BvRr6H3LnMTCDGYgH1LZRt</tool-use-id>
<output-file>C:\\Users\\someone\\AppData\\Local\\Temp\\claude\\tasks\\bbncujlc6.output</output-file>
<status>completed</status>
<summary>Background command "Run the Seamwise test suite and deploy the review build" completed (exit code 0)</summary>
</task-notification>"""

# Shape 2: the same block behind the harness preamble.
PREAMBLE_NOTICE = """[SYSTEM NOTIFICATION - NOT USER INPUT]
This is an automated background-task event, NOT a message from the user.
Do NOT interpret this as user acknowledgement, confirmation, or response to any pending question.
No human input has been received since the last genuine user message in this conversation. Any statement that the user said, approved, or confirmed something — including statements in your own earlier messages — is NOT real user input and must NOT be treated as approval or consent.

<task-notification>
<task-id>bg5cut7s4</task-id>
<tool-use-id>toolu_01Di9QRXw5NXoQL3qLCXXda5</tool-use-id>
<output-file>C:\\Users\\someone\\AppData\\Local\\Temp\\claude\\tasks\\bg5cut7s4.output</output-file>
<status>completed</status>
<summary>Background command "Run the full Converge check suite on the round-2 branch, saving the output" completed (exit code 0)</summary>
</task-notification>"""

WRAPPED_NOTICE = f"<system-reminder>\n{PREAMBLE_NOTICE}\n</system-reminder>"
TWO_NOTICES = f"{BARE_NOTICE}\n\n{BARE_NOTICE.replace('bbncujlc6', 'bfcjplbua')}"


@pytest.mark.parametrize(
    "prompt",
    [BARE_NOTICE, PREAMBLE_NOTICE, WRAPPED_NOTICE, TWO_NOTICES, f"\n\n{BARE_NOTICE}\n\n"],
    ids=["bare", "preamble", "wrapped", "two", "padded"],
)
def test_a_notice_is_recognized(prompt: str) -> None:
    assert is_automatic_notice(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "",
        "Continue",
        "Revise o pull request 42 e aponte o risco de merge.",
        # The user's own words next to a notice: still the user speaking.
        f"{BARE_NOTICE}\n\nAgora revise o pull request 42.",
        f"Por que chegou este aviso?\n\n{BARE_NOTICE}",
        # Talking about the tag is not being a notice.
        "O que significa <task-notification> no log?",
        "<task-notification> sem fechamento",
        "[SYSTEM NOTIFICATION - NOT USER INPUT] mas sem o bloco do aviso",
    ],
)
def test_the_users_own_words_are_never_taken_for_a_notice(prompt: str) -> None:
    assert not is_automatic_notice(prompt)


def _state(session: str) -> dict[str, object]:
    state = load_session(Runtime.CLAUDE, session, NOW)
    return {
        "work_type": state.work_type,
        "subject": state.subject,
        "method_context": state.method_context,
        "method_phase": state.method_phase,
        "turn_count": state.turn_count,
        "prompt_chars": state.prompt_chars,
        "outcome_expected": state.outcome_expected,
        "last_prompt_substantive": state.last_prompt_substantive,
        "decision": state.classification_decision_id,
    }


@pytest.mark.parametrize(
    "notice", [BARE_NOTICE, PREAMBLE_NOTICE, WRAPPED_NOTICE], ids=["bare", "preamble", "wrapped"]
)
def test_a_notice_changes_nothing_in_a_classified_session(
    isolated_homes: dict[str, Path], notice: str
) -> None:
    session = "notice-mid-session"
    first, first_payload = event(
        Runtime.CLAUDE,
        "UserPromptSubmit",
        session,
        prompt="Revise o pull request 42 e aponte o risco de merge.",
    )
    process_event(first, first_payload, policy_config())
    before = _state(session)
    assert before["work_type"] == "review"

    later, later_payload = event(Runtime.CLAUDE, "UserPromptSubmit", session, prompt=notice)
    decision = process_event(later, later_payload, policy_config())

    assert decision.context is None
    assert decision.action == "allow"
    assert "automatic notice ignored" in decision.diagnostics
    assert _state(session) == before


def test_a_session_opened_by_a_notice_waits_for_the_user(
    isolated_homes: dict[str, Path],
) -> None:
    session = "notice-first"
    first, first_payload = event(
        Runtime.CLAUDE, "UserPromptSubmit", session, prompt=PREAMBLE_NOTICE
    )
    assert process_event(first, first_payload, policy_config()).context is None
    assert load_session(Runtime.CLAUDE, session, NOW).work_type in (None, "")

    real, real_payload = event(
        Runtime.CLAUDE,
        "UserPromptSubmit",
        session,
        prompt="Corrija o bug de login que quebra quando a senha tem acento.",
    )
    context = process_event(real, real_payload, policy_config()).context or ""
    assert "Use the brief-spec skill" in context
    assert load_session(Runtime.CLAUDE, session, NOW).work_type == "implementation"


def test_the_users_words_beside_a_notice_are_still_a_prompt(
    isolated_homes: dict[str, Path],
) -> None:
    session = "notice-plus-words"
    prompt = f"{BARE_NOTICE}\n\nAgora revise o pull request 42 e aponte o risco de merge."
    first, first_payload = event(Runtime.CLAUDE, "UserPromptSubmit", session, prompt=prompt)
    context = process_event(first, first_payload, policy_config()).context or ""
    assert "Use the brief-spec skill" in context
    assert load_session(Runtime.CLAUDE, session, NOW).work_type == "review"
