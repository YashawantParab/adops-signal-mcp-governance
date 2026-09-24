"""A synthetic, in-repo mock ad server. NOT a real advertising platform
integration - there is no external system here. It models a narrow set of
campaign settings as mutable "ad server state" on top of the existing
`campaigns` table, which is itself already 100% synthetic seed data (see
docs/architecture.md#dataset-disclaimer). Keeping state on the existing
Campaign row (rather than a separate simulated ad-server database) avoids
building a second parallel data model for the same synthetic campaigns.

Every supported action is narrow, typed, and reversible - exactly the
fields needed to demonstrate propose -> approve -> execute -> verify ->
rollback, not a general campaign-editing API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models import Campaign
from app.services.json_fields import dump_list, parse_list

ActionType = Literal["adjust_frequency_cap", "relax_device_constraint", "pause_campaign", "resume_campaign"]

SUPPORTED_ACTION_TYPES: tuple[ActionType, ...] = (
    "adjust_frequency_cap",
    "relax_device_constraint",
    "pause_campaign",
    "resume_campaign",
)

# Base risk class per action type, independent of campaign state - the
# execution service takes the max of this and the campaign's own deterministic
# risk level (_score_risk), so a risky campaign makes every action riskier,
# never the reverse.
BASE_RISK_CLASS: dict[str, str] = {
    "adjust_frequency_cap": "MEDIUM",
    "relax_device_constraint": "MEDIUM",
    "pause_campaign": "HIGH",  # stops delivery entirely
    "resume_campaign": "MEDIUM",
}

KNOWN_DEVICES = ["CTV", "Desktop", "Mobile", "Tablet"]


class UnsupportedActionError(ValueError):
    pass


class InvalidActionParamsError(ValueError):
    pass


@dataclass(frozen=True)
class ActionState:
    """The subset of campaign fields one action type reads/writes - used for
    both before_state and after_state so a diff is always apples-to-apples."""

    fields: dict[str, Any]


def _relevant_fields(action_type: str) -> list[str]:
    return {
        "adjust_frequency_cap": ["frequency_cap"],
        "relax_device_constraint": ["target_devices"],
        "pause_campaign": ["status"],
        "resume_campaign": ["status"],
    }[action_type]


def read_state(campaign: Campaign, action_type: str) -> ActionState:
    fields: dict[str, Any] = {}
    for name in _relevant_fields(action_type):
        value = getattr(campaign, name)
        fields[name] = parse_list(value) if name == "target_devices" else value
    return ActionState(fields=fields)


def validate_params(action_type: str, params: dict[str, Any]) -> None:
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise UnsupportedActionError(f"'{action_type}' is not a supported synthetic action")
    if action_type == "adjust_frequency_cap":
        value = params.get("new_frequency_cap")
        if not isinstance(value, int) or not (1 <= value <= 20):
            raise InvalidActionParamsError("new_frequency_cap must be an integer between 1 and 20")
    elif action_type == "relax_device_constraint":
        device = params.get("add_device")
        if device not in KNOWN_DEVICES:
            raise InvalidActionParamsError(f"add_device must be one of {KNOWN_DEVICES}")
    elif action_type in ("pause_campaign", "resume_campaign"):
        pass  # no params needed


def requested_state(action_type: str, params: dict[str, Any], current: ActionState) -> ActionState:
    """The state the action is requesting - used both to write the change and,
    unchanged, to verify against after execution."""
    if action_type == "adjust_frequency_cap":
        return ActionState(fields={"frequency_cap": params["new_frequency_cap"]})
    if action_type == "relax_device_constraint":
        devices = list(current.fields["target_devices"])
        if params["add_device"] not in devices:
            devices.append(params["add_device"])
        return ActionState(fields={"target_devices": devices})
    if action_type == "pause_campaign":
        return ActionState(fields={"status": "paused"})
    if action_type == "resume_campaign":
        return ActionState(fields={"status": "active"})
    raise UnsupportedActionError(action_type)  # pragma: no cover - validate_params already guards this


def apply_state(db: Session, campaign: Campaign, state: ActionState) -> None:
    """Writes `state.fields` onto the campaign row - the one place that
    actually mutates synthetic ad-server state."""
    for name, value in state.fields.items():
        setattr(campaign, name, dump_list(value) if name == "target_devices" else value)
    db.add(campaign)
    db.flush()


def states_match(a: ActionState, b: ActionState) -> bool:
    return a.fields == b.fields
