from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import AuditChainState, AuditEvent


class AuditChainError(Exception):
    pass


def _canonical_payload(
    *,
    sequence: int,
    actor_id: int | None,
    actor_email: str,
    action: str,
    object_type: str,
    object_id: str,
    summary: str,
    metadata: dict[str, Any],
    previous_hash: str,
    created_at_iso: str,
) -> str:
    return json.dumps(
        {
            "sequence": sequence,
            "actorId": actor_id,
            "actorEmail": actor_email,
            "action": action,
            "objectType": object_type,
            "objectId": object_id,
            "summary": summary,
            "metadata": metadata,
            "previousHash": previous_hash,
            "createdAt": created_at_iso,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_payload(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_audit_event(
    *,
    actor: User | None,
    action: str,
    object_type: str,
    object_id: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    action = action.strip()
    object_type = object_type.strip()
    object_id = object_id.strip()
    summary = summary.strip()
    if not action or not object_type or not object_id or not summary:
        raise ValueError("Audit action, object type, object id, and summary are required.")

    metadata_value = dict(metadata or {})
    created_at = timezone.now()
    actor_id = actor.pk if actor is not None else None
    actor_email = actor.email if actor is not None else ""

    with transaction.atomic():
        AuditChainState.objects.get_or_create(pk=1)
        state = AuditChainState.objects.select_for_update().get(pk=1)
        sequence = int(state.last_sequence) + 1
        previous_hash = state.last_hash
        payload = _canonical_payload(
            sequence=sequence,
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            object_type=object_type,
            object_id=object_id,
            summary=summary,
            metadata=metadata_value,
            previous_hash=previous_hash,
            created_at_iso=created_at.isoformat(),
        )
        event_hash = _hash_payload(payload)
        event = AuditEvent.objects.create(
            sequence=sequence,
            actor=actor,
            actor_email_snapshot=actor_email,
            action=action,
            object_type=object_type,
            object_id=object_id,
            summary=summary,
            metadata=metadata_value,
            previous_hash=previous_hash,
            event_hash=event_hash,
            created_at=created_at,
        )
        state.last_sequence = sequence
        state.last_hash = event_hash
        state.save(update_fields=("last_sequence", "last_hash", "updated_at"))
        return event


def verify_audit_chain() -> tuple[bool, str]:
    previous_hash = ""
    expected_sequence = 1

    for event in AuditEvent.objects.order_by("sequence").iterator():
        if event.sequence != expected_sequence:
            return False, f"sequence gap at {expected_sequence}"
        if event.previous_hash != previous_hash:
            return False, f"previous hash mismatch at sequence {event.sequence}"
        payload = _canonical_payload(
            sequence=int(event.sequence),
            actor_id=event.actor_id,
            actor_email=event.actor_email_snapshot,
            action=event.action,
            object_type=event.object_type,
            object_id=event.object_id,
            summary=event.summary,
            metadata=dict(event.metadata),
            previous_hash=event.previous_hash,
            created_at_iso=event.created_at.isoformat(),
        )
        expected_hash = _hash_payload(payload)
        if event.event_hash != expected_hash:
            return False, f"event hash mismatch at sequence {event.sequence}"
        previous_hash = event.event_hash
        expected_sequence += 1

    state = AuditChainState.objects.filter(pk=1).first()
    if state is None:
        if expected_sequence == 1:
            return True, "empty"
        return False, "audit chain state is missing"
    if int(state.last_sequence) != expected_sequence - 1:
        return False, "audit chain state sequence mismatch"
    if state.last_hash != previous_hash:
        return False, "audit chain state hash mismatch"
    return True, "ok"
