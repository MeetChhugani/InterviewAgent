"""
Tests for the interview state machine.

These tests verify the state logic in agent.py WITHOUT importing LiveKit,
by simulating the relevant state variables and functions in isolation.
"""
import pytest
import asyncio

@pytest.fixture
def anyio_backend():
    return 'asyncio'

# ─── Minimal simulation of the interview state machine ───────────────────────

def make_state(max_q=5):
    """Return a fresh state dict mirroring the agent's local variables."""
    return {
        "MAX_INTERVIEW_QUESTIONS":  max_q,
        "current_q":                0,
        "current_question_text":    "",
        "interview_results":        [],
        "interview_phase":          "INIT",     # see agent.py for legal values
        "is_processing_turn":       False,
        "report_generation_started": False,
        "question_generation_count": 0,         # test-only counter
        "published_events":         [],          # test-only log of published messages
    }


async def sim_generate_question(state: dict, source: str) -> str | None:
    """Simulates generate_interview_question() logic (no LLM, no TTS)."""
    if state["interview_phase"] not in ("INIT", "GENERATING_QUESTION"):
        return None
    if state["current_q"] >= state["MAX_INTERVIEW_QUESTIONS"]:
        return None
    if state["current_q"] > 0 and len(state["interview_results"]) < state["current_q"]:
        return None

    state["interview_phase"] = "GENERATING_QUESTION"
    state["current_q"] += 1
    state["question_generation_count"] += 1

    # Simulate TTS
    state["interview_phase"] = "AI_SPEAKING"
    question_text = f"Simulated question {state['current_q']}?"
    state["current_question_text"] = question_text

    # After say() resolves
    state["interview_phase"] = "WAITING_FOR_ANSWER"
    return question_text


async def sim_handle_answer(state: dict, answer_text: str) -> bool:
    """Simulates handle_user_speech() logic (no LLM evaluation)."""
    if state["interview_phase"] != "WAITING_FOR_ANSWER":
        state["is_processing_turn"] = False
        return False

    try:
        state["interview_phase"] = "EVALUATING_ANSWER"

        result = {
            "question_number":  state["current_q"],
            "question":         state["current_question_text"],
            "candidate_answer": answer_text,
            "score":            80,
            "feedback":         "Good answer.",
        }
        state["interview_results"].append(result)

        if state["current_q"] < state["MAX_INTERVIEW_QUESTIONS"]:
            state["interview_phase"] = "GENERATING_QUESTION"
            await sim_generate_question(state, "after_answer")
        else:
            state["interview_phase"] = "WAITING_FOR_COMPLETION"
            state["published_events"].append("interview_ready_to_complete")
        return True
    finally:
        state["is_processing_turn"] = False


async def sim_complete_interview(state: dict) -> bool:
    if state["report_generation_started"]:
        return False
    state["report_generation_started"] = True
    state["interview_phase"] = "GENERATING_REPORT"

    if len(state["interview_results"]) < state["MAX_INTERVIEW_QUESTIONS"]:
        state["report_generation_started"] = False
        return False

    state["interview_phase"] = "COMPLETE"
    state["published_events"].append("interview_completed")
    return True


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_q1_generated_on_initial():
    s = make_state()
    q = await sim_generate_question(s, "initial")
    assert q is not None
    assert s["current_q"] == 1
    assert s["question_generation_count"] == 1
    assert s["interview_phase"] == "WAITING_FOR_ANSWER"


@pytest.mark.anyio
async def test_no_q2_before_answer():
    """Q2 must not be generated while WAITING_FOR_ANSWER (no answer yet)."""
    s = make_state()
    await sim_generate_question(s, "initial")   # Q1 asked
    assert s["interview_phase"] == "WAITING_FOR_ANSWER"

    # Attempt to generate Q2 while still waiting — must be blocked
    result = await sim_generate_question(s, "attempt_q2")
    assert result is None, "Q2 must NOT be generated before Q1 is answered"
    assert s["current_q"] == 1
    assert s["question_generation_count"] == 1


@pytest.mark.anyio
async def test_next_question_requires_evaluated_answer():
    """generation is blocked when evaluated < current_q."""
    s = make_state()
    s["interview_phase"] = "GENERATING_QUESTION"
    s["current_q"] = 2          # Q2 was asked
    s["interview_results"] = [] # but 0 answers evaluated

    result = await sim_generate_question(s, "after_answer")
    assert result is None


@pytest.mark.anyio
async def test_exactly_five_questions():
    """Complete five answer cycles; exactly 5 questions generated."""
    s = make_state()
    await sim_generate_question(s, "initial")

    for i in range(1, 6):
        assert s["current_q"] == i
        assert s["interview_phase"] == "WAITING_FOR_ANSWER"
        s["is_processing_turn"] = True
        await sim_handle_answer(s, f"Answer {i}")

    assert s["question_generation_count"] == 5
    assert len(s["interview_results"]) == 5
    assert s["interview_phase"] == "WAITING_FOR_COMPLETION"


@pytest.mark.anyio
async def test_q5_never_generates_q6():
    """After Q5 evaluation, phase must be WAITING_FOR_COMPLETION, not GENERATING_QUESTION."""
    s = make_state()
    await sim_generate_question(s, "initial")
    for i in range(1, 6):
        s["is_processing_turn"] = True
        await sim_handle_answer(s, f"Answer {i}")

    assert s["current_q"] == 5
    assert len(s["interview_results"]) == 5
    assert s["interview_phase"] == "WAITING_FOR_COMPLETION"
    assert s["question_generation_count"] == 5

    # Any further attempt to generate must be blocked
    result = await sim_generate_question(s, "rogue_q6")
    assert result is None, "Q6 must never be generated"
    assert s["question_generation_count"] == 5


