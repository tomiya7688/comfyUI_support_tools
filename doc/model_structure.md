# Safetensors model structure classification

The shared classifier uses tensor names and shapes recorded in the bounded JSON header. It does not import PyTorch, deserialize checkpoints, read tensor data, or allocate GPU memory. Header reads are limited to 64 MiB; negative, boolean, missing, and non-list shape descriptors are rejected. Scalar and empty tensor descriptors are accepted but do not establish a family.

| Family | Structural evidence | Scope |
| --- | --- | --- |
| sd1.5 | Standard UNet input convolution and cross-attention input width 768, or a matched UNet LoRA down/up pair with that input width | SD1.x architectural compatibility; not exact 1.5 release identification |
| sdxl | Standard UNet input convolution and cross-attention input width 2048, or a matched UNet LoRA down/up pair with that input width | SDXL base-family layouts |
| flux | FLUX.1 base image projection 3072×64, text projection 3072×4096, and both double-stream QKV projections 9216×3072 under one prefix | Original FLUX.1 base-style layout; Chroma-specific distilled-guidance keys make the result unknown |
| anima | Backbone MLP 8192×2048, image projection 2048×68, and LLM adapter query projection 1024×1024 under one prefix | Original Anima 2B layout; the Cosmos-like backbone alone is insufficient |

CompVis-style and Diffusers-style SD UNet names, Kohya LoRA names, and common PEFT UNet LoRA pairs are recognized. Text-encoder tensors alone and UNet self-attention dimensions are insufficient. LoRA pairs must have matching ranks and a supported UNet output width. Mixed or unsupported cross-attention dimensions, conflicting model families, and contradictions with filename/metadata evidence remain `unknown`. Layouts outside these fixed signatures, including converted/quantized transformer variants and adapters without their distinguishing tensors, may still need explicit path or metadata evidence.

The reader extracts metadata and shape descriptors once; the local resolver caches only the final classification. Model replacement invalidates the cache through the file update time and size. Remote-only candidates fall back to the existing path/name evidence. Catalog-declared model kinds are preserved.

## Primary sources and redistribution

Architecture facts were checked against the official [SD1.5 UNet configuration](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/raw/main/unet/config.json), [SDXL base UNet configuration](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/raw/main/unet/config.json), [Black Forest Labs FLUX.1 model parameters](https://github.com/black-forest-labs/flux/blob/main/src/flux/util.py), [FLUX.1 projection definitions](https://github.com/black-forest-labs/flux/blob/main/src/flux/model.py), and the [ComfyUI Anima/Cosmos architecture detection](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/model_detection.py). Header shape descriptors follow the [Safetensors format](https://github.com/safetensors/safetensors#format).

The detector is an independently implemented pure header-inspection module. External backend code and model weights are not copied, imported, or included by this feature. ComfyUI's GPLv3 source was reviewed as a reference; this change adds no ComfyUI runtime/source dependency. Referencing architecture signatures does not change the licenses of separately installed models; consult each model's own license for model distribution and use.
