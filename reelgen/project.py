"""Сохранение и загрузка проекта: пути, картинки, классы, правила, сиды."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .rules import DistanceRule, ReelRules, RuleSet, StackRule


@dataclass
class Project:
    name: str = "default"
    game_path: str = ""
    images_folder: str = ""
    image_map: dict[int, str] = field(default_factory=dict)
    rules: RuleSet = field(default_factory=RuleSet)
    seeds: dict[str, int] = field(default_factory=dict)
    bonus_threshold: int = 3
    scatter_threshold: int = 3


def _stack_to_dict(stack: StackRule) -> dict:
    return {
        "symbol_id": stack.symbol_id,
        "count": stack.count,
        "sizes": {str(size): weight for size, weight in stack.sizes.items()},
    }


def _stack_from_dict(data: dict) -> StackRule:
    return StackRule(
        symbol_id=int(data["symbol_id"]),
        count=int(data["count"]),
        sizes={int(size): float(weight) for size, weight in data["sizes"].items()},
    )


def _distance_to_dict(rule: DistanceRule) -> dict:
    return {"a": rule.a, "b": rule.b, "min_gap": rule.min_gap, "filler": rule.filler}


def _distance_from_dict(data: dict) -> DistanceRule:
    return DistanceRule(
        a=data["a"],
        b=data["b"],
        min_gap=int(data["min_gap"]),
        filler=data.get("filler") or None,
    )


def _reel_to_dict(rules: ReelRules) -> dict:
    return {
        "stacks": [_stack_to_dict(stack) for stack in rules.stacks],
        "distances": [_distance_to_dict(rule) for rule in rules.distances],
    }


def _reel_from_dict(data: dict) -> ReelRules:
    return ReelRules(
        stacks=[_stack_from_dict(item) for item in data.get("stacks", [])],
        distances=[_distance_from_dict(item) for item in data.get("distances", [])],
    )


def to_dict(project: Project) -> dict:
    return {
        "name": project.name,
        "game_path": project.game_path,
        "images_folder": project.images_folder,
        "image_map": {str(sid): name for sid, name in project.image_map.items()},
        "bonus_threshold": project.bonus_threshold,
        "scatter_threshold": project.scatter_threshold,
        "seeds": dict(project.seeds),
        "rules": {
            "classes": {str(sid): name for sid, name in project.rules.classes.items()},
            "reels": {
                name: [_reel_to_dict(reel) for reel in reels]
                for name, reels in project.rules.reels.items()
            },
        },
    }


def from_dict(data: dict) -> Project:
    rules_data = data.get("rules", {})
    rules = RuleSet(
        classes={int(sid): name for sid, name in rules_data.get("classes", {}).items()},
        reels={
            name: [_reel_from_dict(reel) for reel in reels]
            for name, reels in rules_data.get("reels", {}).items()
        },
    )
    return Project(
        name=data.get("name", "default"),
        game_path=data.get("game_path", ""),
        images_folder=data.get("images_folder", ""),
        image_map={int(sid): name for sid, name in data.get("image_map", {}).items()},
        rules=rules,
        seeds={name: int(seed) for name, seed in data.get("seeds", {}).items()},
        bonus_threshold=int(data.get("bonus_threshold", 3)),
        scatter_threshold=int(data.get("scatter_threshold", 3)),
    )


def save(project: Project, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{project.name}.json"
    path.write_text(
        json.dumps(to_dict(project), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load(path: str | Path) -> Project:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def list_projects(folder: str | Path) -> list[str]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json"))
