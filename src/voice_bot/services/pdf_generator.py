"""WeasyPrint PDF generation service for rental request forms."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from voice_bot.exceptions import PDFGenerationError
from voice_bot.models import RentalRequestData

logger = structlog.get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_STATIC_DIR = Path(__file__).parent.parent / "static"
_TEMPLATE_NAME = "rental_request.html"
_CSS_FILENAME = "styles.css"


class PDFGeneratorService:
    """Synchronous PDF generator that renders Jinja2 HTML via WeasyPrint.

    The Jinja2 environment is created once in ``__init__`` and reused across
    calls.  CSS is read from ``static/styles.css`` and inlined into a
    ``<style>`` tag so WeasyPrint can render without external URL fetching.
    """

    def __init__(self) -> None:
        """Set up the Jinja2 environment and load the CSS stylesheet."""
        self._template_dir: Path = _TEMPLATE_DIR
        self._static_dir: Path = _STATIC_DIR

        self._env: Environment = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        self._css_content: str = self._read_css()

    def _read_css(self) -> str:
        """Read and return the contents of ``styles.css``.

        Raises:
            PDFGenerationError: If the CSS file cannot be read.
        """
        css_path = self._static_dir / _CSS_FILENAME
        try:
            return css_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(
                "pdf_css_read_failed",
                css_path=str(css_path),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise PDFGenerationError(
                f"Failed to read CSS file: {css_path}",
                cause=exc,
            ) from exc

    def generate(self, data: RentalRequestData) -> bytes:
        """Render the rental request HTML template and produce a PDF.

        Parameters:
            data: The structured rental request data to render.

        Returns:
            PDF document as ``bytes``.

        Raises:
            PDFGenerationError: If template rendering or PDF generation fails.
        """
        logger.debug(
            "pdf_generation_start",
            client_name=data.client_name,
            equipment_count=len(data.equipment),
            urgency=data.urgency,
        )

        try:
            template = self._env.get_template(_TEMPLATE_NAME)
            rendered_html = template.render(
                data=data,
                generated_at=datetime.now(),
            )
        except Exception as exc:
            logger.error(
                "pdf_template_render_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise PDFGenerationError(
                f"Template rendering failed: {exc}",
                cause=exc,
            ) from exc

        html_with_css = self._inline_css(rendered_html)

        try:
            pdf_bytes = HTML(
                string=html_with_css,
                base_url=str(self._template_dir),
            ).write_pdf()
        except Exception as exc:
            logger.error(
                "pdf_weasyprint_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise PDFGenerationError(
                f"WeasyPrint rendering failed: {exc}",
                cause=exc,
            ) from exc

        logger.info(
            "pdf_generation_success",
            pdf_size=len(pdf_bytes),
        )

        return pdf_bytes

    def _inline_css(self, html: str) -> str:
        """Inject the CSS content into the HTML ``<style>`` tag.

        Replaces the ``<link rel="stylesheet" href="styles.css">`` tag with
        an inline ``<style>`` block so WeasyPrint does not need to fetch
        the stylesheet via URL.

        Parameters:
            html: The rendered HTML string with a ``<link>`` stylesheet tag.

        Returns:
            HTML string with CSS inlined in a ``<style>`` tag.
        """
        link_tag = '<link rel="stylesheet" href="styles.css">'
        style_tag = f"<style>\n{self._css_content}\n</style>"
        return html.replace(link_tag, style_tag)


def create_pdf_generator() -> PDFGeneratorService:
    """Create a ``PDFGeneratorService`` instance."""
    return PDFGeneratorService()
