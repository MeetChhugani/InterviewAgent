from pydantic import BaseModel, Field
from typing import List


class InterviewSetup(BaseModel):
    domain: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(min_length=1, max_length=40)
    topics: List[str] = Field(min_length=1, max_length=20)
    num_questions: int = Field(ge=1, le=10)


class AnswerEvaluation(BaseModel):
    score: int
    correctness: str
    relevance: int
    completeness: int
    technical_depth: int
    feedback: str
    strengths: List[str]
    weaknesses: List[str]


class QuestionResult(BaseModel):
    question: str
    answer: str
    score: int
    correctness: str
    feedback: str
    strengths: List[str]
    weaknesses: List[str]


class InterviewReport(BaseModel):
    overall_score: int
    technical_score: int
    communication_score: int
    strengths: List[str]
    weaknesses: List[str]
    final_feedback: str
    recommendation: str
    question_results: List[QuestionResult]
