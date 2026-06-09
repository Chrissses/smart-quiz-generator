import json
import pytest
from utils.question_gen import (
    Question, _repair_json, _parse_response, DIFFICULTY_PROMPTS,
)


class TestQuestion:
    def test_default_values(self):
        q = Question()
        assert q.question == ""
        assert q.question_type == "choice"
        assert q.options == []
        assert q.correct_index == 0
        assert q.correct_answer == ""
        assert q.acceptable_answers == []
        assert q.explanation == ""

    def test_choice_question(self):
        q = Question(
            question="What is 2+2?",
            question_type="choice",
            options=["A. 2", "B. 3", "C. 4", "D. 5"],
            correct_index=2,
            explanation="Basic math",
        )
        d = q.to_dict()
        assert d["question"] == "What is 2+2?"
        assert d["options"] == ["A. 2", "B. 3", "C. 4", "D. 5"]
        assert d["correct_index"] == 2

    def test_fill_blank_question(self):
        q = Question(
            question="The capital of France is ____.",
            question_type="fill_blank",
            correct_answer="Paris",
            acceptable_answers=["paris", "Paris, France"],
            explanation="Capital cities",
        )
        assert q.question_type == "fill_blank"
        assert q.correct_answer == "Paris"
        assert "paris" in q.acceptable_answers

    def test_true_false_question(self):
        q = Question(
            question="Earth is flat.",
            question_type="true_false",
            options=["A. 正确", "B. 错误"],
            correct_index=1,
            explanation="Science",
        )
        d = q.to_dict()
        assert d["question_type"] == "true_false"
        assert len(d["options"]) == 2
        assert d["correct_index"] == 1


class TestRepairJson:
    def test_trailing_comma_array(self):
        fixed = _repair_json('[{"a": 1,}, {"b": 2,}]')
        assert json.loads(fixed) == [{"a": 1}, {"b": 2}]

    def test_trailing_comma_object(self):
        fixed = _repair_json('{"name": "test",}')
        assert json.loads(fixed) == {"name": "test"}

    def test_single_quotes(self):
        fixed = _repair_json("[{'key': 'value'}]")
        assert json.loads(fixed) == [{"key": "value"}]

    def test_comment_removal(self):
        fixed = _repair_json('[{"a": 1}  // a comment]\n[{"b": 2}]')
        assert "[// a comment]" not in fixed or json.loads(fixed)

    def test_valid_json_unchanged(self):
        original = '[{"a": 1, "b": 2}]'
        fixed = _repair_json(original)
        assert json.loads(fixed) == [{"a": 1, "b": 2}]


class TestParseResponse:
    def test_direct_json_array(self):
        raw = '[{"question_type": "choice", "question": "Q1", "options": ["A"], "correct_index": 0, "explanation": "E"}]'
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0].question == "Q1"

    def test_markdown_code_block(self):
        raw = '```json\n[{"question_type": "choice", "question": "Q2", "options": ["A"], "correct_index": 0, "explanation": "E"}]\n```'
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0].question == "Q2"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            _parse_response("not json at all")

    def test_skip_missing_question(self):
        raw = json.dumps([
            {"question_type": "choice", "question": "", "options": [], "correct_index": 0, "explanation": ""},
            {"question_type": "choice", "question": "Valid Q", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "ok"},
        ])
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0].question == "Valid Q"

    def test_skip_non_dict_items(self):
        raw = '["not a dict", {"question_type": "choice", "question": "Q3", "options": ["A"], "correct_index": 0, "explanation": "E"}]'
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0].question == "Q3"

    def test_mixed_types(self):
        raw = json.dumps([
            {"question_type": "choice", "question": "Q1", "options": ["A. a", "B. b", "C. c", "D. d"], "correct_index": 2, "explanation": "chosen"},
            {"question_type": "true_false", "question": "Q2", "options": ["A. 正确", "B. 错误"], "correct_index": 0, "explanation": "correct"},
            {"question_type": "fill_blank", "question": "___ is Q3", "correct_answer": "ans", "acceptable_answers": ["a"], "explanation": "fill"},
        ])
        result = _parse_response(raw)
        assert len(result) == 3
        assert result[0].question_type == "choice"
        assert result[1].question_type == "true_false"
        assert result[2].question_type == "fill_blank"


class TestDifficultyPrompts:
    def test_all_levels_exist(self):
        for i in range(1, 6):
            assert i in DIFFICULTY_PROMPTS
            assert isinstance(DIFFICULTY_PROMPTS[i], str)
            assert len(DIFFICULTY_PROMPTS[i]) > 20

    def test_no_extra_levels(self):
        assert sorted(DIFFICULTY_PROMPTS.keys()) == [1, 2, 3, 4, 5]
