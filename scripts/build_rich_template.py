"""
Build a rich, beautifully-styled test template (test_template_rich.pptx).

This script programmatically generates a PPTX with a consistent modern design
(navy + coral + cream palette), distinct layouts, and sample content that
demonstrates each layout's intent. It exercises every layout type the
template_analyzer can classify:

    - title_slide       (center_title + subtitle, dark hero background)
    - section_header    (title + body text, brand-colored divider)
    - content           (title + single object/content placeholder for bullets)
    - two_column        (title + two content placeholders side-by-side)
    - title_only        (title placeholder only — big statement / quote)
    - image_right       (title + body + picture placeholder on the right)

Run:
    python scripts/build_rich_template.py
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt


# --- Design system ----------------------------------------------------------

NAVY = RGBColor(0x0B, 0x1F, 0x3A)        # deep navy — primary dark
INK = RGBColor(0x14, 0x2A, 0x4C)         # body dark
CORAL = RGBColor(0xFF, 0x6B, 0x6B)       # coral — accent
GOLD = RGBColor(0xF5, 0xC6, 0x5A)        # gold — secondary accent
CREAM = RGBColor(0xF7, 0xF3, 0xEC)       # cream — light background
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY = RGBColor(0x6B, 0x72, 0x80)

SLIDE_W = Inches(13.333)  # 16:9 widescreen
SLIDE_H = Inches(7.5)


# --- Helpers ----------------------------------------------------------------

def _set_slide_bg(slide, color: RGBColor) -> None:
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rect(slide, left, top, width, height, fill: RGBColor, line=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
    shape.shadow.inherit = False
    return shape


def _style_run(run, *, size=18, bold=False, color=INK, name="Calibri"):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _set_textframe(tf, text, *, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT,
                   anchor=MSO_ANCHOR.TOP, name="Calibri"):
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    if p.runs:
        run = p.runs[0]
        run.text = text
    else:
        run = p.add_run()
        run.text = text
    _style_run(run, size=size, bold=bold, color=color, name=name)


def _accent_bar(slide, left, top, width=Inches(0.15), height=Inches(0.6), color=CORAL):
    _add_rect(slide, left, top, width, height, color)


# --- Layout builders --------------------------------------------------------
#
# We build layout-like slides by writing a full slide set. The template_parser
# reads the presentation's actual slides, so each slide here acts as both a
# visual example and a layout signal.
#
# Note: python-pptx lets us pick a slide layout from prs.slide_layouts by
# index. The default PPTX template comes with a standard set:
#   0: Title Slide           -> center_title + subtitle
#   1: Title and Content     -> title + content/object
#   2: Section Header        -> title + body (text)
#   3: Two Content           -> title + two object placeholders
#   4: Comparison            -> title + two object + two text
#   5: Title Only            -> title only
#   6: Blank
#   7: Content with Caption  -> title + body + object
#   8: Picture with Caption  -> title + body + picture
#
# We use layouts 0, 1, 2, 3, 5, 8 and decorate each slide heavily.


def build_title_slide(prs: Presentation) -> None:
    layout = prs.slide_layouts[0]  # Title Slide
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, NAVY)

    # Decorative accent shapes
    _add_rect(slide, Inches(0), Inches(0), Inches(0.35), SLIDE_H, CORAL)
    _add_rect(slide, Inches(12.2), Inches(6.6), Inches(0.9), Inches(0.15), GOLD)
    _add_rect(slide, Inches(11.0), Inches(6.85), Inches(2.1), Inches(0.05), CORAL)

    # Title placeholder (center_title, idx 0)
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(0.8)
    title_ph.top = Inches(2.4)
    title_ph.width = Inches(11.5)
    title_ph.height = Inches(1.8)
    _set_textframe(
        title_ph.text_frame,
        "Aurora 2026 — Annual Business Review",
        size=54, bold=True, color=WHITE, align=PP_ALIGN.LEFT, name="Calibri",
    )

    # Subtitle placeholder (idx 1)
    subtitle_ph = slide.placeholders[1]
    subtitle_ph.left = Inches(0.8)
    subtitle_ph.top = Inches(4.3)
    subtitle_ph.width = Inches(11.5)
    subtitle_ph.height = Inches(1.2)
    _set_textframe(
        subtitle_ph.text_frame,
        "Strategy, performance and roadmap for the year ahead",
        size=24, bold=False, color=GOLD, align=PP_ALIGN.LEFT,
    )

    # Small footer text (non-placeholder decoration)
    tb = slide.shapes.add_textbox(Inches(0.8), Inches(6.4), Inches(6), Inches(0.5))
    _set_textframe(tb.text_frame, "Prepared by the Executive Office  ·  April 2026",
                   size=14, color=CREAM, align=PP_ALIGN.LEFT)


def build_section_header(prs: Presentation, number: str, heading: str, blurb: str) -> None:
    layout = prs.slide_layouts[2]  # Section Header
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, CREAM)

    # Left color band with section number
    _add_rect(slide, Inches(0), Inches(0), Inches(4.5), SLIDE_H, NAVY)
    num_tb = slide.shapes.add_textbox(Inches(0.6), Inches(2.6), Inches(3.5), Inches(2.0))
    _set_textframe(num_tb.text_frame, number, size=140, bold=True, color=CORAL,
                   align=PP_ALIGN.LEFT)

    # Title placeholder (idx 0)
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(5.0)
    title_ph.top = Inches(2.6)
    title_ph.width = Inches(7.9)
    title_ph.height = Inches(1.4)
    _set_textframe(title_ph.text_frame, heading, size=44, bold=True, color=NAVY,
                   align=PP_ALIGN.LEFT)

    # Body placeholder (text, idx 1)
    body_ph = slide.placeholders[1]
    body_ph.left = Inches(5.0)
    body_ph.top = Inches(4.1)
    body_ph.width = Inches(7.9)
    body_ph.height = Inches(1.6)
    _set_textframe(body_ph.text_frame, blurb, size=20, color=GRAY, align=PP_ALIGN.LEFT)

    # Gold underline accent
    _add_rect(slide, Inches(5.0), Inches(4.0), Inches(1.2), Inches(0.08), GOLD)


def build_content_slide(prs: Presentation, title: str, bullets: list[str]) -> None:
    layout = prs.slide_layouts[1]  # Title and Content
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, WHITE)

    # Top accent bar
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.25), CORAL)
    # Side accent
    _accent_bar(slide, Inches(0.6), Inches(0.9), color=GOLD, height=Inches(0.7))

    # Title (idx 0)
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(0.9)
    title_ph.top = Inches(0.75)
    title_ph.width = Inches(11.5)
    title_ph.height = Inches(1.0)
    _set_textframe(title_ph.text_frame, title, size=32, bold=True, color=NAVY,
                   align=PP_ALIGN.LEFT)

    # Content / object (idx 1) — bullet list
    body_ph = slide.placeholders[1]
    body_ph.left = Inches(0.9)
    body_ph.top = Inches(1.9)
    body_ph.width = Inches(11.5)
    body_ph.height = Inches(5.1)
    tf = body_ph.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.level = 0
        run = p.runs[0] if p.runs else p.add_run()
        run.text = b
        _style_run(run, size=22, color=INK)
        p.space_after = Pt(10)

    # Bottom footer
    _add_rect(slide, Inches(0), Inches(7.25), SLIDE_W, Inches(0.25), NAVY)


def build_two_column(prs: Presentation, title: str,
                     left_title: str, left_bullets: list[str],
                     right_title: str, right_bullets: list[str]) -> None:
    layout = prs.slide_layouts[3]  # Two Content
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, WHITE)

    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.25), CORAL)

    # Title (idx 0)
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(0.9)
    title_ph.top = Inches(0.75)
    title_ph.width = Inches(11.5)
    title_ph.height = Inches(1.0)
    _set_textframe(title_ph.text_frame, title, size=32, bold=True, color=NAVY,
                   align=PP_ALIGN.LEFT)

    def fill_column(ph, col_title: str, items: list[str], accent: RGBColor):
        tf = ph.text_frame
        tf.word_wrap = True
        # Title line
        p0 = tf.paragraphs[0]
        p0.alignment = PP_ALIGN.LEFT
        r0 = p0.runs[0] if p0.runs else p0.add_run()
        r0.text = col_title
        _style_run(r0, size=22, bold=True, color=accent)
        p0.space_after = Pt(10)
        for b in items:
            p = tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = "• " + b
            _style_run(r, size=18, color=INK)
            p.space_after = Pt(6)

    # The Two Content layout usually gives placeholders at idx 1 and idx 2.
    left_ph = slide.placeholders[1]
    right_ph = slide.placeholders[2]

    left_ph.left = Inches(0.9)
    left_ph.top = Inches(1.9)
    left_ph.width = Inches(5.8)
    left_ph.height = Inches(5.1)

    right_ph.left = Inches(6.8)
    right_ph.top = Inches(1.9)
    right_ph.width = Inches(5.8)
    right_ph.height = Inches(5.1)

    fill_column(left_ph, left_title, left_bullets, CORAL)
    fill_column(right_ph, right_title, right_bullets, NAVY)

    # Divider
    _add_rect(slide, Inches(6.65), Inches(2.1), Inches(0.04), Inches(4.8), GOLD)

    _add_rect(slide, Inches(0), Inches(7.25), SLIDE_W, Inches(0.25), NAVY)


def build_title_only(prs: Presentation, statement: str, attribution: str) -> None:
    layout = prs.slide_layouts[5]  # Title Only
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, NAVY)

    # Oversized quotation accent
    quote = slide.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(3), Inches(3))
    _set_textframe(quote.text_frame, "\u201C", size=220, bold=True, color=CORAL,
                   align=PP_ALIGN.LEFT)

    # Title (idx 0) — used as the big statement
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(1.2)
    title_ph.top = Inches(2.3)
    title_ph.width = Inches(11.0)
    title_ph.height = Inches(3.4)
    _set_textframe(title_ph.text_frame, statement, size=40, bold=True, color=WHITE,
                   align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # Attribution as a decorative textbox (not a placeholder)
    attr = slide.shapes.add_textbox(Inches(1.2), Inches(5.9), Inches(11), Inches(0.6))
    _set_textframe(attr.text_frame, attribution, size=18, color=GOLD,
                   align=PP_ALIGN.LEFT)

    _add_rect(slide, Inches(1.2), Inches(5.8), Inches(0.8), Inches(0.05), CORAL)


def build_picture_caption(prs: Presentation, title: str, caption: str) -> None:
    layout = prs.slide_layouts[8]  # Picture with Caption
    slide = prs.slides.add_slide(layout)
    _set_slide_bg(slide, CREAM)

    _add_rect(slide, Inches(0), Inches(0), Inches(0.25), SLIDE_H, CORAL)

    # Title (idx 0)
    title_ph = slide.placeholders[0]
    title_ph.left = Inches(0.9)
    title_ph.top = Inches(0.7)
    title_ph.width = Inches(11.5)
    title_ph.height = Inches(0.9)
    _set_textframe(title_ph.text_frame, title, size=30, bold=True, color=NAVY,
                   align=PP_ALIGN.LEFT)

    # Picture placeholder is idx 1 by default in layout 8
    try:
        pic_ph = slide.placeholders[1]
        pic_ph.left = Inches(0.9)
        pic_ph.top = Inches(1.8)
        pic_ph.width = Inches(7.0)
        pic_ph.height = Inches(5.1)
    except KeyError:
        pass

    # Caption / body placeholder
    try:
        cap_ph = slide.placeholders[2]
        cap_ph.left = Inches(8.2)
        cap_ph.top = Inches(1.9)
        cap_ph.width = Inches(4.3)
        cap_ph.height = Inches(4.8)
        _set_textframe(cap_ph.text_frame, caption, size=18, color=INK,
                       align=PP_ALIGN.LEFT)
    except KeyError:
        pass

    _add_rect(slide, Inches(8.2), Inches(1.7), Inches(0.8), Inches(0.08), GOLD)


# --- Main build -------------------------------------------------------------

def build(out_path: Path) -> Path:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # 1. Title slide
    build_title_slide(prs)

    # 2. Section header
    build_section_header(
        prs,
        "01",
        "Executive Summary",
        "A concise overview of the year's performance and priorities for the quarters ahead.",
    )

    # 3. Content slide — bullet example
    build_content_slide(
        prs,
        "Highlights at a Glance",
        [
            "Revenue grew 34% YoY, reaching $248M in annual recurring revenue",
            "Net revenue retention improved to 128%, led by the enterprise segment",
            "Shipped 42 major product releases across four product lines",
            "Expanded into APAC with offices in Singapore and Tokyo",
            "Team grew from 310 to 540 people across 18 countries",
        ],
    )

    # 4. Two-column comparison
    build_two_column(
        prs,
        "2025 Results vs. 2026 Targets",
        "2025 Actuals",
        [
            "ARR: $185M",
            "Customers: 1,240",
            "Enterprise mix: 41%",
            "Gross margin: 72%",
        ],
        "2026 Targets",
        [
            "ARR: $310M (+67%)",
            "Customers: 1,800",
            "Enterprise mix: 55%",
            "Gross margin: 76%",
        ],
    )

    # 5. Title-only statement
    build_title_only(
        prs,
        "We win when our customers ship faster — that is the entire\u202fjob.",
        "— Leadership Offsite, February 2026",
    )

    # 6. Picture with caption
    build_picture_caption(
        prs,
        "Product Spotlight: Aurora Studio 3",
        "A rebuilt workspace that brings planning, authoring and review into a "
        "single canvas. Early-access customers report a 3.1× reduction in "
        "round-trips between design and engineering.",
    )

    # 7. Another section header
    build_section_header(
        prs,
        "02",
        "Market & Customers",
        "Where we are winning, where we are behind, and how the customer base is evolving.",
    )

    # 8. Content slide — market
    build_content_slide(
        prs,
        "Market Landscape",
        [
            "Total addressable market estimated at $48B, growing 19% annually",
            "Top three competitors control 38% of the enterprise segment",
            "Mid-market is consolidating: 7 notable M&A events in the past year",
            "Buyer priorities have shifted toward integrated, AI-native workflows",
            "Security and data residency now rank in the top three buying criteria",
        ],
    )

    # 9. Two-column — wins & losses
    build_two_column(
        prs,
        "Where We Are Winning vs. Where We Must Improve",
        "Winning",
        [
            "Fastest onboarding in the category (4.2 days median)",
            "Highest NPS in the segment (+61)",
            "Deep integrations with the top five data warehouses",
        ],
        "Must Improve",
        [
            "Mobile experience lags behind competitors",
            "Partner channel contributes only 12% of new ARR",
            "Localization coverage: 11 languages vs. 22 for peers",
        ],
    )

    # 10. Section header
    build_section_header(
        prs,
        "03",
        "Financial Deep Dive",
        "A closer look at growth drivers, unit economics and operating leverage.",
    )

    # 11. Content — financials
    build_content_slide(
        prs,
        "Unit Economics Are Compounding",
        [
            "CAC payback shortened from 18 months to 11 months",
            "LTV / CAC ratio improved from 3.2× to 4.8× over the last six quarters",
            "Gross margin reached 74%, up 6 points year over year",
            "Free cash flow turned positive in Q3 — two quarters ahead of plan",
            "Operating expenses grew 22% while revenue grew 34% — scale is real",
        ],
    )

    # 12. Title-only — rallying cry
    build_title_only(
        prs,
        "Compounding beats heroics. Every quarter, a little better — forever.",
        "— Aurora Operating Principles",
    )

    # 13. Section header
    build_section_header(
        prs,
        "04",
        "Product & Roadmap",
        "Shipping velocity, the AI platform bet, and the twelve-month roadmap.",
    )

    # 14. Two-column — product bets
    build_two_column(
        prs,
        "Where We Are Investing in 2026",
        "Foundational Bets",
        [
            "Aurora AI Copilot — intent-level authoring",
            "Unified data model across Studio, Review and Publish",
            "New permissions engine with role-based and attribute-based access",
        ],
        "Horizon Bets",
        [
            "Agents SDK for partners and customers to extend Aurora",
            "On-device / air-gapped deployments for regulated industries",
            "Aurora Academy — a certification & learning platform",
        ],
    )

    # 15. Content — roadmap
    build_content_slide(
        prs,
        "Twelve-Month Roadmap",
        [
            "Q2 — General availability of Aurora Studio 3 and Copilot v1",
            "Q3 — Mobile rebuild; new permissions engine in closed beta",
            "Q4 — Agents SDK developer preview; launch of Aurora Academy",
            "Q1 2027 — Air-gapped deployments; third-party app marketplace",
        ],
    )

    # 16. Picture with caption
    build_picture_caption(
        prs,
        "Customer Story: Helix Robotics",
        "Helix replaced four internal tools with Aurora. Time from concept to "
        "customer delivery dropped from 14 weeks to 6. Their engineering team "
        "now spends 28% more time on differentiated work.",
    )

    # 17. Section header
    build_section_header(
        prs,
        "05",
        "People & Culture",
        "How we hire, how we grow leaders, and how we keep the culture honest as we scale.",
    )

    # 18. Content — team
    build_content_slide(
        prs,
        "Team & Organization",
        [
            "Team grew from 310 to 540, with the strongest growth in R&D (+72%)",
            "Voluntary attrition held at 6.8%, well below the industry benchmark",
            "Engagement score reached 84, with managers scoring highest on clarity",
            "Introduced a two-track career path: individual contributor and manager",
            "Launched internal mobility program — 11% of team changed roles this year",
        ],
    )

    # 19. Title-only — closing line
    build_title_only(
        prs,
        "The next chapter is bigger, but the recipe is the same: customers first, craft always.",
        "— CEO, Annual Letter",
    )

    # 20. Final thank-you
    build_section_header(
        prs,
        "06",
        "Thank You",
        "Questions, feedback and discussion — the floor is yours.",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "test_template_rich.pptx"
    path = build(out)
    print(f"Wrote {path}  ({path.stat().st_size / 1024:.1f} KB)")
