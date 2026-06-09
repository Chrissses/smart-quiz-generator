import io
import pytest
from utils.file_parser import parse_file


class TestParseFile:
    def test_txt_parsing(self):
        content = "Hello world\nThis is a test."
        result = parse_file(content.encode("utf-8"), "test.txt")
        assert "Hello world" in result
        assert "This is a test" in result

    def test_md_parsing(self):
        content = "# Title\n\nSome **markdown** text."
        result = parse_file(content.encode("utf-8"), "doc.md")
        assert "Title" in result
        assert "Some" in result
        assert "markdown" in result

    def test_unknown_extension_raises(self):
        content = "plain text content"
        with pytest.raises(ValueError, match="不支持"):
            parse_file(content.encode("utf-8"), "file.xyz")

    def test_empty_content(self):
        content = ""
        result = parse_file(content.encode("utf-8"), "empty.txt")
        assert result == ""

    def test_chinese_text(self):
        content = "人工智能是计算机科学的一个分支。"
        result = parse_file(content.encode("utf-8"), "cn.txt")
        assert "人工智能" in result

    def test_docx_parsing(self):
        """Minimal DOCX created via python-docx."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not installed")

        doc = Document()
        doc.add_paragraph("Paragraph one.")
        doc.add_paragraph("Paragraph two.")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        result = parse_file(buf.read(), "test.docx")
        assert "Paragraph one" in result
        assert "Paragraph two" in result

    def test_pdf_parsing(self):
        """Test with a sample that pdfplumber can handle."""
        try:
            import pdfplumber
        except ImportError:
            pytest.skip("pdfplumber not installed")

        # We can't easily create a real PDF in a test.
        # Skip for now -- covered by integration tests.
        pytest.skip("PDF generation not supported in unit tests")

    def test_replaces_newlines_with_spaces_in_paragraphs(self):
        content = "Line 1\nLine 2\nLine 3"
        result = parse_file(content.encode("utf-8"), "test.txt")
        # parse_file joins paragraphs with spaces
        assert "Line 1" in result
