import logging
import os

import anthropic

from app.db_models import CategoryCode
from app.models import ExtractedSlipData

logger = logging.getLogger(__name__)

COG_LABELS: dict[CategoryCode, str] = {
    CategoryCode.COG_01: "Materials",
    CategoryCode.COG_02: "Labour",
    CategoryCode.COG_03: "Plant & Equipment",
    CategoryCode.COG_04: "Subcontractors",
    CategoryCode.COG_05: "Transport",
    CategoryCode.COG_06: "Overheads",
    CategoryCode.COG_07: "Professional Fees",
    CategoryCode.COG_08: "Other",
}

_COG_DESCRIPTIONS = "\n".join(
    f"- {code.value} ({label})" for code, label in COG_LABELS.items()
)

_CLASSIFICATION_TOOL = {
    "name": "classify_cost",
    "description": "Assign a COG cost-of-goods code to a supplier slip.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category_code": {
                "type": "string",
                "enum": [c.value for c in CategoryCode],
                "description": "The most appropriate COG code for this purchase.",
            },
        },
        "required": ["category_code"],
    },
}

_SYSTEM_PROMPT = (
    "You are a construction-industry cost accountant. "
    "Classify supplier slip purchases into one of these COG codes for a South African construction company:\n"
    + _COG_DESCRIPTIONS
    + "\n\nRespond only by calling the classify_cost tool."
)


def classify_slip(slip: ExtractedSlipData) -> CategoryCode:
    """Use Claude to classify the slip into a COG code. Falls back to COG-08."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    parts = []
    if slip.supplier:
        parts.append(f"Supplier: {slip.supplier}")
    if slip.description:
        parts.append(f"Description: {slip.description}")
    if slip.amount_incl_vat is not None:
        parts.append(f"Amount (incl VAT): R{slip.amount_incl_vat:,.2f}")
    elif slip.amount_excl_vat is not None:
        parts.append(f"Amount (excl VAT): R{slip.amount_excl_vat:,.2f}")

    user_text = "\n".join(parts) if parts else "No slip details available."

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            tools=[_CLASSIFICATION_TOOL],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": user_text}],
        )
        for block in message.content:
            if block.type == "tool_use" and block.name == "classify_cost":
                code_str = block.input.get("category_code", "COG-08")
                return CategoryCode(code_str)
    except Exception:
        logger.exception("Classification failed — defaulting to COG-08")

    return CategoryCode.COG_08
