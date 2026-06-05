from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import ImageStatus
from app.repositories.image_repo import ImageRepository
from app.utils.exceptions import NotFoundError


class ImageCardService:
    def __init__(self, session: AsyncSession):
        self.image_repo = ImageRepository(session)

    async def build_card(self, image_id: str) -> dict:
        image = await self.image_repo.get(image_id)
        if image is None:
            raise NotFoundError(f"Image not found: {image_id}")
        software = _software_hints(image)
        risk_level, risk_reasons = _risk(image, software)
        return {
            "image_id": str(image.id),
            "name": image.name,
            "tag": image.tag,
            "full_name": image.full_name,
            "registry": image.registry,
            "status": _value(image.status),
            "size_bytes": image.size_bytes,
            "entrypoint": image.entrypoint or [],
            "environment": image.env or [],
            "labels": image.labels or {},
            "software_hints": software,
            "validation_state": "available"
            if _value(image.status) == ImageStatus.LOCAL.value
            else "unverified",
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        }


def _software_hints(image) -> list[dict]:
    candidates: list[str] = []
    candidates.extend(image.env or [])
    candidates.extend(image.entrypoint or [])
    if image.labels:
        candidates.extend(str(value) for value in image.labels.values())
    text = " ".join(candidates).lower()
    hints = []
    for name in ("fastqc", "multiqc", "bwa", "samtools", "gatk", "star", "salmon"):
        if name in text or name in image.full_name.lower():
            hints.append({"name": name, "version": None, "source": "metadata"})
    return hints


def _risk(image, software: list[dict]) -> tuple[str, list[str]]:
    status = _value(image.status)
    if status == ImageStatus.FAILED.value:
        return "high", ["image pull or validation failed"]
    if status == ImageStatus.PULLING.value:
        return "medium", ["image is still pulling"]
    if not software:
        return "medium", ["software inventory has not been probed"]
    return "low", ["software hints detected from image metadata"]


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
