"""Local image-only pipelines; PDF decoding remains in the pdfrune harness.

Paddle: upstream PP-DocLayoutV3 + MLX recognizer with auditable simple assembly.
TeleOCR: pinned Apache-2.0 teleocr-rs CLI, no service or shell involved.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path

from PIL import Image


def teleocr_page(request, page):
    root = Path(__file__).resolve().parents[2]
    binary = root / "runners/teleocr-bin/teleocr"
    weight = Path(request["model_path"]) / "teleocr-q8v.gguf"
    argv = [str(binary), "parse", "-m", str(weight), page["image_path"], "--json", "--batch", "1"]
    # Parent worker owns this process group and kills it on timeout.
    result = subprocess.run(
        argv, capture_output=True, text=True, env={**os.environ, "RUST_LOG": "info"}
    )
    if result.returncode != 0:
        raise RuntimeError(f"TeleOCR exited {result.returncode}: {result.stderr[-10000:]}")
    parsed = json.loads(result.stdout)
    if len(parsed) != 1:
        raise ValueError("TeleOCR returned an unexpected number of pages")
    value = parsed[0]
    return (
        value["markdown"],
        {"pages": parsed, "stderr": result.stderr, "argv": argv},
        {
            "pipeline": "teleocr-rs-0.2.0-q8v",
            "device": "Metal"
            if "Metal(" in result.stderr
            else "Cpu"
            if "Cpu" in result.stderr
            else "unreported",
            "possibly_truncated": "hit max_new_tokens" in result.stderr,
            "timing_note": "Includes CLI model load, layout, crops and recognition",
        },
    )


def paddle_batch_axis_compat(generator):
    """Retain the tested MLX 0.7.10 / Paddle 1.6 input-axis compatibility fix."""
    import mlx.core as mx

    # mlx-vlm 0.7.10's Paddle vision embedding expects [1,N,C,H,W],
    # while the 1.6 processor supplies [N,C,H,W]. Only add the missing
    # batch axis; preserve pixel values and order. No weight changes.
    embeddings = generator.visual.embeddings
    if not getattr(embeddings, "pdfocr_batch_axis_fixed", False):
        original = embeddings._patch_embed

        def patch_embed(values):
            if values.ndim == 4:
                if values.shape[1:] != (3, 14, 14):
                    raise ValueError(f"Unexpected Paddle patch shape: {values.shape}")
                values = mx.expand_dims(values, 0)
            return original(values)

        embeddings._patch_embed = patch_embed
        embeddings.pdfocr_batch_axis_fixed = True


class PaddleLayout:
    def __init__(self, path):
        import torch
        from transformers import AutoImageProcessor, PPDocLayoutV3ForObjectDetection

        self.torch = torch
        torch.set_num_threads(8)
        self.processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        self.model = PPDocLayoutV3ForObjectDetection.from_pretrained(
            path, local_files_only=True
        ).eval()

    def recognize(self, generator, processor, page, config):
        import mlx.core as mx
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        paddle_batch_axis_compat(generator)
        start = time.monotonic()
        image = Image.open(page["image_path"]).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
        result = self.processor.post_process_object_detection(
            outputs, threshold=0.3, target_sizes=[(image.height, image.width)]
        )[0]
        layout_seconds = time.monotonic() - start
        blocks = []
        folder = Path(page["result_path"]).with_suffix("")
        folder.mkdir(exist_ok=True)
        for idx, (box, label, score) in enumerate(
            zip(result["boxes"], result["labels"], result["scores"], strict=True)
        ):
            label = self.model.config.id2label[int(label)]
            coords = [
                max(0, math.floor(float(box[0]))),
                max(0, math.floor(float(box[1]))),
                min(image.width, math.ceil(float(box[2]))),
                min(image.height, math.ceil(float(box[3]))),
            ]
            if coords[2] <= coords[0] or coords[3] <= coords[1]:
                continue
            # Reject only substantial duplicate detections of the same label.
            area = (coords[2] - coords[0]) * (coords[3] - coords[1])
            duplicate = False
            for previous in blocks:
                b = previous["bbox"]
                intersection = max(0, min(b[2], coords[2]) - max(b[0], coords[0])) * max(
                    0, min(b[3], coords[3]) - max(b[1], coords[1])
                )
                oldarea = (b[2] - b[0]) * (b[3] - b[1])
                if previous["label"] == label and intersection / max(1, min(area, oldarea)) > 0.9:
                    duplicate = True
            if duplicate:
                continue
            crop = folder / f"block-{idx:03d}-{label}.png"
            image.crop(coords).save(crop)
            block = {
                "bbox": coords,
                "label": label,
                "score": float(score),
                "crop": str(crop),
                "order": int(result["order_seq"][idx]),
            }
            if label in ("image", "header_image", "footer_image", "chart"):
                block["text"] = ""
                block["skip_reason"] = (
                    "image region; chart recognition disabled as in upstream default"
                )
            else:
                prompt = (
                    "Table Recognition:"
                    if label == "table"
                    else "Formula Recognition:"
                    if label in ("display_formula", "inline_formula")
                    else "OCR:"
                )
                formatted = apply_chat_template(processor, generator.config, prompt, num_images=1)
                t = time.monotonic()
                response = generate(
                    generator,
                    processor,
                    formatted,
                    image=[str(crop)],
                    max_tokens=config["max_tokens"],
                    temperature=0.0,
                    verbose=False,
                )
                block.update(
                    text=response.text,
                    seconds=time.monotonic() - t,
                    tokens=response.generation_tokens,
                    possibly_truncated=response.generation_tokens >= config["max_tokens"],
                    prompt=prompt,
                )
            blocks.append(block)
        ignored = {
            "number",
            "footnote",
            "header",
            "header_image",
            "footer",
            "footer_image",
            "aside_text",
        }
        markdown = "\n\n".join(
            b["text"].strip() for b in blocks if b["label"] not in ignored and b["text"].strip()
        )
        if not markdown:
            raise ValueError("Layout pipeline produced no recognized content; inspect regions")
        return (
            markdown,
            {
                "blocks": blocks,
                "layout_seconds": layout_seconds,
                "assembly": "reading order; upstream default furniture exclusions; rectangle crops",
            },
            {
                "pipeline": "PP-DocLayoutV3+PaddleOCR-VL-1.6-MLX",
                "possibly_truncated": any(b.get("possibly_truncated", False) for b in blocks),
                "mlx_peak_memory_bytes": mx.get_peak_memory(),
                "layout_seconds": layout_seconds,
            },
        )
