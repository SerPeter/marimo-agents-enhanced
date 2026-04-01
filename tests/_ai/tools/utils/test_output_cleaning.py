# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from marimo._ai._tools.utils.output_cleaning import (
    clean_output,
    deduplicate_lines,
    mask_visual_output,
    normalize_progress_bars,
    strip_ansi_codes,
    truncate_output,
)


class TestStripAnsiCodes:
    def test_removes_color_codes(self) -> None:
        lines = ["\x1b[31mError\x1b[0m", "\x1b[32mSuccess\x1b[0m"]
        result = strip_ansi_codes(lines)
        assert result == ["Error", "Success"]

    def test_removes_bold_codes(self) -> None:
        lines = ["\x1b[1mBold text\x1b[0m"]
        result = strip_ansi_codes(lines)
        assert result == ["Bold text"]

    def test_removes_cursor_movement(self) -> None:
        lines = ["\x1b[2JCleared\x1b[H"]
        result = strip_ansi_codes(lines)
        assert result == ["Cleared"]

    def test_handles_no_ansi_codes(self) -> None:
        lines = ["Plain text", "No codes here"]
        result = strip_ansi_codes(lines)
        assert result == ["Plain text", "No codes here"]

    def test_empty_list(self) -> None:
        assert strip_ansi_codes([]) == []


class TestDeduplicateLines:
    def test_single_line(self) -> None:
        assert deduplicate_lines(["Hello"]) == ["Hello"]

    def test_two_identical_lines(self) -> None:
        result = deduplicate_lines(["Warning", "Warning"])
        assert result == ["Warning", "(repeated 2 times)"]

    def test_two_different_lines(self) -> None:
        result = deduplicate_lines(["Line 1", "Line 2"])
        assert result == ["Line 1", "Line 2"]

    def test_multiple_groups(self) -> None:
        lines = ["A", "A", "B", "B", "B", "C"]
        result = deduplicate_lines(lines)
        assert result == [
            "A",
            "(repeated 2 times)",
            "B",
            "(repeated 3 times)",
            "C",
        ]

    def test_all_identical(self) -> None:
        result = deduplicate_lines(["Same"] * 10)
        assert result == ["Same", "(repeated 10 times)"]

    def test_no_duplicates(self) -> None:
        lines = ["A", "B", "C", "D"]
        result = deduplicate_lines(lines)
        assert result == ["A", "B", "C", "D"]

    def test_empty_strings(self) -> None:
        lines = ["", "", "Text", "", ""]
        result = deduplicate_lines(lines)
        assert result == [
            "",
            "(repeated 2 times)",
            "Text",
            "",
            "(repeated 2 times)",
        ]

    def test_empty_list(self) -> None:
        assert deduplicate_lines([]) == []


class TestNormalizeProgressBars:
    def test_simple_carriage_return(self) -> None:
        lines = ["0%\r50%\r100%"]
        result = normalize_progress_bars(lines)
        assert result == ["100%"]

    def test_mixed_lines(self) -> None:
        lines = ["Start", "0%\r50%\r100%", "End"]
        result = normalize_progress_bars(lines)
        assert result == ["Start", "100%", "End"]

    def test_removes_empty_lines(self) -> None:
        lines = ["Text", "", "   ", "More"]
        result = normalize_progress_bars(lines)
        assert result == ["Text", "More"]

    def test_tqdm_style(self) -> None:
        lines = [
            "  0%|          | 0/100\r 50%|█████     | 50/100\r100%|██████████| 100/100"
        ]
        result = normalize_progress_bars(lines)
        assert result == ["100%|██████████| 100/100"]

    def test_no_carriage_returns(self) -> None:
        lines = ["Line 1", "Line 2"]
        result = normalize_progress_bars(lines)
        assert result == ["Line 1", "Line 2"]

    def test_empty_list(self) -> None:
        assert normalize_progress_bars([]) == []


class TestTruncateOutput:
    def test_no_truncation_when_under_limit(self) -> None:
        lines = [f"Line {i}" for i in range(5)]
        result = truncate_output(lines, max_lines=10)
        assert result == lines

    def test_truncates_middle(self) -> None:
        lines = [f"Line {i}" for i in range(1, 11)]
        result = truncate_output(lines, max_lines=5)
        assert len(result) == 6
        assert result[0] == "Line 1"
        assert result[1] == "Line 2"
        assert "truncated" in result[2]
        assert result[-2] == "Line 9"
        assert result[-1] == "Line 10"

    def test_keeps_head_and_tail(self) -> None:
        lines = [f"Epoch {i}" for i in range(1, 21)]
        result = truncate_output(lines, max_lines=6)
        assert result[0] == "Epoch 1"
        assert result[1] == "Epoch 2"
        assert result[2] == "Epoch 3"
        assert "truncated 14 lines" in result[3]
        assert result[-3] == "Epoch 18"
        assert result[-2] == "Epoch 19"
        assert result[-1] == "Epoch 20"

    def test_shows_correct_count(self) -> None:
        lines = ["x"] * 100
        result = truncate_output(lines, max_lines=10)
        assert any("truncated 90 lines" in line for line in result)

    def test_empty_list(self) -> None:
        assert truncate_output([]) == []


