from dataclasses import dataclass, field
from typing import Mapping


# {
#   責務: [ResolvedGenerationParameters: 1枚分に確定した生成パラメータをGUI非依存で表す]
#   フィールド: [cfg: CFG値, steps: 生成step数, width: 画像幅, height: 画像高さ, sampler: sampler名]
#   処理: [バックエンドへ渡す確定済み生成値を保持し, 互換metadata形式へ変換する]
# }
@dataclass(frozen=True)
class ResolvedGenerationParameters:
    cfg: float
    steps: int
    width: int
    height: int
    sampler: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    backend_parameters: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    # {
    #   責務: [to_dict: 確定済み生成値をmetadata互換のmappingへ変換する]
    #   処理: [既存のcfg, steps, resolution, sampler構造を返す]
    #   引数: [self: parameter snapshot]
    #   戻り値: [dict: generation metadata]
    # }
    def to_dict(self) -> dict[str, object]:
        result = {
            "cfg": self.cfg,
            "steps": self.steps,
            "resolution": {"width": self.width, "height": self.height},
            "sampler": self.sampler,
        }
        if self.parameters:
            result["parameters"] = dict(self.parameters)
        if self.backend_parameters:
            result["backend_parameters"] = {
                namespace: dict(values) for namespace, values in self.backend_parameters.items()
            }
        return result