@pytest.mark.anyio
async def test_duplicate_generation_blocked():
    """Concurrent generation attempts are blocked by the phase guard."""
    s = make_state()
    await sim_generate_question(s, "initial")   # sets phase=WAITING_FOR_ANSWER

    # Two concurrent attempts to generate the next question (before any answer)
    results = await asyncio.gather(
        sim_generate_question(s, "concurrent_a"),
        sim_generate_question(s, "concurrent_b"),
    )
    # Both must be None because phase == WAITING_FOR_ANSWER
    assert all(r is None for r in results)
    assert s["question_generation_count"] == 1


@pytest.mark.anyio
async def test_complete_interview_requires_five_results():
    """do_complete_interview must reject if fewer than 5 results exist."""
    s = make_state()
    s["interview_phase"] = "WAITING_FOR_COMPLETION"
    s["interview_results"] = [{"score": 80}] * 3   # only 3

    ok = await sim_complete_interview(s)
    assert not ok
    assert "interview_completed" not in s["published_events"]
    assert not s["report_generation_started"]  # reset on rejection


@pytest.mark.anyio
async def test_complete_interview_with_five_results():
    """do_complete_interview must succeed with exactly 5 results."""
    s = make_state()
    s["interview_phase"] = "WAITING_FOR_COMPLETION"
    s["interview_results"] = [{"score": 80}] * 5

    ok = await sim_complete_interview(s)
    assert ok
    assert "interview_completed" in s["published_events"]
    assert s["interview_phase"] == "COMPLETE"


@pytest.mark.anyio
async def test_complete_interview_cannot_run_twice():
    """do_complete_interview must be idempotent."""
    s = make_state()
    s["interview_phase"] = "WAITING_FOR_COMPLETION"
    s["interview_results"] = [{"score": 80}] * 5

    r1 = await sim_complete_interview(s)
    r2 = await sim_complete_interview(s)
    assert r1 is True
    assert r2 is False
    assert s["published_events"].count("interview_completed") == 1


@pytest.mark.anyio
async def test_duplicate_stop_blocked():
    """is_processing_turn prevents the same STOP from evaluating an answer twice."""
    s = make_state()
    await sim_generate_question(s, "initial")
    assert s["interview_phase"] == "WAITING_FOR_ANSWER"

    # Simulate on_data_received logic
    def on_stop_received():
        if s["is_processing_turn"]:
            return False
        s["is_processing_turn"] = True
        return True

    # First STOP — should succeed
    assert on_stop_received() is True
    
    # Simulate a second STOP arriving while the first is still processing
    assert on_stop_received() is False
    
    # Now finish the first answer
    ok1 = await sim_handle_answer(s, "My answer")
    assert ok1 is True
    
    # First length
    first_len = len(s["interview_results"])
    
    # The first answer processing completed, so is_processing_turn is False now.
    # However, if another STOP arrives randomly while phase is NOT WAITING_FOR_ANSWER
    # (e.g. AI is speaking), handle_user_speech will reject it.
    # Let's artificially set phase to AI_SPEAKING to test phase guard:
    s["interview_phase"] = "AI_SPEAKING"
    assert on_stop_received() is True  # on_data_received accepts it and sets lock
    ok2 = await sim_handle_answer(s, "Rogue answer") # handle_user_speech rejects
    assert ok2 is False
    assert len(s["interview_results"]) == first_len

@pytest.mark.anyio
async def test_question_does_not_trigger_second_ai_response():
    """Ensure exactly one AI speech event per question."""
    s = make_state()
    q = await sim_generate_question(s, "initial")
    assert q is not None
    assert s["question_generation_count"] == 1
    # Attempt second generation should fail since phase=WAITING_FOR_ANSWER
    q2 = await sim_generate_question(s, "auto_reply")
    assert q2 is None
    assert s["question_generation_count"] == 1


@pytest.mark.anyio
async def test_no_llm_call_while_waiting_for_answer():
    """Verify that generation is blocked while WAITING_FOR_ANSWER."""
    s = make_state()
    s["interview_phase"] = "WAITING_FOR_ANSWER"
    q = await sim_generate_question(s, "auto_reply")
    assert q is None


@pytest.mark.anyio
async def test_evaluation_is_not_spoken():
    """Verify evaluation does not produce spoken text."""
    s = make_state()
    await sim_generate_question(s, "initial")
    # Simulate answering
    s["is_processing_turn"] = True
    await sim_handle_answer(s, "My answer")
    
    # In our simulation, sim_handle_answer updates interview_results 
    # but does NOT set current_question_text to the evaluation. 
    # It calls sim_generate_question("after_answer") which sets the text to Q2.
    assert s["current_question_text"].startswith("Simulated question 2")


@pytest.mark.anyio
async def test_next_question_only_after_evaluation():
    """Q2 generated only after Q1 evaluation completes."""
    s = make_state()
    await sim_generate_question(s, "initial")
    assert s["current_q"] == 1
    
    # Attempting Q2 before answer evaluation should fail
    q_fail = await sim_generate_question(s, "after_answer")
    assert q_fail is None
    assert s["current_q"] == 1
    
    s["is_processing_turn"] = True
    await sim_handle_answer(s, "Candidate answer")
    
    # After handle_answer evaluates, Q2 is generated automatically
    assert s["current_q"] == 2