class TestMaskVisualOutput:
    def test_small_html_passes_through(self) -> None:
        data = "<div>hello</div>"
        result, masked = mask_visual_output(data, "text/html")
        assert result == data
        assert masked is False

    def test_large_html_converted_to_markdown(self) -> None:
        data = "<div>" + "x" * 6000 + "</div>"
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert result.startswith("[Parsed from HTML output]")
        assert "x" in result  # text content preserved

    def test_large_html_table_to_markdown(self) -> None:
        rows = "".join(
            f"<tr><td>row{i}</td><td>{i}</td></tr>" for i in range(200)
        )
        data = f"<table><tr><th>Name</th><th>Value</th></tr>{rows}</table>"
        result, masked = mask_visual_output(data, "text/html", threshold=100)
        assert masked is True
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| row0 | 0 |" in result

    def test_large_html_preserves_headings(self) -> None:
        data = "<h1>Title</h1><p>" + "x" * 6000 + "</p>"
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert "# Title" in result

    def test_large_html_preserves_links(self) -> None:
        data = '<a href="https://example.com">click</a>' + "x" * 6000
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert "[click](https://example.com)" in result

    def test_large_html_truncated_when_huge(self) -> None:
        # Even after conversion, very large text gets truncated
        data = "<div>" + "word " * 20000 + "</div>"
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert "truncated" in result

    def test_large_svg_is_masked(self) -> None:
        data = "<svg>" + "x" * 6000 + "</svg>"
        result, masked = mask_visual_output(data, "image/svg+xml")
        assert masked is True
        assert "image/svg+xml" in result

    def test_large_image_is_masked(self) -> None:
        data = "data:image/png;base64," + "A" * 6000
        result, masked = mask_visual_output(data, "image/png")
        assert masked is True

    def test_text_plain_never_masked(self) -> None:
        data = "x" * 10000
        result, masked = mask_visual_output(data, "text/plain")
        assert result == data
        assert masked is False

    def test_text_markdown_never_masked(self) -> None:
        data = "# heading\n" * 1000
        result, masked = mask_visual_output(data, "text/markdown")
        assert result == data
        assert masked is False

    def test_small_json_passes_through(self) -> None:
        data = '{"key": "value"}'
        result, masked = mask_visual_output(data, "application/json")
        assert result == data
        assert masked is False

    def test_large_json_is_truncated(self) -> None:
        data = '{"key": "' + "v" * 10000 + '"}'
        result, masked = mask_visual_output(data, "application/json")
        assert masked is True
        assert result.startswith('{"key": "')
        assert "more chars]" in result
        assert len(result) < len(data)

    def test_large_vegalite_is_truncated(self) -> None:
        data = '{"$schema": "vegalite", "data": "' + "x" * 10000 + '"}'
        result, masked = mask_visual_output(
            data, "application/vnd.vegalite.v5+json"
        )
        assert masked is True
        assert result.startswith('{"$schema":')
        assert "more chars]" in result

    def test_custom_threshold(self) -> None:
        data = "<div>" + "x" * 200 + "</div>"
        result, masked = mask_visual_output(data, "text/html", threshold=100)
        assert masked is True

    def test_at_threshold_not_masked(self) -> None:
        # Exactly at threshold should not be masked
        data = "x" * 5120
        result, masked = mask_visual_output(data, "text/html", threshold=5120)
        assert masked is False

    def test_accordion_labels_extracted(self) -> None:
        labels_json = '"labels": ["Overview", "Details", "Charts"]'
        data = (
            "<marimo-accordion "
            + labels_json
            + ">"
            + "x" * 6000
            + "</marimo-accordion>"
        )
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert "Sections: Overview, Details, Charts" in result

    def test_accordion_without_labels(self) -> None:
        data = "<marimo-accordion>" + "x" * 6000 + "</marimo-accordion>"
        result, masked = mask_visual_output(data, "text/html")
        assert masked is True
        assert "Sections:" not in result

    def test_small_csv_passes_through(self) -> None:
        data = "a,b\n1,2\n3,4\n"
        result, masked = mask_visual_output(data, "text/csv")
        assert result == data
        assert masked is False

    def test_large_csv_truncated_to_100_rows(self) -> None:
        header = "col_a,col_b\n"
        rows = "".join(f"{i},{i * 2}\n" for i in range(200))
        data = header + rows
        result, masked = mask_visual_output(data, "text/csv", threshold=100)
        assert masked is True
        # Header + 100 data rows kept
        result_lines = result.rstrip().splitlines()
        assert result_lines[0] == "col_a,col_b"
        assert result_lines[1] == "0,0"
        assert result_lines[100] == "99,198"
        assert "100 more rows" in result_lines[-1]


class TestCleanOutput:
    def test_full_pipeline_with_ansi_and_duplicates(self) -> None:
        lines = [
            "\x1b[32mStart\x1b[0m",
            "\x1b[33mWarning\x1b[0m",
            "\x1b[33mWarning\x1b[0m",
            "\x1b[33mWarning\x1b[0m",
        ]
        result = clean_output(lines)
        assert result == ["Start", "Warning", "(repeated 3 times)"]

    def test_full_pipeline_with_progress_bars(self) -> None:
        lines = [
            "Training",
            "0%\r50%\r100%",
            "Complete",
        ]
        result = clean_output(lines)
        assert result == ["Training", "100%", "Complete"]

    def test_combined_ml_workflow(self) -> None:
        lines = [
            "\x1b[1mEpoch 1/10\x1b[0m",
            "0%|          | 0/100\r100%|██████████| 100/100",
            "\x1b[34mLoss: 0.543\x1b[0m",
            "\x1b[1mEpoch 2/10\x1b[0m",
            "0%|          | 0/100\r100%|██████████| 100/100",
            "\x1b[34mLoss: 0.432\x1b[0m",
        ]
        result = clean_output(lines)
        assert result == [
            "Epoch 1/10",
            "100%|██████████| 100/100",
            "Loss: 0.543",
            "Epoch 2/10",
            "100%|██████████| 100/100",
            "Loss: 0.432",
        ]

    def test_empty_list(self) -> None:
        assert clean_output([]) == []
