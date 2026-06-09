import json
import pytest
from unittest.mock import MagicMock, patch

from utils.question_gen import generate_questions, Question


MOCK_CHOICE_JSON = json.dumps([
    {
        "question_type": "choice",
        "question": "What is 2+2?",
        "options": ["A. 2", "B. 3", "C. 4", "D. 5"],
        "correct_index": 2,
        "explanation": "Basic arithmetic."
    },
    {
        "question_type": "true_false",
        "question": "判断正误：地球是平的。",
        "options": ["A. 正确", "B. 错误"],
        "correct_index": 1,
        "explanation": "科学常识。"
    },
    {
        "question_type": "fill_blank",
        "question": "法国的首都是（___）。",
        "correct_answer": "巴黎",
        "acceptable_answers": ["Paris", "巴黎市"],
        "explanation": "地理知识。"
    }
])

SHORT_TEXT = "Artificial intelligence is transforming many industries. Machine learning enables computers to learn from data. Deep learning uses neural networks with multiple layers."


class TestGenerateQuestionsIntegration:
    @patch("utils.question_gen.OpenAI")
    def test_generates_all_question_types(self, mock_openai):
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = MOCK_CHOICE_JSON
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai.return_value = mock_instance

        questions = generate_questions(SHORT_TEXT, num_questions=3, difficulty=3)

        assert len(questions) == 3
        assert questions[0].question_type == "choice"
        assert questions[0].question == "What is 2+2?"
        assert questions[0].options == ["A. 2", "B. 3", "C. 4", "D. 5"]
        assert questions[0].correct_index == 2

        assert questions[1].question_type == "true_false"
        assert questions[1].correct_index == 1

        assert questions[2].question_type == "fill_blank"
        assert questions[2].correct_answer == "巴黎"
        assert "Paris" in questions[2].acceptable_answers

    @patch("utils.question_gen.OpenAI")
    def test_short_text_raises_value_error(self, mock_openai):
        with pytest.raises(ValueError, match="文本内容太短"):
            generate_questions("too short", num_questions=3)

    @patch("utils.question_gen.OpenAI")
    def test_empty_response_raises_error(self, mock_openai):
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai.return_value = mock_instance

        with pytest.raises(ValueError, match="AI 返回格式异常"):
            generate_questions(SHORT_TEXT, num_questions=3)

    @patch("utils.question_gen.OpenAI")
    def test_invalid_json_response_raises_error(self, mock_openai):
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "not valid json at all"
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai.return_value = mock_instance

        with pytest.raises(ValueError, match="AI 返回格式异常"):
            generate_questions(SHORT_TEXT, num_questions=3)

    @patch("utils.question_gen.OpenAI")
    def test_network_error_raises_runtime_error(self, mock_openai):
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = Exception("Connection timeout")
        mock_openai.return_value = mock_instance

        with pytest.raises(RuntimeError, match="调用 AI 接口失败"):
            generate_questions(SHORT_TEXT, num_questions=3)

    @patch("utils.question_gen.OpenAI")
    def test_single_choice_question(self, mock_openai):
        single_json = json.dumps([
            {
                "question_type": "choice",
                "question": "What is ML?",
                "options": ["A. Machine Learning", "B. Manual Labor", "C. More Laughs", "D. Major League"],
                "correct_index": 0,
                "explanation": "ML stands for Machine Learning."
            }
        ])
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = single_json
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai.return_value = mock_instance

        questions = generate_questions(SHORT_TEXT, num_questions=1)
        assert len(questions) == 1
        assert isinstance(questions[0], Question)
        assert questions[0].question_type == "choice"
        assert questions[0].correct_index == 0

    @patch("utils.question_gen.OpenAI")
    def test_api_called_with_correct_parameters(self, mock_openai):
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = MOCK_CHOICE_JSON
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_openai.return_value = mock_instance

        generate_questions(SHORT_TEXT, num_questions=3, difficulty=3, language="zh", model="gpt-4o-mini")

        call_kwargs = mock_instance.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["temperature"] == 0.7
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
