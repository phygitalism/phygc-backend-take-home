"""Models we sell and what they cost.

Prices are in credits per output. Availability comes from the provider at
request time (see app/api/routes_models.py); pricing is ours.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: str
    price: int
    max_outputs: int


MODELS: dict[str, ModelSpec] = {
    spec.name: spec
    for spec in (
        ModelSpec(name="flux-fast", kind="image", price=2, max_outputs=4),
        ModelSpec(name="sdxl-pro", kind="image", price=5, max_outputs=4),
        ModelSpec(name="upscale-4x", kind="image", price=3, max_outputs=1),
        ModelSpec(name="video-gen-1", kind="video", price=40, max_outputs=2),
    )
}


def get_model(name: str) -> ModelSpec | None:
    return MODELS.get(name)


def job_cost(spec: ModelSpec, num_outputs: int) -> int:
    return spec.price * num_outputs
