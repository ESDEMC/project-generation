from pathlib import Path

from pygments.lexers import get_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound
from qtpy.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


LIGHT_STYLE_NAME = "default"
DARK_STYLE_NAME = "one-dark"


def style_name_for_background(background: QColor) -> str:
    """Return a Pygments style appropriate for the editor background."""
    return DARK_STYLE_NAME if background.lightness() < 128 else LIGHT_STYLE_NAME


class PygmentsSearchHighlighter(QSyntaxHighlighter):
    """Pygments syntax highlighting with non-invasive find-match overlays."""

    def __init__(self, document, path: Path, search_color: QColor, *, style_name: str = "default") -> None:
        super().__init__(document)
        self.lexer = self._lexer_for_path(path)
        self._style_name = style_name
        self._style = get_style_by_name(style_name)
        self._format_cache: dict[object, QTextCharFormat] = {}
        self._matches: tuple[tuple[int, int], ...] = ()
        self._current_match: tuple[int, int] | None = None

        self._match_format = QTextCharFormat()
        background = QColor(search_color)
        background.setAlpha(55)
        self._match_format.setBackground(background)

        self._current_format = QTextCharFormat()
        current_background = QColor(search_color)
        current_background.setAlpha(125)
        self._current_format.setBackground(current_background)
        self._current_format.setFontUnderline(True)

    @staticmethod
    def _lexer_for_path(path: Path):
        try:
            return get_lexer_for_filename(path.name)
        except ClassNotFound:
            return TextLexer()

    def set_style_name(self, style_name: str) -> None:
        if style_name == self._style_name:
            return
        self._style_name = style_name
        self._style = get_style_by_name(style_name)
        self._format_cache.clear()
        self.rehighlight()

    def set_matches(
        self, matches: list[tuple[int, int]] | tuple[tuple[int, int], ...], current_match: tuple[int, int] | None
    ) -> None:
        normalized = tuple(matches)
        if normalized == self._matches and current_match == self._current_match:
            return
        self._matches = normalized
        self._current_match = current_match
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for start, token_type, value in self.lexer.get_tokens_unprocessed(text):
            if not value:
                continue
            format_ = self._format_for_token(token_type)
            if not format_.isEmpty():
                self.setFormat(start, len(value), format_)

        self._apply_search_matches(text)

    def _format_for_token(self, token_type) -> QTextCharFormat:
        cached = self._format_cache.get(token_type)
        if cached is not None:
            return cached

        style_token = token_type
        while style_token not in self._style.styles and style_token.parent is not None:
            style_token = style_token.parent

        style = self._style.style_for_token(style_token)
        format_ = QTextCharFormat()
        color = style.get("color")
        if color:
            format_.setForeground(QColor(f"#{color}"))
        if style.get("bold"):
            format_.setFontWeight(QFont.Bold)
        if style.get("italic"):
            format_.setFontItalic(True)
        if style.get("underline"):
            format_.setFontUnderline(True)
        self._format_cache[token_type] = format_
        return format_

    def _apply_search_matches(self, text: str) -> None:
        if not self._matches:
            return

        block_start = self.currentBlock().position()
        block_end = block_start + len(text)
        for absolute_start, absolute_end in self._matches:
            start = max(absolute_start, block_start)
            end = min(absolute_end, block_end)
            if start >= end:
                continue

            local_start = start - block_start
            local_length = end - start
            overlay = (
                self._current_format
                if self._current_match == (absolute_start, absolute_end)
                else self._match_format
            )
            for offset in range(local_length):
                position = local_start + offset
                merged = QTextCharFormat(self.format(position))
                merged.merge(overlay)
                self.setFormat(position, 1, merged)
