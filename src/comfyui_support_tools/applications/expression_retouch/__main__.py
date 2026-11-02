"""Launch the face-local expression-retouch editor."""

from __future__ import annotations

import os
from pathlib import Path

from comfyui_support_tools.applications.expression_retouch.data.messenger.retouch_data_messenger import (
    ExpressionRetouchDataEndpoint,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.comfyui_backend import (
    ComfyUIExpressionBackend,
)
from comfyui_support_tools.applications.expression_retouch.process.commander.application import (
    ExpressionRetouchApplication,
)
from comfyui_support_tools.applications.expression_retouch.process.messenger.data_messenger import (
    ExpressionRetouchDataMessenger,
)
from comfyui_support_tools.applications.expression_retouch.process.processing.processor import (
    ExpressionRetouchProcessor,
)
from comfyui_support_tools.applications.expression_retouch.ui.commander.application import (
    ExpressionRetouchUiCommander,
)
from comfyui_support_tools.applications.expression_retouch.ui.messenger.process_messenger import (
    ExpressionRetouchProcessMessenger,
)
from comfyui_support_tools.applications.expression_retouch.ui.processing.window import launch


# {
#   責務: [_node_ids: parse a comma-separated list of ComfyUI workflow nodes]
#   処理: [trim entries and return nonempty IDs in configured order]
#   引数: [value: environment string]
#   戻り値: [tuple[str, ...]: node IDs]
# }
def _node_ids(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


if __name__ == "__main__":
    data_endpoint = ExpressionRetouchDataEndpoint()
    data_messenger = ExpressionRetouchDataMessenger(data_endpoint)
    processor = ExpressionRetouchProcessor(data_messenger)
    workflow_path = os.environ.get("EXPRESSION_RETOUCH_WORKFLOW", "").strip()
    if workflow_path:
        image_node_id = os.environ.get("EXPRESSION_RETOUCH_IMAGE_NODE", "").strip()
        mask_node_id = os.environ.get("EXPRESSION_RETOUCH_MASK_NODE", "").strip()
        if not image_node_id or not mask_node_id:
            raise RuntimeError(
                "EXPRESSION_RETOUCH_IMAGE_NODE and EXPRESSION_RETOUCH_MASK_NODE are required with a workflow"
            )
        processor.register_backend(
            ComfyUIExpressionBackend(
                Path(workflow_path).expanduser(),
                image_node_id=image_node_id,
                mask_node_id=mask_node_id,
                prompt_node_ids=_node_ids(os.environ.get("EXPRESSION_RETOUCH_PROMPT_NODES", ""))
                or None,
                negative_prompt_node_ids=_node_ids(
                    os.environ.get("EXPRESSION_RETOUCH_NEGATIVE_NODES", "")
                )
                or None,
                seed_node_ids=_node_ids(os.environ.get("EXPRESSION_RETOUCH_SEED_NODES", "")),
                sampler_node_id=os.environ.get("EXPRESSION_RETOUCH_SAMPLER_NODE", "").strip()
                or None,
                api_url=os.environ.get("COMFYUI_API_URL", "http://127.0.0.1:8188"),
            )
        )
    process_application = ExpressionRetouchApplication(processor)
    ui_messenger = ExpressionRetouchProcessMessenger(process_application)
    launch(ExpressionRetouchUiCommander(ui_messenger))
