"""
Targeted fix: replace handle_user_speech + user_speech_committed 
with process_answer_task that reads from the transcript buffer.
"""
import re

with open("app/interview/agent.py", "r", encoding="utf-8") as f:
    src = f.read()

# ── 1. Find the line numbers so we can work on the raw text ──────────────────
lines = src.splitlines(keepends=True)

# Find the line that starts handle_user_speech (the async def line)
handler_start_idx = None
handler_end_idx   = None   # last line of the function (finally block)

for i, line in enumerate(lines):
    if "async def handle_user_speech(" in line and handler_start_idx is None:
        # go back to include the comment line before it
        comment_idx = i - 1
        while comment_idx >= 0 and (lines[comment_idx].strip().startswith("#") or lines[comment_idx].strip() == ""):
            comment_idx -= 1
        handler_start_idx = comment_idx + 1
    if handler_start_idx is not None and "is_processing_turn = False" in line and handler_end_idx is None:
        # next non-empty line after this should be the Complete interview section
        handler_end_idx = i

if handler_start_idx is None or handler_end_idx is None:
    raise RuntimeError(f"Could not locate handle_user_speech block: start={handler_start_idx} end={handler_end_idx}")

print(f"Replacing lines {handler_start_idx+1}..{handler_end_idx+1} (handle_user_speech)")

NEW_PROCESS_TASK = '''    # ── Candidate answer handler ─────────────────────────────────────────────
    async def process_answer_task():
        nonlocal is_processing_turn, interview_phase
        try:
            text = ""
            if candidate_transcript_buffer:
                text = " ".join(candidate_transcript_buffer).strip()

            if not text:
                try:
                    await asyncio.wait_for(final_transcript_event.wait(), timeout=10.0)
                    text = " ".join(candidate_transcript_buffer).strip()
                except asyncio.TimeoutError:
                    pass

            if not text:
                logger.info("[DEBUG-STT] EMPTY FINAL TRANSCRIPT")
                interview_phase = "WAITING_FOR_ANSWER"
                await publish({"type": "waiting_for_answer", "question_number": current_q, "question_count": MAX_INTERVIEW_QUESTIONS})
                return

            logger.info("[DEBUG-STT] FINAL ANSWER ACCEPTED")
            logger.info("[DEBUG-STT] STARTING EVALUATION")

            interview_phase = "EVALUATING_ANSWER"
            eval_data = await evaluate_answer(current_question_text, text)
            logger.info("[DEBUG-STT] EVALUATION COMPLETED")

            result = {
                "question_number":  current_q,
                "question":         current_question_text,
                "candidate_answer": text,
                "answer":           text,
                "evaluation":       eval_data,
                "score":            eval_data.get("score", 0),
                "correctness":      eval_data.get("correctness", ""),
                "feedback":         eval_data.get("feedback", ""),
                "strengths":        eval_data.get("strengths", []),
                "weaknesses":       eval_data.get("weaknesses", []),
            }
            interview_results.append(result)
            logger.info("[DEBUG-STT] RESULT STORED")

            if current_q < MAX_INTERVIEW_QUESTIONS:
                logger.info(
                    "[FLOW] NEXT QUESTION AUTHORIZED current_q=%s evaluated_answers=%d",
                    current_q, len(interview_results),
                )
                interview_phase = "GENERATING_QUESTION"
                await generate_interview_question("after_answer")
            else:
                logger.info("[FLOW] Q5 EVALUATED - waiting for completion.")
                interview_phase = "WAITING_FOR_COMPLETION"
                await publish({"type": "interview_ready_to_complete"})

        except Exception:
            logger.exception("Error in process_answer_task")
            interview_phase = "WAITING_FOR_ANSWER"
            await publish({
                "type": "waiting_for_answer",
                "question_number": current_q,
                "question_count":  MAX_INTERVIEW_QUESTIONS,
            })
        finally:
            is_processing_turn = False
            logger.info("[PROCESSING LOCK] is_processing_turn = False")

'''

# ── 2. Remove the old handle_user_speech block ────────────────────────────────
new_lines = lines[:handler_start_idx] + [NEW_PROCESS_TASK] + lines[handler_end_idx + 1:]

# ── 3. Fix the user_speech_committed handler to NOT call handle_user_speech ───
# We just remove/neutralise it - we no longer need it because process_answer_task
# is launched directly from on_data_received
new_src = "".join(new_lines)

# Replace the old user_speech_committed registration with a no-op comment
old_handler = '''    @session.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        asyncio.create_task(handle_user_speech(msg))'''

new_src = new_src.replace(old_handler,
    "    # user_speech_committed is intentionally NOT wired: answer processing\n"
    "    # is driven by process_answer_task launched from on_data_received.\n"
)

if "handle_user_speech" in new_src:
    remaining = [l for l in new_src.splitlines() if "handle_user_speech" in l]
    print("WARNING: handle_user_speech still in file:")
    for r in remaining:
        print("  " + r.encode("ascii", "replace").decode("ascii"))
else:
    print("OK: handle_user_speech fully removed")

if "process_answer_task" not in new_src:
    raise RuntimeError("process_answer_task was not inserted!")
print("OK: process_answer_task inserted")

with open("app/interview/agent.py", "w", encoding="utf-8") as f:
    f.write(new_src)

print("Done. agent.py written.")
