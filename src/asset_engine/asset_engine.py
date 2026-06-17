"""Asset engine — procedural asset resolution (free, no external APIs)."""

from __future__ import annotations

from src.core.models import ScenePlan


class AssetEngine:
    def resolve_assets(self, scene_plan: ScenePlan) -> dict:
        return {
            "assets": scene_plan.assets,
            "background_key": scene_plan.background_key,
            "protagonist": scene_plan.protagonist,
            "emotion": scene_plan.emotion,
            "scene_type": scene_plan.scene_type.value,
        }
