"""Release-gate checks for model catalog and pricing readiness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any


def evaluate_model_catalog_pricing_gate(
    *,
    models: Iterable[Any],
    pricing_policies: Iterable[Any],
    mission_policies: Iterable[Any] = (),
    sandbox_enabled: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate production readiness for admin-managed models and pricing."""

    errors: list[dict[str, str]] = []
    env_source = env if env is not None else os.environ
    if not _model_secret_configured(env_source):
        errors.append(
            {
                "code": "model_secret_key_missing",
                "detail": "MODEL_SECRET_KEY_FILE or a strong MODEL_SECRET_KEY is required.",
            }
        )

    model_rows = list(models)
    policy_rows = list(pricing_policies)
    enabled_models = [model for model in model_rows if _bool_attr(model, "enabled", True)]
    default_llm_models = [model for model in enabled_models if _str_attr(model, "category") == "llm" and _bool_attr(model, "is_default", False)]
    if not default_llm_models:
        errors.append(
            {
                "code": "enabled_default_llm_model_missing",
                "detail": "At least one enabled default LLM model is required.",
            }
        )
    for model in default_llm_models:
        if _str_attr(model, "health_status", "unknown") != "healthy":
            errors.append(
                {
                    "code": "default_model_health_check_missing",
                    "detail": f"Default model {_str_attr(model, 'model_id')} must pass connection test.",
                }
            )

    enabled_global_policies = [policy for policy in policy_rows if _bool_attr(policy, "enabled", True) and _str_attr(policy, "policy_kind") == "global_credit"]
    if not enabled_global_policies:
        errors.append(
            {
                "code": "global_credit_policy_missing",
                "detail": "At least one enabled global_credit pricing policy is required.",
            }
        )

    model_usage_policy_keys = _enabled_policy_keys(policy_rows, "model_usage")
    for model in enabled_models:
        pricing_policy_id = _str_attr(model, "pricing_policy_id")
        if not pricing_policy_id or pricing_policy_id not in model_usage_policy_keys:
            errors.append(
                {
                    "code": "model_usage_policy_missing",
                    "detail": f"Enabled model {_str_attr(model, 'model_id')} lacks an enabled model_usage pricing policy.",
                }
            )

    mission_pricing_rows = [policy for policy in policy_rows if _bool_attr(policy, "enabled", True) and _str_attr(policy, "policy_kind") == "mission"]
    for mission_policy in mission_policies:
        if not _bool_attr(mission_policy, "enabled", True):
            continue
        mission_policy_id = _str_attr(mission_policy, "id")
        workspace_type = _str_attr(mission_policy, "workspace_type")
        if not _has_mission_pricing_policy(
            mission_pricing_rows,
            mission_policy_id=mission_policy_id,
            workspace_type=workspace_type,
        ):
            errors.append(
                {
                    "code": "mission_pricing_policy_missing",
                    "detail": f"MissionPolicy {workspace_type}/{mission_policy_id} lacks Mission pricing policy.",
                }
            )

    if sandbox_enabled and not _enabled_policy_keys(policy_rows, "sandbox"):
        errors.append(
            {
                "code": "sandbox_policy_missing",
                "detail": "Sandbox billing is enabled but no enabled sandbox pricing policy exists.",
            }
        )

    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }


async def evaluate_dataservice_model_catalog_pricing_gate(
    *,
    dataservice: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if dataservice is not None:
        models = await dataservice.list_model_catalog_models(enabled_only=False)
        pricing_policies = await dataservice.list_pricing_policies(enabled_only=False)
        mission_policies = await dataservice.list_mission_policies(enabled_only=True)
        return evaluate_model_catalog_pricing_gate(
            models=models,
            pricing_policies=pricing_policies,
            mission_policies=mission_policies,
            sandbox_enabled=_sandbox_enabled(env),
            env=env,
        )

    from src.dataservice_client.provider import dataservice_client

    async with dataservice_client() as client:
        return await evaluate_dataservice_model_catalog_pricing_gate(
            dataservice=client,
            env=env,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check model catalog and pricing readiness")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    report = asyncio.run(evaluate_dataservice_model_catalog_pricing_gate())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif report["status"] != "passed":
        for error in report["errors"]:
            print(f"{error['code']}: {error['detail']}")
    return 0 if report["status"] == "passed" else 1


def _enabled_policy_keys(policies: Iterable[Any], policy_kind: str) -> set[str]:
    keys: set[str] = set()
    for policy in policies:
        if not _bool_attr(policy, "enabled", True):
            continue
        if _str_attr(policy, "policy_kind") != policy_kind:
            continue
        for key in (_str_attr(policy, "id"), _str_attr(policy, "policy_key")):
            if key:
                keys.add(key)
    return keys


def _has_mission_pricing_policy(
    policies: Iterable[Any],
    *,
    mission_policy_id: str,
    workspace_type: str,
) -> bool:
    for policy in policies:
        config = _dict_attr(policy, "config")
        priced_mission_policy_id = str(config.get("mission_policy_id") or "").strip()
        policy_workspace = str(config.get("workspace_type") or "").strip()
        if priced_mission_policy_id == mission_policy_id and (not policy_workspace or policy_workspace == workspace_type):
            return True
        if not priced_mission_policy_id and policy_workspace in {"", workspace_type}:
            return True
    return False


def _model_secret_configured(env: Mapping[str, str]) -> bool:
    if str(env.get("MODEL_SECRET_KEY_FILE") or "").strip():
        return True
    value = str(env.get("MODEL_SECRET_KEY") or "").strip()
    if len(value) < 32:
        return False
    if value == "base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=":
        return False
    return any(character != "0" for character in value)


def _sandbox_enabled(env: Mapping[str, str] | None) -> bool:
    value = str((env if env is not None else os.environ).get("WENJIN_SANDBOX_ENABLED") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _str_attr(value: Any, key: str, default: str = "") -> str:
    raw = _raw_attr(value, key, default)
    return str(raw or "").strip()


def _bool_attr(value: Any, key: str, default: bool = False) -> bool:
    raw = _raw_attr(value, key, default)
    return bool(raw)


def _dict_attr(value: Any, key: str) -> dict[str, Any]:
    raw = _raw_attr(value, key, {})
    return dict(raw) if isinstance(raw, dict) else {}


def _raw_attr(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


if __name__ == "__main__":
    raise SystemExit(main())
